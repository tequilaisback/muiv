# app/__init__.py
from __future__ import annotations

from flask import Flask, render_template
from flask_login import LoginManager, current_user

from config import Config
from .db import db, init_db
from .models import User

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Пожалуйста, войдите в систему."


@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # init extensions
    db.init_app(app)
    login_manager.init_app(app)

    # blueprints
    from .routes import bp as routes_bp
    from .auth import bp as auth_bp
    from .admin import bp as admin_bp
    from .cabinet import bp as cabinet_bp
    from .feedback import bp as feedback_bp

    app.register_blueprint(routes_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(cabinet_bp, url_prefix="/cabinet")
    app.register_blueprint(feedback_bp, url_prefix="/feedback")

    # context for templates
    @app.context_processor
    def inject_globals():
        return {
            "APP_TITLE": app.config.get("APP_TITLE", "Мониторинг спортсменов"),
            "CURRENT_USER": current_user,  # иногда удобно в шаблонах (опционально)
        }

    # error handlers
    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("403.html"), 403

    @app.errorhandler(500)
    def server_error(_e):
        # в debug пусть Flask показывает трейс, но шаблон тоже полезен
        return render_template("500.html"), 500

    # create DB + seed (учебный проект)
    with app.app_context():
        init_db()
        try:
            from .seed import seed_db
            seed_db()
        except Exception:
            # seed не должен "ронять" приложение в учебной сборке
            app.logger.exception("seed_db failed")

    return app
