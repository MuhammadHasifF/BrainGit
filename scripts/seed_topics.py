"""Discover topic `message_thread_id`s for your Telegram group.

Telegram doesn't expose topic IDs in the UI. The simplest trick:

1. Make sure the bot is added to your group as an admin.
2. Send a message in EACH topic.
3. Run this script. It will dump the latest `update`s and print every
   (topic_name, message_thread_id) pair it sees so you can paste them
   into .env.

This script uses long-polling (`getUpdates`) — only run it BEFORE you
set the webhook URL on the bot. After Telegram has a webhook configured,
`getUpdates` is disabled.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from telegram import Bot

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from brainbot.config import get_settings  # noqa: E402


async def main_async() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        sys.exit("TELEGRAM_BOT_TOKEN not set in .env.")

    bot = Bot(token=settings.telegram_bot_token)
    print("Fetching recent updates...")
    updates = await bot.get_updates(timeout=2, limit=100)

    seen: dict[int, str] = {}
    for upd in updates:
        msg = upd.message or upd.edited_message
        if not msg:
            continue
        thread_id = msg.message_thread_id
        if not thread_id:
            continue
        topic_name = (msg.reply_to_message.forum_topic_created.name
                      if msg.reply_to_message and msg.reply_to_message.forum_topic_created
                      else "(unknown — first message in topic?)")
        if thread_id not in seen:
            seen[thread_id] = topic_name

    if not seen:
        print()
        print("No topic IDs found. Did you:")
        print("  1) Add the bot to the group?")
        print("  2) Enable Topics in group settings?")
        print("  3) Send a message in each topic AFTER adding the bot?")
        print("  4) Not set a webhook URL yet (this only works in polling mode)?")
        return

    print()
    print("Found topics. Paste these into your .env:")
    for tid, name in sorted(seen.items()):
        print(f"  thread_id={tid:<8}  topic={name}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
