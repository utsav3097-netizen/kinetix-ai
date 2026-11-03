"""Server-only environment configuration; never expose this object through an API."""

import json
import secrets
import warnings
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.email_address import canonical_email

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test", "development", "staging", "production"] = "local"
    database_url: str = "sqlite:///./kinetix.db"
    jwt_secret: SecretStr | None = None
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    admin_email: str | None = None
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = "gemini-3.8-flash"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = "gpt-5.6-terra"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    refresh_cookie_name: str = "kinetix_refresh"

    @field_validator("jwt_secret", "gemini_api_key", "openai_api_key", mode="before")
    @classmethod
    def empty_secret(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("admin_email", "gemini_model", "openai_model", mode="before")
    @classmethod
    def optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("admin_email")
    @classmethod
    def canonical_admin_email(cls, value: str | None) -> str | None:
        return canonical_email(value) if value is not None else None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return json.loads(value) if value.startswith("[") else [
                origin.strip() for origin in value.split(",") if origin.strip()
            ]
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        origins = []
        for value in values:
            parts = urlsplit(value)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.username is not None
                or parts.password is not None
                or parts.path not in {"", "/"}
                or parts.query
                or parts.fragment
                or "*" in value
            ):
                raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins")
            origins.append(value.rstrip("/"))
        return origins

    @field_validator("refresh_cookie_name")
    @classmethod
    def validate_cookie_name(cls, value: str) -> str:
        if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in value):
            raise ValueError("REFRESH_COOKIE_NAME must be an alphanumeric cookie name")
        return value

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        url = make_url(self.database_url)
        backend = url.get_backend_name()
        if backend not in {"sqlite", "postgresql"}:
            raise ValueError("DATABASE_URL must use SQLite or PostgreSQL")
        if backend == "sqlite" and self.app_env != "local":
            raise ValueError("SQLite is allowed only with APP_ENV=local")
        if backend == "postgresql":
            if url.drivername not in {"postgresql", "postgresql+psycopg"}:
                raise ValueError("PostgreSQL must use the psycopg synchronous driver")
            self.database_url = url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        elif url.drivername != "sqlite":
            raise ValueError("SQLite must use the synchronous sqlite driver")
        if self.jwt_secret is None:
            if self.app_env != "local":
                raise ValueError("JWT_SECRET is required outside local development")
            self.jwt_secret = SecretStr(secrets.token_urlsafe(48))
            warnings.warn(
                "Using an ephemeral local JWT secret; sessions will not survive restarts. "
                "Set JWT_SECRET for stable sessions.",
                UserWarning,
                stacklevel=2,
            )
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32 or len(set(secret)) < 12 or secret != secret.strip():
            raise ValueError("JWT_SECRET must be a randomly generated secret of at least 32 characters")
        if self.app_env != "local" and any(not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("Non-local CORS_ORIGINS must use HTTPS (or be an empty list for same-origin hosting)")
        return self

    @property
    def refresh_cookie_secure(self) -> bool:
        return self.app_env != "local"

    @property
    def refresh_cookie_httponly(self) -> bool:
        return True

    @property
    def refresh_cookie_samesite(self) -> Literal["lax"]:
        return "lax"

    @property
    def refresh_cookie_path(self) -> str:
        return "/api/v1/auth"


settings = Settings()
