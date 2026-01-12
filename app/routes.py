# app/routes.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, render_template, request, url_for, redirect, flash
from flask_login import current_user, login_required

from .db import db
from .models import Athlete, Indicator, IndicatorCategory, Team, Measurement
from .utils import (
    crumbs,
    parse_datetime,
    to_float,
    clamp_int,
    simple_paginate,
    get_period_from_request,
)

bp = Blueprint("routes", __name__)


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
    Применяет фильтры к запросу Measurement.
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
        # out_of_range вычисляется через нормы индикатора,
        # поэтому фильтруем по Indicator.norm_min/norm_max и Measurement.value
        q = q.join(Measurement.indicator).filter(
            db.or_(
                db.and_(Indicator.norm_min.isnot(None), Measurement.value < Indicator.norm_min),
                db.and_(Indicator.norm_max.isnot(None), Measurement.value > Indicator.norm_max),
            )
        )

    return q


def _get_common_lists():
    """
    Часто используемые списки для фильтров.
    """
    athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()
    teams = Team.query.order_by(Team.name.asc()).all()
    return athletes, indicators, teams


@bp.get("/")
def index():
    # быстрые цифры
    athletes_count = Athlete.query.filter_by(is_active=True).count()
    indicators_count = Indicator.query.filter_by(is_active=True).count()

    # последние измерения
    latest_measurements = (
        Measurement.query
        .join(Measurement.athlete)
        .join(Measurement.indicator)
        .order_by(Measurement.measured_at.desc())
        .limit(12)
        .all()
    )

    # отклонения за последние 7 дней
    since = datetime.utcnow() - timedelta(days=7)
    out_7d = (
        Measurement.query
        .join(Measurement.indicator)
        .filter(Measurement.measured_at >= since)
        .filter(
            db.or_(
                db.and_(Indicator.norm_min.isnot(None), Measurement.value < Indicator.norm_min),
                db.and_(Indicator.norm_max.isnot(None), Measurement.value > Indicator.norm_max),
            )
        )
        .order_by(Measurement.measured_at.desc())
        .limit(12)
        .all()
    )

    bc = crumbs(("Главная", ""))

    return render_template(
        "index.html",
        breadcrumbs=bc,
        athletes_count=athletes_count,
        indicators_count=indicators_count,
        latest_measurements=latest_measurements,
        out_of_range_recent=out_7d,
    )

@bp.get("/catalog")
def catalog():
    athletes, indicators, teams = _get_common_lists()

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
        "catalog.html",
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


@bp.get("/products/<int:athlete_id>")
def product(athlete_id: int):
    athlete = Athlete.query.get_or_404(athlete_id)

    # последние измерения спортсмена
    last_measurements = (
        Measurement.query
        .filter_by(athlete_id=athlete.id)
        .join(Measurement.indicator)
        .order_by(Measurement.measured_at.desc())
        .limit(50)
        .all()
    )

    # список показателей для быстрого фильтра на странице
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()

    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Журнал измерений", url_for("routes.catalog")),
        (athlete.full_name, ""),
    )

    return render_template(
        "product.html",
        breadcrumbs=bc,
        athlete=athlete,
        last_measurements=last_measurements,
        indicators=indicators,
    )

@bp.get("/categories")
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
        "categories.html",
        breadcrumbs=bc,
        categories=cats,
        indicators=indicators,
    )

@bp.get("/offers")
def offers():
    athletes, indicators, teams = _get_common_lists()

    athlete_id = request.args.get("athlete_id", type=int)
    indicator_id = request.args.get("indicator_id", type=int)
    team_id = request.args.get("team_id", type=int)

    period_from, period_to = get_period_from_request("from", "to")
    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=20, min_value=5, max_value=200)

    q = (
        Measurement.query
        .join(Measurement.athlete)
        .join(Measurement.indicator)
        .order_by(Measurement.measured_at.desc())
    )
    q = _apply_measurement_filters(
        q,
        athlete_id=athlete_id,
        indicator_id=indicator_id,
        team_id=team_id,
        period_from=period_from,
        period_to=period_to,
        out_only=True,  # здесь всегда только отклонения
    )

    pagination = simple_paginate(q, page=page, per_page=per_page)

    bc = crumbs(("Главная", url_for("routes.index")), ("Отклонения от нормы", ""))

    return render_template(
        "offers.html",
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
        pagination=pagination,
    )

@bp.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    team_id = request.args.get("team_id", type=int)

    athletes = []
    indicators = []

    if q:
        aq = Athlete.query.filter(Athlete.is_active.is_(True)).filter(Athlete.full_name.ilike(f"%{q}%"))
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

    bc = crumbs(("Главная", url_for("routes.index")), ("Поиск", ""))

    return render_template(
        "search.html",
        breadcrumbs=bc,
        query=q,
        teams=teams,
        team_id=team_id,
        athletes=athletes,
        indicators=indicators,
    )

@bp.get("/about")
def about():
    bc = crumbs(("Главная", url_for("routes.index")), ("О системе", ""))
    return render_template("about.html", breadcrumbs=bc)


@bp.get("/contacts")
def contacts():
    bc = crumbs(("Главная", url_for("routes.index")), ("Контакты", ""))
    return render_template("contacts.html", breadcrumbs=bc)
