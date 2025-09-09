from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from db import create_connection
import mysql.connector

app = Flask(__name__)
app.secret_key = 'your_secret_key' # Change this to a secure, random key

# --- Authentication ---
@app.route('/', methods=['GET', 'POST'])
def login():
    """Handles admin login."""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            conn = create_connection()
            if not conn:
                return render_template('login.html', error='Database connection failed.')
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Admins WHERE email = %s AND password = %s", (email, password))
            admin = cursor.fetchone()
            if admin:
                session['logged_in'] = True
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error='Invalid Credentials.')
        except mysql.connector.Error as err:
            return render_template('login.html', error=f'Database error: {err}')
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logs the admin out."""
    session.clear()
    return redirect(url_for('login'))

def admin_required(func):
    """Decorator to ensure a user is logged in as an admin."""
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__ 
    return wrapper

# --- Main Dashboard & Data Fetching ---
@app.route('/dashboard')
@admin_required
def dashboard():
    """Renders the single-page admin portal."""
    return render_template('admin_portal.html')

@app.route('/classes')
@admin_required
def get_classes():
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT class_id as id, class_name as name FROM Classes ORDER BY name")
        return jsonify({'success': True, 'data': cursor.fetchall()})
    finally:
        if conn and conn.is_connected(): conn.close()

@app.route('/subjects')
@admin_required
def get_subjects():
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT subject_id as id, subject_name as name FROM Subjects ORDER BY subject_name")
        return jsonify({'success': True, 'data': cursor.fetchall()})
    finally:
        if conn and conn.is_connected(): conn.close()

@app.route('/teachers')
@admin_required
def get_teachers():
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT teacher_id as id, name FROM Teachers ORDER BY name")
        return jsonify({'success': True, 'data': cursor.fetchall()})
    finally:
        if conn and conn.is_connected(): conn.close()

@app.route('/api/batches')
@admin_required
def get_batches():
    """Provides a list of available batches from the database."""
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT batch_id as id, batch_name as name FROM Batches ORDER BY name")
        batches = cursor.fetchall()
        return jsonify({'success': True, 'data': batches})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'message': f"Database Error: {err}"}), 500
    finally:
        if conn and conn.is_connected(): conn.close()

@app.route('/api/schedules')
@admin_required
def get_schedules():
    teacher_id = request.args.get('teacher_id')
    if not teacher_id: return jsonify({'success': False, 'message': 'Teacher ID is required.'}), 400
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT s.schedule_id, s.day_of_week, s.start_time, s.end_time, s.batch,
                   c.class_name, sub.subject_name
            FROM Schedules s
            JOIN Classes c ON s.class_id = c.class_id
            JOIN Subjects sub ON s.subject_id = sub.subject_id
            WHERE s.teacher_id = %s
            ORDER BY FIELD(s.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), s.start_time
        """
        cursor.execute(query, (teacher_id,))
        schedules = cursor.fetchall()
        for schedule in schedules: # Convert time objects to strings for JSON
            schedule['start_time'] = str(schedule['start_time'])
            schedule['end_time'] = str(schedule['end_time'])
        return jsonify({'success': True, 'data': schedules})
    finally:
        if conn and conn.is_connected(): conn.close()

# --- API Endpoints for Data Management ---

@app.route('/api/create_user', methods=['POST'])
@admin_required
def create_user_api():
    """Creates a new student or teacher with validation for student batches."""
    data = request.json
    user_type = data.get('user_type')
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    batch = data.get('batch') if user_type == 'student' else None

    if not all([user_type, name, email, password]) or (user_type == 'student' and not batch):
        return jsonify({'success': False, 'message': 'Missing required fields.'}), 400
    
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor()
        
        # Check batch capacity if creating a student
        if user_type == 'student':
            cursor.execute("SELECT COUNT(*) FROM Students WHERE batch = %s", (batch,))
            count = cursor.fetchone()[0]
            if count >= 60:
                return jsonify({'success': False, 'message': f'Error: Batch "{batch}" is full (60 students max).'}), 409

        table_name = f"{user_type.capitalize()}s"
        if user_type == 'student':
            query = f"INSERT INTO {table_name} (name, email, password, batch) VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (name, email, password, batch))
        else:
            query = f"INSERT INTO {table_name} (name, email, password) VALUES (%s, %s, %s)"
            cursor.execute(query, (name, email, password))
        conn.commit()
        return jsonify({'success': True, 'message': f"{user_type.capitalize()} created successfully!"})
    except mysql.connector.Error as err:
        conn.rollback()
        if err.errno == 1062: return jsonify({'success': False, 'message': f'Error: Email "{email}" already exists.'}), 409
        return jsonify({'success': False, 'message': f"Database Error: {err}"}), 500
    finally:
        if conn.is_connected(): conn.close()

@app.route('/api/schedule_class', methods=['POST'])
@admin_required
def schedule_class_api():
    data = request.json
    required = ['class_id', 'subject_id', 'teacher_id', 'batch', 'day_of_week', 'start_time', 'end_time']
    if not all(data.get(field) for field in required):
        return jsonify({'success': False, 'message': 'All fields, including batch, are required.'}), 400

    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor()
        # Check for scheduling conflicts
        conflict_query = "SELECT schedule_id FROM Schedules WHERE teacher_id = %s AND day_of_week = %s AND (%s < end_time AND %s > start_time)"
        cursor.execute(conflict_query, (data['teacher_id'], data['day_of_week'], data['start_time'], data['end_time']))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Scheduling conflict: Teacher is already booked at this time.'}), 409

        insert_query = """
            INSERT INTO Schedules (class_id, subject_id, teacher_id, batch, day_of_week, start_time, end_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        values = (data['class_id'], data['subject_id'], data['teacher_id'], data['batch'], data['day_of_week'], data['start_time'], data['end_time'])
        cursor.execute(insert_query, values)
        conn.commit()
        return jsonify({'success': True, 'message': "Class scheduled successfully!"})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'success': False, 'message': f"Database Error: {err}"}), 500
    finally:
        if conn.is_connected(): conn.close()

@app.route('/api/remove_schedule', methods=['POST'])
@admin_required
def remove_schedule_api():
    schedule_id = request.json.get('schedule_id')
    if not schedule_id: return jsonify({'success': False, 'message': 'Schedule ID is required.'}), 400
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Schedules WHERE schedule_id = %s", (schedule_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'Schedule not found.'}), 404
        return jsonify({'success': True, 'message': 'Schedule removed successfully!'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Database Error: {err}'}), 500
    finally:
        if conn.is_connected(): conn.close()

@app.route('/api/manage_classes', methods=['POST'])
@admin_required
def manage_classes_api():
    data, action = request.json, request.json.get('action')
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor()
        if action == 'add':
            cursor.execute("INSERT INTO Classes (class_name) VALUES (%s)", (data['class_name'],))
            message = "Class added successfully."
        elif action == 'remove':
            cursor.execute("DELETE FROM Classes WHERE class_id = %s", (data['class_id'],))
            message = "Class removed successfully."
        conn.commit()
        return jsonify({'success': True, 'message': message})
    except mysql.connector.Error as err:
        conn.rollback()
        if err.errno == 1451: return jsonify({'success': False, 'message': 'Cannot remove: this class is used in existing schedules.'}), 409
        return jsonify({'success': False, 'message': f"Database Error: {err}"}), 500
    finally:
        if conn.is_connected(): conn.close()

@app.route('/api/manage_subjects', methods=['POST'])
@admin_required
def manage_subjects_api():
    data, action = request.json, request.json.get('action')
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor()
        if action == 'add':
            cursor.execute("INSERT INTO Subjects (subject_name) VALUES (%s)", (data['subject_name'],))
            message = "Subject added successfully."
        elif action == 'remove':
            cursor.execute("DELETE FROM Subjects WHERE subject_id = %s", (data['subject_id'],))
            message = "Subject removed successfully."
        conn.commit()
        return jsonify({'success': True, 'message': message})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'success': False, 'message': f"Database Error: {err}"}), 500
    finally:
        if conn.is_connected(): conn.close()

@app.route('/api/manage_batches', methods=['POST'])
@admin_required
def manage_batches_api():
    """Handles adding and removing batches."""
    data, action = request.json, request.json.get('action')
    conn = create_connection()
    if not conn: return jsonify({'success': False, 'message': 'Database error'}), 500
    try:
        cursor = conn.cursor()
        if action == 'add':
            cursor.execute("INSERT INTO Batches (batch_name) VALUES (%s)", (data['batch_name'],))
            message = "Batch added successfully."
        elif action == 'remove':
            # Before removing, check if the batch is in use.
            batch_name_cursor = conn.cursor(dictionary=True)
            batch_name_cursor.execute("SELECT batch_name FROM Batches WHERE batch_id = %s", (data['batch_id'],))
            batch = batch_name_cursor.fetchone()
            if batch:
                batch_name = batch['batch_name']
                # Check Students table
                cursor.execute("SELECT 1 FROM Students WHERE batch = %s LIMIT 1", (batch_name,))
                if cursor.fetchone():
                    return jsonify({'success': False, 'message': 'Cannot remove: this batch is in use by students.'}), 409
                # Check Schedules table
                cursor.execute("SELECT 1 FROM Schedules WHERE batch = %s LIMIT 1", (batch_name,))
                if cursor.fetchone():
                    return jsonify({'success': False, 'message': 'Cannot remove: this batch is in use by schedules.'}), 409
            
            cursor.execute("DELETE FROM Batches WHERE batch_id = %s", (data['batch_id'],))
            message = "Batch removed successfully."
        conn.commit()
        return jsonify({'success': True, 'message': message})
    except mysql.connector.Error as err:
        conn.rollback()
        if err.errno == 1062:
            return jsonify({'success': False, 'message': f'Error: Batch "{data["batch_name"]}" already exists.'}), 409
        return jsonify({'success': False, 'message': f"Database Error: {err}"}), 500
    finally:
        if conn.is_connected(): conn.close()


if __name__ == '__main__':
    app.run(debug=True, port=5000)