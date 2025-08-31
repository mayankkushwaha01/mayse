"""
Firebase Configuration for Shambhunath College Attendance System
Handles heavy traffic with real-time database and batch operations
"""

import json
import urllib.request
import urllib.parse
import threading
import time
from datetime import datetime
from queue import Queue
import hashlib

class FirebaseManager:
    def __init__(self, firebase_url, api_key=None):
        self.firebase_url = firebase_url.rstrip('/')
        self.api_key = api_key
        self.batch_queue = Queue()
        self.batch_size = 50  # Process 50 records at once
        self.batch_interval = 5  # Process every 5 seconds
        self.start_batch_processor()
    
    def start_batch_processor(self):
        """Start background batch processor for heavy traffic"""
        def process_batches():
            while True:
                try:
                    batch_data = []
                    # Collect batch_size items or wait for batch_interval
                    start_time = time.time()
                    
                    while len(batch_data) < self.batch_size and (time.time() - start_time) < self.batch_interval:
                        try:
                            item = self.batch_queue.get(timeout=1)
                            batch_data.append(item)
                        except:
                            break
                    
                    if batch_data:
                        self.send_batch_to_firebase(batch_data)
                        print(f"Processed batch of {len(batch_data)} records")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"Batch processor error: {e}")
                    time.sleep(5)
        
        thread = threading.Thread(target=process_batches, daemon=True)
        thread.start()
    
    def add_to_batch(self, data_type, data):
        """Add data to batch queue for processing"""
        batch_item = {
            'type': data_type,
            'data': data,
            'timestamp': datetime.now().isoformat(),
            'id': hashlib.md5(f"{data_type}_{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        }
        self.batch_queue.put(batch_item)
    
    def send_batch_to_firebase(self, batch_data):
        """Send batch data to Firebase"""
        try:
            # Group by data type
            grouped_data = {}
            for item in batch_data:
                data_type = item['type']
                if data_type not in grouped_data:
                    grouped_data[data_type] = []
                grouped_data[data_type].append(item['data'])
            
            # Send each group
            for data_type, items in grouped_data.items():
                self.send_to_firebase(f"{data_type}_batch", {
                    'items': items,
                    'batch_timestamp': datetime.now().isoformat(),
                    'count': len(items)
                })
                
        except Exception as e:
            print(f"Batch send error: {e}")
    
    def send_to_firebase(self, path, data):
        """Send data to Firebase Realtime Database"""
        try:
            url = f"{self.firebase_url}/{path}.json"
            if self.api_key:
                url += f"?auth={self.api_key}"
            
            json_data = json.dumps(data).encode('utf-8')
            
            req = urllib.request.Request(
                url,
                data=json_data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode())
                return {'success': True, 'firebase_id': result.get('name')}
                
        except Exception as e:
            print(f"Firebase send error: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_from_firebase(self, path):
        """Get data from Firebase"""
        try:
            url = f"{self.firebase_url}/{path}.json"
            if self.api_key:
                url += f"?auth={self.api_key}"
            
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                return {'success': True, 'data': data}
                
        except Exception as e:
            print(f"Firebase get error: {e}")
            return {'success': False, 'error': str(e)}
    
    def update_firebase(self, path, data):
        """Update data in Firebase"""
        try:
            url = f"{self.firebase_url}/{path}.json"
            if self.api_key:
                url += f"?auth={self.api_key}"
            
            json_data = json.dumps(data).encode('utf-8')
            
            req = urllib.request.Request(
                url,
                data=json_data,
                headers={'Content-Type': 'application/json'},
                method='PATCH'
            )
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode())
                return {'success': True, 'data': result}
                
        except Exception as e:
            print(f"Firebase update error: {e}")
            return {'success': False, 'error': str(e)}

class AttendanceFirebase:
    def __init__(self, firebase_url, api_key=None):
        self.firebase = FirebaseManager(firebase_url, api_key)
        self.college_name = "Shambhunath College of Education"
    
    def mark_attendance_async(self, student_id, student_name, session_id, subject):
        """Mark attendance asynchronously for heavy traffic"""
        attendance_data = {
            'student_id': student_id,
            'student_name': student_name,
            'session_id': session_id,
            'subject': subject,
            'timestamp': datetime.now().isoformat(),
            'college': self.college_name
        }
        
        # Add to batch queue for processing
        self.firebase.add_to_batch('attendance', attendance_data)
        
        # Also update real-time stats
        self.update_realtime_stats()
    
    def create_session_async(self, session_id, subject, expires_at):
        """Create session asynchronously"""
        session_data = {
            'session_id': session_id,
            'subject': subject,
            'created_at': datetime.now().isoformat(),
            'expires_at': expires_at,
            'college': self.college_name,
            'status': 'active'
        }
        
        self.firebase.add_to_batch('sessions', session_data)
    
    def register_student_async(self, student_id, name, password_hash):
        """Register student asynchronously"""
        student_data = {
            'student_id': student_id,
            'name': name,
            'password_hash': password_hash,
            'registered_at': datetime.now().isoformat(),
            'college': self.college_name
        }
        
        self.firebase.add_to_batch('students', student_data)
    
    def update_realtime_stats(self):
        """Update real-time statistics"""
        stats = {
            'last_updated': datetime.now().isoformat(),
            'total_attendance_today': self.get_today_attendance_count(),
            'active_sessions': self.get_active_sessions_count(),
            'college': self.college_name
        }
        
        # Send immediately for real-time updates
        self.firebase.send_to_firebase('stats/realtime', stats)
    
    def get_today_attendance_count(self):
        """Get today's attendance count from local DB"""
        # This would query your local database
        return 0  # Placeholder
    
    def get_active_sessions_count(self):
        """Get active sessions count"""
        return 0  # Placeholder
    
    def sync_all_data(self):
        """Full data sync to Firebase"""
        try:
            # This would sync all data from SQLite to Firebase
            sync_data = {
                'sync_timestamp': datetime.now().isoformat(),
                'college': self.college_name,
                'sync_type': 'full_backup'
            }
            
            result = self.firebase.send_to_firebase('backups/full_sync', sync_data)
            return result
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Configuration
FIREBASE_CONFIG = {
    'url': 'https://shambhunath-college-default-rtdb.firebaseio.com',
    'api_key': 'your_firebase_api_key_here',  # Replace with actual API key
    'project_id': 'shambhunath-college'
}

# Initialize Firebase manager
firebase_attendance = AttendanceFirebase(
    FIREBASE_CONFIG['url'],
    FIREBASE_CONFIG['api_key']
)

if __name__ == '__main__':
    # Test Firebase connection
    print("Testing Firebase connection...")
    
    # Test data
    test_data = {
        'test': True,
        'timestamp': datetime.now().isoformat(),
        'message': 'Firebase connection test'
    }
    
    result = firebase_attendance.firebase.send_to_firebase('test', test_data)
    print(f"Test result: {result}")