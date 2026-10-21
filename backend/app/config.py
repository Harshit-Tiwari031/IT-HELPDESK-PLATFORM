from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/helpdesk_db"
    app_env: str = "development"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: int = Field(default=30, ge=5, le=120)
    auth_session_hours: int = Field(default=8, ge=1, le=168)
    auth_cookie_name: str = "helpdesk_session"
    csrf_cookie_name: str = "helpdesk_csrf"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        origins = [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins; wildcard origins are not supported.")
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("CORS_ORIGINS entries must be explicit HTTP(S) origins without paths.")
            if self.app_env.casefold() in {"production", "prod"} and parsed.scheme != "https":
                raise ValueError("Production CORS origins must use HTTPS.")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
