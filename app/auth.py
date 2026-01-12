# app/auth.py
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from .db import db, safe_commit
from .models import User, ROLE_USER
from .utils import redirect_next

bp = Blueprint("auth", __name__)


@bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("routes.index"))

    # next можно прокинуть в форме скрытым input
    next_url = request.args.get("next", "")
    return render_template("login.html", next=next_url)


@bp.post("/login")
def login_post():
    if current_user.is_authenticated:
        return redirect(url_for("routes.index"))

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not username or not password:
        flash("Введите логин и пароль.", "warning")
        return render_template("login.html", next=request.form.get("next", "")), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        flash("Неверный логин или пароль.", "danger")
        return render_template("login.html", next=request.form.get("next", "")), 401

    if not user.is_active:
        flash("Учетная запись отключена. Обратитесь к администратору.", "danger")
        return render_template("login.html", next=request.form.get("next", "")), 403

    if not check_password_hash(user.password_hash, password):
        flash("Неверный логин или пароль.", "danger")
        return render_template("login.html", next=request.form.get("next", "")), 401

    login_user(user)
    user.last_login_at = datetime.utcnow()
    db.session.add(user)
    safe_commit()

    flash("Вы вошли в систему.", "success")
    return redirect_next("routes.index")


@bp.get("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("routes.index"))


@bp.get("/register")
def register():
    """
    Регистрация можно оставить открытой (учебный проект),
    либо потом ограничить (например только админу).
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
