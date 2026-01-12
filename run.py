# run.py
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Для учебного проекта: debug можно включать через env FLASK_DEBUG=1
    app.run(host="127.0.0.1", port=5000, debug=app.config.get("DEBUG", False))
