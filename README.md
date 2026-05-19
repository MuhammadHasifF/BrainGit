# brainbot

A personal AI assistant accessed via a Telegram group chat.

One user. One group. Many topics. Bot routes messages by topic to a
specialised agent (email, calendar, todos, second brain) and uses Gemini
function calling to take action across your accounts:

- **School Microsoft 365** — Outlook mail + calendar (via Microsoft Graph)
- **Main Gmail** — Gmail + Google Calendar
- **Two spam Gmail accounts** — read-only triage
- **Postgres + pgvector** — todos and a semantic second brain
- **Scheduled briefings** — 7 AM SGT morning brief, 10 PM SGT evening recap

## Stack

| Layer        | Choice                                                |
|--------------|--------------------------------------------------------|
| Language     | Python 3.11+                                          |
| Web          | FastAPI + uvicorn                                     |
| Telegram     | `python-telegram-bot` (async)                         |
| LLM          | Google Gemini (`google-genai` SDK, function calling)  |
| Embeddings   | Gemini `text-embedding-004`                           |
| DB           | PostgreSQL 16 + pgvector                              |
| ORM          | SQLAlchemy 2.0 async + Alembic                        |
| Scheduler    | APScheduler (in-process)                              |
| Deploy       | Docker Compose on Oracle Cloud Always Free ARM VM     |
| TLS          | Caddy (auto Let's Encrypt)                            |

## Quick links

- **Setup from scratch:** see [SETUP.md](SETUP.md). Written for someone who has never used Docker or SSH.
- **For future Claude Code sessions:** see [CLAUDE.md](CLAUDE.md).

## Local dev cheat sheet

```bash
# 1. Copy env template, fill in values
cp .env.example .env

# 2. Start postgres + bot via Docker
docker compose up -d

# 3. Run migrations
docker compose exec bot alembic upgrade head

# 4. Tail logs
docker compose logs -f bot
```

## License

MIT.
