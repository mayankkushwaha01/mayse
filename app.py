from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import hashlib
import qrcode
import io
import base64
from datetime import datetime, timedelta
import uuid
import threading
import time

app = Flask(__name__)
app.secret_key = 'shambhunath_college_secret'

def init_db():
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (id TEXT PRIMARY KEY, password TEXT, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (session_id TEXT PRIMARY KEY, qr_code TEXT, created_at TEXT, expires_at TEXT, subject TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance 
                 (student_id TEXT, session_id TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    
    # Create default admin if not exists
    c.execute("SELECT * FROM admin WHERE username='admin'")
    if not c.fetchone():
        admin_pass = hashlib.md5('admin123'.encode()).hexdigest()
        c.execute("INSERT INTO admin VALUES ('admin', ?)", (admin_pass,))
    
    conn.commit()
    conn.close()

def auto_generate_qr():
    while True:
        session_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(hours=1)
        
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE datetime(expires_at) < datetime('now')")
        c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)", 
                  (session_id, session_id, now.isoformat(), expires_at.isoformat(), 'Auto-Generated Class'))
        conn.commit()
        conn.close()
        
        time.sleep(3600)  # Wait 1 hour

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

@app.route('/generate_qr', methods=['POST'])
def generate_qr():
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    subject = request.json.get('subject', 'General Class')
    
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT session_id, subject FROM sessions WHERE datetime(expires_at) > datetime('now') ORDER BY created_at DESC LIMIT 1")
    result = c.fetchone()
    
    if result:
        session_id, current_subject = result
    else:
        session_id = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(hours=1)
        c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)", 
                  (session_id, session_id, now.isoformat(), expires_at.isoformat(), subject))
        conn.commit()
        current_subject = subject
    
    conn.close()
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(session_id)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    qr_code = base64.b64encode(buffer.getvalue()).decode()
    return jsonify({'qr_code': qr_code, 'session_id': session_id, 'subject': current_subject})

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
        return jsonify({'error': 'QR code expired or invalid'})
    
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
    c.execute("SELECT subject FROM sessions WHERE datetime(expires_at) > datetime('now') ORDER BY created_at DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    
    if result:
        return jsonify({'subject': result[0]})
    return jsonify({'subject': 'No active session'})

@app.route('/qr_scanner')
def qr_scanner():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    return render_template('qr_scanner.html')

@app.route('/scan_qr', methods=['POST'])
def scan_qr():
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
        return jsonify({'error': 'QR code expired or invalid'})
    
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    
    # Start auto QR generation in background
    qr_thread = threading.Thread(target=auto_generate_qr, daemon=True)
    qr_thread.start()
    
    app.run(debug=True)