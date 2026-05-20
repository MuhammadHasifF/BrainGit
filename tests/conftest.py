"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest

# Set safe defaults BEFORE any brainbot imports happen.
os.environ.setdefault("FERNET_KEY", "x" * 44 + "=")  # Fernet keys are 44-char urlsafe-b64
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_GROUP_CHAT_ID", "-100123")
os.environ.setdefault("ALLOWED_USER_IDS", "42")
os.environ.setdefault("GEMINI_API_KEY", "fake")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x@localhost/x")
os.environ.setdefault("TOPIC_EMAILS", "100")
os.environ.setdefault("TOPIC_CALENDAR", "200")
os.environ.setdefault("TOPIC_TODOS", "300")
os.environ.setdefault("TOPIC_SECOND_BRAIN", "400")
os.environ.setdefault("TOPIC_QUICK_NOTES", "500")
os.environ.setdefault("TOPIC_GENERAL", "600")
os.environ.setdefault("TOPIC_DAILY_ROUTINE", "700")
os.environ.setdefault("TOPIC_EVENING_RECAP", "800")


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """The settings singleton is cached — reset it between tests."""
    from brainbot.config import get_settings

    get_settings.cache_clear()
