from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import hashlib
from datetime import datetime, timedelta
import uuid
import os

app = Flask(__name__)
app.secret_key = 'shambhunath_college_secret'

def init_db():
    conn = sqlite3.connect('/tmp/attendance.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (id TEXT PRIMARY KEY, password TEXT, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (session_id TEXT PRIMARY KEY, created_at TEXT, expires_at TEXT, subject TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance 
                 (student_id TEXT, session_id TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    
    c.execute("DELETE FROM admin WHERE username='admin'")
    admin_pass = hashlib.md5('Mayank#0069'.encode()).hexdigest()
    c.execute("INSERT INTO admin VALUES ('admin', ?)", (admin_pass,))
    
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    student_id = request.form['student_id']
    password = hashlib.md5(request.form['password'].encode()).hexdigest()
    
    conn = sqlite3.connect('/tmp/attendance.db')
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
    
    conn = sqlite3.connect('/tmp/attendance.db')
    c = conn.cursor()
    c.execute("INSERT INTO students VALUES (?, ?, ?)", (student_id, password, name))
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('/tmp/attendance.db')
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
    
    conn = sqlite3.connect('/tmp/attendance.db')
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
    session_id = str(uuid.uuid4())[:8].upper()
    now = datetime.now()
    expires_at = now + timedelta(hours=1)
    
    conn = sqlite3.connect('/tmp/attendance.db')
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE datetime(expires_at) < datetime('now')")
    c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", 
              (session_id, now.isoformat(), expires_at.isoformat(), subject))
    conn.commit()
    conn.close()
    
    return jsonify({'session_id': session_id, 'subject': subject})

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    session_id = request.json['session_id']
    student_id = session['student_id']
    
    conn = sqlite3.connect('/tmp/attendance.db')
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
    
    return jsonify({'success': f'Attendance marked for {subject}'})

@app.route('/get_current_session')
def get_current_session():
    conn = sqlite3.connect('/tmp/attendance.db')
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
    
    conn = sqlite3.connect('/tmp/attendance.db')
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

@app.route('/get_all_attendance')
def get_all_attendance():
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    conn = sqlite3.connect('/tmp/attendance.db')
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
    
    conn = sqlite3.connect('/tmp/attendance.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND DATE(timestamp)=?", (student_id, today))
    today_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=?", (student_id,))
    total_count = c.fetchone()[0]
    conn.close()
    
    return jsonify({'today': today_count, 'total': total_count})

@app.route('/download_data')
def download_data():
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    conn = sqlite3.connect('/tmp/attendance.db')
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)