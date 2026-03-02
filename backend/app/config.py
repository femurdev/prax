import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


@dataclass(frozen=True)
class Settings:
    db_path: Path = BASE_DIR / "app.db"
    discord_client_id: str = os.getenv("DISCORD_CLIENT_ID", "")
    discord_client_secret: str = os.getenv("DISCORD_CLIENT_SECRET", "")
    discord_redirect_uri: str = os.getenv(
        "DISCORD_REDIRECT_URI", "http://localhost:5000/auth/discord/callback"
    )
    session_secret: str = os.getenv("SESSION_SECRET", "replace-me")
    session_cookie_secure: bool = (
        os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    )
    port: int = int(os.getenv("PORT", "5000"))
    frontend_dir: Path = FRONTEND_DIR
    base_dir: Path = BASE_DIR


settings = Settings()
