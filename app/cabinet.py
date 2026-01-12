# app/cabinet.py
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .db import db, safe_commit
from .models import (
    ALERT_LEVEL_HIGH,
    ALERT_LEVEL_LOW,
    ALERT_STATUS_OPEN,
    Alert,
    Athlete,
    Feedback,
    Indicator,
    Measurement,
    MeasureSource,
    Team,
    User,
    ROLE_ADMIN,
    ROLE_COACH,
    ROLE_DOCTOR,
    ROLE_OPERATOR,
    ROLE_USER,
    SOURCE_CODE_MANUAL,
)
from .auth import roles_required
from .permissions import get_coach_team_ids, get_coach_teams, is_coach, is_staff, is_user
from .utils import crumbs, is_out_of_range_value, parse_datetime, to_float

bp = Blueprint("cabinet", __name__)


@bp.get("/")
@login_required
def cabinet_home():
    """
    Личный кабинет: краткая карточка профиля.
    """
    bc = crumbs(("Главная", url_for("routes.index")), ("Личный кабинет", ""))

    role_labels = {
        ROLE_ADMIN: "Администратор",
        ROLE_DOCTOR: "Врач",
        ROLE_COACH: "Тренер",
        ROLE_OPERATOR: "Оператор",
        ROLE_USER: "Спортсмен",
    }
    role_title = role_labels.get(getattr(current_user, "role", None), "—")

    team_label = None
    athlete_profile = getattr(current_user, "athlete", None)
    if athlete_profile and athlete_profile.team:
        team_label = athlete_profile.team.name
    elif is_coach(current_user):
        coach_teams = get_coach_teams(current_user)
        if coach_teams:
            team_label = coach_teams[0].name

    return render_template(
        "cabinet.html",
        breadcrumbs=bc,
        athlete_profile=athlete_profile,
        role_title=role_title,
        team_label=team_label,
    )


@bp.post("/measurements/new")
@roles_required(ROLE_ADMIN, ROLE_COACH, ROLE_OPERATOR)
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

    if is_coach(current_user):
        team_ids = get_coach_team_ids(current_user)
        if team_ids and athlete.team_id not in team_ids:
            abort(403)

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

    try:
        out, nmin, nmax, _personal = is_out_of_range_value(athlete.id, indicator.id, value)
        if out:
            level = ALERT_LEVEL_HIGH
            if nmin is not None and value < float(nmin):
                level = ALERT_LEVEL_LOW
            elif nmax is not None and value > float(nmax):
                level = ALERT_LEVEL_HIGH
            alert = Alert(measurement=m, level=level, status=ALERT_STATUS_OPEN)
            db.session.add(alert)
    except Exception:
        pass

    safe_commit()

    flash("Измерение добавлено.", "success")

    # После сохранения логично вести на карточку спортсмена.
    # Если у тебя эндпоинт называется иначе — поменяешь одну строку.
    try:
        return redirect(url_for("routes.product", athlete_id=athlete.id))
    except Exception:
        return redirect(url_for("cabinet.cabinet_home"))


@bp.post("/team/create")
@roles_required(ROLE_COACH)
def team_create():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Укажите название команды.", "warning")
        return redirect(url_for("cabinet.cabinet_home"))

    if Team.query.filter_by(name=name).first():
        flash("Команда с таким названием уже существует.", "danger")
        return redirect(url_for("cabinet.cabinet_home"))

    existing = Team.query.filter_by(coach_id=current_user.id).first()
    if existing:
        flash("У вас уже есть команда. Добавляйте спортсменов в неё.", "warning")
        return redirect(url_for("cabinet.cabinet_home"))

    team = Team(name=name, coach=current_user, is_active=True)
    db.session.add(team)
    safe_commit()
    flash("Команда создана.", "success")
    return redirect(url_for("cabinet.cabinet_home"))


@bp.post("/team/add")
@roles_required(ROLE_COACH)
def team_add_user():
    user_id = request.form.get("user_id", type=int)
    full_name = (request.form.get("full_name") or "").strip()

    team = Team.query.filter_by(coach_id=current_user.id).first()
    if not team:
        flash("Сначала создайте команду.", "warning")
        return redirect(url_for("cabinet.cabinet_home"))

    user = User.query.get(user_id) if user_id else None
    if not user or user.role != ROLE_USER:
        flash("Выберите пользователя-спортсмена.", "warning")
        return redirect(url_for("cabinet.cabinet_home"))

    athlete = Athlete.query.filter_by(user_id=user.id).first()
    if not athlete:
        name = full_name or user.username
        athlete = Athlete(full_name=name, user=user, team=team, is_active=True)
        db.session.add(athlete)
    else:
        athlete.team = team
        db.session.add(athlete)

    safe_commit()
    flash("Спортсмен добавлен в команду.", "success")
    return redirect(url_for("cabinet.cabinet_home"))


@bp.post("/team/remove")
@roles_required(ROLE_COACH)
def team_remove_user():
    user_id = request.form.get("user_id", type=int)
    team = Team.query.filter_by(coach_id=current_user.id).first()
    if not team:
        flash("Команда не найдена.", "warning")
        return redirect(url_for("cabinet.cabinet_home"))

    user = User.query.get(user_id) if user_id else None
    athlete = Athlete.query.filter_by(user_id=user.id).first() if user else None
    if not athlete or athlete.team_id != team.id:
        flash("Спортсмен не найден в вашей команде.", "warning")
        return redirect(url_for("cabinet.cabinet_home"))

    athlete.team = None
    db.session.add(athlete)
    safe_commit()
    flash("Спортсмен удалён из команды.", "info")
    return redirect(url_for("cabinet.cabinet_home"))
