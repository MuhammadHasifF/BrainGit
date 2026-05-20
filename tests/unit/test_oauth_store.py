from __future__ import annotations

from datetime import datetime, timedelta, timezone

from brainbot.connectors.oauth_store import TokenBlob, refresh_required


def _blob(*, access: str | None, expires_at: datetime | None) -> TokenBlob:
    return TokenBlob(
        account_label="main",
        provider="google",
        refresh_token="r",
        access_token=access,
        expires_at=expires_at,
        scopes=[],
        extra={},
    )


def test_refresh_required_when_no_access_token() -> None:
    assert refresh_required(_blob(access=None, expires_at=None)) is True


def test_refresh_required_when_missing_expiry() -> None:
    assert refresh_required(_blob(access="a", expires_at=None)) is True


def test_refresh_required_when_close_to_expiry() -> None:
    near_expiry = datetime.now(tz=timezone.utc) + timedelta(seconds=30)
    assert refresh_required(_blob(access="a", expires_at=near_expiry)) is True


def test_refresh_not_required_when_plenty_of_time() -> None:
    far_expiry = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    assert refresh_required(_blob(access="a", expires_at=far_expiry)) is False
