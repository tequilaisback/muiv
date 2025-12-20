# app/auth.py
from __future__ import annotations

from urllib.parse import urlparse, urljoin

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .db import db
from .models import User, ROLE_USER

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# -----------------------------
# Helpers
# -----------------------------
def _crumbs(*items: tuple[str, str | None]):
    return [{"title": t, "url": u} for (t, u) in items]


def _is_safe_url(target: str) -> bool:
    """
    Защита от open-redirect: разрешаем редирект только внутри текущего хоста.
    """
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def login_user(user: User) -> None:
    session["user_id"] = user.id


def logout_user() -> None:
    session.pop("user_id", None)


def current_user() -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


# -----------------------------
# Routes
# -----------------------------
@auth_bp.get("/login")
def login():
    nxt = (request.args.get("next") or "").strip()
    if nxt and not _is_safe_url(nxt):
        nxt = ""

    return render_template(
        "login.html",
        next=nxt,
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Вход", None)),
        current_user=current_user(),
    )


@auth_bp.post("/login")
def login_post():
    login_val = (request.form.get("login") or "").strip()
    password = request.form.get("password") or ""
    nxt = (request.form.get("next") or "").strip()

    if nxt and not _is_safe_url(nxt):
        nxt = ""

    if not login_val or not password:
        flash("Введите логин и пароль.", "warning")
        return redirect(url_for("auth.login", next=nxt) if nxt else url_for("auth.login"))

    user = db.session.query(User).filter_by(login=login_val).first()
    if not user or not user.check_password(password):
        flash("Неверный логин или пароль.", "danger")
        return redirect(url_for("auth.login", next=nxt) if nxt else url_for("auth.login"))

    if not user.is_active:
        flash("Ваш аккаунт отключён. Обратитесь к администратору.", "warning")
        return redirect(url_for("auth.login"))

    login_user(user)
    flash("Вы вошли в систему.", "success")

    if nxt:
        return redirect(nxt)

    # если есть ЛК — туда, иначе на главную
    try:
        return redirect(url_for("cabinet.dashboard"))
    except Exception:
        return redirect(url_for("main.index"))


@auth_bp.get("/register")
def register():
    return render_template(
        "register.html",
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Регистрация", None)),
        current_user=current_user(),
    )


@auth_bp.post("/register")
def register_post():
    login_val = (request.form.get("login") or "").strip()
    full_name = (request.form.get("full_name") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    if not login_val or not full_name or not password:
        flash("Заполните логин, ФИО и пароль.", "warning")
        return redirect(url_for("auth.register"))

    if password != password2:
        flash("Пароли не совпадают.", "warning")
        return redirect(url_for("auth.register"))

    exists = db.session.query(User).filter_by(login=login_val).first()
    if exists:
        flash("Пользователь с таким логином уже существует.", "danger")
        return redirect(url_for("auth.register"))

    user = User(login=login_val, full_name=full_name, role=ROLE_USER, is_active=True)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    flash("Регистрация успешна. Теперь войдите.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.get("/logout")
def logout():
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("main.index"))
