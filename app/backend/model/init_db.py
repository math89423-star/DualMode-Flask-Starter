import sys
import os
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.config import Config


def create_database_if_not_exists() -> None:
    if Config.DEPLOY_MODE == 'desktop':
        print("[OK] Desktop mode: SQLite auto-creates, skipping.")
        return

    import mysql.connector
    print(f"[INFO] Checking / creating database: {Config.DB_NAME}...")

    max_retries = 20
    retry_interval = 3

    for attempt in range(1, max_retries + 1):
        try:
            conn = mysql.connector.connect(
                host=Config.DB_HOST,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                port=Config.DB_PORT,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci',
                connect_timeout=10
            )
            cursor = conn.cursor()
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {Config.DB_NAME} "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
            cursor.close()
            conn.close()
            print(f"[OK] Database {Config.DB_NAME} is ready.")
            return
        except Exception as e:
            if attempt < max_retries:
                print(f"[INFO] MySQL not ready, retrying ({attempt}/{max_retries})...")
                time.sleep(retry_interval)
            else:
                print(f"[ERROR] Failed to create database.")
                print(f"Detail: {str(e)}")
                sys.exit(1)


def init_database() -> None:
    print("=" * 50)
    print("Database initialization starting")
    print("=" * 50)

    create_database_if_not_exists()

    from backend import create_app
    from backend.extensions import db
    from backend.model import Item, Setting

    app = create_app()
    with app.app_context():
        print("[INFO] Creating tables...")
        try:
            db.create_all()
            print("[OK] Tables created successfully.")
        except Exception as e:
            print(f"[ERROR] Table creation failed: {str(e)}")
            sys.exit(1)

        print("=" * 50)
        print("Database initialization complete!")
        print("=" * 50)


if __name__ == '__main__':
    init_database()
