"""Microsoft Graph mail connector (school Outlook account).

Uses a lightweight httpx-based Graph client rather than the heavy
`msgraph-sdk` for simple REST calls — keeps dependencies tractable on
ARM. We still install msgraph-sdk for future use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import msal

from brainbot.config import get_settings
from brainbot.connectors.oauth_store import load_token, save_token
from brainbot.utils.logging import get_logger

log = get_logger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

MS_SCOPES = [
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "offline_access",
    "User.Read",
]


@dataclass(slots=True)
class OutlookEmail:
    id: str
    sender: str
    subject: str
    preview: str
    unread: bool


async def _access_token(account_label: str | None = None) -> str:
    settings = get_settings()
    label = account_label or settings.ms_account_label
    token = await load_token(account_label=label, provider="microsoft")
    if token is None:
        raise RuntimeError(
            "No Microsoft credentials. Run `python scripts/auth_microsoft.py` first."
        )

    # Use MSAL public client to refresh the access token from refresh token.
    authority = f"https://login.microsoftonline.com/{settings.ms_tenant_id}"
    app = msal.PublicClientApplication(client_id=settings.ms_client_id, authority=authority)

    result = app.acquire_token_by_refresh_token(token.refresh_token, scopes=MS_SCOPES)
    if "access_token" not in result:
        raise RuntimeError(f"MS token refresh failed: {result.get('error_description')}")

    expires_in = int(result.get("expires_in", 3600))
    await save_token(
        account_label=label,
        provider="microsoft",
        refresh_token=result.get("refresh_token", token.refresh_token),
        access_token=result["access_token"],
        expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in - 60),
        scopes=MS_SCOPES,
    )
    return str(result["access_token"])


async def _request(method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None) -> Any:
    tok = await _access_token()
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=GRAPH_BASE, timeout=30.0) as client:
        r = await client.request(method, path, headers=headers, json=json, params=params)
        if r.status_code >= 400:
            log.error("graph_error", status=r.status_code, body=r.text[:500])
            r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return None
        return r.json()


# ── Mail ─────────────────────────────────────────────────────────────

async def list_messages(query: str = "isRead eq false", top: int = 20) -> list[OutlookEmail]:
    params = {"$filter": query, "$top": str(top), "$orderby": "receivedDateTime desc"}
    data = await _request("GET", "/me/messages", params=params) or {}
    out: list[OutlookEmail] = []
    for item in data.get("value", []):
        sender_obj = item.get("from", {}).get("emailAddress", {})
        out.append(
            OutlookEmail(
                id=item["id"],
                sender=sender_obj.get("address", ""),
                subject=item.get("subject", ""),
                preview=item.get("bodyPreview", ""),
                unread=not item.get("isRead", True),
            )
        )
    return out


async def get_message(message_id: str) -> dict[str, Any]:
    return await _request("GET", f"/me/messages/{message_id}")


async def send_mail(*, to: str, subject: str, body: str) -> None:
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }
    await _request("POST", "/me/sendMail", json=payload)


async def delete_message(message_id: str) -> None:
    await _request("DELETE", f"/me/messages/{message_id}")


async def mark_read(message_id: str, is_read: bool = True) -> None:
    await _request("PATCH", f"/me/messages/{message_id}", json={"isRead": is_read})
