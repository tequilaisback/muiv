# app/admin.py
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from sqlalchemy import or_, and_, func

from .db import db, safe_commit
from .models import (
    User,
    Team,
    IndicatorCategory,
    Athlete,
    Indicator,
    Measurement,
    Feedback,
    ExportBatch,
    ROLE_ADMIN,
    ROLE_DOCTOR,
    ROLE_COACH,
    ROLE_OPERATOR,
    ROLE_USER,
    MEASURE_SOURCE_MANUAL,
    MEASURE_SOURCE_CSV,
    MEASURE_SOURCE_DEVICE,
    MEASURE_SOURCE_1C,
)
from .utils import (
    roles_required,
    admin_required,
    staff_required,
    crumbs,
    clamp_int,
    parse_datetime,
    to_float,
    make_1c_csv_response,
    get_period_from_request,
    simple_paginate,
)

bp = Blueprint("admin", __name__)


# -----------------------------
# Helpers
# -----------------------------
def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except Exception:
        return None


def _bool_from_form(value: Optional[str]) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def _common_admin_context(active_view: str):
    """
    Общие данные для admin.html (меню, текущий пользователь и т.п.).
    """
    return {
        "active_view": active_view,
        "roles": [ROLE_ADMIN, ROLE_DOCTOR, ROLE_COACH, ROLE_OPERATOR, ROLE_USER],
        "sources": [MEASURE_SOURCE_MANUAL, MEASURE_SOURCE_CSV, MEASURE_SOURCE_DEVICE, MEASURE_SOURCE_1C],
    }


# -----------------------------
# Dashboard
# -----------------------------
@bp.get("/")
@staff_required
def dashboard():
    bc = crumbs(("Главная", url_for("routes.index")), ("Администрирование", ""))

    athletes_count = Athlete.query.count()
    indicators_count = Indicator.query.count()
    measurements_count = Measurement.query.count()

    open_feedback = Feedback.query.filter(Feedback.status == "open").count()

    latest_exports = (
        ExportBatch.query.order_by(ExportBatch.created_at.desc()).limit(10).all()
        if ExportBatch.query.first()
        else []
    )

    ctx = _common_admin_context("dashboard")
    ctx.update(
        {
            "breadcrumbs": bc,
            "stats": {
                "athletes": athletes_count,
                "indicators": indicators_count,
                "measurements": measurements_count,
                "open_feedback": open_feedback,
            },
            "latest_exports": latest_exports,
        }
    )
    return render_template("admin.html", **ctx)


# -----------------------------
# Teams
# -----------------------------
@bp.get("/teams")
@staff_required
def teams():
    bc = crumbs(("Главная", url_for("routes.index")), ("Администрирование", url_for("admin.dashboard")), ("Команды/группы", ""))

    items = Team.query.order_by(Team.name.asc()).all()
    parents = Team.query.order_by(Team.name.asc()).all()

    ctx = _common_admin_context("teams")
    ctx.update({"breadcrumbs": bc, "items": items, "parents": parents})
    return render_template("admin.html", **ctx)


@bp.post("/teams")
@staff_required
def teams_create():
    name = (request.form.get("name") or "").strip()
    parent_id = request.form.get("parent_id", type=int)

    if not name:
        flash("Название команды/группы обязательно.", "warning")
        return redirect(url_for("admin.teams"))

    if Team.query.filter_by(name=name).first():
        flash("Команда/группа с таким названием уже существует.", "danger")
        return redirect(url_for("admin.teams"))

    parent = Team.query.get(parent_id) if parent_id else None
    item = Team(name=name, parent=parent)
    db.session.add(item)
    safe_commit()
    flash("Команда/группа добавлена.", "success")
    return redirect(url_for("admin.teams"))


@bp.post("/teams/<int:team_id>/delete")
@staff_required
def teams_delete(team_id: int):
    item = Team.query.get_or_404(team_id)

    # Простая защита: не удаляем, если есть спортсмены/дети
    has_children = Team.query.filter_by(parent_id=item.id).first() is not None
    has_athletes = Athlete.query.filter_by(team_id=item.id).first() is not None
    if has_children or has_athletes:
        flash("Нельзя удалить: есть вложенные группы или спортсмены.", "warning")
        return redirect(url_for("admin.teams"))

    db.session.delete(item)
    safe_commit()
    flash("Команда/группа удалена.", "info")
    return redirect(url_for("admin.teams"))


# -----------------------------
# Indicator categories
# -----------------------------
@bp.get("/indicator-categories")
@staff_required
def indicator_categories():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Категории показателей", ""),
    )

    items = IndicatorCategory.query.order_by(IndicatorCategory.name.asc()).all()
    parents = IndicatorCategory.query.order_by(IndicatorCategory.name.asc()).all()

    ctx = _common_admin_context("indicator_categories")
    ctx.update({"breadcrumbs": bc, "items": items, "parents": parents})
    return render_template("admin.html", **ctx)


@bp.post("/indicator-categories")
@staff_required
def indicator_categories_create():
    name = (request.form.get("name") or "").strip()
    parent_id = request.form.get("parent_id", type=int)

    if not name:
        flash("Название категории обязательно.", "warning")
        return redirect(url_for("admin.indicator_categories"))

    if IndicatorCategory.query.filter_by(name=name).first():
        flash("Категория с таким названием уже существует.", "danger")
        return redirect(url_for("admin.indicator_categories"))

    parent = IndicatorCategory.query.get(parent_id) if parent_id else None
    item = IndicatorCategory(name=name, parent=parent)
    db.session.add(item)
    safe_commit()
    flash("Категория добавлена.", "success")
    return redirect(url_for("admin.indicator_categories"))


@bp.post("/indicator-categories/<int:cat_id>/delete")
@staff_required
def indicator_categories_delete(cat_id: int):
    item = IndicatorCategory.query.get_or_404(cat_id)

    has_children = IndicatorCategory.query.filter_by(parent_id=item.id).first() is not None
    has_indicators = Indicator.query.filter_by(category_id=item.id).first() is not None
    if has_children or has_indicators:
        flash("Нельзя удалить: есть подкатегории или показатели.", "warning")
        return redirect(url_for("admin.indicator_categories"))

    db.session.delete(item)
    safe_commit()
    flash("Категория удалена.", "info")
    return redirect(url_for("admin.indicator_categories"))


# -----------------------------
# Athletes
# -----------------------------
@bp.get("/athletes")
@staff_required
def athletes():
    bc = crumbs(("Главная", url_for("routes.index")), ("Администрирование", url_for("admin.dashboard")), ("Спортсмены", ""))

    q = (request.args.get("q") or "").strip()
    team_id = request.args.get("team_id", type=int)
    active = request.args.get("active", "1")  # "1"/"0"/"all"

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=20, min_value=5, max_value=200)

    query = Athlete.query.outerjoin(Athlete.team).order_by(Athlete.full_name.asc())

    if q:
        query = query.filter(Athlete.full_name.ilike(f"%{q}%"))
    if team_id:
        query = query.filter(Athlete.team_id == team_id)
    if active == "1":
        query = query.filter(Athlete.is_active.is_(True))
    elif active == "0":
        query = query.filter(Athlete.is_active.is_(False))

    pagination = simple_paginate(query, page=page, per_page=per_page)

    teams = Team.query.order_by(Team.name.asc()).all()

    ctx = _common_admin_context("athletes")
    ctx.update(
        {
            "breadcrumbs": bc,
            "pagination": pagination,
            "teams": teams,
            "filters": {"q": q, "team_id": team_id, "active": active, "per_page": per_page},
        }
    )
    return render_template("admin.html", **ctx)


@bp.post("/athletes")
@staff_required
def athletes_create():
    full_name = (request.form.get("full_name") or "").strip()
    team_id = request.form.get("team_id", type=int)
    birth_date = _parse_date(request.form.get("birth_date"))
    gender = (request.form.get("gender") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None
    is_active = _bool_from_form(request.form.get("is_active") or "1")

    if not full_name:
        flash("ФИО спортсмена обязательно.", "warning")
        return redirect(url_for("admin.athletes"))

    team = Team.query.get(team_id) if team_id else None

    athlete = Athlete(
        full_name=full_name,
        team=team,
        birth_date=birth_date,
        gender=gender,
        notes=notes,
        is_active=is_active,
    )
    db.session.add(athlete)
    safe_commit()
    flash("Спортсмен добавлен.", "success")
    return redirect(url_for("admin.athletes"))


@bp.get("/athletes/<int:athlete_id>/edit")
@staff_required
def athletes_edit(athlete_id: int):
    athlete = Athlete.query.get_or_404(athlete_id)
    teams = Team.query.order_by(Team.name.asc()).all()

    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Спортсмены", url_for("admin.athletes")),
        ("Редактирование", ""),
    )

    ctx = _common_admin_context("athletes_edit")
    ctx.update({"breadcrumbs": bc, "athlete": athlete, "teams": teams})
    return render_template("admin.html", **ctx)


@bp.post("/athletes/<int:athlete_id>/edit")
@staff_required
def athletes_edit_post(athlete_id: int):
    athlete = Athlete.query.get_or_404(athlete_id)

    athlete.full_name = (request.form.get("full_name") or "").strip() or athlete.full_name
    athlete.team_id = request.form.get("team_id", type=int) or None
    athlete.birth_date = _parse_date(request.form.get("birth_date"))
    athlete.gender = (request.form.get("gender") or "").strip() or None
    athlete.notes = (request.form.get("notes") or "").strip() or None
    athlete.is_active = _bool_from_form(request.form.get("is_active") or "0")

    db.session.add(athlete)
    safe_commit()
    flash("Изменения сохранены.", "success")
    return redirect(url_for("admin.athletes"))


@bp.post("/athletes/<int:athlete_id>/toggle")
@staff_required
def athletes_toggle(athlete_id: int):
    athlete = Athlete.query.get_or_404(athlete_id)
    athlete.is_active = not athlete.is_active
    db.session.add(athlete)
    safe_commit()
    flash("Статус спортсмена изменён.", "info")
    return redirect(url_for("admin.athletes"))


# -----------------------------
# Indicators
# -----------------------------
@bp.get("/indicators")
@staff_required
def indicators():
    bc = crumbs(("Главная", url_for("routes.index")), ("Администрирование", url_for("admin.dashboard")), ("Показатели", ""))

    q = (request.args.get("q") or "").strip()
    category_id = request.args.get("category_id", type=int)
    active = request.args.get("active", "1")  # "1"/"0"/"all"

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=20, min_value=5, max_value=200)

    query = Indicator.query.outerjoin(Indicator.category).order_by(Indicator.name.asc())
    if q:
        query = query.filter(Indicator.name.ilike(f"%{q}%"))
    if category_id:
        query = query.filter(Indicator.category_id == category_id)
    if active == "1":
        query = query.filter(Indicator.is_active.is_(True))
    elif active == "0":
        query = query.filter(Indicator.is_active.is_(False))

    pagination = simple_paginate(query, page=page, per_page=per_page)

    cats = IndicatorCategory.query.order_by(IndicatorCategory.name.asc()).all()

    ctx = _common_admin_context("indicators")
    ctx.update(
        {
            "breadcrumbs": bc,
            "pagination": pagination,
            "categories": cats,
            "filters": {"q": q, "category_id": category_id, "active": active, "per_page": per_page},
        }
    )
    return render_template("admin.html", **ctx)


@bp.post("/indicators")
@staff_required
def indicators_create():
    name = (request.form.get("name") or "").strip()
    unit = (request.form.get("unit") or "").strip() or None
    category_id = request.form.get("category_id", type=int)
    norm_min = to_float(request.form.get("norm_min"))
    norm_max = to_float(request.form.get("norm_max"))
    is_active = _bool_from_form(request.form.get("is_active") or "1")

    if not name:
        flash("Название показателя обязательно.", "warning")
        return redirect(url_for("admin.indicators"))

    cat = IndicatorCategory.query.get(category_id) if category_id else None

    ind = Indicator(
        name=name,
        unit=unit,
        category=cat,
        norm_min=norm_min,
        norm_max=norm_max,
        is_active=is_active,
    )
    db.session.add(ind)
    safe_commit()
    flash("Показатель добавлен.", "success")
    return redirect(url_for("admin.indicators"))


@bp.get("/indicators/<int:indicator_id>/edit")
@staff_required
def indicators_edit(indicator_id: int):
    ind = Indicator.query.get_or_404(indicator_id)
    cats = IndicatorCategory.query.order_by(IndicatorCategory.name.asc()).all()

    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Показатели", url_for("admin.indicators")),
        ("Редактирование", ""),
    )

    ctx = _common_admin_context("indicators_edit")
    ctx.update({"breadcrumbs": bc, "indicator": ind, "categories": cats})
    return render_template("admin.html", **ctx)


@bp.post("/indicators/<int:indicator_id>/edit")
@staff_required
def indicators_edit_post(indicator_id: int):
    ind = Indicator.query.get_or_404(indicator_id)

    name = (request.form.get("name") or "").strip()
    if name:
        ind.name = name

    ind.unit = (request.form.get("unit") or "").strip() or None
    ind.category_id = request.form.get("category_id", type=int) or None
    ind.norm_min = to_float(request.form.get("norm_min"))
    ind.norm_max = to_float(request.form.get("norm_max"))
    ind.is_active = _bool_from_form(request.form.get("is_active") or "0")

    db.session.add(ind)
    safe_commit()
    flash("Изменения сохранены.", "success")
    return redirect(url_for("admin.indicators"))


@bp.post("/indicators/<int:indicator_id>/toggle")
@staff_required
def indicators_toggle(indicator_id: int):
    ind = Indicator.query.get_or_404(indicator_id)
    ind.is_active = not ind.is_active
    db.session.add(ind)
    safe_commit()
    flash("Статус показателя изменён.", "info")
    return redirect(url_for("admin.indicators"))


# -----------------------------
# Measurements
# -----------------------------
@bp.get("/measurements")
@staff_required
def measurements():
    bc = crumbs(("Главная", url_for("routes.index")), ("Администрирование", url_for("admin.dashboard")), ("Измерения", ""))

    athlete_id = request.args.get("athlete_id", type=int)
    indicator_id = request.args.get("indicator_id", type=int)
    team_id = request.args.get("team_id", type=int)
    out_only = request.args.get("out") == "1"

    period_from, period_to = get_period_from_request("from", "to")

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=25, min_value=5, max_value=200)

    query = (
        Measurement.query
        .join(Measurement.athlete)
        .join(Measurement.indicator)
        .order_by(Measurement.measured_at.desc())
    )

    if athlete_id:
        query = query.filter(Measurement.athlete_id == athlete_id)
    if indicator_id:
        query = query.filter(Measurement.indicator_id == indicator_id)
    if team_id:
        query = query.filter(Athlete.team_id == team_id)
    if period_from:
        query = query.filter(Measurement.measured_at >= period_from)
    if period_to:
        query = query.filter(Measurement.measured_at <= period_to)

    if out_only:
        query = query.filter(
            or_(
                and_(Indicator.norm_min.isnot(None), Measurement.value < Indicator.norm_min),
                and_(Indicator.norm_max.isnot(None), Measurement.value > Indicator.norm_max),
            )
        )

    pagination = simple_paginate(query, page=page, per_page=per_page)

    athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()
    teams = Team.query.order_by(Team.name.asc()).all()

    ctx = _common_admin_context("measurements")
    ctx.update(
        {
            "breadcrumbs": bc,
            "pagination": pagination,
            "athletes": athletes,
            "indicators": indicators,
            "teams": teams,
            "filters": {
                "athlete_id": athlete_id,
                "indicator_id": indicator_id,
                "team_id": team_id,
                "from": period_from.strftime("%Y-%m-%d %H:%M") if period_from else "",
                "to": period_to.strftime("%Y-%m-%d %H:%M") if period_to else "",
                "out": "1" if out_only else "0",
                "per_page": per_page,
            },
        }
    )
    return render_template("admin.html", **ctx)


@bp.post("/measurements")
@staff_required
def measurements_create():
    athlete_id = request.form.get("athlete_id", type=int)
    indicator_id = request.form.get("indicator_id", type=int)
    value = to_float(request.form.get("value"))
    measured_at = parse_datetime(request.form.get("measured_at")) or datetime.utcnow()
    source = (request.form.get("source") or MEASURE_SOURCE_MANUAL).strip()
    comment = (request.form.get("comment") or "").strip() or None

    if not athlete_id or not indicator_id or value is None:
        flash("Заполните спортсмена, показатель и значение.", "warning")
        return redirect(url_for("admin.measurements"))

    athlete = Athlete.query.get(athlete_id)
    indicator = Indicator.query.get(indicator_id)
    if not athlete or not indicator:
        flash("Спортсмен или показатель не найден.", "danger")
        return redirect(url_for("admin.measurements"))

    if source not in {MEASURE_SOURCE_MANUAL, MEASURE_SOURCE_CSV, MEASURE_SOURCE_DEVICE, MEASURE_SOURCE_1C}:
        source = MEASURE_SOURCE_MANUAL

    m = Measurement(
        athlete=athlete,
        indicator=indicator,
        value=value,
        measured_at=measured_at,
        source=source,
        created_by=current_user if current_user.is_authenticated else None,
        comment=comment,
    )
    db.session.add(m)
    safe_commit()
    flash("Измерение добавлено.", "success")
    return redirect(url_for("admin.measurements"))


@bp.post("/measurements/<int:measurement_id>/delete")
@staff_required
def measurements_delete(measurement_id: int):
    m = Measurement.query.get_or_404(measurement_id)
    db.session.delete(m)
    safe_commit()
    flash("Измерение удалено.", "info")
    return redirect(url_for("admin.measurements"))


# -----------------------------
# Export to 1C (CSV)
# -----------------------------
@bp.get("/export/1c")
@staff_required
def export_1c():
    bc = crumbs(("Главная", url_for("routes.index")), ("Администрирование", url_for("admin.dashboard")), ("Экспорт в 1С (CSV)", ""))

    athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()
    teams = Team.query.order_by(Team.name.asc()).all()

    # значения по умолчанию
    period_from, period_to = get_period_from_request("from", "to")

    ctx = _common_admin_context("export_1c")
    ctx.update(
        {
            "breadcrumbs": bc,
            "athletes": athletes,
            "indicators": indicators,
            "teams": teams,
            "filters": {
                "athlete_id": request.args.get("athlete_id", type=int),
                "indicator_id": request.args.get("indicator_id", type=int),
                "team_id": request.args.get("team_id", type=int),
                "from": period_from.strftime("%Y-%m-%d %H:%M") if period_from else "",
                "to": period_to.strftime("%Y-%m-%d %H:%M") if period_to else "",
                "out": "1" if request.args.get("out") == "1" else "0",
            },
        }
    )
    return render_template("admin.html", **ctx)


@bp.post("/export/1c")
@staff_required
def export_1c_post():
    athlete_id = request.form.get("athlete_id", type=int)
    indicator_id = request.form.get("indicator_id", type=int)
    team_id = request.form.get("team_id", type=int)
    out_only = request.form.get("out") == "1"

    period_from = parse_datetime(request.form.get("from"))
    period_to = parse_datetime(request.form.get("to"))

    query = (
        Measurement.query
        .join(Measurement.athlete)
        .join(Measurement.indicator)
        .order_by(Measurement.measured_at.asc())
    )

    if athlete_id:
        query = query.filter(Measurement.athlete_id == athlete_id)
    if indicator_id:
        query = query.filter(Measurement.indicator_id == indicator_id)
    if team_id:
        query = query.filter(Athlete.team_id == team_id)
    if period_from:
        query = query.filter(Measurement.measured_at >= period_from)
    if period_to:
        query = query.filter(Measurement.measured_at <= period_to)

    if out_only:
        query = query.filter(
            or_(
                and_(Indicator.norm_min.isnot(None), Measurement.value < Indicator.norm_min),
                and_(Indicator.norm_max.isnot(None), Measurement.value > Indicator.norm_max),
            )
        )

    measurements = query.all()
    rows_count = len(measurements)

    # логируем факт выгрузки (полезно для демонстрации)
    filename = f"export_1c_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    batch = ExportBatch(
        created_by=current_user if current_user.is_authenticated else None,
        period_from=period_from,
        period_to=period_to,
        rows_count=rows_count,
        filename=filename,
        comment="Экспорт измерений в 1С (CSV)",
    )
    db.session.add(batch)
    safe_commit()

    return make_1c_csv_response(measurements, filename=filename)


# -----------------------------
# Users (admin only)
# -----------------------------
@bp.get("/users")
@admin_required
def users():
    bc = crumbs(("Главная", url_for("routes.index")), ("Администрирование", url_for("admin.dashboard")), ("Пользователи", ""))

    q = (request.args.get("q") or "").strip()
    role = (request.args.get("role") or "").strip() or None
    active = request.args.get("active", "1")  # "1"/"0"/"all"

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=20, min_value=5, max_value=200)

    query = User.query.order_by(User.username.asc())

    if q:
        query = query.filter(or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    if role:
        query = query.filter(User.role == role)
    if active == "1":
        query = query.filter(User.is_active.is_(True))
    elif active == "0":
        query = query.filter(User.is_active.is_(False))

    pagination = simple_paginate(query, page=page, per_page=per_page)

    ctx = _common_admin_context("users")
    ctx.update(
        {
            "breadcrumbs": bc,
            "pagination": pagination,
            "filters": {"q": q, "role": role or "", "active": active, "per_page": per_page},
        }
    )
    return render_template("admin.html", **ctx)


@bp.post("/users")
@admin_required
def users_create():
    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip() or None
    password = (request.form.get("password") or "").strip()
    role = (request.form.get("role") or ROLE_USER).strip()

    if not username or len(username) < 3:
        flash("Логин должен быть не короче 3 символов.", "warning")
        return redirect(url_for("admin.users"))
    if not password or len(password) < 6:
        flash("Пароль должен быть не короче 6 символов.", "warning")
        return redirect(url_for("admin.users"))
    if role not in {ROLE_ADMIN, ROLE_DOCTOR, ROLE_COACH, ROLE_OPERATOR, ROLE_USER}:
        role = ROLE_USER

    if User.query.filter_by(username=username).first():
        flash("Пользователь с таким логином уже существует.", "danger")
        return redirect(url_for("admin.users"))
    if email and User.query.filter_by(email=email).first():
        flash("Этот email уже используется.", "danger")
        return redirect(url_for("admin.users"))

    from werkzeug.security import generate_password_hash

    u = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        is_active=True,
    )
    db.session.add(u)
    safe_commit()
    flash("Пользователь создан.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/toggle")
@admin_required
def users_toggle(user_id: int):
    u = User.query.get_or_404(user_id)
    if current_user.is_authenticated and u.id == current_user.id:
        flash("Нельзя отключить самого себя.", "warning")
        return redirect(url_for("admin.users"))

    u.is_active = not u.is_active
    db.session.add(u)
    safe_commit()
    flash("Статус пользователя изменён.", "info")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/role")
@admin_required
def users_set_role(user_id: int):
    u = User.query.get_or_404(user_id)
    new_role = (request.form.get("role") or ROLE_USER).strip()
    if new_role not in {ROLE_ADMIN, ROLE_DOCTOR, ROLE_COACH, ROLE_OPERATOR, ROLE_USER}:
        flash("Некорректная роль.", "warning")
        return redirect(url_for("admin.users"))

    # нельзя понизить самого себя до не-админа (чтобы не потерять доступ)
    if current_user.is_authenticated and u.id == current_user.id and new_role != ROLE_ADMIN:
        flash("Нельзя снять с себя роль администратора.", "warning")
        return redirect(url_for("admin.users"))

    u.role = new_role
    db.session.add(u)
    safe_commit()
    flash("Роль обновлена.", "success")
    return redirect(url_for("admin.users"))
