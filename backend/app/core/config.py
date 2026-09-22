from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_SECRET = "change-me-in-production-change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "demo", "prod", "test"] = "dev"
    database_url: str = "postgresql+asyncpg://sms:sms@localhost:5432/sms"

    # --- auth ---
    jwt_secret: str = _INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    refresh_reuse_grace_seconds: int = 10
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # --- login protection ---
    login_max_attempts: int = 5
    login_window_minutes: int = 15
    login_lock_minutes: int = 15
    login_ip_limit: int = 30  # attempts per window, per IP (per process)

    # --- uploads ---
    upload_dir: str = "./uploads"
    upload_url_prefix: str = "/api/v1/uploads"
    max_upload_bytes: int = 2 * 1024 * 1024

    # --- web ---
    cors_origins: str = "http://localhost:3000"

    # --- seed ---
    first_admin_username: str = "admin"
    first_admin_password: str = ""
    seed_demo_password: str = "Demo@12345"
    seed_sample_data: bool = False  # classes, subjects, fees, students and teachers; always on when APP_ENV=demo

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        if self.app_env in ("prod", "demo"):
            placeholder = self.jwt_secret == _INSECURE_DEFAULT_SECRET or self.jwt_secret.startswith("CHANGE_ME")
            if placeholder or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ characters (openssl rand -hex 32)")
        if self.app_env == "prod" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true when APP_ENV=prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
