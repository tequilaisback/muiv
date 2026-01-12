# app/seed.py
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from werkzeug.security import generate_password_hash

from .db import db, safe_commit
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
    ExportBatch,
    Feedback,
    Indicator,
    IndicatorCategory,
    MeasureSource,
    Measurement,
    Team,
    User,
    resolve_norm_for,
    AuditLog,
)


def _get_or_create(model, defaults: Optional[dict] = None, **kwargs):
    """
    Простой get_or_create для SQLAlchemy.
    Ищет по kwargs. Если не найдено — создаёт с defaults.
    """
    instance = model.query.filter_by(**kwargs).first()
    if instance:
        return instance, False

    params = dict(kwargs)
    if defaults:
        params.update(defaults)
    instance = model(**params)
    db.session.add(instance)
    return instance, True


def _ensure_sources() -> dict[str, MeasureSource]:
    """Создаёт справочник источников измерений."""
    items = [
        ("Вручную (веб)", SOURCE_CODE_MANUAL),
        ("Импорт CSV", SOURCE_CODE_CSV),
        ("Устройство/датчик", SOURCE_CODE_DEVICE),
        ("Интеграция 1С", SOURCE_CODE_1C),
    ]
    out: dict[str, MeasureSource] = {}
    for name, code in items:
        src, _ = _get_or_create(
            MeasureSource,
            code=code,
            defaults={"name": name, "is_active": True},
        )
        out[code] = src
    safe_commit()
    return out


def _ensure_users() -> dict[str, User]:
    """Создаёт тестовые учётки под роли. Идемпотентно."""
    users_data = [
        ("admin", "admin@example.com", "admin123", ROLE_ADMIN),
        ("doctor", "doctor@example.com", "doctor123", ROLE_DOCTOR),
        ("coach", "coach@example.com", "coach123", ROLE_COACH),
        ("operator", "operator@example.com", "operator123", ROLE_OPERATOR),
        ("user", "user@example.com", "user123", ROLE_USER),
    ]

    for username, email, password, role in users_data:
        u, created = _get_or_create(
            User,
            username=username,
            defaults={
                "email": email,
                "password_hash": generate_password_hash(password),
                "role": role,
                "is_active": True,
            },
        )
        if not created:
            changed = False
            if u.email != email and email:
                u.email = email
                changed = True
            if u.role != role and role:
                u.role = role
                changed = True
            if not u.password_hash:
                u.password_hash = generate_password_hash(password)
                changed = True
            if changed:
                db.session.add(u)

    safe_commit()

    return {
        "admin": User.query.filter_by(username="admin").first(),
        "doctor": User.query.filter_by(username="doctor").first(),
        "coach": User.query.filter_by(username="coach").first(),
        "operator": User.query.filter_by(username="operator").first(),
        "user": User.query.filter_by(username="user").first(),
    }


def _ensure_teams() -> dict[str, Team]:
    """Создаёт команды/группы (иерархия)."""
    club, _ = _get_or_create(Team, name="Спортивный клуб «Олимп»", defaults={"is_active": True})
    dept, _ = _get_or_create(Team, name="Отделение: Лёгкая атлетика", defaults={"parent": club, "is_active": True})
    group_a, _ = _get_or_create(Team, name="Группа А", defaults={"parent": dept, "is_active": True})
    group_b, _ = _get_or_create(Team, name="Группа Б", defaults={"parent": dept, "is_active": True})

    dept2, _ = _get_or_create(Team, name="Отделение: Плавание", defaults={"parent": club, "is_active": True})
    swim_a, _ = _get_or_create(Team, name="Плавание — Группа 1", defaults={"parent": dept2, "is_active": True})

    safe_commit()
    return {"club": club, "group_a": group_a, "group_b": group_b, "swim_a": swim_a}


def _ensure_indicator_categories() -> dict[str, IndicatorCategory]:
    """Создаёт категории показателей (иерархия)."""
    cardio, _ = _get_or_create(IndicatorCategory, name="Кардио")
    pressure, _ = _get_or_create(IndicatorCategory, name="Артериальное давление", defaults={"parent": cardio})
    resp, _ = _get_or_create(IndicatorCategory, name="Дыхание/сатурация", defaults={"parent": cardio})

    anthropo, _ = _get_or_create(IndicatorCategory, name="Антропометрия")
    sleep, _ = _get_or_create(IndicatorCategory, name="Сон/восстановление")
    temp_cat, _ = _get_or_create(IndicatorCategory, name="Температура")

    safe_commit()
    return {
        "cardio": cardio,
        "pressure": pressure,
        "resp": resp,
        "anthropo": anthropo,
        "sleep": sleep,
        "temp": temp_cat,
    }


def _ensure_indicators(cats: dict[str, IndicatorCategory]) -> list[Indicator]:
    """
    Создаёт показатели с нормами.
    Ищем по (name) — этого достаточно для учебного проекта.
    """
    indicators_data = [
        ("Пульс", "уд/мин", cats["cardio"], 50.0, 90.0),
        ("Систолическое АД", "мм рт. ст.", cats["pressure"], 90.0, 130.0),
        ("Диастолическое АД", "мм рт. ст.", cats["pressure"], 60.0, 85.0),
        ("SpO₂", "%", cats["resp"], 95.0, 100.0),
        ("Вес", "кг", cats["anthropo"], 55.0, 95.0),
        ("ИМТ", "", cats["anthropo"], 18.5, 27.0),
        ("Сон", "ч", cats["sleep"], 6.0, 9.0),
        ("Самочувствие", "балл", cats["sleep"], 1.0, 10.0),
        ("Температура тела", "°C", cats["temp"], 36.0, 37.5),
        ("Нагрузка (RPE)", "балл", cats["sleep"], 1.0, 10.0),
    ]

    for name, unit, cat, nmin, nmax in indicators_data:
        ind, created = _get_or_create(
            Indicator,
            name=name,
            defaults={
                "unit": unit,
                "category": cat,
                "norm_min": nmin,
                "norm_max": nmax,
                "is_active": True,
            },
        )
        if not created:
            changed = False
            if ind.unit != unit:
                ind.unit = unit
                changed = True
            if ind.category_id != (cat.id if cat else None):
                ind.category = cat
                changed = True
            if ind.norm_min != nmin:
                ind.norm_min = nmin
                changed = True
            if ind.norm_max != nmax:
                ind.norm_max = nmax
                changed = True
            if not ind.is_active:
                ind.is_active = True
                changed = True
            if changed:
                db.session.add(ind)

    safe_commit()
    return Indicator.query.filter_by(is_active=True).all()


def _ensure_athletes(teams: dict[str, Team]) -> list[Athlete]:
    """Создаёт спортсменов (раскидывает по командам)."""
    random.seed(42)

    names = [
        "Иванов Сергей", "Петров Андрей", "Сидорова Анна", "Кузнецова Мария", "Смирнов Илья",
        "Попова Елена", "Волков Артём", "Морозов Даниил", "Фёдорова Полина", "Никитин Максим",
        "Орлова Ксения", "Захаров Кирилл", "Беляев Роман", "Громова Виктория", "Ковалёв Никита",
    ]
    team_pool = [teams["group_a"], teams["group_b"], teams["swim_a"]]

    for full_name in names:
        team = random.choice(team_pool)
        year = random.randint(1996, 2010)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        bdate = date(year, month, day)

        a, created = _get_or_create(
            Athlete,
            full_name=full_name,
            defaults={
                "team": team,
                "birth_date": bdate,
                "gender": random.choice(["M", "F"]),
                "is_active": True,
                "notes": "Тестовый спортсмен (данные сформированы автоматически).",
            },
        )
        if not created:
            # лёгкая актуализация
            if a.team_id is None:
                a.team = team
                db.session.add(a)
            if a.is_active is None:
                a.is_active = True
                db.session.add(a)

    safe_commit()
    return Athlete.query.filter_by(is_active=True).all()


def _ensure_some_individual_norms(athletes: list[Athlete], indicators: list[Indicator]) -> None:
    """
    Создаём немного индивидуальных норм (чтобы таблица точно не была пустой).
    Например: для 2 спортсменов чуть сузим нормы "Пульс" и "Сон".
    """
    if AthleteIndicatorNorm.query.first():
        return

    by_name = {i.name: i for i in indicators}
    pulse = by_name.get("Пульс")
    sleep = by_name.get("Сон")

    if not athletes or not pulse:
        return

    sample = athletes[:2] if len(athletes) >= 2 else athletes[:1]

    for idx, ath in enumerate(sample):
        # пульс — индивидуальная норма
        if pulse:
            _get_or_create(
                AthleteIndicatorNorm,
                athlete_id=ath.id,
                indicator_id=pulse.id,
                defaults={
                    "norm_min": 52.0 + idx,   # чуть варьируем
                    "norm_max": 85.0 + idx,
                    "comment": "Индивидуальная норма (пример).",
                    "is_active": True,
                },
            )

        # сон — индивидуальная норма
        if sleep:
            _get_or_create(
                AthleteIndicatorNorm,
                athlete_id=ath.id,
                indicator_id=sleep.id,
                defaults={
                    "norm_min": 6.5,
                    "norm_max": 8.5,
                    "comment": "Норма сна для данного спортсмена (пример).",
                    "is_active": True,
                },
            )

    safe_commit()


def _value_in_range(nmin: Optional[float], nmax: Optional[float]) -> float:
    """
    Генерация значения "в целом в норме" вокруг середины диапазона.
    """
    if nmin is None or nmax is None:
        return random.uniform(0.0, 1.0)
    mid = (float(nmin) + float(nmax)) / 2.0
    span = (float(nmax) - float(nmin)) / 2.0
    return random.uniform(mid - span * 0.6, mid + span * 0.6)


def _make_anomaly(value: float, nmin: Optional[float], nmax: Optional[float]) -> float:
    """
    Сделать значение аномальным (за пределами нормы), если нормы заданы.
    """
    if nmin is None or nmax is None:
        return value
    if random.random() < 0.5:
        return float(nmin) - random.uniform(0.5, 10.0)
    return float(nmax) + random.uniform(0.5, 10.0)


def _round_value(ind: Indicator, v: float) -> float:
    if ind.name in ("Температура тела",):
        return round(v, 1)
    if ind.name in ("Вес", "ИМТ"):
        return round(v, 2)
    if ind.unit in ("%","уд/мин","мм рт. ст."):
        return round(v, 0)
    return round(v, 1)


def _compute_alert_level(value: float, nmin: Optional[float], nmax: Optional[float]) -> Optional[str]:
    if nmin is not None and value < nmin:
        return ALERT_LEVEL_LOW
    if nmax is not None and value > nmax:
        return ALERT_LEVEL_HIGH
    return None


def _ensure_measurements_and_alerts(
    athletes: list[Athlete],
    indicators: list[Indicator],
    sources: dict[str, MeasureSource],
    created_by: Optional[User],
) -> None:
    """
    Создаёт измерения (если их нет) + алерты.
    Если измерения уже есть, но алертов нет — создаёт алерты для части отклонений.
    """
    random.seed(42)

    have_measurements = Measurement.query.first() is not None
    have_alerts = Alert.query.first() is not None

    # Если измерения есть, но алертов нет — просто добьём алерты и выйдем
    if have_measurements and not have_alerts:
        # создадим алерты по отклонениям на небольшом сэмпле
        q = (
            Measurement.query
            .order_by(Measurement.measured_at.desc())
            .limit(500)
            .all()
        )
        created = 0
        for m in q:
            if m.alert is not None:
                continue
            # нормы с учётом индивидуальных
            nmin, nmax = resolve_norm_for(m.athlete, m.indicator)
            level = _compute_alert_level(m.value, nmin, nmax)
            if not level:
                continue

            a = Alert(measurement=m, level=level, status=ALERT_STATUS_OPEN)
            db.session.add(a)
            created += 1
            if created >= 40:
                break
        safe_commit()
        return

    # Если измерений нет — генерим полный набор
    if not have_measurements:
        now = datetime.utcnow()
        period_days = 60
        points_per_indicator = 14
        anomaly_prob = 0.10

        out_of_range_measurements: list[Measurement] = []

        for ath in athletes:
            for ind in indicators:
                for _ in range(points_per_indicator):
                    dt = now - timedelta(
                        days=random.randint(0, period_days),
                        hours=random.randint(0, 23),
                        minutes=random.randint(0, 59),
                    )

                    # норма с учётом индивидуальной
                    nmin, nmax = resolve_norm_for(ath, ind)

                    v = _value_in_range(nmin, nmax)
                    if random.random() < anomaly_prob:
                        v = _make_anomaly(v, nmin, nmax)

                    v = _round_value(ind, v)

                    src = sources[SOURCE_CODE_MANUAL]
                    m = Measurement(
                        athlete=ath,
                        indicator=ind,
                        measured_at=dt,
                        value=v,
                        source=src,
                        created_by=created_by,
                        comment=None,
                    )
                    db.session.add(m)

                    level = _compute_alert_level(v, nmin, nmax)
                    if level:
                        out_of_range_measurements.append(m)

        safe_commit()

        # Создадим Alerts по сэмплу отклонений (не на все, чтобы не перегружать)
        random.shuffle(out_of_range_measurements)
        for m in out_of_range_measurements[:120]:
            if m.alert is None:
                nmin, nmax = resolve_norm_for(m.athlete, m.indicator)
                level = _compute_alert_level(m.value, nmin, nmax)
                if level:
                    db.session.add(Alert(measurement=m, level=level, status=ALERT_STATUS_OPEN))
        safe_commit()

        # Часть алертов закроем (для демонстрации)
        open_alerts = Alert.query.filter_by(status=ALERT_STATUS_OPEN).limit(12).all()
        for a in open_alerts[:6]:
            a.status = ALERT_STATUS_CLOSED
            a.closed_at = datetime.utcnow()
            a.closed_by = created_by
            a.note = "Закрыто автоматически (пример)."
            db.session.add(a)
        safe_commit()


def _ensure_feedback(users: dict[str, User]) -> None:
    """
    Создаём несколько записей feedback (заметки/инциденты/обращения).
    """
    if Feedback.query.first():
        return

    doctor = users.get("doctor") or users.get("admin")
    user = users.get("user")

    ath = Athlete.query.order_by(Athlete.id.asc()).first()
    if not ath:
        return

    db.session.add(
        Feedback(
            athlete=ath,
            author=doctor,
            kind=FEEDBACK_KIND_NOTE,
            status=ALERT_STATUS_OPEN,
            title="План наблюдения",
            message="Рекомендуется отслеживать пульс и сон в течение 2 недель.",
        )
    )

    # Инцидент по алерту, если есть
    alert = Alert.query.order_by(Alert.created_at.desc()).first()
    if alert:
        m = alert.measurement
        db.session.add(
            Feedback(
                athlete=m.athlete,
                author=doctor,
                kind=FEEDBACK_KIND_INCIDENT,
                status=ALERT_STATUS_OPEN,
                title=f"Отклонение: {m.indicator.name}",
                message=f"Зафиксировано отклонение ({m.value} {m.indicator.unit or ''}) от нормы. Дата: {m.measured_at:%Y-%m-%d %H:%M}.",
            )
        )

    # Публичное обращение (как будто от гостя/пользователя)
    db.session.add(
        Feedback(
            athlete=None,
            author=user,
            kind=FEEDBACK_KIND_REQUEST,
            status=ALERT_STATUS_OPEN,
            title="Вопрос по системе",
            message="Где посмотреть историю измерений по спортсмену?",
        )
    )

    safe_commit()


def _ensure_export_batches(users: dict[str, User]) -> None:
    """Создаём пару записей истории экспорта (export_batches)."""
    if ExportBatch.query.first():
        return

    operator = users.get("operator") or users.get("admin")
    now = datetime.utcnow()

    b1 = ExportBatch(
        created_by=operator,
        created_at=now - timedelta(days=2),
        period_from=now - timedelta(days=30),
        period_to=now - timedelta(days=1),
        rows_count=180,
        filename="export_measurements_30d.csv",
        comment="Экспорт журнала измерений за 30 дней (пример).",
    )
    b2 = ExportBatch(
        created_by=operator,
        created_at=now - timedelta(days=1),
        period_from=now - timedelta(days=7),
        period_to=now,
        rows_count=55,
        filename="export_alerts_7d.csv",
        comment="Экспорт отклонений за 7 дней (пример).",
    )
    db.session.add_all([b1, b2])
    safe_commit()


def _ensure_audit_log(users: dict[str, User]) -> None:
    """Заполняем audit_log несколькими событиями (для демонстрации)."""
    if AuditLog.query.first():
        return

    admin = users.get("admin")
    operator = users.get("operator") or admin

    items = [
        AuditLog(
            user=admin,
            action="login",
            entity="user",
            entity_id=admin.id if admin else None,
            details_json=json.dumps({"username": "admin"}, ensure_ascii=False),
        ),
        AuditLog(
            user=operator,
            action="export",
            entity="export_batches",
            entity_id=None,
            details_json=json.dumps({"format": "csv", "target": "1c"}, ensure_ascii=False),
        ),
        AuditLog(
            user=operator,
            action="create",
            entity="measurement",
            entity_id=None,
            details_json=json.dumps({"source": SOURCE_CODE_MANUAL}, ensure_ascii=False),
        ),
    ]
    db.session.add_all(items)
    safe_commit()


def seed_db() -> None:
    """
    Заполняет БД тестовыми данными (идемпотентно).
    Вызывается после db.create_all().

    Создаём/обеспечиваем:
    - users (5 ролей)
    - teams
    - indicator_categories
    - indicators
    - measure_sources
    - athletes
    - athlete_indicator_norms (немного)
    - measurements (если пусто)
    - alerts (если пусто)
    - feedback (если пусто)
    - export_batches (если пусто)
    - audit_log (если пусто)
    """
    users = _ensure_users()
    teams = _ensure_teams()
    cats = _ensure_indicator_categories()
    indicators = _ensure_indicators(cats)
    sources = _ensure_sources()
    athletes = _ensure_athletes(teams)

    coach = users.get("coach")
    coach_team = teams.get("group_a")
    if coach and coach_team and coach_team.coach_id != coach.id:
        coach_team.coach = coach
        db.session.add(coach_team)

    demo_user = users.get("user")
    if demo_user:
        linked = Athlete.query.filter_by(user_id=demo_user.id).first()
        if not linked and athletes:
            linked = athletes[0]
            linked.user = demo_user
            if not linked.team_id and coach_team:
                linked.team = coach_team
            db.session.add(linked)

    safe_commit()

    _ensure_some_individual_norms(athletes, indicators)

    created_by = users.get("operator") or users.get("coach") or users.get("doctor") or users.get("admin")

    _ensure_measurements_and_alerts(
        athletes=athletes,
        indicators=indicators,
        sources=sources,
        created_by=created_by,
    )

    _ensure_feedback(users)
    _ensure_export_batches(users)
    _ensure_audit_log(users)
