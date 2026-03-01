<<<<<<< HEAD
from app import create_app, socketio
=======
from app import create_app
>>>>>>> e92e0e7b7570d6c4cb3e8476d0b00ed5f72453d5
from app.config import settings

app = create_app()


if __name__ == "__main__":
<<<<<<< HEAD
    socketio.run(
        app,
        host="0.0.0.0",
        port=settings.port,
        debug=True,
        allow_unsafe_werkzeug=True,
    )
=======
    app.run(host="0.0.0.0", port=settings.port, debug=True)
>>>>>>> e92e0e7b7570d6c4cb3e8476d0b00ed5f72453d5
