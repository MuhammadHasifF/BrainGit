"""Application settings loaded from environment variables.

All secrets, IDs, and tunables live here. Nothing else in the codebase
should read `os.environ` directly — go through `settings`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ────────────────────────────────────────────────────────────
    environment: Literal["development", "production"] = "production"
    log_level: str = "INFO"
    timezone: str = "Asia/Singapore"
    public_base_url: str = "https://bot.example.com"

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://brainbot:brainbot@localhost:5432/brainbot",
        description="SQLAlchemy async URL.",
    )

    # ── Crypto ──────────────────────────────────────────────────────────
    fernet_key: str = Field(
        default="",
        description="Fernet key for encrypting OAuth tokens at rest.",
    )

    # ── Telegram ────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_group_chat_id: int = 0
    allowed_user_ids: str = ""

    topic_daily_routine: int = 0
    topic_evening_recap: int = 0
    topic_emails: int = 0
    topic_calendar: int = 0
    topic_todos: int = 0
    topic_second_brain: int = 0
    topic_quick_notes: int = 0
    topic_general: int = 0

    # ── Gemini ──────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model_fast: str = "gemini-2.5-flash"
    gemini_model_smart: str = "gemini-2.5-pro"
    gemini_embedding_model: str = "text-embedding-004"

    # ── Google OAuth ────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8765/oauth/google/callback"
    google_account_labels: str = "main,spam1,spam2"

    # ── Microsoft Graph ─────────────────────────────────────────────────
    ms_client_id: str = ""
    ms_tenant_id: str = "common"
    ms_redirect_uri: str = "http://localhost:8765/oauth/microsoft/callback"
    ms_account_label: str = "school"

    # ── Rate limit ──────────────────────────────────────────────────────
    webhook_rate_limit_per_minute: int = 120

    # ── Validators / derived ────────────────────────────────────────────
    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def allowed_user_id_set(self) -> set[int]:
        """Parse comma-separated user IDs into a set of ints."""
        if not self.allowed_user_ids:
            return set()
        return {int(x.strip()) for x in self.allowed_user_ids.split(",") if x.strip()}

    @property
    def google_account_label_list(self) -> list[str]:
        return [x.strip() for x in self.google_account_labels.split(",") if x.strip()]

    @property
    def topic_map(self) -> dict[int, str]:
        """Reverse map: topic_thread_id -> topic name. Zeroes are skipped."""
        candidates = {
            self.topic_daily_routine: "daily_routine",
            self.topic_evening_recap: "evening_recap",
            self.topic_emails: "emails",
            self.topic_calendar: "calendar",
            self.topic_todos: "todos",
            self.topic_second_brain: "second_brain",
            self.topic_quick_notes: "quick_notes",
            self.topic_general: "general",
        }
        return {tid: name for tid, name in candidates.items() if tid}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Use this everywhere."""
    return Settings()
