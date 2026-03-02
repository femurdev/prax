from app import create_app, socketio
from app.config import settings

app = create_app()


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=settings.port,
        debug=True,
        allow_unsafe_werkzeug=True,
    )
