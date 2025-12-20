# app/seed.py
from __future__ import annotations

from decimal import Decimal

from .db import db
from .models import Category, Feedback, Product, User, ROLE_ADMIN, ROLE_MANAGER, ROLE_USER


def seed_db() -> dict:
    """
    Заполняет БД начальными данными (идемпотентно: не дублирует при повторном запуске).

    Создаёт:
    - 3 пользователя (admin/manager/user)
    - категории
    - товары (часть со скидками и "featured" для витрины)
    - 1-2 записи обратной связи (для проверки админки)

    Возвращает статистику, сколько объектов было добавлено.
    """
    stats = {"users": 0, "categories": 0, "products": 0, "feedback": 0}

    # ----------------------------
    # Пользователи (минимум 3 роли)
    # ----------------------------
    def _ensure_user(login: str, password: str, full_name: str, role: str) -> None:
        nonlocal stats
        u = db.session.query(User).filter_by(login=login).first()
        if u:
            return
        u = User(login=login, full_name=full_name, role=role, is_active=True)
        u.set_password(password)
        db.session.add(u)
        stats["users"] += 1

    _ensure_user("admin", "admin123", "Администратор системы", ROLE_ADMIN)
    _ensure_user("manager", "manager123", "Менеджер каталога", ROLE_MANAGER)
    _ensure_user("user", "user123", "Тестовый пользователь", ROLE_USER)

    db.session.commit()

    # ----------------------------
    # Категории
    # ----------------------------
    def _ensure_category(name: str, description: str | None = None) -> Category:
        nonlocal stats
        c = db.session.query(Category).filter_by(name=name).first()
        if c:
            return c
        c = Category(name=name, description=description, is_active=True)
        db.session.add(c)
        db.session.flush()  # получаем id без commit
        stats["categories"] += 1
        return c

    cat_electronics = _ensure_category("Электроника", "Товары для дома и офиса: техника и аксессуары.")
    cat_stationery = _ensure_category("Канцтовары", "Бумага, ручки, папки и прочее.")
    cat_furniture = _ensure_category("Мебель", "Рабочие столы, кресла, стеллажи.")
    cat_services = _ensure_category("Услуги", "Сопровождение, настройка, консультации.")

    db.session.commit()

    # ----------------------------
    # Товары (если ещё нет ни одного — добавляем набор)
    # ----------------------------
    if db.session.query(Product).count() == 0:
        products_seed = [
            # Electronics
            (cat_electronics.id, "Мышь беспроводная", "Эргономичная мышь для работы.", Decimal("1490.00"), 10, True),
            (cat_electronics.id, "Клавиатура механическая", "Подсветка, удобный ход клавиш.", Decimal("5990.00"), 0, True),
            (cat_electronics.id, "Монитор 24''", "IPS, 75 Гц, Full HD.", Decimal("12990.00"), 15, False),
            (cat_electronics.id, "Флеш-накопитель 64GB", "USB 3.0.", Decimal("790.00"), 0, False),
            # Stationery
            (cat_stationery.id, "Блокнот A5", "В клетку, 80 листов.", Decimal("290.00"), 0, True),
            (cat_stationery.id, "Ручка гелевая", "Чёрная, 0.5 мм.", Decimal("90.00"), 20, False),
            (cat_stationery.id, "Папка-регистратор", "Для документов формата A4.", Decimal("420.00"), 0, False),
            # Furniture
            (cat_furniture.id, "Кресло офисное", "Регулировка высоты, поддержка поясницы.", Decimal("9990.00"), 5, True),
            (cat_furniture.id, "Стол рабочий", "120×60 см, светлый дуб.", Decimal("7990.00"), 0, False),
            (cat_furniture.id, "Стеллаж", "5 полок, металл/ЛДСП.", Decimal("6490.00"), 12, False),
            # Services
            (cat_services.id, "Настройка рабочего места", "Установка ПО, настройка доступа, рекомендации.", Decimal("2500.00"), 0, False),
            (cat_services.id, "Консультация по системе", "Обучение пользователя, ответы на вопросы.", Decimal("1200.00"), 0, False),
        ]

        for category_id, name, desc, price, disc, featured in products_seed:
            p = Product(
                category_id=category_id,
                name=name,
                description=desc,
                price=price,
                discount_percent=int(disc),
                is_featured=bool(featured),
                is_active=True,
            )
            db.session.add(p)
            stats["products"] += 1

        db.session.commit()

    # ----------------------------
    # Обратная связь (для проверки админки)
    # ----------------------------
    if db.session.query(Feedback).count() == 0:
        u = db.session.query(User).filter_by(login="user").first()
        demo = Feedback(
            user_id=u.id if u else None,
            name="Тестовый пользователь",
            email="user@example.com",
            subject="Вопрос по работе портала",
            message="Проверка формы обратной связи и отображения сообщений в админке.",
            status="new",
        )
        db.session.add(demo)
        stats["feedback"] += 1
        db.session.commit()

    return stats


def ensure_seed() -> None:
    """
    Удобный алиас: просто вызвать ensure_seed() в app_context,
    чтобы гарантированно были тестовые данные.
    """
    seed_db()
