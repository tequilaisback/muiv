# app/cabinet.py
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, render_template, url_for, request, flash, redirect
from flask_login import login_required, current_user

from .db import db, safe_commit
from .models import Athlete, Indicator, Measurement, Feedback, MEASURE_SOURCE_MANUAL
from .utils import crumbs, parse_datetime, to_float, staff_required

bp = Blueprint("cabinet", __name__)


@bp.get("/")
@login_required
def cabinet_home():
    """
    Личный кабинет: короткая сводка для текущего пользователя.
    """
    bc = crumbs(("Главная", url_for("routes.index")), ("Личный кабинет", ""))

    # последние измерения, которые внёс пользователь
    my_last = (
        Measurement.query
        .filter(Measurement.created_by_id == current_user.id)
        .order_by(Measurement.measured_at.desc())
        .limit(10)
        .all()
        if getattr(current_user, "id", None)
        else []
    )

    # последние заметки/обращения, созданные пользователем
    my_feedback = (
        Feedback.query
        .filter(Feedback.author_id == current_user.id)
        .order_by(Feedback.created_at.desc())
        .limit(10)
        .all()
        if getattr(current_user, "id", None)
        else []
    )

    return render_template(
        "cabinet.html",
        breadcrumbs=bc,
        my_last_measurements=my_last,
        my_feedback=my_feedback,
    )


@bp.get("/profile")
@login_required
def cabinet_profile():
    """
    Профиль пользователя (пока только просмотр).
    """
    bc = crumbs(("Главная", url_for("routes.index")), ("Личный кабинет", url_for("cabinet.cabinet_home")), ("Профиль", ""))
    return render_template("cabinet_profile.html", breadcrumbs=bc, user=current_user)


@bp.get("/measurements/new")
@staff_required
def measurement_new():
    """
    Быстрое внесение измерения (внутри личного кабинета).
    Доступ: staff_required (admin/doctor/coach/operator).
    """
    athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()

    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Личный кабинет", url_for("cabinet.cabinet_home")),
        ("Внести измерение", ""),
    )

    return render_template(
        "cabinet_measurement_new.html",
        breadcrumbs=bc,
        athletes=athletes,
        indicators=indicators,
    )


@bp.post("/measurements/new")
@staff_required
def measurement_new_post():
    athlete_id = request.form.get("athlete_id", type=int)
    indicator_id = request.form.get("indicator_id", type=int)
    value = to_float(request.form.get("value"))
    measured_at = parse_datetime(request.form.get("measured_at")) or datetime.utcnow()
    comment = (request.form.get("comment") or "").strip() or None

    if not athlete_id or not indicator_id or value is None:
        flash("Заполните спортсмена, показатель и значение.", "warning")
        return redirect(url_for("cabinet.measurement_new"))

    athlete = Athlete.query.get(athlete_id)
    indicator = Indicator.query.get(indicator_id)
    if not athlete or not indicator:
        flash("Спортсмен или показатель не найден.", "danger")
        return redirect(url_for("cabinet.measurement_new"))

    m = Measurement(
        athlete=athlete,
        indicator=indicator,
        value=value,
        measured_at=measured_at,
        source=MEASURE_SOURCE_MANUAL,
        created_by=current_user,
        comment=comment,
    )
    db.session.add(m)
    safe_commit()

    flash("Измерение добавлено.", "success")
    return redirect(url_for("routes.product", athlete_id=athlete.id))
