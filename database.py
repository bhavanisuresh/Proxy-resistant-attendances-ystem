import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'attendance_pro.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users (Students and Faculty)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            enrollment_number TEXT UNIQUE,
            department TEXT,
            photo_path TEXT,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student', -- 'student' or 'faculty'
            academic_details TEXT,
            cgpa REAL DEFAULT 0.0
        )
    ''')
    
    # Monitoring Sessions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            end_time DATETIME,
            avg_focus_score REAL,
            efficiency_score REAL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # High-frequency Behavioral Logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS behavior_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            focus_score REAL,
            liveness_status BOOLEAN,
            gaze_direction TEXT,
            task_efficiency REAL,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    ''')
    
    # Alerts / Deviations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            type TEXT, -- 'Spoof', 'Low Focus', 'Identity'
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    ''')
    
    # Classroom Attendance (for batch results)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classroom_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Present',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Demo Data
    # Admin
    cursor.execute("INSERT OR IGNORE INTO users (name, email, password, role) VALUES ('System Admin', 'admin@smart.ai', 'admin123', 'admin')")
    
    # Faculty
    cursor.execute("INSERT OR IGNORE INTO users (name, email, password, role) VALUES ('Dr. Kumar', 'faculty@smart.ai', 'password123', 'faculty')")
    
    # Student (Gangadhar)
    cursor.execute('''
        INSERT OR IGNORE INTO users (name, email, enrollment_number, department, photo_path, password, role, academic_details) 
        VALUES ('Gangadhar', 'gangadharreddy1432@gmail.com', 'ENR001', 'B.Tech AIDS', 'static/students/gangadhar.jpg', 'student123', 'student', 'Year: 3, GPA: 8.5')
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

if __name__ == '__main__':
    init_db()
    print("Advanced Database initialized.")
