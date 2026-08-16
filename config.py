import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    API_URL = os.getenv('API_URL', 'http://localhost:5000/api')
    ADMIN_TELEGRAM_ID = os.getenv('ADMIN_TELEGRAM_ID')
    
    # Wallet settings (matching your backend)
    MIN_WITHDRAWAL = 100
    MAX_DEPOSIT = 10000
    WELCOME_BONUS = 50

config = Config()