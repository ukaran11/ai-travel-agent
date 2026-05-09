"""
Application configuration using pydantic-settings.
All settings are loaded from environment variables or .env file.
"""
from __future__ import annotations

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Google API Keys ──────────────────────────────────────────────────
    google_places_api_key: str = ""
    google_geocoding_api_key: str = ""

    # ── Gemini / LLM ────────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-001"

    # ── Application ──────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    version: str = "1.0.0"

    # ── Search ──────────────────────────────────────────────────────────
    max_results: int = 20
    default_radius_meters: int = 5000

    # ── Mock mode ────────────────────────────────────────────────────────
    # When True, all external API calls (Places, Geocoding, Gemini) are
    # replaced with pre-canned fake responses so the app works locally
    # without any real API keys.  Set USE_MOCKS=false in .env to disable.
    use_mocks: bool = True

    # ── Session ─────────────────────────────────────────────────────────
    session_ttl_seconds: int = 3600
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


settings = Settings()
