# app/utils.py
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urljoin

from flask import Response, abort, redirect, request, url_for
from flask_login import current_user

from .db import db, safe_commit


# ============================================================
# Safe redirect (next=...)
# ============================================================
def is_safe_url(target: str) -> bool:
    """
    Защита от open-redirect. Разрешаем редирект только на тот же хост.
    """
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def redirect_next(default_endpoint: str, **values):
    """
    Редирект на next, если он безопасен; иначе на default_endpoint.
    """
    target = request.args.get("next") or request.form.get("next")
    if target and is_safe_url(target):
        return redirect(target)
    return redirect(url_for(default_endpoint, **values))


# ============================================================
# Dates & parsing
# ============================================================
def parse_date(value: Optional[str]) -> Optional[date]:
    """
    ISO: YYYY-MM-DD
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except Exception:
        return None


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """
    Поддержка:
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM
    - YYYY-MM-DDTHH:MM
    - YYYY-MM-DD HH:MM:SS
    - YYYY-MM-DDTHH:MM:SS
    """
    if not value:
        return None
    s = value.strip()
    d = parse_date(s)
    if d and len(s) == 10:
        return datetime(d.year, d.month, d.day, 0, 0, 0)
    try:
        return datetime.fromisoformat(s.replace(" ", "T"))
    except Exception:
        return None


def format_dt(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(str(value).replace(",", ".").strip())
    except Exception:
        return default


# ============================================================
# Pagination helpers
# ============================================================
def clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        v = int(value)
    except Exception:
        return default
    return max(min_value, min(max_value, v))


def simple_paginate(query, page: int, per_page: int) -> Dict[str, Any]:
    """
    SQLAlchemy query -> dict pagination.
    """
    page = max(1, int(page or 1))
    per_page = max(1, min(200, int(per_page or 20)))

    try:
        total = query.count()
    except Exception:
        total = 0

    offset = (page - 1) * per_page
    items = query.offset(offset).limit(per_page).all()

    pages = (total + per_page - 1) // per_page if per_page else 1
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": page < pages,
        "prev_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if page < pages else None,
    }


# ============================================================
# Breadcrumbs
# ============================================================
def crumbs(*items: Tuple[str, str]) -> List[Dict[str, str]]:
    """
    items: (title, url) — url может быть "" для текущей страницы.
    """
    return [{"title": title, "url": url or ""} for title, url in items]


# ============================================================
# Period helpers (for filters / export)
# ============================================================
def get_period_from_request(from_key: str = "from", to_key: str = "to") -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    period_from/period_to из query-string.
    """
    period_from = parse_datetime(request.args.get(from_key))
    period_to = parse_datetime(request.args.get(to_key))
    return period_from, period_to


# ============================================================
# Norms & out-of-range (with athlete индивидуальные нормы)
# ============================================================
def get_effective_norm(
    athlete_id: int,
    indicator_id: int,
) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Возвращает (norm_min, norm_max, has_personal_norm).

    Приоритет: AthleteIndicatorNorm (is_active=True) -> Indicator.norm_min/max.
    """
    from .models import AthleteIndicatorNorm, Indicator

    personal = (
        AthleteIndicatorNorm.query
        .filter_by(athlete_id=athlete_id, indicator_id=indicator_id, is_active=True)
        .first()
    )
    if personal:
        return personal.norm_min, personal.norm_max, True

    ind = Indicator.query.get(indicator_id)
    if not ind:
        return None, None, False

    return ind.norm_min, ind.norm_max, False


def is_out_of_range_value(
    athlete_id: int,
    indicator_id: int,
    value: float,
) -> Tuple[bool, Optional[float], Optional[float], bool]:
    """
    (out_of_range, norm_min, norm_max, used_personal_norm)
    """
    nmin, nmax, personal = get_effective_norm(athlete_id, indicator_id)
    out = False
    if nmin is not None and value < float(nmin):
        out = True
    if nmax is not None and value > float(nmax):
        out = True
    return out, nmin, nmax, personal


def measurement_out_of_range(m) -> bool:
    """
    Быстрая проверка по объекту Measurement.
    """
    try:
        if not m or m.athlete_id is None or m.indicator_id is None:
            return False
        return is_out_of_range_value(m.athlete_id, m.indicator_id, float(m.value))[0]
    except Exception:
        return False


def apply_out_of_range_filter(query):
    """
    Применяет к запросу Measurement фильтр "вне нормы" с учётом индивидуальных норм.
    Удобно вызывать в routes/admin вместо дублирования coalesce-логики.

    Требует, чтобы query был по Measurement с join(Measurement.indicator) или
    чтобы Indicator был доступен через join ниже (мы подцепим join сами).
    """
    from sqlalchemy.orm import aliased
    from .models import AthleteIndicatorNorm, Indicator, Measurement

    Norm = aliased(AthleteIndicatorNorm)

    # гарантируем join Indicator (если уже был — SQLAlchemy нормально переживёт)
    query = query.join(Measurement.indicator)

    query = query.outerjoin(
        Norm,
        db.and_(
            Norm.athlete_id == Measurement.athlete_id,
            Norm.indicator_id == Measurement.indicator_id,
            Norm.is_active.is_(True),
        ),
    )

    eff_min = db.func.coalesce(Norm.norm_min, Indicator.norm_min)
    eff_max = db.func.coalesce(Norm.norm_max, Indicator.norm_max)

    return query.filter(
        db.or_(
            db.and_(eff_min.isnot(None), Measurement.value < eff_min),
            db.and_(eff_max.isnot(None), Measurement.value > eff_max),
        )
    )


# ============================================================
# CSV export for 1C
# ============================================================
def measurements_to_1c_csv_rows(measurements, profile: str = "simple") -> List[List[str]]:
    """
    profile:
      - "simple": 3 колонки (как в твоём примере импорта 1С)
          Date consultation;Student name;Group name
      - "full": расширенный журнал (удобен для реальной интеграции/проверки)
    """
    rows: List[List[str]] = []

    for m in measurements:
        dt = getattr(m, "measured_at", None)
        athlete = getattr(m, "athlete", None)
        indicator = getattr(m, "indicator", None)
        source = getattr(m, "source", None)
        created_by = getattr(m, "created_by", None)

        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S") if isinstance(dt, datetime) else ""

        athlete_name = getattr(athlete, "full_name", "") if athlete else ""
        team_name = getattr(getattr(athlete, "team", None), "name", "") if athlete else ""

        ind_name = getattr(indicator, "name", "") if indicator else ""
        unit = getattr(indicator, "unit", "") if indicator else ""
        val = getattr(m, "value", "")
        src_code = getattr(source, "code", "") if source else ""
        created_by_name = getattr(created_by, "username", "") if created_by else ""
        comment = getattr(m, "comment", "") or ""

        if profile == "simple":
            # Group name: компактная строка для "журнала"
            cell = f"{ind_name}={val}".strip()
            if unit:
                cell = f"{cell} {unit}".strip()
            if team_name:
                cell = f"{team_name} | {cell}".strip()
            rows.append([dt_str, athlete_name, cell])
        else:
            # full
            rows.append(
                [
                    dt_str,
                    athlete_name,
                    team_name,
                    ind_name,
                    str(val),
                    unit,
                    src_code,
                    created_by_name,
                    comment,
                ]
            )

    return rows


def make_1c_csv_response(
    measurements,
    filename: str = "export_1c.csv",
    delimiter: str = ";",
    profile: str = "simple",
) -> Response:
    """
    CSV Response (UTF-8 with BOM) — чтобы 1С/Excel корректно читали кириллицу.
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter)

    if profile == "simple":
        writer.writerow(["Date consultation", "Student name", "Group name"])
    else:
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

    for row in measurements_to_1c_csv_rows(measurements, profile=profile):
        writer.writerow(row)

    data = output.getvalue().encode("utf-8-sig")  # BOM
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# Audit log helper
# ============================================================
def log_audit(
    action: str,
    entity: str,
    entity_id: Optional[int] = None,
    details: Optional[dict] = None,
    *,
    user=None,
    commit: bool = False,
) -> None:
    """
    Запись в audit_log.

    По умолчанию только добавляет запись в текущую сессию (commit=False),
    чтобы вызывающий код мог коммитить один раз за всю операцию.
    Если commit=True — сделает safe_commit().
    """
    from .models import AuditLog

    u = user if user is not None else (current_user if getattr(current_user, "is_authenticated", False) else None)

    ev = AuditLog(
        user=u,
        action=(action or "").strip()[:64],
        entity=(entity or "").strip()[:64],
        entity_id=entity_id,
        details_json=json.dumps(details or {}, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    db.session.add(ev)

    if commit:
        try:
            safe_commit()
        except Exception:
            # если вдруг лог не пишется — не ломаем основную логику
            try:
                db.session.rollback()
            except Exception:
                pass
