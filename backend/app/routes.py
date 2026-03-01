import secrets

import requests
from flask import Flask, jsonify, redirect, request, session

from .config import settings
from .db import current_user, get_db


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
