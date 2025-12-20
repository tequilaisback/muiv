# app/db.py
from __future__ import annotations

import os
import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

# Единый объект БД, который импортируется в models.py
db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """
    Включаем поддержку FOREIGN KEY для SQLite.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


def init_db(app) -> None:
    """
    Инициализация SQLAlchemy и автосоздание БД/таблиц.
    База создастся автоматически при первом запуске.
    """
    # гарантируем, что папка instance существует (там будет app.sqlite)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    # Важно: импортируем модели, чтобы SQLAlchemy их "увидела" перед create_all()
    with app.app_context():
        from . import models  # noqa: F401

        db.create_all()
