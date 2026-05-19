"""Gmail connector.

Provides high-level async helpers backed by the Google API Python
client. All blocking SDK calls are pushed to a worker thread.

Each call accepts `account_label` so the same module can serve the main
Gmail and the two spam Gmail accounts; the only difference is which
stored OAuth credentials we load.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Any

from google.auth.transport.requests import Request as GAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from brainbot.config import get_settings
from brainbot.connectors.oauth_store import load_token, save_token
from brainbot.utils.logging import get_logger

log = get_logger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


@dataclass(slots=True)
class EmailSummary:
    id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str
    unread: bool


async def _credentials(account_label: str) -> Credentials:
    """Return refreshed google.oauth2.Credentials for the labelled account."""
    settings = get_settings()
    token = await load_token(account_label=account_label, provider="google")
    if token is None:
        raise RuntimeError(
            f"No Google credentials for account {account_label!r}. "
            "Run `python scripts/auth_google.py` first."
        )
    creds = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=token.scopes or GMAIL_SCOPES,
    )
    if not creds.valid:
        await asyncio.to_thread(creds.refresh, GAuthRequest())
        await save_token(
            account_label=account_label,
            provider="google",
            refresh_token=creds.refresh_token or token.refresh_token,
            access_token=creds.token,
            expires_at=creds.expiry.replace(tzinfo=None) if creds.expiry else None,
            scopes=list(creds.scopes or token.scopes),
        )
    return creds


async def _service(account_label: str) -> Any:
    creds = await _credentials(account_label)
    return await asyncio.to_thread(build, "gmail", "v1", credentials=creds, cache_discovery=False)


# ── Read ─────────────────────────────────────────────────────────────

async def list_messages(
    account_label: str, *, query: str = "is:unread", max_results: int = 20
) -> list[EmailSummary]:
    svc = await _service(account_label)
    listing = await asyncio.to_thread(
        lambda: svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    )
    out: list[EmailSummary] = []
    for entry in listing.get("messages", []):
        msg = await asyncio.to_thread(
            lambda mid=entry["id"]: svc.users()
            .messages()
            .get(userId="me", id=mid, format="metadata",
                 metadataHeaders=["From", "Subject"]).execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        out.append(
            EmailSummary(
                id=msg["id"],
                thread_id=msg["threadId"],
                sender=headers.get("From", ""),
                subject=headers.get("Subject", ""),
                snippet=msg.get("snippet", ""),
                unread="UNREAD" in msg.get("labelIds", []),
            )
        )
    return out


async def get_message(account_label: str, message_id: str) -> dict[str, Any]:
    svc = await _service(account_label)
    return await asyncio.to_thread(
        lambda: svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    )


# ── Write ────────────────────────────────────────────────────────────

async def send_message(
    account_label: str, *, to: str, subject: str, body: str, reply_to_message_id: str | None = None
) -> str:
    """Send a plain-text email. Returns the new message id.

    Raises if the account is read-only (spam accounts).
    """
    if account_label in {"spam1", "spam2"}:
        raise PermissionError(f"Account {account_label!r} is read-only; cannot send.")

    svc = await _service(account_label)
    mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    body_payload: dict[str, Any] = {"raw": raw}
    if reply_to_message_id:
        # Threading hint: pass threadId so Gmail keeps it in the same thread.
        original = await get_message(account_label, reply_to_message_id)
        body_payload["threadId"] = original.get("threadId")
    sent = await asyncio.to_thread(
        lambda: svc.users().messages().send(userId="me", body=body_payload).execute()
    )
    log.info("email_sent", account=account_label, to=to, id=sent.get("id"))
    return sent.get("id", "")


async def delete_message(account_label: str, message_id: str) -> None:
    svc = await _service(account_label)
    # `trash` is reversible; `delete` is permanent. We default to trash.
    await asyncio.to_thread(
        lambda: svc.users().messages().trash(userId="me", id=message_id).execute()
    )


async def modify_labels(
    account_label: str, message_id: str, *, add: list[str] | None = None, remove: list[str] | None = None
) -> None:
    svc = await _service(account_label)
    body = {"addLabelIds": add or [], "removeLabelIds": remove or []}
    await asyncio.to_thread(
        lambda: svc.users().messages().modify(userId="me", id=message_id, body=body).execute()
    )
