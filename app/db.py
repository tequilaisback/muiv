# app/db.py
from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

# Единый объект БД на всё приложение
db = SQLAlchemy()


def init_db() -> None:
    """
    Создаёт все таблицы (для учебного проекта без миграций).
    Используется в create_app() или в seed/init логике.
    """
    db.create_all()


def reset_db() -> None:
    """
    Полный сброс БД: удаление и создание таблиц заново.
    ОСТОРОЖНО: удалит все данные.
    """
    db.drop_all()
    db.create_all()


def safe_commit() -> None:
    """
    Коммит с откатом при ошибке, чтобы не оставлять сессию "сломленной".
    """
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
