import mysql.connector
from mysql.connector import Error

def create_connection():
    """Create and return a database connection object for the teacher portal."""
    
    try:
        connection = mysql.connector.connect(
            host='localhost',        # Your database host
            database='portal',          # The name of your database
            user='root',             # Your database username
            password='aditya',       # Your database password
            auth_plugin='mysql_native_password'
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None
