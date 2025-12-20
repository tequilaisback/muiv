# app/admin.py
from __future__ import annotations

import os
import uuid
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from .db import db
from .models import (
    Category,
    Feedback,
    Product,
    User,
    validate_role,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_USER,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# -----------------------------
# Загрузка изображений
# -----------------------------
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

PRODUCT_IMAGES_DIR = os.path.join("img", "products")     # app/static/img/products
CATEGORY_IMAGES_DIR = os.path.join("img", "categories")  # app/static/img/categories


def _allowed_image(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _ensure_static_subdir(rel_dir: str) -> str:
    """
    Возвращает абсолютный путь к подпапке внутри app/static.
    """
    abs_dir = os.path.join(current_app.root_path, "static", rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    return abs_dir


# -----------------------------
# Product images (как было)
# -----------------------------
def _save_product_image(file_storage) -> str | None:
    """
    Сохраняет загруженный файл в app/static/img/products и возвращает имя файла (без пути).
    """
    if not file_storage:
        return None

    original = (file_storage.filename or "").strip()
    if not original:
        return None

    if not _allowed_image(original):
        raise ValueError("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, webp, gif.")

    safe = secure_filename(original)
    ext = safe.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"

    folder = _ensure_static_subdir(PRODUCT_IMAGES_DIR)
    abs_path = os.path.join(folder, new_name)

    file_storage.save(abs_path)
    return new_name


def _delete_product_image(filename: str | None) -> None:
    if not filename:
        return
    try:
        folder = _ensure_static_subdir(PRODUCT_IMAGES_DIR)
        abs_path = os.path.join(folder, filename)
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except Exception:
        pass


# -----------------------------
# Category images (БЕЗ БД)
# Имя файла: cat_<category_id>.<ext>
# -----------------------------
def _category_image_basename(category_id: int) -> str:
    return f"cat_{category_id}"


def _find_category_image_filename(category_id: int) -> str | None:
    """
    Ищет существующее изображение категории по шаблону cat_<id>.<ext>.
    """
    folder = _ensure_static_subdir(CATEGORY_IMAGES_DIR)
    base = _category_image_basename(category_id)
    for ext in ("png", "jpg", "jpeg", "webp", "gif"):
        name = f"{base}.{ext}"
        if os.path.isfile(os.path.join(folder, name)):
            return name
    return None


def _delete_category_image(category_id: int) -> None:
    """
    Удаляет все варианты cat_<id>.* (по разрешённым расширениям).
    """
    try:
        folder = _ensure_static_subdir(CATEGORY_IMAGES_DIR)
        base = _category_image_basename(category_id)
        for ext in ("png", "jpg", "jpeg", "webp", "gif"):
            name = f"{base}.{ext}"
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                os.remove(path)
    except Exception:
        pass


def _save_category_image(category_id: int, file_storage) -> str | None:
    """
    Сохраняет (или заменяет) изображение категории в app/static/img/categories/
    Возвращает имя файла (cat_<id>.<ext>) или None.
    """
    if not file_storage:
        return None

    original = (file_storage.filename or "").strip()
    if not original:
        return None

    if not _allowed_image(original):
        raise ValueError("Недопустимый формат изображения. Разрешены: png, jpg, jpeg, webp, gif.")

    safe = secure_filename(original)
    ext = safe.rsplit(".", 1)[1].lower()

    # удалим прошлые варианты cat_<id>.* чтобы не плодить мусор
    _delete_category_image(category_id)

    folder = _ensure_static_subdir(CATEGORY_IMAGES_DIR)
    name = f"{_category_image_basename(category_id)}.{ext}"
    abs_path = os.path.join(folder, name)
    file_storage.save(abs_path)
    return name


# -------------------------------------------------------------------
# Минимальная авторизация/роли
# -------------------------------------------------------------------
def get_current_user() -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or not user.is_active:
            flash("Войдите в систему.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapper


def role_required(*roles: str):
    roles_set = set(roles)

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user or not user.is_active:
                flash("Войдите в систему.", "warning")
                return redirect(url_for("auth.login"))
            if user.role not in roles_set:
                flash("Недостаточно прав доступа.", "danger")
                return redirect(url_for("main.index"))
            return view(*args, **kwargs)

        return wrapper

    return decorator


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _crumbs(*items: tuple[str, str | None]):
    return [{"title": t, "url": u} for (t, u) in items]


def _parse_decimal(value: str, default: Decimal = Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    s = str(value).strip().replace(",", ".")
    if s == "":
        return default
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return default


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


# -------------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------------
@admin_bp.get("/")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def dashboard():
    users_count = db.session.query(User).count()
    products_count = db.session.query(Product).count()
    categories_count = db.session.query(Category).count()
    feedback_new = db.session.query(Feedback).filter_by(status="new").count()

    return render_template(
        "admin.html",
        section="dashboard",
        breadcrumbs=_crumbs(("Главная", url_for("main.index")), ("Админ-панель", None)),
        stats={
            "users": users_count,
            "products": products_count,
            "categories": categories_count,
            "feedback_new": feedback_new,
        },
        current_user=get_current_user(),
    )


# -------------------------------------------------------------------
# USERS (только админ)
# -------------------------------------------------------------------
@admin_bp.get("/users")
@login_required
@role_required(ROLE_ADMIN)
def users_list():
    q = (request.args.get("q") or "").strip()
    query = db.session.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter((User.login.ilike(like)) | (User.full_name.ilike(like)))
    users = query.order_by(User.created_at.desc()).all()

    return render_template(
        "admin.html",
        section="users",
        users=users,
        q=q,
        roles=[ROLE_ADMIN, ROLE_MANAGER, ROLE_USER],
        breadcrumbs=_crumbs(
            ("Главная", url_for("main.index")),
            ("Админ-панель", url_for("admin.dashboard")),
            ("Пользователи", None),
        ),
        current_user=get_current_user(),
    )


@admin_bp.post("/users/create")
@login_required
@role_required(ROLE_ADMIN)
def users_create():
    login = (request.form.get("login") or "").strip()
    password = request.form.get("password") or ""
    full_name = (request.form.get("full_name") or "").strip()
    role = validate_role(request.form.get("role") or ROLE_USER)

    if not login or not password or not full_name:
        flash("Заполните login, пароль и ФИО.", "warning")
        return redirect(url_for("admin.users_list"))

    exists = db.session.query(User).filter_by(login=login).first()
    if exists:
        flash("Пользователь с таким login уже существует.", "danger")
        return redirect(url_for("admin.users_list"))

    u = User(login=login, full_name=full_name, role=role, is_active=True)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()

    flash("Пользователь создан.", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.post("/users/<int:user_id>/update")
@login_required
@role_required(ROLE_ADMIN)
def users_update(user_id: int):
    u = db.session.get(User, user_id)
    if not u:
        flash("Пользователь не найден.", "danger")
        return redirect(url_for("admin.users_list"))

    me = get_current_user()

    full_name = (request.form.get("full_name") or "").strip()
    role = validate_role(request.form.get("role") or u.role)
    is_active = (request.form.get("is_active") == "on")

    if full_name:
        u.full_name = full_name

    if me and u.id == me.id:
        pass
    else:
        u.role = role
        u.is_active = is_active

    new_password = (request.form.get("new_password") or "").strip()
    if new_password:
        u.set_password(new_password)

    db.session.commit()
    flash("Пользователь обновлён.", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.post("/users/<int:user_id>/delete")
@login_required
@role_required(ROLE_ADMIN)
def users_delete(user_id: int):
    u = db.session.get(User, user_id)
    if not u:
        flash("Пользователь не найден.", "danger")
        return redirect(url_for("admin.users_list"))

    me = get_current_user()
    if me and u.id == me.id:
        flash("Нельзя удалить текущего пользователя.", "warning")
        return redirect(url_for("admin.users_list"))

    db.session.delete(u)
    db.session.commit()
    flash("Пользователь удалён.", "success")
    return redirect(url_for("admin.users_list"))


# -------------------------------------------------------------------
# CATEGORIES (админ + менеджер) + фото без БД
# -------------------------------------------------------------------
@admin_bp.get("/categories")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def categories_list():
    categories = db.session.query(Category).order_by(Category.created_at.desc()).all()

    # карта id -> filename (cat_<id>.<ext>), если есть
    category_images = {c.id: _find_category_image_filename(c.id) for c in categories}

    return render_template(
        "admin.html",
        section="categories",
        categories=categories,
        category_images=category_images,
        breadcrumbs=_crumbs(
            ("Главная", url_for("main.index")),
            ("Админ-панель", url_for("admin.dashboard")),
            ("Категории", None),
        ),
        current_user=get_current_user(),
    )


@admin_bp.post("/categories/create")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def categories_create():
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None

    if not name:
        flash("Название категории обязательно.", "warning")
        return redirect(url_for("admin.categories_list"))

    exists = db.session.query(Category).filter_by(name=name).first()
    if exists:
        flash("Категория с таким названием уже существует.", "danger")
        return redirect(url_for("admin.categories_list"))

    c = Category(name=name, description=description, is_active=True)
    db.session.add(c)
    db.session.commit()  # нужен id

    # фото категории (опционально) — без БД
    try:
        img = request.files.get("image")
        if img and (img.filename or "").strip():
            _save_category_image(c.id, img)
    except ValueError as e:
        flash(str(e), "warning")
        return redirect(url_for("admin.categories_list"))

    flash("Категория создана.", "success")
    return redirect(url_for("admin.categories_list"))


@admin_bp.post("/categories/<int:category_id>/update")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def categories_update(category_id: int):
    c = db.session.get(Category, category_id)
    if not c:
        flash("Категория не найдена.", "danger")
        return redirect(url_for("admin.categories_list"))

    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    is_active = (request.form.get("is_active") == "on")

    if name:
        c.name = name
    c.description = description
    c.is_active = is_active
    db.session.commit()

    # если выбрали новую картинку — заменяем (без БД)
    try:
        img = request.files.get("image")
        if img and (img.filename or "").strip():
            _save_category_image(c.id, img)
    except ValueError as e:
        flash(str(e), "warning")
        return redirect(url_for("admin.categories_list"))

    flash("Категория обновлена.", "success")
    return redirect(url_for("admin.categories_list"))


@admin_bp.post("/categories/<int:category_id>/delete")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def categories_delete(category_id: int):
    c = db.session.get(Category, category_id)
    if not c:
        flash("Категория не найдена.", "danger")
        return redirect(url_for("admin.categories_list"))

    # удаляем картинку категории
    _delete_category_image(category_id)

    db.session.delete(c)
    db.session.commit()
    flash("Категория удалена.", "success")
    return redirect(url_for("admin.categories_list"))


# -------------------------------------------------------------------
# PRODUCTS (админ + менеджер)
# -------------------------------------------------------------------
@admin_bp.get("/products")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def products_list():
    q = (request.args.get("q") or "").strip()
    query = db.session.query(Product).join(Category)
    if q:
        like = f"%{q}%"
        query = query.filter(Product.name.ilike(like))

    products = query.order_by(Product.created_at.desc()).all()
    categories = db.session.query(Category).filter_by(is_active=True).order_by(Category.name.asc()).all()

    return render_template(
        "admin.html",
        section="products",
        products=products,
        categories=categories,
        q=q,
        breadcrumbs=_crumbs(
            ("Главная", url_for("main.index")),
            ("Админ-панель", url_for("admin.dashboard")),
            ("Товары", None),
        ),
        current_user=get_current_user(),
    )


@admin_bp.post("/products/create")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def products_create():
    category_id = _to_int(request.form.get("category_id"), 0)
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    price = _parse_decimal(request.form.get("price"), Decimal("0.00"))
    discount_percent = _to_int(request.form.get("discount_percent"), 0)
    is_featured = (request.form.get("is_featured") == "on")
    is_active = (request.form.get("is_active") == "on")

    if not category_id or not name:
        flash("Категория и название товара обязательны.", "warning")
        return redirect(url_for("admin.products_list"))

    cat = db.session.get(Category, category_id)
    if not cat:
        flash("Категория не найдена.", "danger")
        return redirect(url_for("admin.products_list"))

    if discount_percent < 0:
        discount_percent = 0
    if discount_percent > 99:
        discount_percent = 99

    p = Product(
        category_id=category_id,
        name=name,
        description=description,
        price=price,
        discount_percent=discount_percent,
        is_featured=is_featured,
        is_active=is_active,
    )

    # картинка товара (опционально)
    try:
        img = request.files.get("image")
        saved = _save_product_image(img)
        if saved:
            p.image_filename = saved
    except ValueError as e:
        flash(str(e), "warning")
        return redirect(url_for("admin.products_list"))

    db.session.add(p)
    db.session.commit()
    flash("Товар создан.", "success")
    return redirect(url_for("admin.products_list"))


@admin_bp.post("/products/<int:product_id>/update")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def products_update(product_id: int):
    p = db.session.get(Product, product_id)
    if not p:
        flash("Товар не найден.", "danger")
        return redirect(url_for("admin.products_list"))

    category_id = _to_int(request.form.get("category_id"), p.category_id)
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    price = _parse_decimal(request.form.get("price"), p.price_value)
    discount_percent = _to_int(request.form.get("discount_percent"), p.discount_percent or 0)
    is_featured = (request.form.get("is_featured") == "on")
    is_active = (request.form.get("is_active") == "on")

    if discount_percent < 0:
        discount_percent = 0
    if discount_percent > 99:
        discount_percent = 99

    cat = db.session.get(Category, category_id)
    if not cat:
        flash("Категория не найдена.", "danger")
        return redirect(url_for("admin.products_list"))

    p.category_id = category_id
    if name:
        p.name = name
    p.description = description
    p.price = price
    p.discount_percent = discount_percent
    p.is_featured = is_featured
    p.is_active = is_active

    # картинка товара (если выбрали новую — заменяем)
    try:
        img = request.files.get("image")
        saved = _save_product_image(img)
        if saved:
            old = p.image_filename
            p.image_filename = saved
            _delete_product_image(old)
    except ValueError as e:
        flash(str(e), "warning")
        return redirect(url_for("admin.products_list"))

    db.session.commit()
    flash("Товар обновлён.", "success")
    return redirect(url_for("admin.products_list"))


@admin_bp.post("/products/<int:product_id>/delete")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def products_delete(product_id: int):
    p = db.session.get(Product, product_id)
    if not p:
        flash("Товар не найден.", "danger")
        return redirect(url_for("admin.products_list"))

    _delete_product_image(p.image_filename)

    db.session.delete(p)
    db.session.commit()
    flash("Товар удалён.", "success")
    return redirect(url_for("admin.products_list"))


# -------------------------------------------------------------------
# FEEDBACK (админ + менеджер)
# -------------------------------------------------------------------
@admin_bp.get("/feedback")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def feedback_list():
    status = (request.args.get("status") or "").strip().lower()
    query = db.session.query(Feedback)
    if status in ("new", "processed"):
        query = query.filter_by(status=status)

    items = query.order_by(Feedback.created_at.desc()).all()

    return render_template(
        "admin.html",
        section="feedback",
        feedback_items=items,
        status=status,
        breadcrumbs=_crumbs(
            ("Главная", url_for("main.index")),
            ("Админ-панель", url_for("admin.dashboard")),
            ("Обратная связь", None),
        ),
        current_user=get_current_user(),
    )


@admin_bp.post("/feedback/<int:feedback_id>/set_status")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def feedback_set_status(feedback_id: int):
    f = db.session.get(Feedback, feedback_id)
    if not f:
        flash("Сообщение не найдено.", "danger")
        return redirect(url_for("admin.feedback_list"))

    new_status = (request.form.get("status") or "").strip().lower()
    if new_status not in ("new", "processed"):
        new_status = "processed"

    f.status = new_status
    db.session.commit()

    flash("Статус обновлён.", "success")
    return redirect(url_for("admin.feedback_list"))


@admin_bp.post("/feedback/<int:feedback_id>/delete")
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def feedback_delete(feedback_id: int):
    f = db.session.get(Feedback, feedback_id)
    if not f:
        flash("Сообщение не найдено.", "danger")
        return redirect(url_for("admin.feedback_list"))

    db.session.delete(f)
    db.session.commit()
    flash("Сообщение удалено.", "success")
    return redirect(url_for("admin.feedback_list"))
