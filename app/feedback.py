# app/feedback.py
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .auth import staff_required
from .db import db, safe_commit
from .models import (
    ALERT_STATUS_CLOSED,
    ALERT_STATUS_OPEN,
    FEEDBACK_KIND_INCIDENT,
    FEEDBACK_KIND_NOTE,
    FEEDBACK_KIND_REQUEST,
    Athlete,
    Feedback,
)
from .utils import crumbs, clamp_int

bp = Blueprint("feedback", __name__)


def _is_staff_user() -> bool:
    return bool(
        getattr(current_user, "is_authenticated", False)
        and getattr(current_user, "is_active", True)
        and getattr(current_user, "has_role", lambda *_: False)("admin", "doctor", "coach", "operator")
    )


@bp.get("/")
def feedback_home():
    """
    Обращения/заметки.

    - Гость/обычный пользователь: только форма отправки (kind=request)
    - Staff: форма + список + фильтры + закрытие
    """
    bc = crumbs(("Главная", url_for("routes.index")), ("Обращения и заметки", ""))

    athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()
    is_staff = _is_staff_user()

    # фильтры списка (только staff)
    athlete_id = request.args.get("athlete_id", type=int)
    kind = (request.args.get("kind") or "").strip() or None
    status = (request.args.get("status") or "").strip() or None
    q = (request.args.get("q") or "").strip()

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=15, min_value=5, max_value=100)

    items = []
    total = 0
    pages = 1

    if is_staff:
        query = Feedback.query.order_by(Feedback.created_at.desc())

        if athlete_id:
            query = query.filter(Feedback.athlete_id == athlete_id)
        if kind:
            query = query.filter(Feedback.kind == kind)
        if status:
            query = query.filter(Feedback.status == status)
        if q:
            query = query.filter(
                db.or_(
                    Feedback.title.ilike(f"%{q}%"),
                    Feedback.message.ilike(f"%{q}%"),
                )
            )

        total = query.count()
        pages = (total + per_page - 1) // per_page if per_page else 1
        items = query.offset((page - 1) * per_page).limit(per_page).all()

    return render_template(
        "feedback.html",  # <-- актуальное имя по твоему скрину
        breadcrumbs=bc,
        athletes=athletes,
        is_staff=is_staff,
        items=items,
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "has_prev": page > 1,
            "has_next": page < pages,
            "prev_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if page < pages else None,
        },
        filters={
            "athlete_id": athlete_id,
            "kind": kind or "",
            "status": status or "",
            "q": q,
        },
        kinds=[FEEDBACK_KIND_REQUEST, FEEDBACK_KIND_NOTE, FEEDBACK_KIND_INCIDENT],
        statuses=[ALERT_STATUS_OPEN, ALERT_STATUS_CLOSED],
    )


@bp.post("/")
def feedback_create():
    """
    Создание feedback.

    - Гость/обычный пользователь: только request, без athlete
    - Staff: request/note/incident + (опционально) athlete
    """
    title = (request.form.get("title") or "").strip()
    message = (request.form.get("message") or "").strip()

    athlete_id = request.form.get("athlete_id", type=int)
    kind = (request.form.get("kind") or FEEDBACK_KIND_REQUEST).strip()
    status = ALERT_STATUS_OPEN

    if not title or not message:
        flash("Заполните тему и текст сообщения.", "warning")
        return redirect(url_for("feedback.feedback_home"))

    is_staff = _is_staff_user()

    # ограничения для гостя/обычного пользователя
    if not is_staff:
        kind = FEEDBACK_KIND_REQUEST
        athlete_id = None

    # страховка kind для staff
    if is_staff and kind not in (FEEDBACK_KIND_REQUEST, FEEDBACK_KIND_NOTE, FEEDBACK_KIND_INCIDENT):
        kind = FEEDBACK_KIND_NOTE

    athlete = None
    if athlete_id:
        athlete = Athlete.query.get(athlete_id)
        if not athlete:
            flash("Спортсмен не найден.", "danger")
            return redirect(url_for("feedback.feedback_home"))

    fb = Feedback(
        athlete=athlete,
        author=current_user if getattr(current_user, "is_authenticated", False) else None,
        kind=kind,
        status=status,
        title=title,
        message=message,
        created_at=datetime.utcnow(),
    )
    db.session.add(fb)
    safe_commit()

    flash("Сообщение сохранено.", "success")
    return redirect(url_for("feedback.thanks"))


@bp.get("/thanks")
def thanks():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Обращения и заметки", url_for("feedback.feedback_home")),
        ("Готово", ""),
    )
    return render_template("thanks.html", breadcrumbs=bc)  # <-- актуальное имя по твоему скрину


@bp.post("/<int:fb_id>/close")
@staff_required
def feedback_close(fb_id: int):
    fb = Feedback.query.get_or_404(fb_id)
    fb.status = ALERT_STATUS_CLOSED
    fb.closed_at = datetime.utcnow()
    db.session.add(fb)
    safe_commit()

    flash("Обращение закрыто.", "info")
    return redirect(url_for("feedback.feedback_home"))
