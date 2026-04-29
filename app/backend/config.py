import os
import sys
from dotenv import load_dotenv
from backend.paths import get_dotenv_path, get_data_dir

load_dotenv(dotenv_path=get_dotenv_path())


def _resolve_deploy_mode() -> str:
    mode = os.environ.get('DEPLOY_MODE', 'auto').lower()
    if mode == 'auto':
        return 'desktop' if sys.platform == 'win32' else 'server'
    return mode


class Config:
    DEPLOY_MODE = _resolve_deploy_mode()

    APP_HOST = os.environ.get('APP_HOST', '127.0.0.1' if DEPLOY_MODE == 'desktop' else '0.0.0.0')
    APP_PORT = int(os.environ.get('APP_PORT', 5000))

    if DEPLOY_MODE == 'desktop':
        _db_dir = get_data_dir()
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(_db_dir, 'app.db')}"
        SQLALCHEMY_ENGINE_OPTIONS = {}
    else:
        DB_USER = os.environ.get('DB_USER', 'root')
        DB_PASSWORD = os.environ.get('DB_PASSWORD', 'admin')
        DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
        DB_PORT = os.environ.get('DB_PORT', '3306')
        DB_NAME = os.environ.get('DB_NAME', 'dualmode_starter')
        SQLALCHEMY_DATABASE_URI = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_size": 16,
            "max_overflow": 24,
            "pool_recycle": 1800,
            "pool_pre_ping": True,
            "pool_timeout": 30,
            "connect_args": {"charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"}
        }

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', 8))

    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '123456')


class WorkerConfig:
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', 8))
    RETRY_TIMES = int(os.environ.get('RETRY_TIMES', 3))
    RETRY_DELAY_BASE = int(os.environ.get('RETRY_DELAY_BASE', 2))


class RedisKeyManager:
    @staticmethod
    def task_key(task_id: int) -> str:
        return f"task:{task_id}"

    @staticmethod
    def cancel_key(task_id: int) -> str:
        return f"cancel:task:{task_id}"

    @staticmethod
    def stream_channel(task_id: int) -> str:
        return f"stream:task:{task_id}"
