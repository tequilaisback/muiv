# config.py
import os


class Config:
    """
    Базовые настройки учебного Flask-приложения.

    Важно:
    - SECRET_KEY нужен для сессий и Flask-WTF (если будет).
    - SQLite хранится в папке instance/ (правильно для Flask).
    """

    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # instance/ — стандартное место для локальных файлов (БД и т.п.)
    INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
    os.makedirs(INSTANCE_DIR, exist_ok=True)

    DB_PATH = os.path.join(INSTANCE_DIR, "app.db")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-me"

    # UI/бренд
    APP_TITLE = os.environ.get("APP_TITLE") or "Мониторинг спортсменов"

    # Поведение
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    TESTING = os.environ.get("FLASK_TESTING", "0") == "1"

    # Опционально: максимальный размер запроса (если позже добавишь импорт файлов)
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
