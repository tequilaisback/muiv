# app/utils.py
from __future__ import annotations

import csv
import io
from datetime import datetime, date
from functools import wraps
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urljoin

from flask import abort, current_app, redirect, request, url_for, Response
from flask_login import current_user


# -----------------------------
# Безопасные редиректы (next=...)
# -----------------------------
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


# -----------------------------
# Роли и доступ
# -----------------------------
def roles_required(*roles: str):
    """
    Декоратор: пользователь должен быть авторизован и иметь одну из ролей.
    Если не авторизован -> редирект на login.
    Если авторизован, но нет роли -> 403.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.path))
            # User.has_role есть в models.py
            if roles and not getattr(current_user, "has_role", lambda *_: False)(*roles):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# Частые комбинации (удобно в коде)
def admin_required(fn):
    return roles_required("admin")(fn)


def staff_required(fn):
    # Врач/тренер/оператор/админ
    return roles_required("admin", "doctor", "coach", "operator")(fn)


# -----------------------------
# Даты/время: парсинг и форматирование
# -----------------------------
def parse_date(value: Optional[str]) -> Optional[date]:
    """
    Ожидаем ISO: YYYY-MM-DD
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
    # если прислали только дату
    d = parse_date(s)
    if d and len(s) == 10:
        return datetime(d.year, d.month, d.day, 0, 0, 0)
    try:
        return datetime.fromisoformat(s.replace(" ", "T"))
    except Exception:
        return None


def format_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(str(value).replace(",", ".").strip())
    except Exception:
        return default


# -----------------------------
# Простейшая пагинация (без зависимости от paginate())
# -----------------------------
def clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        v = int(value)
    except Exception:
        return default
    return max(min_value, min(max_value, v))


def simple_paginate(query, page: int, per_page: int) -> Dict[str, Any]:
    """
    query: SQLAlchemy query (Model.query или db.session.query(...))
    Возвращает dict: items, page, per_page, total, pages
    """
    page = max(1, page)
    per_page = max(1, min(200, per_page))

    # total
    try:
        total = query.count()
    except Exception:
        # если вдруг query уже лимитирован/сложный
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


# -----------------------------
# Хлебные крошки (для templates/partials/_breadcrumbs.html)
# -----------------------------
def crumbs(*items: Tuple[str, str]) -> List[Dict[str, str]]:
    """
    items: (title, url) — url может быть "" для текущей страницы.
    """
    result = []
    for title, url in items:
        result.append({"title": title, "url": url or ""})
    return result


# -----------------------------
# Экспорт CSV для 1С (под твою идею импорта)
# -----------------------------
def measurements_to_1c_csv_rows(measurements) -> List[List[str]]:
    """
    Делает строки под простой импорт в 1С:
    Date consultation;Student name;Group name

    Мы используем:
    - Date consultation = measured_at
    - Student name      = athlete.full_name
    - Group name        = "{Indicator}={Value} {Unit}"
    """
    rows: List[List[str]] = []
    for m in measurements:
        dt = getattr(m, "measured_at", None)
        athlete = getattr(m, "athlete", None)
        indicator = getattr(m, "indicator", None)

        athlete_name = getattr(athlete, "full_name", "") if athlete else ""
        ind_name = getattr(indicator, "name", "") if indicator else ""
        unit = getattr(indicator, "unit", "") if indicator else ""
        val = getattr(m, "value", "")

        # формат даты/времени максимально "понятный" для 1С/журнала
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S") if isinstance(dt, datetime) else ""

        group_cell = f"{ind_name}={val}".strip()
        if unit:
            group_cell = f"{group_cell} {unit}".strip()

        rows.append([dt_str, athlete_name, group_cell])
    return rows


def make_1c_csv_response(
    measurements,
    filename: str = "export_1c.csv",
    delimiter: str = ";",
) -> Response:
    """
    Возвращает Flask Response с CSV (UTF-8 with BOM) для корректного открытия в 1С/Excel.
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter)

    # заголовок под твой импорт
    writer.writerow(["Date consultation", "Student name", "Group name"])
    for row in measurements_to_1c_csv_rows(measurements):
        writer.writerow(row)

    csv_text = output.getvalue()
    output.close()

    # BOM чтобы Excel/1С не ломали кириллицу
    data = ("\ufeff" + csv_text).encode("utf-8")

    resp = Response(data, mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# -----------------------------
# Утилита для периодов (часто нужна в фильтрах/экспорте)
# -----------------------------
def get_period_from_request(
    from_key: str = "from",
    to_key: str = "to",
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Берёт period_from/period_to из query-string.
    """
    period_from = parse_datetime(request.args.get(from_key))
    period_to = parse_datetime(request.args.get(to_key))
    return period_from, period_to
