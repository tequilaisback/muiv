# app/cabinet.py
from __future__ import annotations

from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .db import db
from .models import User, ROLE_ADMIN, ROLE_MANAGER

cabinet_bp = Blueprint("cabinet", __name__, url_prefix="/cabinet")


# -------------------------------------------------------------------
# Минимальные auth-хелперы (чтобы работало без utils.py)
# -------------------------------------------------------------------
def get_current_user() -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or not user.is_active:
            flash("Войдите в систему.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


# -------------------------------------------------------------------
# Breadcrumbs helper
# -------------------------------------------------------------------
def _crumbs(*items: tuple[str, str | None]):
    return [{"title": t, "url": u} for (t, u) in items]


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@cabinet_bp.get("/")
@login_required
def dashboard():
    user = get_current_user()
    return render_template(
        "cabinet.html",
        section="dashboard",
        user=user,
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Личный кабинет", None)),
        current_user=user,
        role_label=_role_label(user.role if user else ""),
    )


@cabinet_bp.get("/profile")
@login_required
def profile():
    user = get_current_user()
    return render_template(
        "cabinet.html",
        section="profile",
        user=user,
        breadcrumbs=_crumbs(
            ("Главная", url_for("main.index")),
            ("Личный кабинет", url_for("cabinet.dashboard")),
            ("Профиль", None),
        ),
        current_user=user,
        role_label=_role_label(user.role if user else ""),
    )


@cabinet_bp.post("/profile")
@login_required
def profile_post():
    user = get_current_user()
    if not user:
        flash("Войдите в систему.", "warning")
        return redirect(url_for("auth.login"))

    full_name = (request.form.get("full_name") or "").strip()
    new_password = (request.form.get("new_password") or "").strip()
    new_password2 = (request.form.get("new_password2") or "").strip()

    if full_name:
        user.full_name = full_name

    if new_password:
        if new_password != new_password2:
            flash("Пароли не совпадают.", "warning")
            return redirect(url_for("cabinet.profile"))
        user.set_password(new_password)

    db.session.commit()
    flash("Профиль обновлён.", "success")
    return redirect(url_for("cabinet.profile"))


def _role_label(role: str) -> str:
    role = (role or "").strip().lower()
    if role == ROLE_ADMIN:
        return "Администратор"
    if role == ROLE_MANAGER:
        return "Менеджер"
    return "Пользователь"
