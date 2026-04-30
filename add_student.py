from database import get_db_connection, init_db
import os
import base64

def enroll_student(name, email, enroll_num, dept, password, academic, photo_path):
    conn = get_db_connection()
    try:
        # Create student folder if it doesn't exist
        if not os.path.exists('static/students'):
            os.makedirs('static/students')

        # Check if student already exists
        existing = conn.execute('SELECT id FROM users WHERE enrollment_number = ?', (enroll_num,)).fetchone()
        if existing:
            print(f"Error: Student with Enrollment {enroll_num} already exists.")
            return

        conn.execute('''
            INSERT INTO users (name, email, enrollment_number, department, photo_path, password, role, academic_details)
            VALUES (?, ?, ?, ?, ?, ?, 'student', ?)
        ''', (name, email, enroll_num, dept, photo_path, password, academic))
        conn.commit()
        print(f"Successfully Enrolled: {name} [{enroll_num}]")
    except Exception as e:
        print(f"Critical Error: {e}")
    finally:
        conn.close()

def main():
    init_db()
    print("\n--- Smart Attendance: Manual Database Entry ---")
    name = input("Student Full Name: ")
    email = input("Institutional Email: ")
    enroll_num = input("Enrollment Number (e.g. ENR001): ")
    dept = input("Department: ")
    password = input("Portal Password: ")
    academic = input("Academic Summary (optional): ")
    photo_path = input("Path to Identity Photo (relative to project root): ")
    
    if not os.path.exists(photo_path):
        print(f"Warning: Photo not found at {photo_path}. AI matching will be disabled for this user until a photo is uploaded.")
    
    enroll_student(name, email, enroll_num, dept, password, academic, photo_path)
    print("\nEnrollment Complete. Please restart the Flask server to retrain the AI Engine.")

if __name__ == '__main__':
    main()
