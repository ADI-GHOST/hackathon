import mysql.connector
from mysql.connector import Error

def create_connection():
    """Create and return a database connection object."""
    
    connection = mysql.connector.connect(
            host='localhost', # Replace with your host
            database='portal',
            user='root', # Replace with your username
            password='aditya',
            auth_plugin='mysql_native_password'
              
        )
    if connection.is_connected():
            return connection
  

