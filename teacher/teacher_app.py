from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from teacher_db import create_connection
import mysql.connector
from functools import wraps
import datetime

app = Flask(__name__, template_folder='templates')
app.secret_key = 'a_different_teacher_secret_key'

@app.route('/')
def index():
    """Redirects the base URL to the teacher login page."""
    return redirect(url_for('teacher_login_page'))

def teacher_required(f):
    """Decorator to ensure a user is logged in as a teacher."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_type' not in session or session['user_type'] != 'teacher':
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            return redirect(url_for('teacher_login_page'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/teacher')
def teacher_login_page():
    """Renders the teacher portal login page."""
    return render_template('teacher_portal.html')

@app.route('/teacher/login', methods=['POST'])
def teacher_login_action():
    """Handles teacher login."""
    data = request.get_json()
    email, password = data.get('email'), data.get('password')
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required.'}), 400
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Teachers WHERE email = %s AND password = %s", (email, password))
        teacher = cursor.fetchone()
        if teacher:
            session['user_type'] = 'teacher'
            session['user_id'] = teacher['teacher_id']
            session['user_name'] = teacher['name']
            return jsonify({'success': True, 'teacher': {'name': teacher['name'], 'id': teacher['teacher_id']}})
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401
    finally:
        if conn.is_connected(): conn.close()

@app.route('/teacher/logout', methods=['POST'])
def teacher_logout():
    """Logs the teacher out."""
    session.clear()
    return jsonify({'success': True})

# --- Teacher API Endpoints ---

@app.route('/api/teacher/session')
def teacher_session():
    """Checks for an active teacher session."""
    if session.get('user_type') == 'teacher':
        return jsonify({
            'logged_in': True,
            'teacher': { 'id': session.get('user_id'), 'name': session.get('user_name') }
        })
    return jsonify({'logged_in': False})

@app.route('/api/teacher/schedule')
@teacher_required
def get_teacher_schedule():
    """Fetches the weekly schedule for the logged-in teacher."""
    teacher_id = session.get('user_id')
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT s.day_of_week, s.start_time, s.end_time, s.batch,
                   c.class_name, sub.subject_name
            FROM Schedules s
            JOIN Classes c ON s.class_id = c.class_id
            JOIN Subjects sub ON s.subject_id = sub.subject_id
            WHERE s.teacher_id = %s
        """
        cursor.execute(query, (teacher_id,))
        schedule = cursor.fetchall()
        for item in schedule:
            item['start_time'] = str(item['start_time'])
            item['end_time'] = str(item['end_time'])
        return jsonify({'success': True, 'data': schedule})
    finally:
        if conn.is_connected(): conn.close()

@app.route('/api/teacher/today_classes')
@teacher_required
def get_today_classes():
    """Fetches classes scheduled for the current day for the logged-in teacher."""
    teacher_id = session.get('user_id')
    today_name = datetime.datetime.now().strftime('%A')
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT s.schedule_id, s.start_time, s.end_time, s.batch,
                   c.class_name, sub.subject_name
            FROM Schedules s
            JOIN Classes c ON s.class_id = c.class_id
            JOIN Subjects sub ON s.subject_id = sub.subject_id
            WHERE s.teacher_id = %s AND s.day_of_week = %s
            ORDER BY s.start_time
        """
        cursor.execute(query, (teacher_id, today_name))
        classes = cursor.fetchall()
        for item in classes:
            item['start_time'] = str(item['start_time'])
            item['end_time'] = str(item['end_time'])
        return jsonify({'success': True, 'data': classes})
    finally:
        if conn.is_connected(): conn.close()

@app.route('/api/teacher/all_classes')
@teacher_required
def get_all_teacher_classes():
    """Fetches all unique classes assigned to the teacher."""
    teacher_id = session.get('user_id')
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT DISTINCT s.schedule_id, c.class_name, sub.subject_name, s.batch
            FROM Schedules s
            JOIN Classes c ON s.class_id = c.class_id
            JOIN Subjects sub ON s.subject_id = sub.subject_id
            WHERE s.teacher_id = %s
            ORDER BY c.class_name, sub.subject_name, s.batch
        """
        cursor.execute(query, (teacher_id,))
        return jsonify({'success': True, 'data': cursor.fetchall()})
    finally:
        if conn.is_connected(): conn.close()


# MODIFIED: Logic simplified to fetch students by batch only
@app.route('/api/teacher/class_students')
@teacher_required
def get_class_students():
    """Fetches all students belonging to the batch of a given schedule."""
    schedule_id = request.args.get('schedule_id')
    if not schedule_id:
        return jsonify({'success': False, 'message': 'Schedule ID is required.'}), 400

    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Step 1: Find the batch for the given schedule
        cursor.execute("SELECT batch FROM Schedules WHERE schedule_id = %s", (schedule_id,))
        schedule_info = cursor.fetchone()

        if not schedule_info:
            return jsonify({'success': False, 'message': 'Schedule not found.'}), 404

        batch = schedule_info['batch']

        # Step 2: Get all students who are in that batch (class_id check removed)
        query = """
            SELECT student_id, name, email, batch
            FROM Students
            WHERE batch = %s
            ORDER BY name;
        """
        cursor.execute(query, (batch,))
        students = cursor.fetchall()
        return jsonify({'success': True, 'data': students})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': f"Database Error: {err}"}), 500
    finally:
        if conn.is_connected(): conn.close()

@app.route('/api/teacher/mark_attendance', methods=['POST'])
@teacher_required
def mark_attendance():
    """Saves attendance data for multiple students."""
    data = request.get_json()
    schedule_id = data.get('schedule_id')
    date = data.get('date')
    attendance_data = data.get('attendance_data')
    if not all([schedule_id, date, attendance_data]):
        return jsonify({'success': False, 'message': 'Missing required data.'}), 400
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor()
        query = """
            INSERT INTO attendance (student_id, schedule_id, attendance_date, status)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status = VALUES(status)
        """
        records = [(item['student_id'], schedule_id, date, item['status']) for item in attendance_data]
        cursor.executemany(query, records)
        conn.commit()
        return jsonify({'success': True, 'message': f'Attendance for {cursor.rowcount} students saved.'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'success': False, 'message': str(err)}), 500
    finally:
        if conn.is_connected(): conn.close()

# MODIFIED: Logic simplified to fetch students by batch only
@app.route('/api/teacher/attendance')
@teacher_required
def view_attendance():
    """
    Fetches a complete student list for a given schedule and date based on batch.
    """
    schedule_id = request.args.get('schedule_id')
    date = request.args.get('date')

    if not schedule_id or not date:
        return jsonify({'success': False, 'message': 'Schedule ID and date are required.'}), 400

    conn = create_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Step 1: Find the batch for the given schedule
        cursor.execute("SELECT batch FROM Schedules WHERE schedule_id = %s", (schedule_id,))
        schedule_info = cursor.fetchone()
        if not schedule_info:
            return jsonify({'success': False, 'message': 'Schedule not found.'}), 404

        batch = schedule_info['batch']

        # Step 2: Get all students belonging to that batch (class_id check removed)
        cursor.execute(
            "SELECT student_id, name, email FROM Students WHERE batch = %s ORDER BY name",
            (batch,)
        )
        all_students = cursor.fetchall()

        # Step 3: Get existing attendance records for that day
        cursor.execute("""
            SELECT student_id, status, timestamp
            FROM attendance
            WHERE schedule_id = %s AND attendance_date = %s
        """, (schedule_id, date))
        attendance_records = {rec['student_id']: rec for rec in cursor.fetchall()}

        # Step 4: Merge the two lists
        full_attendance_list = []
        for student in all_students:
            record = attendance_records.get(student['student_id'])
            status = record['status'] if record else 'absent'
            timestamp_str = str(record['timestamp']) if record and record.get('timestamp') else None

            full_attendance_list.append({
                'student_id': student['student_id'],
                'student_name': student['name'],
                'student_email': student['email'],
                'status': status,
                'timestamp': timestamp_str
            })

        return jsonify({'success': True, 'data': full_attendance_list})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': f"Database error: {str(err)}"}), 500
    finally:
        if conn.is_connected():
            conn.close()


if __name__ == '__main__':
    app.run(debug=True, port=5001)