"""One-off CLI to authorise the school Microsoft 365 account.

Uses the OAuth device-code flow: easy on a headless box, but you can
run this from your laptop too. The script:

1. Reads MS_CLIENT_ID / MS_TENANT_ID from .env.
2. Prints a code + URL. You open the URL on any device, paste the code,
   and approve.
3. Saves refresh + access tokens, encrypted, into `account_tokens`.

    python scripts/auth_microsoft.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import msal

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from brainbot.config import get_settings  # noqa: E402
from brainbot.connectors.oauth_store import save_token  # noqa: E402

SCOPES = [
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "User.Read",
]
# `offline_access` gets us a refresh token; it's a reserved scope so we add it implicitly.


async def main_async() -> None:
    settings = get_settings()
    if not settings.ms_client_id:
        sys.exit("MS_CLIENT_ID not set in .env. Register an app in Azure first (see SETUP.md).")

    authority = f"https://login.microsoftonline.com/{settings.ms_tenant_id}"
    app = msal.PublicClientApplication(client_id=settings.ms_client_id, authority=authority)

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        sys.exit(f"Failed to start device-code flow: {flow}")

    print()
    print(flow["message"])
    print()
    print("Waiting for you to approve in the browser...")

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        sys.exit(f"Auth failed: {result.get('error_description')}")

    expires_in = int(result.get("expires_in", 3600))
    await save_token(
        account_label=settings.ms_account_label,
        provider="microsoft",
        refresh_token=result.get("refresh_token", ""),
        access_token=result["access_token"],
        expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in - 60),
        scopes=SCOPES,
    )
    print(f"Saved Microsoft tokens for label={settings.ms_account_label!r}.")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
