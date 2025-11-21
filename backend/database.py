import sqlite3
import hashlib
import datetime
import os

DATABASE_PATH = "docfox.db"

def init_database():
    """Initialize the SQLite database with the required tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Users table for authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Notebooks table for storing user notebooks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notebooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Chat messages table for storing conversations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notebook_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (notebook_id) REFERENCES notebooks (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get a database connection"""
    return sqlite3.connect(DATABASE_PATH)

def hash_password(password: str) -> str:
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return hash_password(password) == hashed

def create_user(username: str, email: str, password: str):
    """Create a new user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    
    try:
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def authenticate_user(username: str, password: str):
    """Authenticate a user by username and password"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, username, email, password_hash FROM users WHERE username = ?",
        (username,)
    )
    user = cursor.fetchone()
    conn.close()
    
    if user and verify_password(password, user[3]):
        return {
            "id": user[0],
            "username": user[1],
            "email": user[2]
        }
    return None

def get_user_by_id(user_id: int):
    """Get user by ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, username, email FROM users WHERE id = ?",
        (user_id,)
    )
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            "id": user[0],
            "username": user[1],
            "email": user[2]
        }
    return None

def create_notebook(user_id: int, title: str, description: str = None):
    """Create a new notebook for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO notebooks (user_id, title, description) VALUES (?, ?, ?)",
        (user_id, title, description)
    )
    conn.commit()
    notebook_id = cursor.lastrowid
    conn.close()
    return notebook_id

def get_user_notebooks(user_id: int):
    """Get all notebooks for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, title, description, created_at, updated_at FROM notebooks WHERE user_id = ?",
        (user_id,)
    )
    notebooks = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": notebook[0],
            "title": notebook[1],
            "description": notebook[2],
            "created_at": notebook[3],
            "updated_at": notebook[4]
        }
        for notebook in notebooks
    ]

def add_chat_message(notebook_id: int, user_id: int, message: str, response: str = None):
    """Add a chat message to a notebook"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO chat_messages (notebook_id, user_id, message, response) VALUES (?, ?, ?, ?)",
        (notebook_id, user_id, message, response)
    )
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    return message_id

def get_chat_messages(notebook_id: int, user_id: int):
    """Get all chat messages for a notebook (ensuring user owns the notebook)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # First verify the user owns this notebook
    cursor.execute(
        "SELECT id FROM notebooks WHERE id = ? AND user_id = ?",
        (notebook_id, user_id)
    )
    if not cursor.fetchone():
        conn.close()
        return []
    
    # Get the messages
    cursor.execute(
        "SELECT id, message, response, created_at FROM chat_messages WHERE notebook_id = ? ORDER BY created_at",
        (notebook_id,)
    )
    messages = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": message[0],
            "message": message[1],
            "response": message[2],
            "created_at": message[3]
        }
        for message in messages
    ]

# Initialize the database when the module is imported
init_database()
