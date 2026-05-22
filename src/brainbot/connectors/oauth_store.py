"""Encrypted OAuth token storage.

We store refresh + access tokens in the `account_tokens` table, each
encrypted with a Fernet key from `FERNET_KEY`. Tokens are decrypted only
in-memory at the moment we need them.

Scope across the codebase:
- `save_token(...)`  — upsert credentials for a (provider, label).
- `load_token(...)`  — return a decrypted TokenBlob or None.
- `refresh_required(token)` — has the access token expired?
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from brainbot.config import get_settings
from brainbot.db import session_scope
from brainbot.models import AccountToken
from brainbot.utils.logging import get_logger

log = get_logger(__name__)

# Treat tokens as expired this many seconds before their real expiry to
# give us breathing room for clock skew.
EXPIRY_SKEW = timedelta(seconds=60)


@dataclass(slots=True)
class TokenBlob:
    account_label: str
    provider: str
    refresh_token: str
    access_token: str | None
    expires_at: datetime | None
    scopes: list[str]
    extra: dict[str, Any]


def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise RuntimeError("FERNET_KEY not configured; cannot encrypt tokens.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def _encrypt(value: str | None) -> bytes | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode())


def _decrypt(value: bytes | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value).decode()
    except InvalidToken as exc:
        raise RuntimeError("Failed to decrypt token — wrong FERNET_KEY?") from exc


async def save_token(
    *,
    account_label: str,
    provider: str,
    refresh_token: str,
    access_token: str | None = None,
    expires_at: datetime | None = None,
    scopes: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    async with session_scope() as session:
        result = await session.execute(
            select(AccountToken).where(
                AccountToken.account_label == account_label,
                AccountToken.provider == provider,
            )
        )
        row = result.scalar_one_or_none()

        encrypted_refresh = _encrypt(refresh_token)
        encrypted_access = _encrypt(access_token)

        if row is None:
            row = AccountToken(
                account_label=account_label,
                provider=provider,
                encrypted_refresh_token=encrypted_refresh,  # type: ignore[arg-type]
                encrypted_access_token=encrypted_access,
                expires_at=expires_at,
                scopes=scopes or [],
                extra=extra or {},
            )
            session.add(row)
        else:
            row.encrypted_refresh_token = encrypted_refresh  # type: ignore[assignment]
            row.encrypted_access_token = encrypted_access
            row.expires_at = expires_at
            if scopes is not None:
                row.scopes = scopes
            if extra is not None:
                row.extra = extra
        log.info("token_saved", provider=provider, account=account_label)


async def load_token(*, account_label: str, provider: str) -> TokenBlob | None:
    async with session_scope() as session:
        result = await session.execute(
            select(AccountToken).where(
                AccountToken.account_label == account_label,
                AccountToken.provider == provider,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return TokenBlob(
            account_label=row.account_label,
            provider=row.provider,
            refresh_token=_decrypt(row.encrypted_refresh_token) or "",
            access_token=_decrypt(row.encrypted_access_token),
            expires_at=row.expires_at,
            scopes=list(row.scopes or []),
            extra=dict(row.extra or {}),
        )


def refresh_required(token: TokenBlob) -> bool:
    if not token.access_token:
        return True
    if token.expires_at is None:
        return True
    now = datetime.now(tz=timezone.utc)
    return now + EXPIRY_SKEW >= token.expires_at
