# app/models.py
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from flask_login import UserMixin

# ВАЖНО: используем ЕДИНСТВЕННЫЙ db из app/db.py, второй SQLAlchemy() тут НЕ создаём!
from .db import db


# -------------------------
# Константы (удобно и читаемо)
# -------------------------
ROLE_ADMIN = "admin"
ROLE_DOCTOR = "doctor"
ROLE_COACH = "coach"
ROLE_OPERATOR = "operator"
ROLE_USER = "user"

ALERT_LEVEL_LOW = "low"
ALERT_LEVEL_HIGH = "high"

ALERT_STATUS_OPEN = "open"
ALERT_STATUS_CLOSED = "closed"

FEEDBACK_KIND_REQUEST = "request"
FEEDBACK_KIND_NOTE = "note"
FEEDBACK_KIND_INCIDENT = "incident"

SOURCE_CODE_MANUAL = "manual"
SOURCE_CODE_CSV = "csv"
SOURCE_CODE_DEVICE = "device"
SOURCE_CODE_1C = "1c"

GENDER_M = "M"
GENDER_F = "F"


# -------------------------
# Пользователь (врач/тренер/админ и т.д.)
# -------------------------
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)

    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(32), nullable=False, default=ROLE_USER, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # связи
    measurements_created = db.relationship(
        "Measurement",
        back_populates="created_by",
        lazy="select",
    )

    feedback_created = db.relationship(
        "Feedback",
        back_populates="author",
        lazy="select",
    )

    exports_created = db.relationship(
        "ExportBatch",
        back_populates="created_by",
        lazy="select",
    )

    alerts_closed = db.relationship(
        "Alert",
        back_populates="closed_by",
        lazy="select",
        foreign_keys="Alert.closed_by_id",
    )

    audit_events = db.relationship(
        "AuditLog",
        back_populates="user",
        lazy="select",
    )

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


# -------------------------
# Команда/группа спортсменов (иерархия)
# -------------------------
class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)

    parent_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True)
    parent = db.relationship("Team", remote_side=[id], backref="children")

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    athletes = db.relationship("Athlete", back_populates="team", lazy="select")

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name!r}>"


# -------------------------
# Категория показателей (иерархия)
# -------------------------
class IndicatorCategory(db.Model):
    __tablename__ = "indicator_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)

    parent_id = db.Column(db.Integer, db.ForeignKey("indicator_categories.id"), nullable=True)
    parent = db.relationship("IndicatorCategory", remote_side=[id], backref="children")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    indicators = db.relationship("Indicator", back_populates="category", lazy="select")

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
    gender = db.Column(db.String(16), nullable=True)  # "M"/"F"/etc

    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True, index=True)
    team = db.relationship("Team", back_populates="athletes", lazy="select")

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
        lazy="select",
    )

    norms = db.relationship(
        "AthleteIndicatorNorm",
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
# Показатель здоровья
# -------------------------
class Indicator(db.Model):
    __tablename__ = "indicators"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False, index=True)
    unit = db.Column(db.String(32), nullable=True)

    category_id = db.Column(db.Integer, db.ForeignKey("indicator_categories.id"), nullable=True, index=True)
    category = db.relationship("IndicatorCategory", back_populates="indicators", lazy="select")

    # "общая" норма по показателю (если нет индивидуальной)
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

    norms = db.relationship(
        "AthleteIndicatorNorm",
        back_populates="indicator",
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
# Источник измерений (справочник) — ВАЖНО: отдельная таблица (для 10+)
# -------------------------
class MeasureSource(db.Model):
    __tablename__ = "measure_sources"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)  # manual/csv/device/1c
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    measurements = db.relationship("Measurement", back_populates="source", lazy="select")

    def __repr__(self) -> str:
        return f"<MeasureSource id={self.id} code={self.code!r}>"


# -------------------------
# Индивидуальные нормы (спортсмен + показатель)
# -------------------------
class AthleteIndicatorNorm(db.Model):
    __tablename__ = "athlete_indicator_norms"

    id = db.Column(db.Integer, primary_key=True)

    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id"), nullable=False, index=True)
    indicator_id = db.Column(db.Integer, db.ForeignKey("indicators.id"), nullable=False, index=True)

    norm_min = db.Column(db.Float, nullable=True)
    norm_max = db.Column(db.Float, nullable=True)

    comment = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    athlete = db.relationship("Athlete", back_populates="norms", lazy="select")
    indicator = db.relationship("Indicator", back_populates="norms", lazy="select")

    __table_args__ = (
        db.UniqueConstraint("athlete_id", "indicator_id", name="uq_athlete_indicator_norm"),
    )

    def __repr__(self) -> str:
        return f"<AthleteIndicatorNorm athlete_id={self.athlete_id} indicator_id={self.indicator_id}>"


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

    # FK на справочник источников
    source_id = db.Column(db.Integer, db.ForeignKey("measure_sources.id"), nullable=True, index=True)
    source = db.relationship("MeasureSource", back_populates="measurements", lazy="select")

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    comment = db.Column(db.String(255), nullable=True)

    athlete = db.relationship("Athlete", back_populates="measurements", lazy="select")
    indicator = db.relationship("Indicator", back_populates="measurements", lazy="select")
    created_by = db.relationship("User", back_populates="measurements_created", lazy="select")

    alert = db.relationship(
        "Alert",
        back_populates="measurement",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<Measurement id={self.id} athlete_id={self.athlete_id} "
            f"indicator_id={self.indicator_id} value={self.value} at={self.measured_at}>"
        )


# -------------------------
# Alert: зафиксированное отклонение (чтобы “Отклонения” было таблицей, а не фильтром)
# -------------------------
class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)

    measurement_id = db.Column(db.Integer, db.ForeignKey("measurements.id"), nullable=False, unique=True, index=True)
    measurement = db.relationship("Measurement", back_populates="alert", lazy="select")

    level = db.Column(db.String(16), nullable=False, index=True)  # low/high
    status = db.Column(db.String(16), nullable=False, default=ALERT_STATUS_OPEN, index=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    closed_by = db.relationship("User", back_populates="alerts_closed", lazy="select", foreign_keys=[closed_by_id])

    note = db.Column(db.String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Alert id={self.id} level={self.level!r} status={self.status!r}>"


# -------------------------
# Feedback: обращения/заметки/инциденты
# -------------------------
class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)

    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id"), nullable=True, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    kind = db.Column(db.String(32), nullable=False, default=FEEDBACK_KIND_NOTE, index=True)
    status = db.Column(db.String(32), nullable=False, default=ALERT_STATUS_OPEN, index=True)  # open/closed

    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    closed_at = db.Column(db.DateTime, nullable=True)

    athlete = db.relationship("Athlete", back_populates="feedback", lazy="select")
    author = db.relationship("User", back_populates="feedback_created", lazy="select")

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} kind={self.kind!r} status={self.status!r}>"


# -------------------------
# Журнал экспорта в 1С (CSV)
# -------------------------
class ExportBatch(db.Model):
    __tablename__ = "export_batches"

    id = db.Column(db.Integer, primary_key=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_by = db.relationship("User", back_populates="exports_created", lazy="select")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    period_from = db.Column(db.DateTime, nullable=True)
    period_to = db.Column(db.DateTime, nullable=True)

    rows_count = db.Column(db.Integer, nullable=False, default=0)
    filename = db.Column(db.String(255), nullable=True)

    comment = db.Column(db.String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<ExportBatch id={self.id} rows={self.rows_count} created_at={self.created_at}>"


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    user = db.relationship("User", back_populates="audit_events", lazy="select")

    action = db.Column(db.String(64), nullable=False, index=True)  # e.g. create/update/delete/export/login
    entity = db.Column(db.String(64), nullable=True, index=True)   # e.g. athlete/measurement/indicator
    entity_id = db.Column(db.Integer, nullable=True, index=True)

    details_json = db.Column(db.Text, nullable=True)  # можно хранить JSON строкой

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action!r} entity={self.entity!r}>"



def resolve_norm_for(athlete: Athlete, indicator: Indicator) -> tuple[Optional[float], Optional[float]]:
    """
    Возвращает (min, max) для спортсмена по показателю:
    - если есть активная индивидуальная норма -> она
    - иначе -> общая норма показателя
    """
    # Простой поиск по подгруженной коллекции (если athlete.norms уже есть)
    for n in getattr(athlete, "norms", []) or []:
        if n.is_active and n.indicator_id == indicator.id:
            return n.norm_min, n.norm_max
    return indicator.norm_min, indicator.norm_max
