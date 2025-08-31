from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import hashlib
from datetime import datetime, timedelta
import uuid
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)
app.secret_key = 'shambhunath_college_secret'

# Heavy load optimizations
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # Cache static files for 1 year
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Thread pool for database operations
executor = ThreadPoolExecutor(max_workers=50)

# Connection pool simulation
connection_pool = queue.Queue(maxsize=20)
for _ in range(20):
    connection_pool.put(sqlite3.connect('attendance.db', check_same_thread=False))

def get_db_connection():
    """Get database connection from pool"""
    try:
        return connection_pool.get(timeout=5)
    except queue.Empty:
        return sqlite3.connect('attendance.db', check_same_thread=False)

def return_db_connection(conn):
    """Return connection to pool"""
    try:
        connection_pool.put(conn, timeout=1)
    except queue.Full:
        conn.close()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Optimized table creation with indexes
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (id TEXT PRIMARY KEY, password TEXT, name TEXT)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_student_id ON students(id)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (session_id TEXT PRIMARY KEY, created_at TEXT, expires_at TEXT, subject TEXT)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_session_expires ON sessions(expires_at)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS attendance 
                 (student_id TEXT, session_id TEXT, timestamp TEXT)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance(session_id)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admin 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    
    # Update admin password
    c.execute("DELETE FROM admin WHERE username='admin'")
    admin_pass = hashlib.md5('Mayank#0069'.encode()).hexdigest()
    c.execute("INSERT INTO admin VALUES ('admin', ?)", (admin_pass,))
    
    conn.commit()
    return_db_connection(conn)

# Batch processing for high load
batch_queue = queue.Queue()
batch_size = 100
batch_timeout = 2

def batch_processor():
    """Process attendance in batches for heavy load"""
    while True:
        batch = []
        start_time = time.time()
        
        # Collect batch
        while len(batch) < batch_size and (time.time() - start_time) < batch_timeout:
            try:
                item = batch_queue.get(timeout=0.5)
                batch.append(item)
            except queue.Empty:
                break
        
        if batch:
            process_attendance_batch(batch)
        
        time.sleep(0.1)

def process_attendance_batch(batch):
    """Process multiple attendance records at once"""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # Batch insert
        attendance_data = [(item['student_id'], item['session_id'], item['timestamp']) for item in batch]
        c.executemany("INSERT INTO attendance VALUES (?, ?, ?)", attendance_data)
        conn.commit()
        
        # Mark as processed
        for item in batch:
            item['callback'](True)
            
    except Exception as e:
        for item in batch:
            item['callback'](False)
    finally:
        return_db_connection(conn)

# Start batch processor
batch_thread = threading.Thread(target=batch_processor, daemon=True)
batch_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    student_id = request.form['student_id']
    password = hashlib.md5(request.form['password'].encode()).hexdigest()
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM students WHERE id=? AND password=?", (student_id, password))
        user = c.fetchone()
        return_db_connection(conn)
        return user
    
    future = executor.submit(db_operation)
    user = future.result(timeout=5)
    
    if user:
        session['student_id'] = student_id
        session.permanent = True
        return redirect(url_for('dashboard'))
    return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    student_id = request.form['student_id']
    password = hashlib.md5(request.form['password'].encode()).hexdigest()
    name = request.form['name']
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO students VALUES (?, ?, ?)", (student_id, password, name))
        conn.commit()
        return_db_connection(conn)
    
    executor.submit(db_operation)
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT name FROM students WHERE id=?", (session['student_id'],))
        student = c.fetchone()
        return_db_connection(conn)
        return student
    
    future = executor.submit(db_operation)
    student = future.result(timeout=5)
    
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
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM admin WHERE username=? AND password=?", (username, password))
        admin = c.fetchone()
        return_db_connection(conn)
        return admin
    
    future = executor.submit(db_operation)
    admin = future.result(timeout=5)
    
    if admin:
        session['admin_logged_in'] = True
        session.permanent = True
        return redirect(url_for('admin'))
    return render_template('admin_login.html', error='Invalid credentials')

@app.route('/generate_session', methods=['POST'])
def generate_session():
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    subject = request.json.get('subject', 'General Class')
    session_id = str(uuid.uuid4())[:8].upper()
    now = datetime.now()
    expires_at = now + timedelta(hours=1)
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE datetime(expires_at) < datetime('now')")
        c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", 
                  (session_id, now.isoformat(), expires_at.isoformat(), subject))
        conn.commit()
        return_db_connection(conn)
    
    executor.submit(db_operation)
    return jsonify({'session_id': session_id, 'subject': subject})

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    session_id = request.json['session_id']
    student_id = session['student_id']
    
    # Validate session first
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT subject FROM sessions WHERE session_id=? AND datetime(expires_at) > datetime('now')", (session_id,))
    result = c.fetchone()
    
    if not result:
        return_db_connection(conn)
        return jsonify({'error': 'Session expired or invalid'})
    
    subject = result[0]
    
    # Check if already marked
    c.execute("SELECT * FROM attendance WHERE student_id=? AND session_id=?", (student_id, session_id))
    if c.fetchone():
        return_db_connection(conn)
        return jsonify({'error': 'Attendance already marked for this session'})
    
    return_db_connection(conn)
    
    # Add to batch queue for processing
    result_queue = queue.Queue()
    
    def callback(success):
        result_queue.put(success)
    
    batch_item = {
        'student_id': student_id,
        'session_id': session_id,
        'timestamp': datetime.now().isoformat(),
        'callback': callback
    }
    
    batch_queue.put(batch_item)
    
    # Wait for result
    try:
        success = result_queue.get(timeout=10)
        if success:
            return jsonify({'success': f'Attendance marked for {subject}'})
        else:
            return jsonify({'error': 'Failed to mark attendance'})
    except queue.Empty:
        return jsonify({'error': 'Request timeout'})

@app.route('/get_current_session')
def get_current_session():
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT subject, session_id FROM sessions WHERE datetime(expires_at) > datetime('now') ORDER BY created_at DESC LIMIT 1")
        result = c.fetchone()
        return_db_connection(conn)
        return result
    
    future = executor.submit(db_operation)
    result = future.result(timeout=5)
    
    if result:
        return jsonify({'subject': result[0], 'session_id': result[1]})
    return jsonify({'subject': 'No active session', 'session_id': None})

@app.route('/get_attendance_stats')
def get_attendance_stats():
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    student_id = session['student_id']
    today = datetime.now().date().isoformat()
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND DATE(timestamp)=?", (student_id, today))
        today_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=?", (student_id,))
        total_count = c.fetchone()[0]
        return_db_connection(conn)
        return today_count, total_count
    
    future = executor.submit(db_operation)
    today_count, total_count = future.result(timeout=5)
    
    return jsonify({'today': today_count, 'total': total_count})

@app.route('/get_all_attendance')
def get_all_attendance():
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute('''
            SELECT a.student_id, s.name, a.session_id, ses.subject, a.timestamp
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN sessions ses ON a.session_id = ses.session_id
            ORDER BY a.timestamp DESC
            LIMIT 1000
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
        
        return_db_connection(conn)
        return attendance_records
    
    future = executor.submit(db_operation)
    attendance_records = future.result(timeout=10)
    
    return jsonify({
        'attendance': attendance_records,
        'total_records': len(attendance_records)
    })

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Error handlers for heavy load
@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Server overloaded, please try again'}), 500

@app.errorhandler(503)
def service_unavailable(error):
    return jsonify({'error': 'Service temporarily unavailable'}), 503

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Heavy Load Attendance System Starting...")
    print(f"⚡ Optimized for {batch_size} concurrent users")
    print(f"🔧 Thread pool: {executor._max_workers} workers")
    print(f"💾 Connection pool: 20 connections")
    print("🔑 Admin Password: Mayank#0069")
    
    # Production settings for heavy load
    app.run(
        debug=False, 
        host='0.0.0.0', 
        port=port, 
        threaded=True,
        processes=1
    )