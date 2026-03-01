from flask import Flask
from flask_socketio import SocketIO

from .config import settings
from .db import init_db
from .routes import register_routes
from .sockets import register_socket_handlers, start_tick_loop

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")


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
    socketio.init_app(app)
    register_socket_handlers(socketio)
    start_tick_loop(socketio)
    return app
