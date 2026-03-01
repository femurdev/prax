"""
Map + world state: JSON maps, in-memory world state, delta broadcast.
Action code: pseudo-code parser, rate-limited move execution.
"""
import json
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings

MAPS_DIR = settings.base_dir / "maps"
MOVE_RATE_SEC = 0.3  # max one move per 0.3s per player
PLAYER_EMOJIS = ["😀", "😊", "🥳", "😎", "🤩", "😇", "🙂", "🙃", "😜", "🤪", "🧐", "😏"]

# Commands the action script can use (one per line, case-insensitive)
MOVES = {"MOVE_UP": (0, -1), "MOVE_DOWN": (0, 1), "MOVE_LEFT": (-1, 0), "MOVE_RIGHT": (1, 0)}


def load_map(map_id: str) -> dict[str, Any] | None:
    path = MAPS_DIR / f"{map_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_action_code(text: str) -> list[tuple[int, int]]:
    """Parse action code into list of (dx, dy) moves. Invalid lines skipped."""
    out = []
    for line in text.strip().upper().splitlines():
        line = line.strip().split("#")[0].strip()
        if not line:
            continue
        if line in MOVES:
            out.append(MOVES[line])
        else:
            # Optional: REPEAT n MOVE_UP etc.
            parts = line.split()
            if len(parts) == 3 and parts[0] == "REPEAT" and parts[2] in MOVES:
                try:
                    n = min(int(parts[1]), 100)
                    dx, dy = MOVES[parts[2]]
                    out.extend([(dx, dy)] * n)
                except ValueError:
                    pass
    return out


class GameRoom:
    """One map instance: static map data + player positions + move queues. Thread-safe."""

    def __init__(self, map_id: str):
        self.map_id = map_id
        self._lock = threading.Lock()
        self._map_data = load_map(map_id)
        if not self._map_data:
            raise ValueError(f"Map not found: {map_id}")
        self._players: dict[str, dict[str, Any]] = {}
        self._move_queues: dict[str, list[tuple[int, int]]] = {}
        self._last_move_time: dict[str, float] = {}
        self._tick = 0
        self._spawn_index = 0

    def _is_blocked(self, x: int, y: int, exclude_player_id: str | None = None) -> bool:
        w = self._map_data["width"]
        h = self._map_data["height"]
        if x < 0 or x >= w or y < 0 or y >= h:
            return True
        if x == 0 or x == w - 1 or y == 0 or y == h - 1:
            return True
        walls = [tuple(c) for c in self._map_data["walls"]]
        if (x, y) in walls:
            return True
        for pid, p in self._players.items():
            if pid != exclude_player_id and p["x"] == x and p["y"] == y:
                return True
        return False

    def _next_spawn(self) -> tuple[int, int] | None:
        spawns = self._map_data["spawns"]
        used = {(p["x"], p["y"]) for p in self._players.values()}
        for i in range(len(spawns)):
            idx = (self._spawn_index + i) % len(spawns)
            pos = tuple(spawns[idx])
            if pos not in used:
                self._spawn_index = (idx + 1) % len(spawns)
                return pos
        return None

    def join(self, player_id: str) -> dict[str, Any] | None:
        with self._lock:
            if len(self._players) >= self._map_data["max_players"]:
                return None
            pos = self._next_spawn()
            if pos is None:
                return None
            x, y = pos
            idx = len(self._players) % len(PLAYER_EMOJIS)
            self._players[player_id] = {
                "x": x,
                "y": y,
                "emoji": PLAYER_EMOJIS[idx],
            }
            self._move_queues[player_id] = []
            self._last_move_time[player_id] = 0.0
            return self.get_state()

    def leave(self, player_id: str) -> dict[str, Any]:
        with self._lock:
            self._players.pop(player_id, None)
            self._move_queues.pop(player_id, None)
            self._last_move_time.pop(player_id, None)
            return self.get_state()

    def submit_action(self, player_id: str, action_code: str) -> dict[str, Any] | None:
        moves = parse_action_code(action_code)
        if not moves:
            return None
        with self._lock:
            if player_id not in self._players:
                return None
            self._move_queues[player_id] = moves[:200]
            return {"ok": True, "queued": len(self._move_queues[player_id])}

    def tick(self) -> dict[str, Any] | None:
        """Process one tick: dequeue one move per player (rate-limited). Returns delta or None."""
        with self._lock:
            now = time.monotonic()
            deltas = []
            any_move = False
            for player_id in list(self._players.keys()):
                queue = self._move_queues.get(player_id) or []
                if not queue:
                    continue
                if now - self._last_move_time.get(player_id, 0) < MOVE_RATE_SEC:
                    continue
                dx, dy = queue.pop(0)
                self._move_queues[player_id] = queue
                p = self._players[player_id]
                nx, ny = p["x"] + dx, p["y"] + dy
                if not self._is_blocked(nx, ny, exclude_player_id=player_id):
                    deltas.append((player_id, p["x"], p["y"], nx, ny))
                    p["x"], p["y"] = nx, ny
                    self._last_move_time[player_id] = now
                    any_move = True
            if not any_move:
                return None
            self._tick += 1
            return self._state_delta(deltas)

    def _state_delta(self, deltas: list[tuple[str, int, int, int, int]]) -> dict[str, Any]:
        players_update = {}
        for player_id, _ox, _oy, nx, ny in deltas:
            players_update[player_id] = {
                "x": self._players[player_id]["x"],
                "y": self._players[player_id]["y"],
            }
        return {
            "type": "delta",
            "tick": self._tick,
            "players": players_update,
        }

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "map_id": self.map_id,
                "map": self._map_data,
                "tick": self._tick,
                "players": {
                    pid: {"x": p["x"], "y": p["y"], "emoji": p["emoji"]}
                    for pid, p in self._players.items()
                },
            }


# Global: one room per map_id for now; key = map_id
_rooms: dict[str, GameRoom] = {}
_rooms_lock = threading.Lock()


def get_or_create_room(map_id: str) -> GameRoom | None:
    with _rooms_lock:
        if map_id not in _rooms:
            if load_map(map_id) is None:
                return None
            _rooms[map_id] = GameRoom(map_id)
        return _rooms[map_id]


def get_room(map_id: str) -> GameRoom | None:
    with _rooms_lock:
        return _rooms.get(map_id)


def get_all_rooms() -> list[tuple[str, "GameRoom"]]:
    with _rooms_lock:
        return list(_rooms.items())
