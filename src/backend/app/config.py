"""Application configuration.

All secrets and environment-specific values come from environment variables.
See .env.example at the repository root.
"""
from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    # --- Core ---
    APP_NAME: str = "Mysuru CivicPulse API"
    ENV: str = os.getenv("ENV", "development")

    # Default is a local SQLite file so the project runs from a clean machine
    # with zero external services. Set DATABASE_URL to a Postgres DSN for
    # production / Supabase. See docs/setup.md.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./civicpulse.db"
    )

    # --- Auth ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "720"))

    # --- Evidence uploads ---
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    ALLOWED_MIME: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")
    EVIDENCE_DIR: str = os.getenv("EVIDENCE_DIR", "./evidence_store")

    # --- Duplicate detection tuning (documented, not magic) ---
    DUP_RADIUS_M: float = float(os.getenv("DUP_RADIUS_M", "150"))
    DUP_TIME_WINDOW_HOURS: int = int(os.getenv("DUP_TIME_WINDOW_HOURS", "336"))  # 14d
    DUP_MIN_SIMILARITY: float = float(os.getenv("DUP_MIN_SIMILARITY", "0.55"))

    # --- Paging ---
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200

    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")

    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
