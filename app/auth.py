# app/auth.py
from __future__ import annotations

from datetime import datetime
from functools import wraps
from typing import Callable, Iterable

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from .db import db, safe_commit
from .models import (
    User,
    ROLE_ADMIN,
    ROLE_COACH,
    ROLE_DOCTOR,
    ROLE_OPERATOR,
    ROLE_USER,
)
from .utils import redirect_next

bp = Blueprint("auth", __name__)


# -------------------------
# Декораторы доступа по ролям
# -------------------------
def roles_required(*roles: str) -> Callable:
    """
    Пропускает только авторизованных пользователей с одной из ролей.
    Иначе -> 403.

    Пример:
        @roles_required(ROLE_ADMIN, ROLE_DOCTOR)
        def view(): ...
    """
    allowed = set(roles)

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                # login_required редиректит на login, но этот декоратор может использоваться без него
                return redirect(url_for("auth.login", next=request.full_path))
            if not getattr(current_user, "is_active", True):
                abort(403)
            if not getattr(current_user, "has_role", None) or not current_user.has_role(*allowed):
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def staff_required(fn: Callable) -> Callable:
    """
    Staff = admin/doctor/coach/operator.
    Удобно для админки/журнала/внесения измерений.
    """
    return roles_required(ROLE_ADMIN, ROLE_DOCTOR, ROLE_COACH, ROLE_OPERATOR)(fn)


# -------------------------
# Auth: login/logout/register
# -------------------------
@bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("routes.index"))

    next_url = request.args.get("next", "")
    return render_template("login.html", next=next_url)


@bp.post("/login")
def login_post():
    if current_user.is_authenticated:
        return redirect(url_for("routes.index"))

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    remember = bool(request.form.get("remember"))

    if not username or not password:
        flash("Введите логин и пароль.", "warning")
        return render_template("login.html", next=request.form.get("next", "")), 400

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        flash("Неверный логин или пароль.", "danger")
        return render_template("login.html", next=request.form.get("next", "")), 401

    if not user.is_active:
        flash("Учетная запись отключена. Обратитесь к администратору.", "danger")
        return render_template("login.html", next=request.form.get("next", "")), 403

    login_user(user, remember=remember)

    user.last_login_at = datetime.utcnow()
    db.session.add(user)
    safe_commit()

    flash("Вы вошли в систему.", "success")
    return redirect_next("routes.index")


@bp.post("/logout")
@login_required
def logout_post():
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("routes.index"))


# Оставим GET для совместимости (если где-то уже стоит ссылка)
@bp.get("/logout")
@login_required
def logout():
    return logout_post()


@bp.get("/register")
def register():
    """
    Регистрация (учебный проект):
    - можно оставить открытой,
    - либо позже ограничить только администратору.
    """
    if current_user.is_authenticated:
        return redirect(url_for("routes.index"))

    next_url = request.args.get("next", "")
    return render_template("register.html", next=next_url)


@bp.post("/register")
def register_post():
    if current_user.is_authenticated:
        return redirect(url_for("routes.index"))

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip() or None
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    # минимальная валидация
    if len(username) < 3:
        flash("Логин должен быть не короче 3 символов.", "warning")
        return render_template("register.html", next=request.form.get("next", "")), 400
    if len(password) < 6:
        flash("Пароль должен быть не короче 6 символов.", "warning")
        return render_template("register.html", next=request.form.get("next", "")), 400
    if password != password2:
        flash("Пароли не совпадают.", "warning")
        return render_template("register.html", next=request.form.get("next", "")), 400

    if User.query.filter_by(username=username).first():
        flash("Такой логин уже занят.", "danger")
        return render_template("register.html", next=request.form.get("next", "")), 409

    if email and User.query.filter_by(email=email).first():
        flash("Этот email уже используется.", "danger")
        return render_template("register.html", next=request.form.get("next", "")), 409

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role=ROLE_USER,
        is_active=True,
    )
    db.session.add(user)
    safe_commit()

    login_user(user)
    flash("Регистрация успешна. Добро пожаловать!", "success")
    return redirect_next("routes.index")
