# app/utils.py
from __future__ import annotations

from functools import wraps
from typing import Callable, Iterable

from flask import flash, redirect, request, session, url_for

from .db import db
from .models import User


# -----------------------------
# Auth helpers
# -----------------------------
def current_user() -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


def login_required(view: Callable):
    """
    Декоратор: требует авторизацию.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user.is_active:
            flash("Войдите в систему.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def role_required(*roles: str):
    """
    Декоратор: требует одну из ролей.
    Пример: @role_required("admin", "manager")
    """
    roles_set = set([r.strip().lower() for r in roles if r])

    def decorator(view: Callable):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user or not user.is_active:
                flash("Войдите в систему.", "warning")
                return redirect(url_for("auth.login", next=request.path))
            if roles_set and (user.role or "").lower() not in roles_set:
                flash("Недостаточно прав доступа.", "danger")
                return redirect(url_for("main.index"))
            return view(*args, **kwargs)

        return wrapper

    return decorator


# -----------------------------
# Breadcrumbs helpers
# -----------------------------
def crumbs(*items: tuple[str, str | None]):
    """
    items: (title, url) где url может быть None для текущей страницы.
    Возвращает список словарей для шаблона _breadcrumbs.html
    """
    return [{"title": t, "url": u} for (t, u) in items]


def default_menu_items() -> list[dict]:
    """
    10+ пунктов меню (для проверки требований).
    Шаблон _nav.html может использовать этот список.

    url_name — имя endpoint'а (url_for(url_name)).
    """
    return [
        {"title": "Главная", "url_name": "main.index"},
        {"title": "О проекте", "url_name": "main.about"},
        {"title": "Контакты", "url_name": "main.contacts"},
        {"title": "Каталог", "url_name": "main.catalog"},
        {"title": "Категории", "url_name": "main.categories"},
        {"title": "Акции", "url_name": "main.offers"},
        {"title": "Поиск", "url_name": "main.search"},
        {"title": "Обратная связь", "url_name": "feedback.form"},
        {"title": "Личный кабинет", "url_name": "cabinet.dashboard"},
        {"title": "Админка", "url_name": "admin.dashboard"},
    ]
