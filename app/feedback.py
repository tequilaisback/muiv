# app/feedback.py
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .db import db
from .models import Feedback, User

feedback_bp = Blueprint("feedback", __name__, url_prefix="/feedback")


def _crumbs(*items: tuple[str, str | None]):
    return [{"title": t, "url": u} for (t, u) in items]


def _current_user() -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


@feedback_bp.get("/")
def form():
    return render_template(
        "feedback.html",
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Обратная связь", None)),
        current_user=_current_user(),
    )


@feedback_bp.post("/")
def form_post():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    subject = (request.form.get("subject") or "").strip()
    message = (request.form.get("message") or "").strip()

    if not name or not email or not subject or not message:
        flash("Заполните все поля формы.", "warning")
        return redirect(url_for("feedback.form"))

    user = _current_user()
    fb = Feedback(
        user_id=user.id if user else None,
        name=name,
        email=email,
        subject=subject,
        message=message,
        status="new",
    )
    db.session.add(fb)
    db.session.commit()

    return redirect(url_for("feedback.thanks"))


@feedback_bp.get("/thanks")
def thanks():
    return render_template(
        "thanks.html",
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Спасибо", None)),
        current_user=_current_user(),
    )
