from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import hashlib
from datetime import datetime, timedelta
import uuid
import json
import threading
import os
# from firebase_config import firebase_attendance

app = Flask(__name__)
app.secret_key = 'shambhunath_college_secret'

def init_db():
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (id TEXT PRIMARY KEY, password TEXT, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance 
                 (student_id TEXT, session_id TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    
    # Drop and recreate sessions table to ensure correct schema
    c.execute('DROP TABLE IF EXISTS sessions')
    c.execute('''CREATE TABLE sessions 
                 (session_id TEXT PRIMARY KEY, qr_code TEXT, created_at TEXT, expires_at TEXT, subject TEXT)''')
    
    # Create default admin with new password
    c.execute("DELETE FROM admin WHERE username='admin'")
    admin_pass = hashlib.md5('Mayank#0069'.encode()).hexdigest()
    c.execute("INSERT INTO admin VALUES ('admin', ?)", (admin_pass,))
    
    conn.commit()
    conn.close()

def cleanup_expired_sessions():
    """Clean up expired sessions periodically"""
    import threading
    import time
    
    def cleanup():
        while True:
            conn = sqlite3.connect('attendance.db')
            c = conn.cursor()
            c.execute("DELETE FROM sessions WHERE datetime(expires_at) < datetime('now')")
            deleted = c.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                print(f"Cleaned up {deleted} expired sessions")
            
            time.sleep(1800)  # Clean every 30 minutes
    
    thread = threading.Thread(target=cleanup, daemon=True)
    thread.start()



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    student_id = request.form['student_id']
    password = hashlib.md5(request.form['password'].encode()).hexdigest()
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE id=? AND password=?", (student_id, password))
    user = c.fetchone()
    conn.close()
    
    if user:
        session['student_id'] = student_id
        return redirect(url_for('dashboard'))
    return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    student_id = request.form['student_id']
    password = hashlib.md5(request.form['password'].encode()).hexdigest()
    name = request.form['name']
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("INSERT INTO students VALUES (?, ?, ?)", (student_id, password, name))
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT name FROM students WHERE id=?", (session['student_id'],))
    student = c.fetchone()
    conn.close()
    
    student_name = student[0] if student else 'Student'
    return render_template('dashboard.html', student_name=student_name, student_id=session['student_id'])

@app.route('/admin')
def admin():
    if 'admin_logged_in' not in session:
        return render_template('admin_login.html')
    return render_template('admin.html')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    username = request.form['username']
    password = hashlib.md5(request.form['password'].encode()).hexdigest()
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT * FROM admin WHERE username=? AND password=?", (username, password))
    admin = c.fetchone()
    conn.close()
    
    if admin:
        session['admin_logged_in'] = True
        return redirect(url_for('admin'))
    return render_template('admin_login.html', error='Invalid credentials')

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin'))

@app.route('/generate_session', methods=['POST'])
def generate_session():
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    subject = request.json.get('subject', 'General Class')
    
    # Always generate a new session
    session_id = str(uuid.uuid4())[:8].upper()
    now = datetime.now()
    expires_at = now + timedelta(hours=1)
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    # Delete expired sessions
    c.execute("DELETE FROM sessions WHERE datetime(expires_at) < datetime('now')")
    # Insert new session
    c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)", 
              (session_id, session_id, now.isoformat(), expires_at.isoformat(), subject))
    conn.commit()
    conn.close()
    
    return jsonify({
        'session_id': session_id, 
        'subject': subject
    })

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    session_id = request.json['session_id']
    student_id = session['student_id']
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT subject FROM sessions WHERE session_id=? AND datetime(expires_at) > datetime('now')", (session_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return jsonify({'error': 'Session expired or invalid'})
    
    subject = result[0]
    
    c.execute("SELECT * FROM attendance WHERE student_id=? AND session_id=?", (student_id, session_id))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'Attendance already marked for this session'})
    
    c.execute("INSERT INTO attendance VALUES (?, ?, ?)", 
              (student_id, session_id, datetime.now().isoformat()))
    conn.commit()
    
    conn.close()
    
    # Store to local cloud backup
    threading.Thread(target=sync_to_cloud, daemon=True).start()
    
    return jsonify({'success': f'Attendance marked for {subject}'})

def sync_to_cloud():
    """Sync attendance data to cloud storage"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # Get all attendance data with student and session info
        c.execute('''
            SELECT a.student_id, s.name, a.session_id, ses.subject, a.timestamp
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN sessions ses ON a.session_id = ses.session_id
            ORDER BY a.timestamp DESC
        ''')
        
        attendance_data = []
        for row in c.fetchall():
            attendance_data.append({
                'student_id': row[0],
                'student_name': row[1],
                'session_id': row[2],
                'subject': row[3],
                'timestamp': row[4],
                'date': row[4][:10],
                'time': row[4][11:19]
            })
        
        conn.close()
        
        # Prepare cloud data
        cloud_data = {
            'college_name': 'Shambhunath College of Education',
            'last_updated': datetime.now().isoformat(),
            'total_records': len(attendance_data),
            'attendance_records': attendance_data
        }
        
        # Save to local cloud backup file (simulating cloud storage)
        backup_dir = 'cloud_backups'
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f'{backup_dir}/attendance_backup_{timestamp}.json'
        
        with open(backup_file, 'w') as f:
            json.dump(cloud_data, f, indent=2)
        
        # Also maintain latest backup
        with open('cloud_backup_latest.json', 'w') as f:
            json.dump(cloud_data, f, indent=2)
        
        print(f"Cloud backup completed: {len(attendance_data)} records saved to {backup_file}")
        
    except Exception as e:
        print(f"Cloud sync failed: {str(e)}")

@app.route('/cloud_backup')
def cloud_backup():
    """Manual cloud backup endpoint for admin"""
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    try:
        sync_to_cloud()
        return jsonify({'success': 'Data backed up to cloud successfully'})
    except Exception as e:
        return jsonify({'error': f'Backup failed: {str(e)}'})

@app.route('/download_data')
def download_data():
    """Download attendance data as JSON"""
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT a.student_id, s.name, a.session_id, ses.subject, a.timestamp
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        JOIN sessions ses ON a.session_id = ses.session_id
        ORDER BY a.timestamp DESC
    ''')
    
    data = []
    for row in c.fetchall():
        data.append({
            'student_id': row[0],
            'student_name': row[1],
            'session_id': row[2],
            'subject': row[3],
            'timestamp': row[4]
        })
    
    conn.close()
    
    response = jsonify({
        'college': 'Shambhunath College of Education',
        'exported_at': datetime.now().isoformat(),
        'total_records': len(data),
        'attendance_data': data
    })
    
    response.headers['Content-Disposition'] = 'attachment; filename=attendance_data.json'
    response.headers['Content-Type'] = 'application/json'
    return response

@app.route('/get_admin_stats')
def get_admin_stats():
    """Get admin statistics"""
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    # Total students
    c.execute("SELECT COUNT(*) FROM students")
    total_students = c.fetchone()[0]
    
    # Total sessions
    c.execute("SELECT COUNT(*) FROM sessions")
    total_sessions = c.fetchone()[0]
    
    # Total attendance
    c.execute("SELECT COUNT(*) FROM attendance")
    total_attendance = c.fetchone()[0]
    
    # Today's attendance
    today = datetime.now().date().isoformat()
    c.execute("SELECT COUNT(*) FROM attendance WHERE DATE(timestamp)=?", (today,))
    today_attendance = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_students': total_students,
        'total_sessions': total_sessions,
        'total_attendance': total_attendance,
        'today_attendance': today_attendance
    })

@app.route('/get_all_attendance')
def get_all_attendance():
    """Get all attendance records with student names"""
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT a.student_id, s.name, a.session_id, ses.subject, a.timestamp
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        JOIN sessions ses ON a.session_id = ses.session_id
        ORDER BY a.timestamp DESC
    ''')
    
    attendance_records = []
    for row in c.fetchall():
        attendance_records.append({
            'student_id': row[0],
            'student_name': row[1],
            'session_id': row[2],
            'subject': row[3],
            'timestamp': row[4]
        })
    
    conn.close()
    
    return jsonify({
        'attendance': attendance_records,
        'total_records': len(attendance_records)
    })

@app.route('/get_attendance_stats')
def get_attendance_stats():
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    student_id = session['student_id']
    today = datetime.now().date().isoformat()
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND DATE(timestamp)=?", (student_id, today))
    today_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=?", (student_id,))
    total_count = c.fetchone()[0]
    conn.close()
    
    return jsonify({'today': today_count, 'total': total_count})

@app.route('/get_current_session')
def get_current_session():
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT subject, session_id FROM sessions WHERE datetime(expires_at) > datetime('now') ORDER BY created_at DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    
    if result:
        return jsonify({'subject': result[0], 'session_id': result[1]})
    return jsonify({'subject': 'No active session', 'session_id': None})

@app.route('/get_current_session_admin')
def get_current_session_admin():
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT session_id, subject, created_at, expires_at FROM sessions WHERE datetime(expires_at) > datetime('now') ORDER BY created_at DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    
    if result:
        return jsonify({
            'session_id': result[0],
            'subject': result[1],
            'created_at': result[2],
            'expires_at': result[3]
        })
    return jsonify({'session_id': None})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    cleanup_expired_sessions()
    print("Starting Shambhunath College Attendance System...")
    print("Student Portal: http://localhost:5000")
    print("Admin Portal: http://localhost:5000/admin")
    print("Admin Login: username=admin, password=admin123")
    print("Generate sessions manually with subjects")
    app.run(debug=True, host='0.0.0.0', port=5000)