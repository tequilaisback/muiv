# app/cabinet.py
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .db import db, safe_commit
from .models import Athlete, Feedback, Indicator, Measurement, MeasureSource, Team, User, ROLE_ADMIN, ROLE_COACH, ROLE_DOCTOR, ROLE_OPERATOR, ROLE_USER, SOURCE_CODE_MANUAL
from .auth import roles_required
from .permissions import get_coach_team_ids, get_coach_teams, is_coach, is_staff, is_user
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

    my_last = []
    athlete_profile = None
    doctor_recommendations = []
    is_staff = is_staff(current_user)
    is_user_role = is_user(current_user)
    is_coach_role = is_coach(current_user)

    if is_user_role:
        athlete_profile = getattr(current_user, "athlete", None)
        if athlete_profile:
            my_last = (
                Measurement.query
                .filter(Measurement.athlete_id == athlete_profile.id)
                .order_by(Measurement.measured_at.desc())
                .limit(10)
                .all()
            )

            doctor_recommendations = (
                Feedback.query
                .join(Feedback.author)
                .filter(Feedback.athlete_id == athlete_profile.id)
                .filter(User.role == ROLE_DOCTOR)
                .order_by(Feedback.created_at.desc())
                .limit(10)
                .all()
            )
    else:
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

    # Данные для модалки внесения (только staff)
    athletes = []
    indicators = []
    if is_staff:
        athletes_query = Athlete.query.filter_by(is_active=True)
        if is_coach_role:
            team_ids = get_coach_team_ids(current_user)
            if team_ids:
                athletes_query = athletes_query.filter(Athlete.team_id.in_(team_ids))
        athletes = athletes_query.order_by(Athlete.full_name.asc()).all()
        indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()

    # можно дергать ?modal=measure чтобы авт-открывать модалку
    open_modal = (request.args.get("modal") == "measure")

    coach_team = None
    team_members = []
    users_pool = []
    if is_coach_role:
        coach_teams = get_coach_teams(current_user)
        coach_team = coach_teams[0] if coach_teams else None
        if coach_team:
            team_members = (
                User.query
                .join(Athlete, Athlete.user_id == User.id)
                .filter(User.role == ROLE_USER, Athlete.team_id == coach_team.id)
                .order_by(User.username.asc())
                .all()
            )

        users_pool = User.query.filter(User.role == ROLE_USER).order_by(User.username.asc()).all()

    return render_template(
        "cabinet.html",
        breadcrumbs=bc,
        my_last_measurements=my_last,
        my_feedback=my_feedback,
        is_staff=is_staff,
        is_user=is_user_role,
        is_coach=is_coach_role,
        athlete_profile=athlete_profile,
        doctor_recommendations=doctor_recommendations,
        coach_team=coach_team,
        team_members=team_members,
        users_pool=users_pool,
        athletes=athletes,
        indicators=indicators,
        open_modal=open_modal,
        now_dt=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
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
