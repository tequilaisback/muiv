# app/admin.py
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, date
from typing import Optional

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import aliased
from werkzeug.security import generate_password_hash

from .auth import roles_required, staff_required
from .db import db, safe_commit
from .permissions import get_coach_team_ids, is_admin, is_coach, is_doctor, is_operator
from .models import (
    ALERT_LEVEL_HIGH,
    ALERT_LEVEL_LOW,
    ALERT_STATUS_CLOSED,
    ALERT_STATUS_OPEN,
    FEEDBACK_KIND_INCIDENT,
    FEEDBACK_KIND_NOTE,
    FEEDBACK_KIND_REQUEST,
    ROLE_ADMIN,
    ROLE_COACH,
    ROLE_DOCTOR,
    ROLE_OPERATOR,
    ROLE_USER,
    SOURCE_CODE_1C,
    SOURCE_CODE_CSV,
    SOURCE_CODE_DEVICE,
    SOURCE_CODE_MANUAL,
    Alert,
    Athlete,
    AthleteIndicatorNorm,
    AuditLog,
    ExportBatch,
    Feedback,
    Indicator,
    IndicatorCategory,
    MeasureSource,
    Measurement,
    Team,
    User,
)
from .utils import (
    crumbs,
    clamp_int,
    get_period_from_request,
    parse_datetime,
    simple_paginate,
    to_float,
)

bp = Blueprint("admin", __name__)

admin_required = roles_required(ROLE_ADMIN)
operator_required = roles_required(ROLE_ADMIN, ROLE_OPERATOR)
data_entry_required = roles_required(ROLE_ADMIN, ROLE_COACH, ROLE_OPERATOR)
doctor_or_admin_required = roles_required(ROLE_ADMIN, ROLE_DOCTOR)


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
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _log_action(action: str, entity: str, entity_id: Optional[int] = None, details: Optional[dict] = None) -> None:
    """
    Пишем в audit_log. Ошибка логирования не должна ломать основную операцию.
    """
    try:
        ev = AuditLog(
            user=current_user if getattr(current_user, "is_authenticated", False) else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details_json=json.dumps(details or {}, ensure_ascii=False),
        )
        db.session.add(ev)
        safe_commit(log=False)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def _common_admin_context(active_view: str) -> dict:
    return {
        "active_view": active_view,
        "roles": [ROLE_ADMIN, ROLE_DOCTOR, ROLE_COACH, ROLE_OPERATOR, ROLE_USER],
        "source_codes": [SOURCE_CODE_MANUAL, SOURCE_CODE_CSV, SOURCE_CODE_DEVICE, SOURCE_CODE_1C],
    }


def _get_source_by_code(code: str) -> Optional[MeasureSource]:
    if not code:
        return None
    return MeasureSource.query.filter_by(code=code).first()


def _effective_out_of_range_filter(q):
    """
    Фильтр "только вне нормы" с учётом индивидуальных норм (если есть),
    иначе общие нормы Indicator.
    """
    Norm = aliased(AthleteIndicatorNorm)
    q = q.outerjoin(
        Norm,
        db.and_(
            Norm.athlete_id == Measurement.athlete_id,
            Norm.indicator_id == Measurement.indicator_id,
            Norm.is_active.is_(True),
        ),
    )
    eff_min = db.func.coalesce(Norm.norm_min, Indicator.norm_min)
    eff_max = db.func.coalesce(Norm.norm_max, Indicator.norm_max)
    q = q.filter(
        db.or_(
            db.and_(eff_min.isnot(None), Measurement.value < eff_min),
            db.and_(eff_max.isnot(None), Measurement.value > eff_max),
        )
    )
    return q


def _make_1c_csv_response(measurements: list[Measurement], *, filename: str) -> Response:
    """
    CSV для 1С: UTF-8 with BOM + ';' delimiter (обычно 1С так проще).
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow(
        [
            "measured_at",
            "athlete",
            "team",
            "indicator",
            "value",
            "unit",
            "source_code",
            "created_by",
            "comment",
        ]
    )

    for m in measurements:
        team_name = m.athlete.team.name if (m.athlete and m.athlete.team) else ""
        src_code = m.source.code if m.source else ""
        created_by = m.created_by.username if m.created_by else ""
        writer.writerow(
            [
                m.measured_at.strftime("%Y-%m-%d %H:%M:%S"),
                m.athlete.full_name if m.athlete else "",
                team_name,
                m.indicator.name if m.indicator else "",
                str(m.value),
                m.indicator.unit if (m.indicator and m.indicator.unit) else "",
                src_code,
                created_by,
                m.comment or "",
            ]
        )

    data = output.getvalue().encode("utf-8-sig")  # BOM
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -----------------------------
# Dashboard
# -----------------------------
@bp.get("/")
@staff_required
def dashboard():
    bc = crumbs(("Главная", url_for("routes.index")), ("Администрирование", ""))

    athletes_query = Athlete.query
    measurements_query = Measurement.query.join(Measurement.athlete)
    alerts_query = (
        Alert.query
        .join(Alert.measurement)
        .join(Measurement.athlete)
    )
    feedback_query = Feedback.query

    if is_coach(current_user):
        team_ids = get_coach_team_ids(current_user)
        if team_ids:
            athletes_query = athletes_query.filter(Athlete.team_id.in_(team_ids))
            measurements_query = measurements_query.filter(Athlete.team_id.in_(team_ids))
            alerts_query = alerts_query.filter(Athlete.team_id.in_(team_ids))
            feedback_query = (
                feedback_query
                .join(Feedback.athlete)
                .filter(Athlete.team_id.in_(team_ids))
            )

    athletes_count = athletes_query.count()
    indicators_count = Indicator.query.count()
    measurements_count = measurements_query.count()
    alerts_open = alerts_query.filter(Alert.status == ALERT_STATUS_OPEN).count()
    feedback_open = feedback_query.filter(Feedback.status == ALERT_STATUS_OPEN).count()

    latest_exports = ExportBatch.query.order_by(ExportBatch.created_at.desc()).limit(10).all()
    latest_audit = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()

    ctx = _common_admin_context("dashboard")
    ctx.update(
        {
            "breadcrumbs": bc,
            "stats": {
                "athletes": athletes_count,
                "indicators": indicators_count,
                "measurements": measurements_count,
                "alerts_open": alerts_open,
                "feedback_open": feedback_open,
            },
            "latest_exports": latest_exports,
            "latest_audit": latest_audit,
        }
    )
    return render_template("admin.html", **ctx)


# -----------------------------
# Teams
# -----------------------------
@bp.get("/teams")
@operator_required
def teams():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Команды/группы", ""),
    )
    items = Team.query.order_by(Team.name.asc()).all()
    parents = Team.query.order_by(Team.name.asc()).all()

    ctx = _common_admin_context("teams")
    ctx.update({"breadcrumbs": bc, "items": items, "parents": parents})
    return render_template("admin.html", **ctx)


@bp.post("/teams")
@operator_required
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
    item = Team(name=name, parent=parent, is_active=True)
    db.session.add(item)
    safe_commit()
    _log_action("create", "team", item.id, {"name": name, "parent_id": parent_id})
    flash("Команда/группа добавлена.", "success")
    return redirect(url_for("admin.teams"))


@bp.post("/teams/<int:team_id>/delete")
@operator_required
def teams_delete(team_id: int):
    item = Team.query.get_or_404(team_id)

    has_children = Team.query.filter_by(parent_id=item.id).first() is not None
    has_athletes = Athlete.query.filter_by(team_id=item.id).first() is not None
    if has_children or has_athletes:
        flash("Нельзя удалить: есть вложенные группы или спортсмены.", "warning")
        return redirect(url_for("admin.teams"))

    db.session.delete(item)
    safe_commit()
    _log_action("delete", "team", team_id, {"name": item.name})
    flash("Команда/группа удалена.", "info")
    return redirect(url_for("admin.teams"))


# -----------------------------
# Indicator categories
# -----------------------------
@bp.get("/indicator-categories")
@operator_required
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
@operator_required
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
    _log_action("create", "indicator_category", item.id, {"name": name, "parent_id": parent_id})
    flash("Категория добавлена.", "success")
    return redirect(url_for("admin.indicator_categories"))


@bp.post("/indicator-categories/<int:cat_id>/delete")
@operator_required
def indicator_categories_delete(cat_id: int):
    item = IndicatorCategory.query.get_or_404(cat_id)

    has_children = IndicatorCategory.query.filter_by(parent_id=item.id).first() is not None
    has_indicators = Indicator.query.filter_by(category_id=item.id).first() is not None
    if has_children or has_indicators:
        flash("Нельзя удалить: есть подкатегории или показатели.", "warning")
        return redirect(url_for("admin.indicator_categories"))

    db.session.delete(item)
    safe_commit()
    _log_action("delete", "indicator_category", cat_id, {"name": item.name})
    flash("Категория удалена.", "info")
    return redirect(url_for("admin.indicator_categories"))


# -----------------------------
# Measure sources (справочник источников)
# -----------------------------
@bp.get("/sources")
@operator_required
def sources():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Источники данных", ""),
    )
    items = MeasureSource.query.order_by(MeasureSource.code.asc()).all()

    ctx = _common_admin_context("sources")
    ctx.update({"breadcrumbs": bc, "items": items})
    return render_template("admin.html", **ctx)


@bp.post("/sources")
@operator_required
def sources_create():
    name = (request.form.get("name") or "").strip()
    code = (request.form.get("code") or "").strip().lower()

    if not name or not code:
        flash("Заполните название и код источника.", "warning")
        return redirect(url_for("admin.sources"))

    if MeasureSource.query.filter_by(code=code).first():
        flash("Источник с таким кодом уже существует.", "danger")
        return redirect(url_for("admin.sources"))

    item = MeasureSource(name=name, code=code, is_active=True)
    db.session.add(item)
    safe_commit()
    _log_action("create", "measure_source", item.id, {"name": name, "code": code})
    flash("Источник добавлен.", "success")
    return redirect(url_for("admin.sources"))


@bp.post("/sources/<int:source_id>/toggle")
@operator_required
def sources_toggle(source_id: int):
    item = MeasureSource.query.get_or_404(source_id)
    item.is_active = not item.is_active
    db.session.add(item)
    safe_commit()
    _log_action("update", "measure_source", source_id, {"is_active": item.is_active})
    flash("Статус источника изменён.", "info")
    return redirect(url_for("admin.sources"))


# -----------------------------
# Athletes
# -----------------------------
@bp.get("/athletes")
@operator_required
def athletes():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Спортсмены", ""),
    )

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
@operator_required
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
    _log_action("create", "athlete", athlete.id, {"full_name": full_name, "team_id": team_id})
    flash("Спортсмен добавлен.", "success")
    return redirect(url_for("admin.athletes"))


@bp.post("/athletes/<int:athlete_id>/toggle")
@operator_required
def athletes_toggle(athlete_id: int):
    athlete = Athlete.query.get_or_404(athlete_id)
    athlete.is_active = not athlete.is_active
    db.session.add(athlete)
    safe_commit()
    _log_action("update", "athlete", athlete_id, {"is_active": athlete.is_active})
    flash("Статус спортсмена изменён.", "info")
    return redirect(url_for("admin.athletes"))


# -----------------------------
# Indicators
# -----------------------------
@bp.get("/indicators")
@operator_required
def indicators():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Показатели", ""),
    )

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
@operator_required
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
    _log_action("create", "indicator", ind.id, {"name": name, "category_id": category_id})
    flash("Показатель добавлен.", "success")
    return redirect(url_for("admin.indicators"))


@bp.post("/indicators/<int:indicator_id>/toggle")
@operator_required
def indicators_toggle(indicator_id: int):
    ind = Indicator.query.get_or_404(indicator_id)
    ind.is_active = not ind.is_active
    db.session.add(ind)
    safe_commit()
    _log_action("update", "indicator", indicator_id, {"is_active": ind.is_active})
    flash("Статус показателя изменён.", "info")
    return redirect(url_for("admin.indicators"))


# -----------------------------
# Individual norms
# -----------------------------
@bp.get("/norms")
@operator_required
def norms():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Индивидуальные нормы", ""),
    )

    athlete_id = request.args.get("athlete_id", type=int)
    indicator_id = request.args.get("indicator_id", type=int)

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=20, min_value=5, max_value=200)

    query = AthleteIndicatorNorm.query.join(AthleteIndicatorNorm.athlete).join(AthleteIndicatorNorm.indicator)

    if athlete_id:
        query = query.filter(AthleteIndicatorNorm.athlete_id == athlete_id)
    if indicator_id:
        query = query.filter(AthleteIndicatorNorm.indicator_id == indicator_id)

    query = query.order_by(Athlete.full_name.asc(), Indicator.name.asc())

    pagination = simple_paginate(query, page=page, per_page=per_page)

    athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()

    ctx = _common_admin_context("norms")
    ctx.update(
        {
            "breadcrumbs": bc,
            "pagination": pagination,
            "athletes": athletes,
            "indicators": indicators,
            "filters": {"athlete_id": athlete_id, "indicator_id": indicator_id, "per_page": per_page},
        }
    )
    return render_template("admin.html", **ctx)


@bp.post("/norms")
@operator_required
def norms_create():
    athlete_id = request.form.get("athlete_id", type=int)
    indicator_id = request.form.get("indicator_id", type=int)
    norm_min = to_float(request.form.get("norm_min"))
    norm_max = to_float(request.form.get("norm_max"))
    comment = (request.form.get("comment") or "").strip() or None
    is_active = _bool_from_form(request.form.get("is_active") or "1")

    if not athlete_id or not indicator_id:
        flash("Выберите спортсмена и показатель.", "warning")
        return redirect(url_for("admin.norms"))

    # upsert по unique constraint (athlete_id, indicator_id)
    norm = AthleteIndicatorNorm.query.filter_by(athlete_id=athlete_id, indicator_id=indicator_id).first()
    if norm is None:
        norm = AthleteIndicatorNorm(
            athlete_id=athlete_id,
            indicator_id=indicator_id,
            norm_min=norm_min,
            norm_max=norm_max,
            comment=comment,
            is_active=is_active,
        )
    else:
        norm.norm_min = norm_min
        norm.norm_max = norm_max
        norm.comment = comment
        norm.is_active = is_active

    db.session.add(norm)
    safe_commit()
    _log_action("upsert", "athlete_indicator_norm", norm.id, {"athlete_id": athlete_id, "indicator_id": indicator_id})
    flash("Норма сохранена.", "success")
    return redirect(url_for("admin.norms", athlete_id=athlete_id))


@bp.post("/norms/<int:norm_id>/delete")
@operator_required
def norms_delete(norm_id: int):
    norm = AthleteIndicatorNorm.query.get_or_404(norm_id)
    db.session.delete(norm)
    safe_commit()
    _log_action("delete", "athlete_indicator_norm", norm_id)
    flash("Норма удалена.", "info")
    return redirect(url_for("admin.norms"))


# -----------------------------
# Measurements
# -----------------------------
@bp.get("/measurements")
@staff_required
def measurements():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Измерения", ""),
    )

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
        .outerjoin(Measurement.source)
        .order_by(Measurement.measured_at.desc())
    )
    if is_coach(current_user):
        team_ids = get_coach_team_ids(current_user)
        if team_ids:
            query = query.filter(Athlete.team_id.in_(team_ids))

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
        query = _effective_out_of_range_filter(query)

    pagination = simple_paginate(query, page=page, per_page=per_page)

    athletes_query = Athlete.query.filter_by(is_active=True)
    teams_query = Team.query
    if is_coach(current_user):
        team_ids = get_coach_team_ids(current_user)
        if team_ids:
            athletes_query = athletes_query.filter(Athlete.team_id.in_(team_ids))
            teams_query = teams_query.filter(Team.id.in_(team_ids))

    athletes = athletes_query.order_by(Athlete.full_name.asc()).all()
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()
    teams = teams_query.order_by(Team.name.asc()).all()
    sources = MeasureSource.query.filter_by(is_active=True).order_by(MeasureSource.code.asc()).all()

    ctx = _common_admin_context("measurements")
    ctx.update(
        {
            "breadcrumbs": bc,
            "pagination": pagination,
            "athletes": athletes,
            "indicators": indicators,
            "teams": teams,
            "sources": sources,
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
@data_entry_required
def measurements_create():
    athlete_id = request.form.get("athlete_id", type=int)
    indicator_id = request.form.get("indicator_id", type=int)
    value = to_float(request.form.get("value"))
    measured_at = parse_datetime(request.form.get("measured_at")) or datetime.utcnow()
    source_code = (request.form.get("source_code") or SOURCE_CODE_MANUAL).strip().lower()
    comment = (request.form.get("comment") or "").strip() or None

    if not athlete_id or not indicator_id or value is None:
        flash("Заполните спортсмена, показатель и значение.", "warning")
        return redirect(url_for("admin.measurements"))

    athlete = Athlete.query.get(athlete_id)
    indicator = Indicator.query.get(indicator_id)
    if not athlete or not indicator:
        flash("Спортсмен или показатель не найден.", "danger")
        return redirect(url_for("admin.measurements"))

    if is_coach(current_user):
        team_ids = get_coach_team_ids(current_user)
        if team_ids and athlete.team_id not in team_ids:
            flash("Спортсмен не из вашей команды.", "danger")
            return redirect(url_for("admin.measurements"))

    src = _get_source_by_code(source_code) or _get_source_by_code(SOURCE_CODE_MANUAL)

    m = Measurement(
        athlete=athlete,
        indicator=indicator,
        value=value,
        measured_at=measured_at,
        source=src,
        created_by=current_user if current_user.is_authenticated else None,
        comment=comment,
    )
    db.session.add(m)
    safe_commit()
    _log_action("create", "measurement", m.id, {"athlete_id": athlete_id, "indicator_id": indicator_id, "source": source_code})

    flash("Измерение добавлено.", "success")
    return redirect(url_for("admin.measurements"))


@bp.post("/measurements/<int:measurement_id>/delete")
@operator_required
def measurements_delete(measurement_id: int):
    m = Measurement.query.get_or_404(measurement_id)
    db.session.delete(m)
    safe_commit()
    _log_action("delete", "measurement", measurement_id)
    flash("Измерение удалено.", "info")
    return redirect(url_for("admin.measurements"))


# -----------------------------
# Alerts (журнал отклонений)
# -----------------------------
@bp.get("/alerts")
@doctor_or_admin_required
def alerts():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Отклонения (Alerts)", ""),
    )

    status = (request.args.get("status") or "").strip() or None
    level = (request.args.get("level") or "").strip() or None

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=25, min_value=5, max_value=200)

    query = (
        Alert.query
        .join(Alert.measurement)
        .join(Measurement.athlete)
        .join(Measurement.indicator)
        .order_by(Alert.created_at.desc())
    )

    if status:
        query = query.filter(Alert.status == status)
    if level:
        query = query.filter(Alert.level == level)

    pagination = simple_paginate(query, page=page, per_page=per_page)

    ctx = _common_admin_context("alerts")
    ctx.update(
        {
            "breadcrumbs": bc,
            "pagination": pagination,
            "filters": {"status": status or "", "level": level or "", "per_page": per_page},
        }
    )
    return render_template("admin.html", **ctx)


@bp.post("/alerts/<int:alert_id>/close")
@doctor_or_admin_required
def alerts_close(alert_id: int):
    a = Alert.query.get_or_404(alert_id)
    a.status = ALERT_STATUS_CLOSED
    a.closed_at = datetime.utcnow()
    a.closed_by = current_user
    a.note = (request.form.get("note") or "").strip() or a.note
    db.session.add(a)
    safe_commit()
    _log_action("update", "alert", alert_id, {"status": a.status})
    flash("Отклонение закрыто.", "info")
    return redirect(url_for("admin.alerts"))


# -----------------------------
# Export to 1C (CSV) + ExportBatch log
# -----------------------------
@bp.get("/export/1c")
@admin_required
def export_1c():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Экспорт в 1С (CSV)", ""),
    )

    athletes = Athlete.query.filter_by(is_active=True).order_by(Athlete.full_name.asc()).all()
    indicators = Indicator.query.filter_by(is_active=True).order_by(Indicator.name.asc()).all()
    teams = Team.query.order_by(Team.name.asc()).all()

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
@admin_required
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
        .outerjoin(Measurement.source)
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
        query = _effective_out_of_range_filter(query)

    measurements = query.all()
    rows_count = len(measurements)

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

    _log_action(
        "export",
        "export_batches",
        batch.id,
        {
            "filename": filename,
            "rows": rows_count,
            "filters": {"athlete_id": athlete_id, "indicator_id": indicator_id, "team_id": team_id, "out_only": out_only},
        },
    )

    return _make_1c_csv_response(measurements, filename=filename)


# -----------------------------
# Users (admin only)
# -----------------------------
@bp.get("/users")
@admin_required
def users():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Пользователи", ""),
    )

    q = (request.args.get("q") or "").strip()
    role = (request.args.get("role") or "").strip() or None
    active = request.args.get("active", "1")  # "1"/"0"/"all"

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=20, min_value=5, max_value=200)

    query = User.query.order_by(User.username.asc())

    if q:
        query = query.filter(
            db.or_(
                User.username.ilike(f"%{q}%"),
                User.email.ilike(f"%{q}%"),
            )
        )
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

    u = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        is_active=True,
    )
    db.session.add(u)
    safe_commit()
    _log_action("create", "user", u.id, {"username": username, "role": role})
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
    _log_action("update", "user", user_id, {"is_active": u.is_active})
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

    if current_user.is_authenticated and u.id == current_user.id and new_role != ROLE_ADMIN:
        flash("Нельзя снять с себя роль администратора.", "warning")
        return redirect(url_for("admin.users"))

    u.role = new_role
    db.session.add(u)
    safe_commit()
    _log_action("update", "user", user_id, {"role": new_role})
    flash("Роль обновлена.", "success")
    return redirect(url_for("admin.users"))


# -----------------------------
# Audit log view (staff)
# -----------------------------
@bp.get("/audit")
@staff_required
def audit():
    bc = crumbs(
        ("Главная", url_for("routes.index")),
        ("Администрирование", url_for("admin.dashboard")),
        ("Журнал действий", ""),
    )

    page = clamp_int(request.args.get("page"), default=1, min_value=1, max_value=10_000)
    per_page = clamp_int(request.args.get("per_page"), default=25, min_value=5, max_value=200)

    query = AuditLog.query.outerjoin(AuditLog.user).order_by(AuditLog.created_at.desc())
    pagination = simple_paginate(query, page=page, per_page=per_page)

    ctx = _common_admin_context("audit")
    ctx.update({"breadcrumbs": bc, "pagination": pagination})
    return render_template("admin.html", **ctx)
