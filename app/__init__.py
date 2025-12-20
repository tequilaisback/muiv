# app/__init__.py
from __future__ import annotations

import os

from flask import Flask, render_template

from .db import init_db
from .seed import seed_db


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # -----------------------------
    # Config (минимально)
    # -----------------------------
    # Секрет берём из окружения, иначе ставим простой (для учебного проекта)
    app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    # SQLite в папке instance/app.sqlite
    db_path = os.path.join(app.instance_path, "app.sqlite")
    os.makedirs(app.instance_path, exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # -----------------------------
    # DB init + create tables
    # -----------------------------
    init_db(app)

    # -----------------------------
    # Blueprints
    # -----------------------------
    from .routes import main_bp
    from .auth import auth_bp
    from .cabinet import cabinet_bp
    from .admin import admin_bp
    from .feedback import feedback_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cabinet_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(feedback_bp)

    # -----------------------------
    # Error handlers
    # -----------------------------
    @app.errorhandler(404)
    def not_found(e):
        # current_user и breadcrumbs могут быть пустыми — base.html это переживёт
        return render_template("404.html", breadcrumbs=[{"title": "404", "url": None}], current_user=None), 404

    @app.errorhandler(500)
    def server_error(e):
        return (
            render_template(
                "404.html",
                breadcrumbs=[{"title": "Ошибка", "url": None}],
                current_user=None,
            ),
            500,
        )

    # -----------------------------
    # Автозаполнение тестовыми данными
    # (идемпотентно, не плодит дублей)
    # -----------------------------
    with app.app_context():
        seed_db()

    return app
