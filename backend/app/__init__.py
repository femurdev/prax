from flask import Flask

from .config import settings
from .db import init_db
from .routes import register_routes


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.session_secret
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = settings.session_cookie_secure

    @app.before_request
    def ensure_db() -> None:
        init_db()

    register_routes(app)
    return app
