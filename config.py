# config.py
import os


class Config:
    """
    Минимальная конфигурация для учебного проекта.
    """

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    # Если задан DATABASE_URL (например, для деплоя) — используем его.
    # Иначе базу задаём в create_app() в app/__init__.py (sqlite в instance/app.sqlite).
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
