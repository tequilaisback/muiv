# app/cabinet.py
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .db import db, safe_commit
from .models import Athlete, Indicator, Feedback, Measurement, MeasureSource, SOURCE_CODE_MANUAL
from .auth import staff_required
from .utils import crumbs, parse_datetime, to_float

bp = Blueprint("cabinet", __name__)


@bp.get("/")
@login_required
def cabinet_home():
    """
    Личный кабинет:
    - мои последние внесённые измерения
    - мои обращения/заметки
    - (для staff) форма/модалка "внести измерение"
    """
    bc = crumbs(("Главная", url_for("routes.index")), ("Личный кабинет", ""))

    my_last = (
        Measurement.query
        .filter(Measurement.created_by_id == current_user.id)
        .order_by(Measurement.measured_at.desc())
        .limit(10)
        .all()
    )

    my_feedback = (
        Feedback.query
        .filter(Feedback.author_id == current_user.id)
        .order_by(Feedback.created_at.desc())
        .limit(10)
        .all()
    )

    is_staff = bool(getattr(current_user, "has_role", lambda *_: False)("admin", "doctor", "coach", "operator"))

    # Данные для модалки внесения (только staff)
    athletes = []
    indicators = []
    if is_staff:
        athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()
        indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()

    # можно дергать ?modal=measure чтобы авт-открывать модалку
    open_modal = (request.args.get("modal") == "measure")

    return render_template(
        "cabinet.html",
        breadcrumbs=bc,
        my_last_measurements=my_last,
        my_feedback=my_feedback,
        is_staff=is_staff,
        athletes=athletes,
        indicators=indicators,
        open_modal=open_modal,
        now_dt=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    )


@bp.post("/measurements/new")
@staff_required
def measurement_new_post():
    """
    Создание измерения из ЛК (staff-only).
    Ожидаемые поля формы:
    athlete_id, indicator_id, value, measured_at, comment
    """
    athlete_id = request.form.get("athlete_id", type=int)
    indicator_id = request.form.get("indicator_id", type=int)
    value = to_float(request.form.get("value"))
    measured_at = parse_datetime(request.form.get("measured_at")) or datetime.utcnow()
    comment = (request.form.get("comment") or "").strip() or None

    if not athlete_id or not indicator_id or value is None:
        flash("Заполните спортсмена, показатель и значение.", "warning")
        return redirect(url_for("cabinet.cabinet_home", modal="measure"))

    athlete = Athlete.query.get(athlete_id)
    indicator = Indicator.query.get(indicator_id)
    if not athlete or not indicator:
        flash("Спортсмен или показатель не найден.", "danger")
        return redirect(url_for("cabinet.cabinet_home", modal="measure"))

    # источник manual из справочника
    src = MeasureSource.query.filter_by(code=SOURCE_CODE_MANUAL).first()

    m = Measurement(
        athlete=athlete,
        indicator=indicator,
        value=value,
        measured_at=measured_at,
        source=src,
        created_by=current_user,
        comment=comment,
    )
    db.session.add(m)
    safe_commit()

    flash("Измерение добавлено.", "success")

    # После сохранения логично вести на карточку спортсмена.
    # Если у тебя эндпоинт называется иначе — поменяешь одну строку.
    try:
        return redirect(url_for("routes.product", athlete_id=athlete.id))
    except Exception:
        return redirect(url_for("cabinet.cabinet_home"))
