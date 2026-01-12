# app/feedback.py
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .db import db, safe_commit
from .models import Athlete, Feedback
from .utils import crumbs, clamp_int, staff_required

bp = Blueprint("feedback", __name__)


@bp.get("/")
def feedback_home():
    """
    Страница обращений/заметок.
    - Для гостей: можно оставить обращение (kind=request)
    - Для сотрудников (admin/doctor/coach/operator): видно список + фильтры
    """
    bc = crumbs(("Главная", url_for("routes.index")), ("Обращения и заметки", ""))

    athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()

    # Фильтры (для просмотра списка)
    athlete_id = request.args.get("athlete_id", type=int)
    kind = (request.args.get("kind") or "").strip() or None   # note/request/incident
    status = (request.args.get("status") or "").strip() or None  # open/closed
    q = (request.args.get("q") or "").strip()

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=15, min_value=5, max_value=100)

    items = []
    total = 0
    pages = 1

    # список показываем только персоналу (чтобы не светить внутренние заметки всем)
    is_staff = bool(
        current_user.is_authenticated
        and getattr(current_user, "has_role", lambda *_: False)("admin", "doctor", "coach", "operator")
    )

    if is_staff:
        query = Feedback.query.order_by(Feedback.created_at.desc())

        if athlete_id:
            query = query.filter(Feedback.athlete_id == athlete_id)
        if kind:
            query = query.filter(Feedback.kind == kind)
        if status:
            query = query.filter(Feedback.status == status)
        if q:
            # простой поиск по заголовку/тексту
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
        "feedback.html",
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
    )


@bp.post("/")
def feedback_create():
    """
    Создание обращения/заметки.
    Гость может создать только kind=request (обращение).
    Персонал может создавать note/incident + привязку к спортсмену.
    """
    title = (request.form.get("title") or "").strip()
    message = (request.form.get("message") or "").strip()
    athlete_id = request.form.get("athlete_id", type=int)

    kind = (request.form.get("kind") or "request").strip()
    status = "open"

    if not title or not message:
        flash("Заполните тему и текст сообщения.", "warning")
        return redirect(url_for("feedback.feedback_home"))

    # Определяем, кто создаёт и что ему разрешено
    is_staff = bool(
        current_user.is_authenticated
        and getattr(current_user, "has_role", lambda *_: False)("admin", "doctor", "coach", "operator")
    )

    if not is_staff:
        # для гостей — только обращения и без обязательной привязки к спортсмену
        kind = "request"
        athlete_id = None

    athlete = None
    if athlete_id:
        athlete = Athlete.query.get(athlete_id)
        if not athlete:
            flash("Спортсмен не найден.", "danger")
            return redirect(url_for("feedback.feedback_home"))

    fb = Feedback(
        athlete=athlete,
        author=current_user if current_user.is_authenticated else None,
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
    bc = crumbs(("Главная", url_for("routes.index")), ("Обращения и заметки", url_for("feedback.feedback_home")), ("Готово", ""))
    return render_template("thanks.html", breadcrumbs=bc)


# ---- опционально: закрытие обращения (для персонала) ----
@bp.post("/<int:fb_id>/close")
@staff_required
def feedback_close(fb_id: int):
    fb = Feedback.query.get_or_404(fb_id)
    fb.status = "closed"
    fb.closed_at = datetime.utcnow()
    db.session.add(fb)
    safe_commit()
    flash("Обращение закрыто.", "info")
    return redirect(url_for("feedback.feedback_home"))
