"""One-off CLI to authorise a Google account (Gmail + Calendar).

Run this on your laptop (not the server) for each Google account:

    python scripts/auth_google.py --label main
    python scripts/auth_google.py --label spam1
    python scripts/auth_google.py --label spam2

The script:
1. Reads GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET from .env (or accepts a
   path to credentials.json via --credentials).
2. Opens a browser, runs the OAuth consent flow.
3. Saves the resulting refresh + access tokens, encrypted, into the
   `account_tokens` table.

Requires the bot's database to be reachable (DATABASE_URL).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Make `src/` importable when running from a checkout.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from brainbot.config import get_settings  # noqa: E402
from brainbot.connectors.oauth_store import save_token  # noqa: E402

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def _build_client_config(credentials_path: Path | None) -> dict:
    settings = get_settings()
    if credentials_path:
        return json.loads(credentials_path.read_text())
    if not settings.google_client_id or not settings.google_client_secret:
        sys.exit(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing in .env. "
            "Pass --credentials path/to/credentials.json instead."
        )
    return {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


async def main_async(label: str, credentials: Path | None, port: int) -> None:
    client_config = _build_client_config(credentials)
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")
    print(f"\nOAuth complete. Saving tokens for label={label!r}...")
    await save_token(
        account_label=label,
        provider="google",
        refresh_token=creds.refresh_token,
        access_token=creds.token,
        expires_at=creds.expiry,
        scopes=list(creds.scopes or SCOPES),
    )
    print("Saved. You can close this window.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorise a Google account for brainbot.")
    parser.add_argument("--label", required=True, help="e.g. main, spam1, spam2")
    parser.add_argument("--credentials", type=Path, help="Path to credentials.json")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    asyncio.run(main_async(args.label, args.credentials, args.port))


if __name__ == "__main__":
    main()
