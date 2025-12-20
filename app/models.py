# app/models.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from werkzeug.security import generate_password_hash, check_password_hash

from .db import db


# -----------------------------
# Константы ролей (минимум 3)
# -----------------------------
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_USER = "user"

ALL_ROLES = {ROLE_ADMIN, ROLE_MANAGER, ROLE_USER}


# -----------------------------
# Модели
# -----------------------------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    login = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    full_name = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), nullable=False, default=ROLE_USER, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    feedback_items = db.relationship(
        "Feedback",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def is_manager(self) -> bool:
        return self.role == ROLE_MANAGER

    def __repr__(self) -> str:
        return f"<User id={self.id} login={self.login!r} role={self.role!r} active={self.is_active}>"


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    products = db.relationship(
        "Product",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} active={self.is_active}>"


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)

    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)

    name = db.Column(db.String(160), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)

    # В SQLite Numeric хранится нормально для учебного проекта; при необходимости округляем на выводе
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # для витрины/акций
    discount_percent = db.Column(db.Integer, nullable=False, default=0, index=True)  # 0..99
    is_featured = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # если потом добавишь загрузку изображений — тут будет имя файла
    image_filename = db.Column(db.String(255), nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    category = db.relationship("Category", back_populates="products", lazy="select")

    @property
    def price_value(self) -> Decimal:
        # удобный Decimal для вычислений/вывода
        val = self.price if self.price is not None else Decimal("0")
        try:
            return Decimal(val)
        except Exception:
            return Decimal(str(val))

    @property
    def final_price(self) -> Decimal:
        """Цена с учётом скидки."""
        p = self.price_value
        d = int(self.discount_percent or 0)
        if d <= 0:
            return p
        if d >= 99:
            d = 99
        return (p * (Decimal("100") - Decimal(d)) / Decimal("100")).quantize(Decimal("0.01"))

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r} price={self.price} disc={self.discount_percent}%>"


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)

    # можно анонимно, но если пользователь авторизован — привяжем
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    subject = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(20), nullable=False, default="new", index=True)  # new / processed
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    user = db.relationship("User", back_populates="feedback_items", lazy="select")

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} email={self.email!r} status={self.status!r}>"


# -----------------------------
# Быстрая валидация (опционально)
# -----------------------------
def validate_role(role: str) -> str:
    role = (role or "").strip().lower()
    if role not in ALL_ROLES:
        return ROLE_USER
    return role
