# database.py
import sqlite3
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_file='bot_sessions.db'):
        self.db_file = db_file
        self.init_db()
    
    def init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # ✅ Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                telegram_id TEXT PRIMARY KEY,
                user_id TEXT,
                token TEXT,
                user_data TEXT,
                phone TEXT,
                tg_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ✅ User languages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_languages (
                telegram_id TEXT PRIMARY KEY,
                language TEXT DEFAULT 'en',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    
    def save_session(self, telegram_id, session_data):
        """Save or update user session"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO sessions 
            (telegram_id, user_id, token, user_data, phone, tg_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            telegram_id,
            session_data.get('user_id'),
            session_data.get('token'),
            json.dumps(session_data.get('user_data', {})),
            session_data.get('phone'),
            session_data.get('tg_id')
        ))
        
        conn.commit()
        conn.close()
        logger.debug(f"✅ Session saved for {telegram_id}")
    
    def get_session(self, telegram_id):
        """Get user session"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM sessions WHERE telegram_id = ?', (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'telegram_id': row[0],
                'user_id': row[1],
                'token': row[2],
                'user_data': json.loads(row[3]) if row[3] else {},
                'phone': row[4],
                'tg_id': row[5],
                'created_at': row[6],
                'updated_at': row[7]
            }
        return None
    
    def delete_session(self, telegram_id):
        """Delete user session"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE telegram_id = ?', (telegram_id,))
        conn.commit()
        conn.close()
        logger.debug(f"🗑️ Session deleted for {telegram_id}")
    
    def get_all_sessions(self):
        """Get all sessions (for debugging)"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id, user_id, phone, tg_id FROM sessions')
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    def save_language(self, telegram_id, language):
        """Save user language preference"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_languages (telegram_id, language, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (telegram_id, language))
        
        conn.commit()
        conn.close()
        logger.debug(f"🌐 Language saved for {telegram_id}: {language}")
    
    def get_language(self, telegram_id):
        """Get user language preference"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT language FROM user_languages WHERE telegram_id = ?', (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else 'en'
    
    # database.py - Add this method

    def get_all_languages(self):
        """Get all language preferences"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id, language FROM user_languages')
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    
    def close(self):
        """Close database connection"""
        # SQLite doesn't need explicit close
        pass

# ✅ Global database instance
db = Database()