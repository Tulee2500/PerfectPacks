import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    DEBUG = os.getenv('DEBUG', 'True') == 'True'
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 3333))

    # Scraper
    CHROME_HEADLESS = os.getenv('CHROME_HEADLESS', 'False') == 'True'
    WAIT_TIMEOUT = int(os.getenv('WAIT_TIMEOUT', 20))

    # Paths
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, 'data', 'results')
    LOG_DIR = os.path.join(BASE_DIR, 'logs')

    @staticmethod
    def init_app():
        """Khởi tạo các thư mục cần thiết"""
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        os.makedirs(Config.LOG_DIR, exist_ok=True)