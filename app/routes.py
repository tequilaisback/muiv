# app/routes.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, abort, render_template, request, url_for
from flask_login import current_user, login_required

from .auth import staff_required
from .models import (
    Alert,
    Athlete,
    Feedback,
    Indicator,
    IndicatorCategory,
    Measurement,
    Team,
    User,
    ROLE_DOCTOR,
)
from .permissions import get_coach_team_ids, is_coach, is_staff, is_user
from .utils import (
    apply_out_of_range_filter,
    crumbs,
    clamp_int,
    simple_paginate,
    get_period_from_request,
)

bp = Blueprint("routes", __name__)


def _get_common_lists(team_ids: Optional[list[int]] = None):
    athletes_query = Athlete.query.filter_by(is_active=True)
    teams_query = Team.query
    if team_ids:
        athletes_query = athletes_query.filter(Athlete.team_id.in_(team_ids))
        teams_query = teams_query.filter(Team.id.in_(team_ids))

    athletes = athletes_query.order_by(Athlete.full_name.asc()).all()
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()
    teams = teams_query.order_by(Team.name.asc()).all()
    return athletes, indicators, teams


def _apply_measurement_filters(
    q,
    athlete_id: Optional[int] = None,
    indicator_id: Optional[int] = None,
    team_id: Optional[int] = None,
    period_from: Optional[datetime] = None,
    period_to: Optional[datetime] = None,
    out_only: bool = False,
):
    """
    Фильтры по Measurement.

    out_only учитывает индивидуальные нормы (AthleteIndicatorNorm),
    иначе общие нормы Indicator — через utils.apply_out_of_range_filter().
    """
    if athlete_id:
        q = q.filter(Measurement.athlete_id == athlete_id)

    if indicator_id:
        q = q.filter(Measurement.indicator_id == indicator_id)

    if team_id:
        q = q.join(Measurement.athlete).filter(Athlete.team_id == team_id)

    if period_from:
        q = q.filter(Measurement.measured_at >= period_from)

    if period_to:
        q = q.filter(Measurement.measured_at <= period_to)

    if out_only:
        q = apply_out_of_range_filter(q)

    return q


# -------------------------
# PUBLIC (GUEST) PAGES
# -------------------------
@bp.get("/")
def index():
    """
    Гостю показываем только агрегаты.
    Staff — дополнительно последние измерения и последние alerts.
    """
    athletes_count = 0
    indicators_count = 0

    latest_measurements = []
    alerts_recent = []

    is_staff_role = is_staff(current_user)
    is_user_role = is_user(current_user)
    is_coach_role = is_coach(current_user)
    team_ids = get_coach_team_ids(current_user) if is_coach_role else []

    if is_staff_role:
        athletes_query = Athlete.query.filter_by(is_active=True)
        if team_ids:
            athletes_query = athletes_query.filter(Athlete.team_id.in_(team_ids))
        athletes_count = athletes_query.count()
        indicators_count = Indicator.query.filter_by(is_active=True).count()

        latest_query = (
            Measurement.query
            .join(Measurement.athlete)
            .join(Measurement.indicator)
            .order_by(Measurement.measured_at.desc())
        )
        if team_ids:
            latest_query = latest_query.filter(Athlete.team_id.in_(team_ids))
        latest_measurements = latest_query.limit(12).all()

        since = datetime.utcnow() - timedelta(days=7)
        alerts_query = (
            Alert.query
            .join(Alert.measurement)
            .join(Measurement.athlete)
            .join(Measurement.indicator)
            .filter(Measurement.measured_at >= since)
            .order_by(Alert.created_at.desc())
        )
        if team_ids:
            alerts_query = alerts_query.filter(Athlete.team_id.in_(team_ids))
        alerts_recent = alerts_query.limit(12).all()
    elif is_user_role:
        athlete_profile = getattr(current_user, "athlete", None)
        if athlete_profile:
            athletes_count = 1
            indicators_count = Indicator.query.filter_by(is_active=True).count()
            latest_measurements = (
                Measurement.query
                .join(Measurement.indicator)
                .filter(Measurement.athlete_id == athlete_profile.id)
                .order_by(Measurement.measured_at.desc())
                .limit(12)
                .all()
            )

    bc = crumbs(("Главная", ""))

    return render_template(
        "dashboard.html",  # было: index.html
        breadcrumbs=bc,
        athletes_count=athletes_count,
        indicators_count=indicators_count,
        latest_measurements=latest_measurements,
        alerts_recent=alerts_recent,
        is_staff=is_staff_role,
    )


@bp.get("/about")
def about():
    bc = crumbs(("Главная", url_for("routes.index")), ("О системе", ""))
    return render_template("about.html", breadcrumbs=bc)


@bp.get("/contacts")
def contacts():
    bc = crumbs(("Главная", url_for("routes.index")), ("Контакты", ""))
    return render_template("contacts.html", breadcrumbs=bc)


# -------------------------
# STAFF-ONLY PAGES
# -------------------------
@bp.get("/catalog")
@staff_required
def catalog():
    team_ids = get_coach_team_ids(current_user) if is_coach(current_user) else []
    athletes, indicators, teams = _get_common_lists(team_ids=team_ids)

    athlete_id = request.args.get("athlete_id", type=int)
    indicator_id = request.args.get("indicator_id", type=int)
    team_id = request.args.get("team_id", type=int)
    out_only = (request.args.get("out") == "1")

    period_from, period_to = get_period_from_request("from", "to")

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=20, min_value=5, max_value=200)

    q = (
        Measurement.query
        .join(Measurement.athlete)
        .join(Measurement.indicator)
        .order_by(Measurement.measured_at.desc())
    )

    if team_ids:
        q = q.filter(Athlete.team_id.in_(team_ids))

    q = _apply_measurement_filters(
        q,
        athlete_id=athlete_id,
        indicator_id=indicator_id,
        team_id=team_id,
        period_from=period_from,
        period_to=period_to,
        out_only=out_only,
    )

    pagination = simple_paginate(q, page=page, per_page=per_page)

    bc = crumbs(("Главная", url_for("routes.index")), ("Журнал измерений", ""))

    return render_template(
        "measurements.html",  # было: catalog.html
        breadcrumbs=bc,
        athletes=athletes,
        indicators=indicators,
        teams=teams,
        filters={
            "athlete_id": athlete_id,
            "indicator_id": indicator_id,
            "team_id": team_id,
            "from": period_from.strftime("%Y-%m-%d %H:%M") if period_from else "",
            "to": period_to.strftime("%Y-%m-%d %H:%M") if period_to else "",
            "out": "1" if out_only else "0",
            "per_page": per_page,
        },
        pagination=pagination,
    )


@bp.get("/offers")
@staff_required
def offers():
    """
    Отклонения — из таблицы alerts.
    """
    team_ids = get_coach_team_ids(current_user) if is_coach(current_user) else []
    athletes, indicators, teams = _get_common_lists(team_ids=team_ids)

    athlete_id = request.args.get("athlete_id", type=int)
    indicator_id = request.args.get("indicator_id", type=int)
    team_id = request.args.get("team_id", type=int)

    period_from, period_to = get_period_from_request("from", "to")
    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=20, min_value=5, max_value=200)

    q = (
        Alert.query
        .join(Alert.measurement)
        .join(Measurement.athlete)
        .join(Measurement.indicator)
        .order_by(Alert.created_at.desc())
    )
    if team_ids:
        q = q.filter(Athlete.team_id.in_(team_ids))

    if athlete_id:
        q = q.filter(Measurement.athlete_id == athlete_id)
    if indicator_id:
        q = q.filter(Measurement.indicator_id == indicator_id)
    if team_id:
        q = q.filter(Athlete.team_id == team_id)
    if period_from:
        q = q.filter(Measurement.measured_at >= period_from)
    if period_to:
        q = q.filter(Measurement.measured_at <= period_to)

    pagination = simple_paginate(q, page=page, per_page=per_page)

    bc = crumbs(("Главная", url_for("routes.index")), ("Отклонения от нормы", ""))

    return render_template(
        "alerts.html",  # было: offers.html
        breadcrumbs=bc,
        athletes=athletes,
        indicators=indicators,
        teams=teams,
        filters={
            "athlete_id": athlete_id,
            "indicator_id": indicator_id,
            "team_id": team_id,
            "from": period_from.strftime("%Y-%m-%d %H:%M") if period_from else "",
            "to": period_to.strftime("%Y-%m-%d %H:%M") if period_to else "",
            "per_page": per_page,
        },
        pagination=pagination,  # items = Alert, в шаблоне: a.measurement.athlete / a.measurement.indicator
    )


@bp.get("/categories")
@staff_required
def categories():
    cats = IndicatorCategory.query.order_by(IndicatorCategory.name.asc()).all()
    indicators = (
        Indicator.query
        .filter_by(is_active=True)
        .outerjoin(Indicator.category)
        .order_by(Indicator.name.asc())
        .all()
    )

    bc = crumbs(("Главная", url_for("routes.index")), ("Показатели и нормы", ""))

    return render_template(
        "indicators.html",  # было: categories.html
        breadcrumbs=bc,
        categories=cats,
        indicators=indicators,
    )


@bp.get("/search")
@staff_required
def search():
    q = (request.args.get("q") or "").strip()
    team_id = request.args.get("team_id", type=int)

    athletes = []
    indicators = []

    if q and len(q) >= 2:
        aq = Athlete.query.filter(Athlete.is_active.is_(True)).filter(Athlete.full_name.ilike(f"%{q}%"))
        team_ids = get_coach_team_ids(current_user) if is_coach(current_user) else []
        if team_ids:
            aq = aq.filter(Athlete.team_id.in_(team_ids))
        if team_id:
            aq = aq.filter(Athlete.team_id == team_id)
        athletes = aq.order_by(Athlete.full_name.asc()).limit(50).all()

        indicators = (
            Indicator.query
            .filter(Indicator.is_active.is_(True))
            .filter(Indicator.name.ilike(f"%{q}%"))
            .order_by(Indicator.name.asc())
            .limit(50)
            .all()
        )

    teams = Team.query.order_by(Team.name.asc()).all()
    if is_coach(current_user):
        team_ids = get_coach_team_ids(current_user)
        if team_ids:
            teams = Team.query.filter(Team.id.in_(team_ids)).order_by(Team.name.asc()).all()

    bc = crumbs(("Главная", url_for("routes.index")), ("Поиск", ""))

    return render_template(
        "search.html",
        breadcrumbs=bc,
        q=q,
        scope="all",
        teams=teams,
        team_id=team_id,
        athletes=athletes,
        indicators=indicators,
    )


@bp.get("/products/<int:athlete_id>")
@login_required
def product(athlete_id: int):
    athlete = Athlete.query.get_or_404(athlete_id)
    if is_user(current_user):
        athlete_profile = getattr(current_user, "athlete", None)
        if not athlete_profile or athlete_profile.id != athlete.id:
            abort(403)
    elif is_coach(current_user):
        team_ids = get_coach_team_ids(current_user)
        if team_ids and athlete.team_id not in team_ids:
            abort(403)
    elif not is_staff(current_user):
        abort(403)

    last_measurements = (
        Measurement.query
        .filter_by(athlete_id=athlete.id)
        .join(Measurement.indicator)
        .order_by(Measurement.measured_at.desc())
        .limit(50)
        .all()
    )

    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()
    doctor_recommendations = (
        Feedback.query
        .join(Feedback.author)
        .filter(Feedback.athlete_id == athlete.id)
        .filter(User.role == ROLE_DOCTOR)
        .order_by(Feedback.created_at.desc())
        .limit(10)
        .all()
    )

    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Журнал измерений", url_for("routes.catalog")),
        (athlete.full_name, ""),
    )

    return render_template(
        "athlete.html",  # было: product.html
        breadcrumbs=bc,
        athlete=athlete,
        last_measurements=last_measurements,
        indicators=indicators,
        doctor_recommendations=doctor_recommendations,
    )
