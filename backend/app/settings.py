# backend/app/settings.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

class Settings(BaseSettings):
    APP_NAME: str = "music-backend"
    APP_ENV: str = "dev"
    APP_PORT: int = 8000
    APP_HOST: str = "0.0.0.0"

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MIN: int = 60

    PG_URL: str

    SPOTIFY_CLIENT_ID: str | None = None
    SPOTIFY_CLIENT_SECRET: str | None = None
    YOUTUBE_API_KEY: str | None = None
    GENIUS_API_TOKEN: str | None = None

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

settings = Settings()
