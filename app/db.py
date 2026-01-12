# app/db.py
from __future__ import annotations

from typing import Any, Optional

from flask import current_app
from flask_sqlalchemy import SQLAlchemy

# Единый объект БД на всё приложение
db = SQLAlchemy()


def init_db() -> None:
    """
    Создаёт все таблицы (для учебного проекта без миграций).

    ВАЖНО: вызывать внутри app.app_context().
    Обычно делается в create_app() после регистрации моделей/blueprints.
    """
    db.create_all()


def reset_db() -> None:
    """
    Полный сброс БД: удаление и создание таблиц заново.
    ОСТОРОЖНО: удалит все данные.

    ВАЖНО: вызывать внутри app.app_context().
    """
    db.drop_all()
    db.create_all()


def safe_commit(*, log: bool = True) -> None:
    """
    Коммит с откатом при ошибке, чтобы не оставлять сессию "сломленной".

    log=True: пишет ошибку в current_app.logger (если есть контекст Flask).
    """
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if log:
            try:
                current_app.logger.exception("DB commit failed: %s", exc)
            except Exception:
                # если нет app_context или логгер недоступен
                pass
        raise


def safe_add(obj: Any, *, commit: bool = True) -> None:
    """Добавить объект в сессию и (опционально) закоммитить безопасно."""
    db.session.add(obj)
    if commit:
        safe_commit()


def safe_add_all(items: list[Any], *, commit: bool = True) -> None:
    """Добавить список объектов в сессию и (опционально) закоммитить безопасно."""
    db.session.add_all(items)
    if commit:
        safe_commit()


def safe_delete(obj: Any, *, commit: bool = True) -> None:
    """Удалить объект и (опционально) закоммитить безопасно."""
    db.session.delete(obj)
    if commit:
        safe_commit()


def safe_rollback() -> None:
    """Явный откат транзакции."""
    db.session.rollback()


def get_or_404(model: Any, pk: Any, *, description: str = "Not found") -> Any:
    """
    Утилита: получить запись по PK или выбросить 404.
    Удобно использовать в роутинге.

    Пример:
      user = get_or_404(User, user_id)
    """
    obj = db.session.get(model, pk)
    if obj is None:
        # импорт внутри, чтобы не тянуть flask везде, где используется db.py
        from flask import abort

        abort(404, description=description)
    return obj


def try_parse_int(value: Optional[str]) -> Optional[int]:
    """Мелкий helper под query params (иногда удобно держать рядом)."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
