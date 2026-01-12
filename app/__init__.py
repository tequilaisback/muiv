# app/__init__.py
import os
from pathlib import Path

from flask import Flask, render_template
from flask_login import LoginManager

from .models import db, User


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

    # --- базовый конфиг ---
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

    # SQLite в instance/
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db_path = os.path.join(app.instance_path, "app.sqlite")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # --- init extensions ---
    db.init_app(app)
    login_manager.init_app(app)

    # --- blueprints ---
    # (в этих файлах мы дальше сделаем: bp = Blueprint(...))
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

    # --- контекст для шаблонов ---
    @app.context_processor
    def inject_globals():
        return {
            "APP_TITLE": "Мониторинг показателей здоровья спортсменов",
        }

    # --- ошибки ---
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500

    # --- создание БД + сиды (для учебного проекта) ---
    with app.app_context():
        db.create_all()
        try:
            from .seed import seed_db
            seed_db()
        except Exception:
            # seed_db добавим/настроим позже — чтобы приложение не падало
            pass

    return app
