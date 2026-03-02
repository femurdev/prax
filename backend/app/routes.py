import secrets
from typing import Any

import requests
from flask import Flask, jsonify, redirect, request, session

from .config import settings
from .db import current_user, get_db
from .tilemap import (
    TileValidationError,
    create_foreground_entity,
    get_foreground_entity,
    get_region_tiles,
    get_tile,
    set_tile,
    validate_coordinates,
    validate_entity_part_reference,
    world_to_chunk_local,
)


def _parse_query_int(name: str) -> int:
    raw = request.args.get(name)
    if raw is None:
        raise TileValidationError(f"Missing query parameter '{name}'")
    try:
        return int(raw)
    except ValueError as exc:
        raise TileValidationError(f"Query parameter '{name}' must be an integer") from exc


def _parse_allow_unresolved(payload: dict[str, Any] | None) -> bool:
    query_val = request.args.get("allow_unresolved_entity")
    if query_val is not None:
        return query_val.lower() in {"1", "true", "yes", "on"}

    if isinstance(payload, dict) and "allow_unresolved_entity" in payload:
        return bool(payload["allow_unresolved_entity"])

    return False


def register_routes(app: Flask) -> None:
    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/auth/discord/login")
    def discord_login():
        if not settings.discord_client_id or not settings.discord_client_secret:
            return jsonify({"error": "Discord OAuth is not configured"}), 500

        state = secrets.token_urlsafe(24)
        session["oauth_state"] = state

        params = {
            "client_id": settings.discord_client_id,
            "redirect_uri": settings.discord_redirect_uri,
            "response_type": "code",
            "scope": "identify email",
            "state": state,
            "prompt": "none",
        }

        query = "&".join(
            f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items()
        )
        return redirect(f"https://discord.com/oauth2/authorize?{query}", code=302)

    @app.get("/auth/discord/callback")
    def discord_callback():
        error = request.args.get("error")
        if error:
            return jsonify({"error": error}), 400

        code = request.args.get("code")
        state = request.args.get("state")

        if not code or not state:
            return jsonify({"error": "Missing OAuth code or state"}), 400

        expected_state = session.pop("oauth_state", None)
        if expected_state != state:
            return jsonify({"error": "Invalid OAuth state"}), 400

        token_res = requests.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

        if token_res.status_code != 200:
            return jsonify(
                {"error": "Failed to fetch OAuth token", "details": token_res.text}
            ), 400

        access_token = token_res.json().get("access_token")
        if not access_token:
            return jsonify({"error": "Missing access token"}), 400

        user_res = requests.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

        if user_res.status_code != 200:
            return jsonify(
                {"error": "Failed to fetch user profile", "details": user_res.text}
            ), 400

        discord_user = user_res.json()

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO users (discord_id, username, global_name, avatar, email, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(discord_id) DO UPDATE SET
                    username = excluded.username,
                    global_name = excluded.global_name,
                    avatar = excluded.avatar,
                    email = excluded.email,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    discord_user["id"],
                    discord_user.get("username") or "unknown",
                    discord_user.get("global_name"),
                    discord_user.get("avatar"),
                    discord_user.get("email"),
                ),
            )

            row = conn.execute(
                "SELECT id FROM users WHERE discord_id = ?",
                (discord_user["id"],),
            ).fetchone()

        session["user_id"] = row["id"]

        return jsonify(
            {"ok": True, "user": {"id": row["id"], "discord_id": discord_user["id"]}}
        ), 200

    @app.get("/me")
    def me():
        user = current_user()
        if not user:
            return jsonify({"authenticated": False}), 401

        return jsonify({"authenticated": True, "user": user}), 200

    @app.post("/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True}), 200

    @app.get("/tile")
    def get_single_tile():
        try:
            x = _parse_query_int("x")
            y = _parse_query_int("y")
        except TileValidationError as exc:
            return jsonify({"error": str(exc)}), 400

        with get_db() as conn:
            tile = get_tile(conn, x, y)

        return jsonify({"x": x, "y": y, "tile": tile}), 200

    @app.put("/tile")
    def put_single_tile():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        try:
            x, y = validate_coordinates(payload, "x", "y")
            tile_patch = payload.get("tile")
            if tile_patch is None:
                raise TileValidationError("Missing 'tile' object")

            allow_unresolved = _parse_allow_unresolved(payload)

            with get_db() as conn:
                merged_tile, warnings = set_tile(conn, x, y, tile_patch)
                validate_entity_part_reference(conn, merged_tile, allow_unresolved)

            response: dict[str, Any] = {"x": x, "y": y, "tile": merged_tile}
            if warnings:
                response["warnings"] = warnings

            return jsonify(response), 200
        except TileValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/tiles/bulk")
    def bulk_update_tiles():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        updates = payload.get("updates")
        if not isinstance(updates, list):
            return jsonify({"error": "updates must be an array"}), 400

        allow_unresolved = _parse_allow_unresolved(payload)
        touched_chunks: set[tuple[int, int]] = set()
        warnings_out: list[dict[str, Any]] = []
        applied: list[dict[str, Any]] = []

        try:
            with get_db() as conn:
                for idx, update in enumerate(updates):
                    if not isinstance(update, dict):
                        raise TileValidationError(f"updates[{idx}] must be an object")

                    x, y = validate_coordinates(update, "x", "y")
                    tile_patch = update.get("tile")
                    if tile_patch is None:
                        raise TileValidationError(f"updates[{idx}].tile is required")

                    merged_tile, warnings = set_tile(conn, x, y, tile_patch)
                    validate_entity_part_reference(conn, merged_tile, allow_unresolved)

                    chunk_x, chunk_y, _, _ = world_to_chunk_local(x, y)
                    touched_chunks.add((chunk_x, chunk_y))
                    applied.append({"x": x, "y": y, "tile": merged_tile})

                    if warnings:
                        warnings_out.append({"index": idx, "warnings": warnings})

            response: dict[str, Any] = {
                "updated": len(applied),
                "touched_chunks": [
                    {"chunk_x": cx, "chunk_y": cy}
                    for (cx, cy) in sorted(touched_chunks)
                ],
                "tiles": applied,
            }
            if warnings_out:
                response["warnings"] = warnings_out

            return jsonify(response), 200
        except TileValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/tiles/region")
    def get_tiles_region():
        try:
            x1 = _parse_query_int("x1")
            y1 = _parse_query_int("y1")
            x2 = _parse_query_int("x2")
            y2 = _parse_query_int("y2")
        except TileValidationError as exc:
            return jsonify({"error": str(exc)}), 400

        with get_db() as conn:
            tiles = get_region_tiles(conn, x1, y1, x2, y2)

        return jsonify({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "tiles": tiles}), 200

    @app.post("/foreground-entities")
    def create_entity():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        entity_type = payload.get("entity_type")
        if not isinstance(entity_type, str) or not entity_type:
            return jsonify({"error": "entity_type must be a non-empty string"}), 400

        origin_x = payload.get("origin_x")
        origin_y = payload.get("origin_y")
        if not isinstance(origin_x, int) or not isinstance(origin_y, int):
            return jsonify({"error": "origin_x and origin_y must be integers"}), 400

        data_json = payload.get("data_json", {})
        if not isinstance(data_json, dict):
            return jsonify({"error": "data_json must be an object"}), 400

        entity_id = payload.get("id")
        if entity_id is not None and (not isinstance(entity_id, str) or not entity_id):
            return jsonify({"error": "id must be a non-empty string when provided"}), 400

        try:
            with get_db() as conn:
                entity = create_foreground_entity(
                    conn,
                    entity_type=entity_type,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    data_json=data_json,
                    entity_id=entity_id,
                )
            return jsonify(entity), 201
        except Exception as exc:
            # sqlite3.IntegrityError and other storage errors
            return jsonify({"error": f"Failed to create foreground entity: {exc}"}), 500

    @app.get("/foreground-entities/<entity_id>")
    def get_entity(entity_id: str):
        with get_db() as conn:
            entity = get_foreground_entity(conn, entity_id)

        if not entity:
            return jsonify({"error": "foreground entity not found"}), 404

        return jsonify(entity), 200
