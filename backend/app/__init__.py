from flask import Flask
<<<<<<< HEAD
from flask_socketio import SocketIO
=======
>>>>>>> e92e0e7b7570d6c4cb3e8476d0b00ed5f72453d5

from .config import settings
from .db import init_db
from .routes import register_routes
<<<<<<< HEAD
from .sockets import register_socket_handlers, start_tick_loop

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")
=======
>>>>>>> e92e0e7b7570d6c4cb3e8476d0b00ed5f72453d5


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
<<<<<<< HEAD
    socketio.init_app(app)
    register_socket_handlers(socketio)
    start_tick_loop(socketio)
=======
>>>>>>> e92e0e7b7570d6c4cb3e8476d0b00ed5f72453d5
    return app
