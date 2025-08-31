from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import hashlib
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = 'shambhunath_college_secret'

def init_db():
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (id TEXT PRIMARY KEY, password TEXT, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (session_id TEXT PRIMARY KEY, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance 
                 (student_id TEXT, session_id TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins 
                 (id TEXT PRIMARY KEY, password TEXT, name TEXT)''')
    
    # Create default admin account
    admin_password = hashlib.md5('admin123'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO admins VALUES (?, ?, ?)", 
              ('admin', admin_password, 'Administrator'))
    
    conn.commit()
    conn.close()

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
    try:
        c.execute("INSERT INTO students VALUES (?, ?, ?)", (student_id, password, name))
        conn.commit()
    except:
        pass
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    
    # Get student details
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT name FROM students WHERE id=?", (session['student_id'],))
    student = c.fetchone()
    conn.close()
    
    student_name = student[0] if student else 'Unknown'
    return render_template('dashboard.html', student_name=student_name, student_id=session['student_id'])

@app.route('/qr_scanner')
def qr_scanner():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    return render_template('qr_scanner.html')

@app.route('/admin')
def admin():
    if 'admin_id' not in session:
        return render_template('admin_login.html')
    return render_template('simple_admin.html')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    admin_id = request.form['admin_id']
    password = hashlib.md5(request.form['password'].encode()).hexdigest()
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT * FROM admins WHERE id=? AND password=?", (admin_id, password))
    admin = c.fetchone()
    conn.close()
    
    if admin:
        session['admin_id'] = admin_id
        return redirect(url_for('admin'))
    return render_template('admin_login.html', error='Invalid credentials')

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_id', None)
    return redirect(url_for('index'))

@app.route('/generate_session', methods=['POST'])
def generate_session():
    if 'admin_id' not in session:
        return jsonify({'error': 'Unauthorized'})
        
    session_id = str(uuid.uuid4())[:8]
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("INSERT INTO sessions VALUES (?, ?)", 
              (session_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return jsonify({'session_id': session_id})

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    session_id = request.json['session_id']
    student_id = session['student_id']
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,))
    if not c.fetchone():
        conn.close()
        return jsonify({'error': 'Invalid session ID'})
    
    # Check if already marked
    c.execute("SELECT * FROM attendance WHERE student_id=? AND session_id=?", (student_id, session_id))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'Attendance already marked for this session'})
    
    c.execute("INSERT INTO attendance VALUES (?, ?, ?)", 
              (student_id, session_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return jsonify({'success': 'Attendance marked successfully'})

@app.route('/get_attendance_stats')
def get_attendance_stats():
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    student_id = session['student_id']
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    # Get today's attendance count
    today = datetime.now().date().isoformat()
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date(timestamp)=?", 
              (student_id, today))
    today_count = c.fetchone()[0]
    
    # Get total attendance count
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=?", (student_id,))
    total_count = c.fetchone()[0]
    
    conn.close()
    return jsonify({'today': today_count, 'total': total_count})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)