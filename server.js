const express = require('express');
const mysql = require('mysql2/promise');
const session = require('express-session');
const bcrypt = require('bcrypt');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const compression = require('compression');
const { v4: uuidv4 } = require('uuid');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 5000;

// Security middleware
app.use(helmet());
app.use(compression());
app.use(cors({
  origin: process.env.FRONTEND_URL || 'http://localhost:5000',
  credentials: true
}));

// Rate limiting for login attempts
const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 10, // limit each IP to 10 requests per windowMs
  message: 'Too many login attempts, please try again later',
  standardHeaders: true,
  legacyHeaders: false,
});

// General rate limiting
const generalLimiter = rateLimit({
  windowMs: 1 * 60 * 1000, // 1 minute
  max: 100, // limit each IP to 100 requests per windowMs
});

app.use('/login', loginLimiter);
app.use(generalLimiter);

// Body parsing middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Static files
app.use(express.static(path.join(__dirname, 'templates')));

// Session configuration
app.use(session({
  secret: process.env.SESSION_SECRET || 'shambhunath_college_secret_key_2024',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: process.env.NODE_ENV === 'production',
    httpOnly: true,
    maxAge: 24 * 60 * 60 * 1000 // 24 hours
  }
}));

// MySQL Connection Pool Configuration
const dbConfig = {
  host: process.env.DB_HOST || 'localhost',
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || '',
  database: process.env.DB_NAME || 'shambhunath_attendance',
  waitForConnections: true,
  connectionLimit: 50, // Maximum 50 concurrent connections
  queueLimit: 0,
  acquireTimeout: 60000,
  timeout: 60000,
  reconnect: true,
  charset: 'utf8mb4'
};

// Create connection pool
const pool = mysql.createPool(dbConfig);

// Database initialization
async function initDatabase() {
  try {
    const connection = await pool.getConnection();
    
    // Create database if not exists
    await connection.execute(`CREATE DATABASE IF NOT EXISTS ${dbConfig.database}`);
    await connection.execute(`USE ${dbConfig.database}`);
    
    // Create tables with indexes for performance
    await connection.execute(`
      CREATE TABLE IF NOT EXISTS students (
        id VARCHAR(50) PRIMARY KEY,
        password VARCHAR(255) NOT NULL,
        name VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP NULL,
        INDEX idx_student_id (id),
        INDEX idx_name (name)
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    `);
    
    await connection.execute(`
      CREATE TABLE IF NOT EXISTS sessions (
        session_id VARCHAR(50) PRIMARY KEY,
        subject VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        status ENUM('active', 'expired') DEFAULT 'active',
        INDEX idx_expires_at (expires_at),
        INDEX idx_status (status)
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    `);
    
    await connection.execute(`
      CREATE TABLE IF NOT EXISTS attendance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        student_id VARCHAR(50) NOT NULL,
        session_id VARCHAR(50) NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
        UNIQUE KEY unique_attendance (student_id, session_id),
        INDEX idx_student_id (student_id),
        INDEX idx_session_id (session_id),
        INDEX idx_timestamp (timestamp)
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    `);
    
    await connection.execute(`
      CREATE TABLE IF NOT EXISTS admin (
        username VARCHAR(50) PRIMARY KEY,
        password VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    `);
    
    // Create default admin user
    const adminPassword = await bcrypt.hash('Mayank#0069', 12);
    await connection.execute(`
      INSERT IGNORE INTO admin (username, password) VALUES (?, ?)
    `, ['admin', adminPassword]);
    
    connection.release();
    console.log('✅ Database initialized successfully');
    
  } catch (error) {
    console.error('❌ Database initialization error:', error);
    process.exit(1);
  }
}

// Middleware to check authentication
const requireAuth = (req, res, next) => {
  if (!req.session.student_id) {
    return res.status(401).json({ error: 'Authentication required' });
  }
  next();
};

const requireAdmin = (req, res, next) => {
  if (!req.session.admin_logged_in) {
    return res.status(401).json({ error: 'Admin authentication required' });
  }
  next();
};

// Routes
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'templates', 'index.html'));
});

app.get('/dashboard', (req, res) => {
  if (!req.session.student_id) {
    return res.redirect('/');
  }
  res.sendFile(path.join(__dirname, 'templates', 'dashboard.html'));
});

app.get('/admin', (req, res) => {
  if (!req.session.admin_logged_in) {
    return res.sendFile(path.join(__dirname, 'templates', 'admin_login.html'));
  }
  res.sendFile(path.join(__dirname, 'templates', 'admin.html'));
});

// Student registration
app.post('/register', async (req, res) => {
  const { student_id, password, name } = req.body;
  
  if (!student_id || !password || !name) {
    return res.status(400).json({ error: 'All fields are required' });
  }
  
  try {
    const hashedPassword = await bcrypt.hash(password, 12);
    
    await pool.execute(
      'INSERT INTO students (id, password, name) VALUES (?, ?, ?)',
      [student_id, hashedPassword, name]
    );
    
    res.json({ success: 'Registration successful' });
    
  } catch (error) {
    if (error.code === 'ER_DUP_ENTRY') {
      return res.status(400).json({ error: 'Student ID already exists' });
    }
    console.error('Registration error:', error);
    res.status(500).json({ error: 'Registration failed' });
  }
});

// Student login with connection pooling
app.post('/login', async (req, res) => {
  const { student_id, password } = req.body;
  
  if (!student_id || !password) {
    return res.status(400).json({ error: 'Student ID and password are required' });
  }
  
  try {
    const [rows] = await pool.execute(
      'SELECT id, password, name FROM students WHERE id = ?',
      [student_id]
    );
    
    if (rows.length === 0) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }
    
    const student = rows[0];
    const isValidPassword = await bcrypt.compare(password, student.password);
    
    if (!isValidPassword) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }
    
    // Update last login
    await pool.execute(
      'UPDATE students SET last_login = CURRENT_TIMESTAMP WHERE id = ?',
      [student_id]
    );
    
    req.session.student_id = student_id;
    req.session.student_name = student.name;
    
    res.json({ 
      success: 'Login successful',
      student_name: student.name,
      student_id: student_id
    });
    
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Login failed' });
  }
});

// Admin login
app.post('/admin_login', async (req, res) => {
  const { username, password } = req.body;
  
  try {
    const [rows] = await pool.execute(
      'SELECT username, password FROM admin WHERE username = ?',
      [username]
    );
    
    if (rows.length === 0) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }
    
    const admin = rows[0];
    const isValidPassword = await bcrypt.compare(password, admin.password);
    
    if (!isValidPassword) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }
    
    req.session.admin_logged_in = true;
    res.json({ success: 'Admin login successful' });
    
  } catch (error) {
    console.error('Admin login error:', error);
    res.status(500).json({ error: 'Login failed' });
  }
});

// Generate session
app.post('/generate_session', requireAdmin, async (req, res) => {
  const { subject } = req.body;
  
  if (!subject) {
    return res.status(400).json({ error: 'Subject is required' });
  }
  
  try {
    const session_id = uuidv4().substring(0, 8).toUpperCase();
    const expires_at = new Date(Date.now() + 60 * 60 * 1000); // 1 hour from now
    
    // Clean expired sessions
    await pool.execute('DELETE FROM sessions WHERE expires_at < NOW()');
    
    // Insert new session
    await pool.execute(
      'INSERT INTO sessions (session_id, subject, expires_at) VALUES (?, ?, ?)',
      [session_id, subject, expires_at]
    );
    
    res.json({
      session_id: session_id,
      subject: subject,
      expires_at: expires_at
    });
    
  } catch (error) {
    console.error('Session generation error:', error);
    res.status(500).json({ error: 'Failed to generate session' });
  }
});

// Mark attendance with batch processing
app.post('/mark_attendance', requireAuth, async (req, res) => {
  const { session_id } = req.body;
  const student_id = req.session.student_id;
  
  if (!session_id) {
    return res.status(400).json({ error: 'Session ID is required' });
  }
  
  const connection = await pool.getConnection();
  
  try {
    await connection.beginTransaction();
    
    // Check if session is valid
    const [sessionRows] = await connection.execute(
      'SELECT subject FROM sessions WHERE session_id = ? AND expires_at > NOW() AND status = "active"',
      [session_id]
    );
    
    if (sessionRows.length === 0) {
      await connection.rollback();
      return res.status(400).json({ error: 'Session expired or invalid' });
    }
    
    const subject = sessionRows[0].subject;
    
    // Check if attendance already marked
    const [attendanceRows] = await connection.execute(
      'SELECT id FROM attendance WHERE student_id = ? AND session_id = ?',
      [student_id, session_id]
    );
    
    if (attendanceRows.length > 0) {
      await connection.rollback();
      return res.status(400).json({ error: 'Attendance already marked for this session' });
    }
    
    // Mark attendance
    await connection.execute(
      'INSERT INTO attendance (student_id, session_id) VALUES (?, ?)',
      [student_id, session_id]
    );
    
    await connection.commit();
    res.json({ success: `Attendance marked for ${subject}` });
    
  } catch (error) {
    await connection.rollback();
    console.error('Attendance marking error:', error);
    res.status(500).json({ error: 'Failed to mark attendance' });
  } finally {
    connection.release();
  }
});

// Get current session
app.get('/get_current_session', async (req, res) => {
  try {
    const [rows] = await pool.execute(
      'SELECT session_id, subject FROM sessions WHERE expires_at > NOW() AND status = "active" ORDER BY created_at DESC LIMIT 1'
    );
    
    if (rows.length > 0) {
      res.json({
        session_id: rows[0].session_id,
        subject: rows[0].subject
      });
    } else {
      res.json({
        subject: 'No active session',
        session_id: null
      });
    }
    
  } catch (error) {
    console.error('Get current session error:', error);
    res.status(500).json({ error: 'Failed to get current session' });
  }
});

// Get all attendance (admin)
app.get('/get_all_attendance', requireAdmin, async (req, res) => {
  try {
    const [rows] = await pool.execute(`
      SELECT 
        a.student_id,
        s.name as student_name,
        a.session_id,
        ses.subject,
        a.timestamp
      FROM attendance a
      JOIN students s ON a.student_id = s.id
      JOIN sessions ses ON a.session_id = ses.session_id
      ORDER BY a.timestamp DESC
      LIMIT 1000
    `);
    
    res.json({
      attendance: rows,
      total_records: rows.length
    });
    
  } catch (error) {
    console.error('Get attendance error:', error);
    res.status(500).json({ error: 'Failed to get attendance records' });
  }
});

// Get attendance stats
app.get('/get_attendance_stats', requireAuth, async (req, res) => {
  const student_id = req.session.student_id;
  
  try {
    const [todayRows] = await pool.execute(
      'SELECT COUNT(*) as count FROM attendance WHERE student_id = ? AND DATE(timestamp) = CURDATE()',
      [student_id]
    );
    
    const [totalRows] = await pool.execute(
      'SELECT COUNT(*) as count FROM attendance WHERE student_id = ?',
      [student_id]
    );
    
    res.json({
      today: todayRows[0].count,
      total: totalRows[0].count
    });
    
  } catch (error) {
    console.error('Get stats error:', error);
    res.status(500).json({ error: 'Failed to get attendance stats' });
  }
});

// Logout
app.post('/logout', (req, res) => {
  req.session.destroy((err) => {
    if (err) {
      return res.status(500).json({ error: 'Logout failed' });
    }
    res.json({ success: 'Logged out successfully' });
  });
});

// Health check endpoint
app.get('/health', async (req, res) => {
  try {
    await pool.execute('SELECT 1');
    res.json({ 
      status: 'healthy',
      database: 'connected',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({ 
      status: 'unhealthy',
      database: 'disconnected',
      error: error.message
    });
  }
});

// Error handling middleware
app.use((error, req, res, next) => {
  console.error('Unhandled error:', error);
  res.status(500).json({ error: 'Internal server error' });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, shutting down gracefully');
  await pool.end();
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('SIGINT received, shutting down gracefully');
  await pool.end();
  process.exit(0);
});

// Start server
async function startServer() {
  try {
    await initDatabase();
    
    app.listen(PORT, '0.0.0.0', () => {
      console.log('🚀 Scalable Attendance System Started');
      console.log(`📡 Server running on port ${PORT}`);
      console.log(`🗄️  Database: MySQL with connection pooling`);
      console.log(`⚡ Max connections: ${dbConfig.connectionLimit}`);
      console.log(`🔐 Admin Password: Mayank#0069`);
      console.log(`🌐 Health check: http://localhost:${PORT}/health`);
    });
    
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

startServer();