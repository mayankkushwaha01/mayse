from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import hashlib
from datetime import datetime, timedelta
import uuid
import os
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
app.secret_key = 'shambhunath_college_secret'

# Heavy load optimizations
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Thread pool for database operations (increased for concurrent logins)
executor = ThreadPoolExecutor(max_workers=50)

# Login cache for faster authentication
login_cache = {}
login_cache_lock = threading.Lock()
cache_timeout = 300  # 5 minutes

# Active sessions tracking
active_sessions = {}
session_lock = threading.Lock()

# Connection pool (increased for concurrent users)
connection_pool = queue.Queue(maxsize=20)
for _ in range(20):
    conn = sqlite3.connect('/tmp/attendance.db', check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')  # Better concurrency
    conn.execute('PRAGMA synchronous=NORMAL')  # Faster writes
    conn.execute('PRAGMA cache_size=10000')  # More cache
    connection_pool.put(conn)

# Batch processing
batch_queue = queue.Queue()
batch_size = 50
batch_timeout = 2

def get_db_connection():
    try:
        return connection_pool.get(timeout=2)
    except queue.Empty:
        conn = sqlite3.connect('/tmp/attendance.db', check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        return conn

def cleanup_expired_cache():
    """Clean expired login cache entries"""
    while True:
        current_time = time.time()
        with login_cache_lock:
            expired_keys = [k for k, v in login_cache.items() 
                          if current_time - v['timestamp'] > cache_timeout]
            for key in expired_keys:
                del login_cache[key]
        time.sleep(60)  # Clean every minute

def track_user_session(student_id, action='login'):
    """Track active user sessions"""
    with session_lock:
        if action == 'login':
            active_sessions[student_id] = {
                'login_time': datetime.now().isoformat(),
                'last_activity': datetime.now().isoformat()
            }
        elif action == 'logout' and student_id in active_sessions:
            del active_sessions[student_id]
        elif action == 'activity' and student_id in active_sessions:
            active_sessions[student_id]['last_activity'] = datetime.now().isoformat()

# Start cache cleanup thread
cache_cleanup_thread = threading.Thread(target=cleanup_expired_cache, daemon=True)
cache_cleanup_thread.start()

def return_db_connection(conn):
    try:
        connection_pool.put(conn, timeout=1)
    except queue.Full:
        conn.close()

def batch_processor():
    while True:
        batch = []
        start_time = time.time()
        
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
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        attendance_data = [(item['student_id'], item['session_id'], item['timestamp']) for item in batch]
        c.executemany("INSERT INTO attendance VALUES (?, ?, ?)", attendance_data)
        conn.commit()
        
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
    
    c.execute("DELETE FROM admin WHERE username='admin'")
    admin_pass = hashlib.md5('Mayank#0069'.encode()).hexdigest()
    c.execute("INSERT INTO admin VALUES ('admin', ?)", (admin_pass,))
    
    conn.commit()
    return_db_connection(conn)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    student_id = request.form['student_id']
    password = request.form['password']
    password_hash = hashlib.md5(password.encode()).hexdigest()
    
    # Check login cache first
    cache_key = f"{student_id}:{password_hash}"
    with login_cache_lock:
        if cache_key in login_cache:
            cache_entry = login_cache[cache_key]
            if time.time() - cache_entry['timestamp'] < cache_timeout:
                session['student_id'] = student_id
                session['student_name'] = cache_entry['name']
                session.permanent = True
                track_user_session(student_id, 'login')
                return redirect(url_for('dashboard'))
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, name FROM students WHERE id=? AND password=?", (student_id, password_hash))
        user = c.fetchone()
        return_db_connection(conn)
        return user
    
    future = executor.submit(db_operation)
    try:
        user = future.result(timeout=3)
        
        if user:
            # Cache successful login
            with login_cache_lock:
                login_cache[cache_key] = {
                    'name': user[1],
                    'timestamp': time.time()
                }
            
            session['student_id'] = student_id
            session['student_name'] = user[1]
            session.permanent = True
            track_user_session(student_id, 'login')
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Login error: {e}")
    
    return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    student_id = request.form['student_id']
    password = hashlib.md5(request.form['password'].encode()).hexdigest()
    name = request.form['name']
    
    def db_operation():
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO students VALUES (?, ?, ?)", (student_id, password, name))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            return_db_connection(conn)
    
    future = executor.submit(db_operation)
    try:
        success = future.result(timeout=3)
        if not success:
            # Student ID already exists
            return redirect(url_for('index'))
    except Exception as e:
        print(f"Registration error: {e}")
    
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    
    student_id = session['student_id']
    track_user_session(student_id, 'activity')
    
    # Use cached name if available
    if 'student_name' in session:
        student_name = session['student_name']
    else:
        def db_operation():
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT name FROM students WHERE id=?", (student_id,))
            student = c.fetchone()
            return_db_connection(conn)
            return student[0] if student else 'Student'
        
        future = executor.submit(db_operation)
        try:
            student_name = future.result(timeout=3)
            session['student_name'] = student_name
        except:
            student_name = 'Student'
    
    return render_template('dashboard.html', student_name=student_name, student_id=student_id)

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
    if 'student_id' in session:
        track_user_session(session['student_id'], 'logout')
    session.clear()
    return redirect(url_for('index'))

@app.route('/active_users')
def active_users():
    """Get count of active users (admin only)"""
    if 'admin_logged_in' not in session:
        return jsonify({'error': 'Unauthorized'})
    
    with session_lock:
        active_count = len(active_sessions)
        recent_logins = list(active_sessions.values())[-10:]  # Last 10 logins
    
    return jsonify({
        'active_users': active_count,
        'recent_logins': recent_logins,
        'cache_size': len(login_cache)
    })

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Multi-User Attendance System Starting...")
    print(f"⚡ Optimized for {batch_size} concurrent users")
    print(f"🔧 Thread pool: {executor._max_workers} workers")
    print(f"💾 Connection pool: 20 connections")
    print(f"💾 Login cache: {cache_timeout}s timeout")
    print("👥 Multiple concurrent logins supported")
    print("🔑 Admin Password: Mayank#0069")
    
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True, processes=1)