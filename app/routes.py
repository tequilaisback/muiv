# app/routes.py
from __future__ import annotations

from flask import Blueprint, abort, render_template, request, session, url_for

from .db import db
from .models import Category, Product, User

main_bp = Blueprint("main", __name__)


# -----------------------------
# Helpers
# -----------------------------
def _crumbs(*items: tuple[str, str | None]):
    return [{"title": t, "url": u} for (t, u) in items]


def _current_user() -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


# -----------------------------
# Public pages (10+)
# -----------------------------
@main_bp.get("/")
def index():
    # Витрина: "избранное" + акции (со скидкой)
    featured = (
        db.session.query(Product)
        .filter(Product.is_active.is_(True))
        .filter(Product.is_featured.is_(True))
        .order_by(Product.created_at.desc())
        .limit(8)
        .all()
    )

    offers = (
        db.session.query(Product)
        .filter(Product.is_active.is_(True))
        .filter(Product.discount_percent > 0)
        .order_by(Product.discount_percent.desc(), Product.created_at.desc())
        .limit(8)
        .all()
    )

    categories = (
        db.session.query(Category)
        .filter(Category.is_active.is_(True))
        .order_by(Category.name.asc())
        .limit(12)
        .all()
    )

    return render_template(
        "index.html",
        featured=featured,
        offers=offers,
        categories=categories,
        breadcrumbs=_crumbs(("Главная", None)),
        current_user=_current_user(),
    )


@main_bp.get("/about")
def about():
    return render_template(
        "about.html",
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("О проекте", None)),
        current_user=_current_user(),
    )


@main_bp.get("/contacts")
def contacts():
    return render_template(
        "contacts.html",
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Контакты", None)),
        current_user=_current_user(),
    )


@main_bp.get("/catalog")
def catalog():
    """
    Страница каталога (список товаров).
    Можно фильтровать по category_id и поиском по названию.
    """
    category_id = request.args.get("category_id", "").strip()
    q = (request.args.get("q") or "").strip()

    query = db.session.query(Product).filter(Product.is_active.is_(True))

    selected_category = None
    if category_id:
        try:
            cid = int(category_id)
            selected_category = db.session.get(Category, cid)
            if selected_category:
                query = query.filter(Product.category_id == cid)
        except Exception:
            selected_category = None

    if q:
        like = f"%{q}%"
        query = query.filter(Product.name.ilike(like))

    products = query.order_by(Product.created_at.desc()).all()

    categories = (
        db.session.query(Category)
        .filter(Category.is_active.is_(True))
        .order_by(Category.name.asc())
        .all()
    )

    crumbs = [("Главная", url_for("main.index")), ("Каталог", None)]
    if selected_category:
        crumbs = [("Главная", url_for("main.index")), ("Каталог", url_for("main.catalog")), (selected_category.name, None)]

    return render_template(
        "catalog.html",
        products=products,
        categories=categories,
        selected_category=selected_category,
        q=q,
        breadcrumbs=_crumbs(*crumbs),
        current_user=_current_user(),
    )


@main_bp.get("/products/<int:product_id>")
def product_detail(product_id: int):
    p = db.session.get(Product, product_id)
    if not p or not p.is_active:
        abort(404)

    cat = db.session.get(Category, p.category_id) if p.category_id else None

    return render_template(
        "product.html",
        product=p,
        category=cat,
        breadcrumbs=_crumbs(
            ("Главная", url_for("main.index")),
            ("Каталог", url_for("main.catalog")),
            (p.name, None),
        ),
        current_user=_current_user(),
    )


@main_bp.get("/categories")
def categories():
    categories_list = (
        db.session.query(Category)
        .filter(Category.is_active.is_(True))
        .order_by(Category.name.asc())
        .all()
    )

    # для удобства можно показать количество товаров в категории
    counts = dict(
        db.session.query(Product.category_id, db.func.count(Product.id))
        .filter(Product.is_active.is_(True))
        .group_by(Product.category_id)
        .all()
    )

    return render_template(
        "categories.html",
        categories=categories_list,
        counts=counts,
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Категории", None)),
        current_user=_current_user(),
    )


@main_bp.get("/offers")
def offers():
    # Акции/скидки
    products = (
        db.session.query(Product)
        .filter(Product.is_active.is_(True))
        .filter(Product.discount_percent > 0)
        .order_by(Product.discount_percent.desc(), Product.created_at.desc())
        .all()
    )

    return render_template(
        "offers.html",
        products=products,
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Акции", None)),
        current_user=_current_user(),
    )


@main_bp.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    products = []

    if q:
        like = f"%{q}%"
        products = (
            db.session.query(Product)
            .filter(Product.is_active.is_(True))
            .filter(Product.name.ilike(like))
            .order_by(Product.created_at.desc())
            .all()
        )

    return render_template(
        "search.html",
        q=q,
        products=products,
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Поиск", None)),
        current_user=_current_user(),
    )
