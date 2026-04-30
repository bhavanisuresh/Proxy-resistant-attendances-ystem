from flask import Flask, render_template, request, jsonify, session
import os
import base64
from database import get_db_connection, init_db
from engine import engine
from models import model

app = Flask(__name__)
app.secret_key = 'advanced_attendance_pro_key'

def train_engine():
    conn = get_db_connection()
    students = conn.execute('SELECT id, name, photo_path FROM users WHERE photo_path IS NOT NULL').fetchall()
    conn.close()
    if students:
        student_data = [{'id': s['id'], 'path': s['photo_path'], 'name': s['name']} for s in students]
        engine.train_on_dataset(student_data)
        print(f"Intelligence engine trained on {len(students)} student records.")

# Initialize
init_db()
train_engine()

@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/faculty')
def faculty_page():
    return render_template('index.html')

@app.route('/student')
def student_page():
    return render_template('student.html')

@app.route('/outcomes')
def outcomes_page():
    return render_template('outcomes.html')

@app.route('/enroll')
def enroll_page():
    return render_template('enroll.html')

@app.route('/hub')
def hub_page():
    return render_template('hub.html')


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    identifier = data.get('email') or data.get('identifier')
    password = data.get('password')
    
    conn = get_db_connection()
    # Support login with either Email or Enrollment Number
    user = conn.execute('''
        SELECT * FROM users 
        WHERE (email = ? OR enrollment_number = ?) AND password = ?
    ''', (identifier, identifier, password)).fetchone()
    conn.close()
    
    if user:
        session['user_id'] = user['id']
        session['role'] = user['role']
        session['user_name'] = user['name']
        
        # Start a new session for students
        if user['role'] == 'student':
            conn = get_db_connection()
            conn.execute('INSERT INTO sessions (user_id) VALUES (?)', (user['id'],))
            conn.commit()
            conn.close()
            
        return jsonify({"success": True, "role": user['role'], "name": user['name']})
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route('/api/student/data', methods=['GET'])
def get_student_data():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    # Calculate Smart Attendance (Weighted by Focus)
    # 1. Total potential heartbeats (how long the class has been running)
    total_logs = conn.execute('SELECT COUNT(*) as count FROM behavior_logs WHERE session_id IN (SELECT id FROM sessions)').fetchone()['count'] or 1
    
    # 2. Student's specific focus-weighted logs
    # We sum the focus scores. If focus is 1.0 (paying attention), they get full attendance for that second.
    # If focus is 0.3 (away), they only get 0.3 attendance.
    focus_sum = conn.execute('''
        SELECT SUM(focus_score) 
        FROM behavior_logs b
        JOIN sessions s ON b.session_id = s.id
        WHERE s.user_id = ?
    ''', (user_id,)).fetchone()[0] or 0
    
    # 3. Final Percentage = (Earned Focus / Potential Focus) * 100
    # For demo simplicity, we'll use a relative scale
    attendance_percentage = min(100.0, round((focus_sum / (total_logs / 10 if total_logs > 0 else 1)) * 100, 1))
    
    # Alternatively, more direct: (Present Heartbeats * Avg Focus)
    # Let's use a simpler but impactful formula for the demo:
    my_logs = conn.execute('SELECT COUNT(*) as count FROM behavior_logs b JOIN sessions s ON b.session_id = s.id WHERE s.user_id = ?', (user_id,)).fetchone()['count']
    avg_focus = conn.execute('SELECT AVG(focus_score) FROM behavior_logs b JOIN sessions s ON b.session_id = s.id WHERE s.user_id = ?', (user_id,)).fetchone()[0] or 0
    
    # Percentage = (My Presence Count / Target Count) * Avg Focus
    target_count = 100 # Simulated class duration in heartbeats
    smart_percentage = round((my_logs / target_count) * avg_focus * 100, 1) if my_logs > 0 else 0
    
    conn.close()
    
    return jsonify({
        "name": user['name'],
        "enrollment": user['enrollment_number'],
        "department": user['department'],
        "academic_details": user['academic_details'],
        "cgpa": user['cgpa'] if 'cgpa' in user.keys() else 0.0,
        "photo_path": user['photo_path'] or '',
        "attendance_percentage": min(100.0, smart_percentage),
        "eligible_for_exams": smart_percentage >= 75.0
    })

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/api/monitor/heartbeat', methods=['POST'])
def heartbeat():
    if session.get('role') != 'faculty':
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    image = data.get('image')
    
    # Batch Analysis using upgraded MediaPipe Engine
    batch_results = engine.analyze_behavior(image)
    
    conn = get_db_connection()
    
    for result in batch_results:
        if result['user_id']:
            # 1. Update Classroom Attendance
            # Attendance is only marked if liveness is confirmed and spoof check passes
            quality_check = result['liveness'] and result['spoof_check'] == 'Pass'
            if result['status'] == 'Verified' and quality_check:
                conn.execute('INSERT INTO classroom_attendance (user_id) VALUES (?)', (result['user_id'],))
            
            # 2. Log Detailed Behavior for Dashboard
            # Store focus score and basic gaze
            conn.execute('''
                INSERT INTO behavior_logs (session_id, focus_score, liveness_status, gaze_direction, task_efficiency)
                VALUES ((SELECT id FROM sessions WHERE user_id = ? ORDER BY start_time DESC LIMIT 1), ?, ?, ?, ?)
            ''', (result['user_id'], result['focus'], result['liveness'], result['gaze'], result['focus']))

            # 3. Handle Spoof Alerts
            if result['spoof_check'] == 'Fail':
                conn.execute('INSERT INTO alerts (session_id, type, message) VALUES ((SELECT id FROM sessions WHERE user_id = ? ORDER BY start_time DESC LIMIT 1), "Spoof", "Potential 2D/Screen spoofing detected")', (result['user_id'],))
            
    conn.commit()
    conn.close()
    
    return jsonify({
        "results": batch_results,
        "count": len(batch_results)
    })

@app.route('/api/faculty/add_student', methods=['POST'])
def add_student():
    # Role check relaxed for build/demo purposes
    # if session.get('role') != 'faculty':
    #     return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    name = data.get('name')
    email = data.get('email')
    enrollment = data.get('enrollment')
    dept = data.get('department')
    password = data.get('password')
    academic = data.get('academic')
    photo_b64 = data.get('photo')
    
    # Save photo
    photo_filename = f"{enrollment}.jpg"
    app_root = os.path.dirname(os.path.abspath(__file__))
    photo_dir = os.path.join(app_root, 'static', 'students')
    photo_path = os.path.join(photo_dir, photo_filename)
    
    if not os.path.exists(photo_dir):
        os.makedirs(photo_dir)
        
    if photo_b64:
        header, encoded = photo_b64.split(",", 1)
        with open(photo_path, "wb") as f:
            f.write(base64.b64decode(encoded))
            
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO users (name, email, enrollment_number, department, photo_path, password, role, academic_details)
            VALUES (?, ?, ?, ?, ?, ?, 'student', ?)
        ''', (name, email, enrollment, dept, photo_path, password, academic))
        conn.commit()
        # Retrain engine with new student
        train_engine()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400
    finally:
        conn.close()

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/api/faculty/bulk_enroll', methods=['POST'])
def bulk_enroll():
    if session.get('role') not in ['faculty', 'admin']:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    students = data.get('students', [])
    
    conn = get_db_connection()
    success_count = 0
    errors = []
    
    for s in students:
        try:
            conn.execute('''
                INSERT INTO users (name, email, enrollment_number, department, password, role, academic_details)
                VALUES (?, ?, ?, ?, ?, 'student', ?)
            ''', (s['name'], s['email'], s['enrollment'], s['department'], s['password'], s['academic']))
            success_count += 1
        except Exception as e:
            errors.append(f"{s['name']}: {str(e)}")
            
    conn.commit()
    conn.close()
    
    # Training is deferred until the end of bulk upload
    train_engine()
    
    return jsonify({"success": True, "count": success_count, "errors": errors})

@app.route('/api/faculty/students', methods=['GET'])
def get_faculty_students():
    if session.get('role') != 'faculty':
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db_connection()
    students = conn.execute('SELECT id, name, enrollment_number, department, photo_path FROM users WHERE role = "student"').fetchall()
    conn.close()
    return jsonify([dict(s) for s in students])

@app.route('/api/faculty/present_list', methods=['GET'])
def get_present_list():
    if session.get('role') != 'faculty':
        return jsonify({"error": "Unauthorized"}), 403
    
    conn = get_db_connection()
    present = conn.execute('''
        SELECT DISTINCT u.name, u.enrollment_number, MAX(c.timestamp) as last_seen
        FROM users u
        JOIN classroom_attendance c ON u.id = c.user_id
        WHERE date(c.timestamp) = date('now')
        GROUP BY u.id
        ORDER BY last_seen DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in present])

@app.route('/dashboard')
def dashboard_page():
    if session.get('role') not in ['admin', 'faculty']:
        return render_template('index.html')
    return render_template('dashboard.html')

@app.route('/api/admin/analytics', methods=['GET'])
def get_analytics():
    if session.get('role') not in ['admin', 'faculty']:
        return jsonify({"error": "Unauthorized"}), 403
    
    conn = get_db_connection()
    # Get overall engagement stats
    engagement = conn.execute('''
        SELECT u.name, AVG(b.focus_score) as avg_focus, COUNT(a.id) as alert_count
        FROM users u
        LEFT JOIN sessions s ON u.id = s.user_id
        LEFT JOIN behavior_logs b ON s.id = b.session_id
        LEFT JOIN alerts a ON s.id = a.session_id
        WHERE u.role = 'student'
        GROUP BY u.id
    ''').fetchall()
    
    # Get Hourly Attendance Trend
    trends = conn.execute('''
        SELECT strftime('%H:00', timestamp) as hour, COUNT(*) as count
        FROM classroom_attendance
        GROUP BY hour
        ORDER BY hour DESC
        LIMIT 12
    ''').fetchall()

    # Get Live Monitoring (currently in frame)
    live_students = conn.execute('''
        SELECT DISTINCT u.name, u.enrollment_number, b.focus_score, b.gaze_direction
        FROM users u
        JOIN classroom_attendance c ON u.id = c.user_id
        JOIN behavior_logs b ON u.id = (SELECT user_id FROM behavior_logs WHERE user_id = u.id ORDER BY timestamp DESC LIMIT 1)
        WHERE c.timestamp > datetime('now', '-1 minute')
    ''').fetchall()

    # Get Verified Students List (Present Folder - anyone verified today)
    verified_students = conn.execute('''
        SELECT DISTINCT u.name, u.enrollment_number, MAX(c.timestamp) as last_seen
        FROM users u
        JOIN classroom_attendance c ON u.id = c.user_id
        WHERE date(c.timestamp) = date('now')
        GROUP BY u.id
    ''').fetchall()
    
    conn.close()
    return jsonify({
        "engagement": [dict(e) for e in engagement],
        "trends": [dict(t) for t in trends],
        "live": [dict(l) for l in live_students],
        "verified": [dict(v) for v in verified_students]
    })

@app.route('/api/admin/users', methods=['GET'])
def get_all_users():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    conn = get_db_connection()
    users = conn.execute('SELECT id, name, email, role, department FROM users').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5005)
