# app/models.py
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from .db import db

db = SQLAlchemy()


# -------------------------
# Константы (удобно и читаемо)
# -------------------------
ROLE_ADMIN = "admin"
ROLE_DOCTOR = "doctor"
ROLE_COACH = "coach"
ROLE_OPERATOR = "operator"
ROLE_USER = "user"

MEASURE_SOURCE_MANUAL = "manual"       # введено вручную в веб-кабинете
MEASURE_SOURCE_CSV = "csv"             # импорт из CSV (например из Excel/устройства)
MEASURE_SOURCE_DEVICE = "device"       # условное устройство/датчик
MEASURE_SOURCE_1C = "1c"               # пришло/прошло через 1С


# -------------------------
# Пользователь (врач/тренер/админ и т.д.)
# -------------------------
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)

    # Пароль: можно хранить как hash (рекомендовано), но ты сам решишь в auth.py
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(32), nullable=False, default=ROLE_USER, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # связи
    measurements_created = db.relationship(
        "Measurement",
        back_populates="created_by",
        cascade="all, delete-orphan",
        lazy="select",
    )

    feedback_created = db.relationship(
        "Feedback",
        back_populates="author",
        cascade="all, delete-orphan",
        lazy="select",
    )

    exports_created = db.relationship(
        "ExportBatch",
        back_populates="created_by",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


# -------------------------
# Иерархические справочники (на будущее)
# -------------------------
class Team(db.Model):
    """
    Команда/группа спортсменов (иерархическая структура: клуб -> отделение -> группа).
    """
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)

    parent_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)
    parent = db.relationship("Team", remote_side=[id], backref="children")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name!r}>"


class IndicatorCategory(db.Model):
    """
    Категория показателей (иерархическая: 'Кардио' -> 'Пульс', 'Сон' -> 'Длительность').
    """
    __tablename__ = "indicator_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)

    parent_id = db.Column(db.Integer, db.ForeignKey("indicator_categories.id"), nullable=True)
    parent = db.relationship("IndicatorCategory", remote_side=[id], backref="children")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<IndicatorCategory id={self.id} name={self.name!r}>"


# -------------------------
# Спортсмен
# -------------------------
class Athlete(db.Model):
    __tablename__ = "athletes"

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(db.String(180), nullable=False, index=True)
    birth_date = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(16), nullable=True)  # "M"/"F"/"other" — как решишь

    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)
    team = db.relationship("Team", lazy="select")

    # Доп. инфа (по желанию)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    measurements = db.relationship(
        "Measurement",
        back_populates="athlete",
        cascade="all, delete-orphan",
        lazy="select",
    )

    feedback = db.relationship(
        "Feedback",
        back_populates="athlete",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @property
    def age(self) -> Optional[int]:
        if not self.birth_date:
            return None
        today = date.today()
        years = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

    def __repr__(self) -> str:
        return f"<Athlete id={self.id} full_name={self.full_name!r}>"


# -------------------------
# Показатель здоровья (пульс, вес, давление, сон...)
# -------------------------
class Indicator(db.Model):
    __tablename__ = "indicators"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False, index=True)
    unit = db.Column(db.String(32), nullable=True)  # "уд/мин", "кг", "мм рт.ст.", "ч"...

    category_id = db.Column(db.Integer, db.ForeignKey("indicator_categories.id"), nullable=True)
    category = db.relationship("IndicatorCategory", lazy="select")

    # Нормативы (для простоты в модели; позже можно вынести в отдельную таблицу)
    norm_min = db.Column(db.Float, nullable=True)
    norm_max = db.Column(db.Float, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    measurements = db.relationship(
        "Measurement",
        back_populates="indicator",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def is_out_of_range(self, value: float) -> bool:
        if self.norm_min is not None and value < self.norm_min:
            return True
        if self.norm_max is not None and value > self.norm_max:
            return True
        return False

    def __repr__(self) -> str:
        return f"<Indicator id={self.id} name={self.name!r} unit={self.unit!r}>"


# -------------------------
# Измерение (основная “журналируемая” сущность)
# -------------------------
class Measurement(db.Model):
    __tablename__ = "measurements"

    id = db.Column(db.Integer, primary_key=True)

    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id"), nullable=False, index=True)
    indicator_id = db.Column(db.Integer, db.ForeignKey("indicators.id"), nullable=False, index=True)

    measured_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    value = db.Column(db.Float, nullable=False)

    source = db.Column(db.String(32), nullable=False, default=MEASURE_SOURCE_MANUAL, index=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    comment = db.Column(db.String(255), nullable=True)

    athlete = db.relationship("Athlete", back_populates="measurements", lazy="select")
    indicator = db.relationship("Indicator", back_populates="measurements", lazy="select")
    created_by = db.relationship("User", back_populates="measurements_created", lazy="select")

    @property
    def out_of_range(self) -> bool:
        # если индикатора нет — не бывает, но на всякий
        if not self.indicator:
            return False
        return self.indicator.is_out_of_range(self.value)

    def __repr__(self) -> str:
        return (
            f"<Measurement id={self.id} athlete_id={self.athlete_id} "
            f"indicator_id={self.indicator_id} value={self.value} at={self.measured_at}>"
        )


# -------------------------
# "Feedback" обновляем: теперь это обращения/заметки (врач/тренер -> по спортсмену)
# -------------------------
class Feedback(db.Model):
    """
    Единая сущность для:
    - заметок врача/тренера
    - обращений/комментариев
    - фиксации событий (например: "подозрение на перегрузку")
    """
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)

    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id"), nullable=True, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    kind = db.Column(db.String(32), nullable=False, default="note", index=True)   # note/request/incident
    status = db.Column(db.String(32), nullable=False, default="open", index=True) # open/closed

    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)

    athlete = db.relationship("Athlete", back_populates="feedback", lazy="select")
    author = db.relationship("User", back_populates="feedback_created", lazy="select")

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} kind={self.kind!r} status={self.status!r}>"


# -------------------------
# Журнал экспорта в 1С (опционально, но полезно)
# -------------------------
class ExportBatch(db.Model):
    __tablename__ = "export_batches"

    id = db.Column(db.Integer, primary_key=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_by = db.relationship("User", back_populates="exports_created", lazy="select")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    period_from = db.Column(db.DateTime, nullable=True)
    period_to = db.Column(db.DateTime, nullable=True)

    rows_count = db.Column(db.Integer, nullable=False, default=0)
    filename = db.Column(db.String(255), nullable=True)

    comment = db.Column(db.String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<ExportBatch id={self.id} rows={self.rows_count} created_at={self.created_at}>"
