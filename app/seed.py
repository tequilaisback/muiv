# app/seed.py
from __future__ import annotations

import random
from datetime import datetime, timedelta, date
from typing import Optional

from werkzeug.security import generate_password_hash

from .db import db
from .models import (
    User,
    Team,
    IndicatorCategory,
    Athlete,
    Indicator,
    Measurement,
    Feedback,
    ROLE_ADMIN,
    ROLE_DOCTOR,
    ROLE_COACH,
    ROLE_OPERATOR,
    ROLE_USER,
    MEASURE_SOURCE_MANUAL,
)


def _get_or_create(model, defaults: Optional[dict] = None, **kwargs):
    """
    Простой get_or_create для SQLAlchemy.
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


def seed_db() -> None:
    """
    Заполняет БД тестовыми данными (идемпотентно).
    Вызывается из create_app() после db.create_all().

    Что создаём:
    - Пользователи (admin/doctor/coach/operator/user)
    - Команды/группы (Team) с иерархией
    - Категории показателей (IndicatorCategory) с иерархией
    - Показатели (Indicator) с нормами
    - Спортсмены (Athlete)
    - Измерения (Measurement) за последние ~60 дней
    - Несколько заметок/инцидентов (Feedback)
    """
    random.seed(42)

    # ---- users ----
    users_data = [
        ("admin", "admin@example.com", "admin123", ROLE_ADMIN),
        ("doctor", "doctor@example.com", "doctor123", ROLE_DOCTOR),
        ("coach", "coach@example.com", "coach123", ROLE_COACH),
        ("operator", "operator@example.com", "operator123", ROLE_OPERATOR),
        ("user", "user@example.com", "user123", ROLE_USER),
    ]

    created_any = False
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
        # если юзер уже был, но роль/почта пустые — подправим
        if not created:
            changed = False
            if not u.email and email:
                u.email = email
                changed = True
            if not u.role and role:
                u.role = role
                changed = True
            if changed:
                db.session.add(u)
        created_any = created_any or created

    db.session.commit()

    admin = User.query.filter_by(username="admin").first()
    doctor = User.query.filter_by(username="doctor").first()
    coach = User.query.filter_by(username="coach").first()
    operator = User.query.filter_by(username="operator").first()

    # ---- teams (иерархия) ----
    club, _ = _get_or_create(Team, name="Спортивный клуб «Олимп»")
    dept, _ = _get_or_create(Team, name="Отделение: Лёгкая атлетика", defaults={"parent": club})
    group_a, _ = _get_or_create(Team, name="Группа А", defaults={"parent": dept})
    group_b, _ = _get_or_create(Team, name="Группа Б", defaults={"parent": dept})

    dept2, _ = _get_or_create(Team, name="Отделение: Плавание", defaults={"parent": club})
    swim_a, _ = _get_or_create(Team, name="Плавание — Группа 1", defaults={"parent": dept2})

    db.session.commit()

    # ---- indicator categories (иерархия) ----
    cardio, _ = _get_or_create(IndicatorCategory, name="Кардио")
    pressure, _ = _get_or_create(IndicatorCategory, name="Артериальное давление", defaults={"parent": cardio})
    respiration, _ = _get_or_create(IndicatorCategory, name="Дыхание/сатурация", defaults={"parent": cardio})

    anthropo, _ = _get_or_create(IndicatorCategory, name="Антропометрия")
    sleep, _ = _get_or_create(IndicatorCategory, name="Сон/восстановление")
    temp_cat, _ = _get_or_create(IndicatorCategory, name="Температура")

    db.session.commit()

    # ---- indicators ----
    indicators_data = [
        # name, unit, category, norm_min, norm_max
        ("Пульс", "уд/мин", cardio, 50.0, 90.0),
        ("Систолическое АД", "мм рт. ст.", pressure, 90.0, 130.0),
        ("Диастолическое АД", "мм рт. ст.", pressure, 60.0, 85.0),
        ("SpO₂", "%", respiration, 95.0, 100.0),
        ("Вес", "кг", anthropo, 55.0, 95.0),
        ("ИМТ", "", anthropo, 18.5, 27.0),
        ("Сон", "ч", sleep, 6.0, 9.0),
        ("Самочувствие", "балл", sleep, 1.0, 10.0),
        ("Температура тела", "°C", temp_cat, 36.0, 37.5),
        ("Нагрузка (RPE)", "балл", sleep, 1.0, 10.0),
    ]

    for name, unit, cat, nmin, nmax in indicators_data:
        _get_or_create(
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

    db.session.commit()

    indicators = Indicator.query.filter_by(is_active=True).all()
    teams = [group_a, group_b, swim_a]

    # ---- athletes ----
    names = [
        "Иванов Сергей", "Петров Андрей", "Сидорова Анна", "Кузнецова Мария", "Смирнов Илья",
        "Попова Елена", "Волков Артём", "Морозов Даниил", "Фёдорова Полина", "Никитин Максим",
        "Орлова Ксения", "Захаров Кирилл", "Беляев Роман", "Громова Виктория", "Ковалёв Никита",
    ]

    for full_name in names:
        # распределим по командам
        team = random.choice(teams)
        # возраст 16-30 (примерно)
        year = random.randint(1996, 2010)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        bdate = date(year, month, day)

        _get_or_create(
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

    db.session.commit()

    athletes = Athlete.query.filter_by(is_active=True).all()

    # ---- measurements ----
    # Если измерения уже есть — не плодим заново (обычно достаточно)
    if Measurement.query.first():
        return

    now = datetime.utcnow()
    period_days = 60
    points_per_indicator = 18  # на каждого спортсмена на каждый показатель

    # вероятность "аномалии" (вылет за норму), чтобы были отклонения
    anomaly_prob = 0.10

    def gen_value(ind: Indicator) -> float:
        # базовое значение в норме
        if ind.norm_min is not None and ind.norm_max is not None:
            mid = (float(ind.norm_min) + float(ind.norm_max)) / 2.0
            span = (float(ind.norm_max) - float(ind.norm_min)) / 2.0
            v = random.uniform(mid - span * 0.6, mid + span * 0.6)
        else:
            v = random.uniform(0.0, 1.0)

        # иногда делаем аномалию
        if ind.norm_min is not None and ind.norm_max is not None and random.random() < anomaly_prob:
            if random.random() < 0.5:
                v = float(ind.norm_min) - random.uniform(0.5, 10.0)
            else:
                v = float(ind.norm_max) + random.uniform(0.5, 10.0)

        # округление под типы
        if ind.name in ("Температура тела",):
            return round(v, 1)
        if ind.name in ("Вес", "ИМТ"):
            return round(v, 2)
        if ind.unit in ("%","уд/мин","мм рт. ст."):
            return round(v, 0)
        return round(v, 1)

    created_by = operator or coach or doctor or admin

    out_of_range_samples = []  # чтобы потом сделать несколько Feedback

    for athlete in athletes:
        for ind in indicators:
            for _ in range(points_per_indicator):
                # случайная дата в диапазоне period_days
                dt = now - timedelta(days=random.randint(0, period_days),
                                    hours=random.randint(0, 23),
                                    minutes=random.randint(0, 59))
                val = gen_value(ind)

                m = Measurement(
                    athlete=athlete,
                    indicator=ind,
                    measured_at=dt,
                    value=val,
                    source=MEASURE_SOURCE_MANUAL,
                    created_by=created_by,
                    comment=None,
                )
                db.session.add(m)

                # пометим для заметок
                if ind.is_out_of_range(val):
                    out_of_range_samples.append((athlete, ind, dt, val))

    db.session.commit()

    # ---- feedback (заметки/инциденты) ----
    # создадим несколько инцидентов по реальным "аномальным" точкам
    random.shuffle(out_of_range_samples)
    for i, (athlete, ind, dt, val) in enumerate(out_of_range_samples[:12], start=1):
        fb = Feedback(
            athlete=athlete,
            author=doctor or coach or admin,
            kind="incident",
            status="open",
            title=f"Отклонение: {ind.name}",
            message=(
                f"Зафиксировано отклонение показателя '{ind.name}' "
                f"({val} {ind.unit or ''}) от нормы. Дата/время: {dt:%Y-%m-%d %H:%M}."
            ),
        )
        db.session.add(fb)

    db.session.commit()
