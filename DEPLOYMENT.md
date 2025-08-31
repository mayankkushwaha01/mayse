# Deployment Guide

## GitHub Deployment Steps

### 1. Initialize Git Repository
```bash
cd d:\newwwwwwwwwwwwwwwwwwwww
git init
git add .
git commit -m "Initial commit: Shambhunath College Attendance System"
```

### 2. Create GitHub Repository
1. Go to [GitHub.com](https://github.com)
2. Click "New repository"
3. Repository name: `shambhunath-attendance`
4. Description: `Live Session Attendance App for Shambhunath College of Education`
5. Set to Public or Private
6. Don't initialize with README (we already have one)
7. Click "Create repository"

### 3. Connect Local Repository to GitHub
```bash
git remote add origin https://github.com/yourusername/shambhunath-attendance.git
git branch -M main
git push -u origin main
```

### 4. Verify Deployment
- Check that all files are uploaded
- Verify README.md displays correctly
- Test clone functionality

## Local Development Setup

### Prerequisites
- Python 3.7+
- Git
- Web browser

### Installation
```bash
git clone https://github.com/yourusername/shambhunath-attendance.git
cd shambhunath-attendance
pip install -r requirements.txt
python fast_app.py
```

## Production Deployment Options

### 1. Heroku Deployment
Create `Procfile`:
```
web: python fast_app.py
```

Create `runtime.txt`:
```
python-3.9.18
```

Deploy:
```bash
heroku create shambhunath-attendance
git push heroku main
```

### 2. Railway Deployment
1. Connect GitHub repository to Railway
2. Deploy automatically from main branch
3. Set environment variables if needed

### 3. Render Deployment
1. Connect GitHub repository
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `python fast_app.py`

### 4. PythonAnywhere Deployment
1. Upload files to PythonAnywhere
2. Create web app with Flask
3. Configure WSGI file
4. Set static files path

## Environment Configuration

### Development
```python
app.run(debug=True, host='localhost', port=5000)
```

### Production
```python
app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
```

## Database Considerations

### Development
- Uses SQLite (attendance.db)
- Automatically created on first run
- Suitable for testing and small deployments

### Production
- Consider PostgreSQL for larger deployments
- Set up regular backups
- Monitor database size and performance

## Security Checklist

- [ ] Change default admin password
- [ ] Use environment variables for secrets
- [ ] Enable HTTPS in production
- [ ] Set up proper error handling
- [ ] Implement rate limiting
- [ ] Regular security updates

## Monitoring and Maintenance

### Logs
- Monitor application logs
- Set up error tracking
- Regular performance monitoring

### Backups
- Database backups
- Code repository backups
- Configuration backups

### Updates
- Regular dependency updates
- Security patches
- Feature updates

## Troubleshooting

### Common Issues
1. **Port already in use**: Change port in app.run()
2. **Database locked**: Restart application
3. **Template not found**: Check templates directory
4. **Import errors**: Verify requirements.txt

### Debug Mode
Enable debug mode for development:
```python
app.run(debug=True)
```

## Support

For deployment issues:
- Check GitHub Issues
- Review deployment logs
- Contact system administrator