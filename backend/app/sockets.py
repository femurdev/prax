import threading
import time

from flask import request
from flask_socketio import SocketIO, join_room, leave_room

from .game import get_or_create_room, get_room

TICK_INTERVAL = 0.2  # run game tick every 200ms


def register_socket_handlers(socketio: SocketIO) -> None:
    @socketio.on("join_game")
    def on_join(data: dict):
        map_id = (data or {}).get("map_id") or "map_01"
        player_id = (data or {}).get("player_id") or ""
        if not player_id:
            return
        room = get_or_create_room(map_id)
        if not room:
            return
        state = room.join(player_id)
        if state is None:
            return
        join_room(map_id)
        socketio.emit("state", state, room=map_id)

    @socketio.on("leave_game")
    def on_leave(data: dict):
        map_id = (data or {}).get("map_id") or "map_01"
        player_id = (data or {}).get("player_id") or ""
        room = get_room(map_id)
        if room and player_id:
            state = room.leave(player_id)
            leave_room(map_id)
            socketio.emit("state", state, room=map_id)

    @socketio.on("submit_action")
    def on_submit_action(data: dict):
        map_id = (data or {}).get("map_id") or "map_01"
        player_id = (data or {}).get("player_id") or ""
        action_code = (data or {}).get("action_code") or ""
        room = get_room(map_id)
        if not room or not player_id:
            return
        result = room.submit_action(player_id, action_code)
        if result:
            socketio.emit("action_queued", result, room=request.sid)


def start_tick_loop(socketio: SocketIO) -> None:
    def loop():
        while True:
            time.sleep(TICK_INTERVAL)
            from .game import get_all_rooms

            for map_id, room in get_all_rooms():
                delta = room.tick()
                if delta:
                    socketio.emit("delta", delta, room=map_id)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
