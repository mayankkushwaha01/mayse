# Shambhunath College of Education - Live Session Attendance App

A modern web-based attendance management system for educational institutions with real-time session management and QR code-free attendance marking.

## 🚀 Features

- **Student Management**: Registration and login system
- **Session Management**: Create time-limited sessions with subjects
- **Attendance Tracking**: Mark attendance using session IDs
- **Admin Dashboard**: View all attendance records with student details
- **Real-time Updates**: Live session status and attendance stats
- **Data Export**: Download attendance data in JSON format
- **Responsive Design**: Works on desktop and mobile devices

## 🛠️ Technology Stack

- **Backend**: Python Flask
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, JavaScript
- **Styling**: Modern gradient designs with responsive layout

## 📋 Prerequisites

- Python 3.7 or higher
- Flask 2.0+
- Modern web browser

## ⚡ Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/shambhunath-attendance.git
   cd shambhunath-attendance
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python fast_app.py
   ```

4. **Access the application**
   - Student Portal: http://localhost:5000
   - Admin Portal: http://localhost:5000/admin

## 👥 Default Credentials

- **Admin Username**: admin
- **Admin Password**: Mayank#0069

## 📱 How to Use

### For Students:
1. Register with Student ID, Name, and Password
2. Login to access dashboard
3. Enter Session ID provided by teacher
4. Mark attendance for the active session

### For Admins:
1. Login to admin portal
2. Generate new sessions with subject names
3. Share Session ID with students
4. View total attendance records
5. Download attendance data

## 🏗️ Project Structure

```
shambhunath-attendance/
├── templates/
│   ├── index.html          # Student login/registration
│   ├── dashboard.html      # Student dashboard
│   ├── admin_login.html    # Admin login
│   └── admin.html          # Admin dashboard
├── fast_app.py             # Main application file
├── requirements.txt        # Python dependencies
├── README.md              # Project documentation
├── .gitignore             # Git ignore rules
└── attendance.db          # SQLite database (auto-created)
```

## 🔧 Configuration

### Database
The app uses SQLite database with the following tables:
- `students`: Student information
- `sessions`: Active sessions with subjects
- `attendance`: Attendance records
- `admin`: Admin credentials

### Session Management
- Sessions expire after 1 hour
- Each session has a unique 8-character ID
- Students can only mark attendance once per session

## 🚀 Deployment

### Local Development
```bash
python fast_app.py
```

### Production Deployment
1. Set `debug=False` in the app configuration
2. Use a production WSGI server like Gunicorn
3. Configure environment variables for security
4. Set up proper database backups

### Docker Deployment
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "fast_app.py"]
```

## 📊 API Endpoints

### Student Endpoints
- `POST /login` - Student login
- `POST /register` - Student registration
- `POST /mark_attendance` - Mark attendance
- `GET /get_attendance_stats` - Get student stats
- `GET /get_current_session` - Get active session info

### Admin Endpoints
- `POST /admin_login` - Admin login
- `POST /generate_session` - Create new session
- `GET /get_all_attendance` - Get all attendance records
- `GET /download_data` - Export attendance data

## 🔒 Security Features

- Password hashing using MD5
- Session-based authentication
- Input validation and sanitization
- SQL injection prevention
- Admin access control

## 🎨 UI Features

- Modern gradient designs
- Responsive layout for all devices
- Real-time updates without page refresh
- Interactive buttons with loading states
- Clean and intuitive interface

## 📈 Performance Optimizations

- Lightweight SQLite database
- Minimal dependencies
- Efficient query optimization
- Threaded Flask server
- Fast session management

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author

**Mayank Kushwaha**
- GitHub: [@yourusername](https://github.com/yourusername)
- Email: your.email@example.com

## 🙏 Acknowledgments

- Shambhunath College of Education for the project requirements
- Flask community for the excellent framework
- Contributors and testers

## 📞 Support

For support and queries:
- Create an issue on GitHub
- Email: support@shambhunathcollege.edu
- Phone: +91-XXXXXXXXXX

---

**Made with ❤️ for Shambhunath College of Education**# apps
