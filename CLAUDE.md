# CLAUDE.md — brainbot

Working notes for future Claude Code sessions. Read this *before* making
non-trivial changes.

---

## What this project is

A single-user personal AI assistant accessed via a Telegram group with
Topics enabled. One user (configured via `ALLOWED_USER_IDS`) sends
natural-language messages in topic-scoped threads; the bot routes each
message to a specialised agent and uses Gemini function calling to
execute actions across Gmail, Outlook (school), Google Calendar,
Outlook Calendar, a todo list (Postgres), and a pgvector-backed second
brain.

Deploy target: Oracle Cloud Always Free ARM Ubuntu 22.04 via Docker
Compose. Free-tier across the stack — don't introduce paid services.

See [README.md](README.md) for the stack table and [SETUP.md](SETUP.md)
for the full deploy procedure.

---

## High-level layout

```
src/brainbot/
├── main.py            # FastAPI app, /telegram/webhook, lifespan
├── config.py          # Pydantic Settings; reads .env
├── db.py              # async SQLAlchemy engine + session_scope
├── models.py          # all ORM tables (todos, notes, embeddings, ...)
│
├── telegram/
│   ├── webhook.py     # parse + auth incoming updates
│   ├── send.py        # outbound messages, inline buttons, MarkdownV2 escape
│   └── topics.py      # TopicName enum + thread_id <-> topic mapping
│
├── llm/
│   ├── client.py      # GeminiClient: function-calling loop, embeddings
│   └── tools.py       # Tool, ToolRegistry, schema_* helpers
│
├── agents/
│   ├── base.py        # BaseAgent (system_prompt, ToolRegistry, .handle)
│   ├── router.py      # topic -> agent dispatch
│   ├── general_agent.py
│   ├── email_agent.py
│   ├── calendar_agent.py
│   ├── todo_agent.py
│   ├── brain_agent.py      # 2nd brain + quick-notes auto-save
│   └── routine_agent.py    # composes morning + evening briefings
│
├── connectors/
│   ├── oauth_store.py      # Fernet-encrypted token CRUD
│   ├── gmail.py            # Gmail (3 accounts via account_label)
│   ├── google_calendar.py
│   ├── outlook.py          # MS Graph mail (httpx + MSAL)
│   └── outlook_calendar.py
│
├── memory/
│   ├── embeddings.py       # text-embedding-004 wrapper
│   ├── vector_store.py     # save_note, semantic_search, notes_in_range
│   └── conversation.py     # per-topic short-term state
│
├── scheduler/
│   ├── jobs.py             # APScheduler bootstrap + deliver_due_reminders
│   ├── morning.py          # runs at 07:00 SGT
│   └── evening.py          # runs at 22:00 SGT
│
└── utils/
    ├── time.py             # SGT timezone helpers (UTC <-> local)
    └── logging.py          # structlog JSON logging
```

Other top-level dirs: `alembic/` (migrations), `infra/` (Caddy, Oracle
bootstrap, systemd), `scripts/` (one-off OAuth + topic-seed CLIs),
`tests/{unit,integration}/`.

---

## Conventions

- **Python 3.11+**, async everywhere.
- **Format & lint:** `ruff format .` and `ruff check .`. CI not wired up
  — run them by hand. Strict mypy where it doesn't fight too hard.
- **Type hints required.** No untyped public functions.
- **No blocking IO in async paths.** Use `asyncio.to_thread` for sync
  SDK calls (the Gmail/Calendar Google libs are synchronous).
- **Logging:** `from brainbot.utils.logging import get_logger`; structured
  JSON to stdout (docker logs reads it).
- **Settings:** never `os.environ`, always `get_settings()`.
- **Commits:** conventional commits (`feat:`, `fix:`, `chore:`, `docs:`,
  `test:`). One logical change per commit.
- **Modules under ~300 lines.** If something is getting long, split.
- **Comments:** prefer not. When you write one, explain *why*, not *what*.
  Use the `# DESIGN NOTE:` prefix when capturing a deliberate
  simplification.

---

## How to add a new agent

1. Create `src/brainbot/agents/foo_agent.py` subclassing `BaseAgent`.
2. Set `name`, `system_prompt`, and `smart = True/False`.
3. Override `register_tools(self)` and add `Tool(...)` entries with JSON
   Schema parameters and an async handler. Use the `schema_object`,
   `schema_string`, etc. helpers in `brainbot.llm.tools`.
4. Register the agent in `router._agent_for(topic)`.
5. If the agent needs a new topic, add it to `topics.py`'s `TopicName`
   enum, the `topic_map` property in `config.py`, the `.env.example`,
   and SETUP.md's topic list.

The default `BaseAgent.handle` runs the LLM with your tools and posts the
text reply. Override `handle` only if you need bespoke behaviour
(e.g. `BrainAgent` auto-saves Quick Notes without an LLM round-trip).

---

## How to add a new tool to an existing agent

Inside that agent's `register_tools`:

```python
self.tools.add(Tool(
    name="my_tool",
    description="Short, imperative description.",
    parameters=schema_object(
        {"arg1": schema_string("what this is")},
        required=["arg1"],
    ),
    handler=_my_tool_handler,
))
```

Handler signature: `async def _my_tool_handler(args: dict[str, Any]) -> Any`.
Return must be JSON-serialisable (the client coerces via `default=str`).

---

## How to add a new connector / external account

1. Put the connector in `src/brainbot/connectors/<name>.py`. Mirror the
   shape of `gmail.py`/`outlook.py`: a small dataclass for read results,
   plus async functions that wrap the SDK.
2. If it requires OAuth, store the refresh token via
   `connectors.oauth_store.save_token` keyed by `provider="<name>"` and
   `account_label="<label>"`. Reads go through `load_token` +
   `refresh_required`.
3. Run blocking SDK calls inside `asyncio.to_thread`.
4. Add a one-off CLI in `scripts/auth_<name>.py` modelled on
   `auth_google.py` / `auth_microsoft.py`.

---

## How to add a new database table

1. Add the ORM model to `src/brainbot/models.py`.
2. Generate a migration:
   ```bash
   docker compose exec bot alembic revision -m "add foo" --autogenerate
   ```
   Review the generated file; autogen misses indexes and JSONB defaults
   sometimes. Hand-fix as needed.
3. Apply: `docker compose exec bot alembic upgrade head`.

---

## How to test

```bash
pip install -e ".[dev]"
pytest -q                  # unit + integration
pytest tests/unit -q       # unit only
```

The integration test in `tests/integration/test_webhook_endpoint.py`
boots the FastAPI app with `TestClient`, patching the scheduler and
agent router. It's a good template for writing more integration tests —
don't reach for live Gemini/Postgres unless absolutely necessary.

`conftest.py` sets safe default env vars before any `brainbot.*` imports.
If you add a new required setting, give it a sensible default there.

---

## Scheduling work

The scheduler lives in-process (APScheduler `AsyncIOScheduler`). It is
started in the FastAPI lifespan, so you get scheduled jobs only when the
app is running — that's fine for our single-instance setup.

To add a job:

```python
# in scheduler/jobs.py inside start_scheduler()
_scheduler.add_job(
    run_my_task,
    CronTrigger(hour=12, minute=0, timezone=tz),
    id="my_task",
    replace_existing=True,
)
```

For one-off "fire at this UTC time" reminders, write a row into
`scheduled_reminders` — `deliver_due_reminders` flushes due rows every
minute.

---

## Secrets, never-commit-these list

- `.env` is gitignored. Only `.env.example` is committed.
- `secrets/` is gitignored. OAuth client JSONs and any local keys live
  there.
- `postgres_data/`, `caddy_data/`, `caddy_config/`, `logs/` are mounted
  by Compose and gitignored.

If you find a file with real credentials in the repo: stop, remove it,
rotate the secret, and force-push only if it never reached `main`.

---

## Operational gotchas

- **Oracle Cloud iptables.** UFW alone is not enough — the Oracle
  iptables ruleset blocks 80/443 by default. `oracle_setup.sh` patches
  this. If you reset iptables, run that script again.
- **Caddy + DNS.** Caddy fails closed if the domain doesn't resolve. If
  the bot's TLS isn't coming up, check `dig +short bot.example.com`.
- **Gemini quotas.** Free tier is generous but not infinite. The tool
  loop is capped at 8 turns (`MAX_TOOL_TURNS` in `llm/client.py`) to
  avoid runaway usage.
- **Microsoft refresh-token expiry.** Inactive refresh tokens age out
  (~90 days). Re-run `scripts/auth_microsoft.py` if refresh stops working.
- **FERNET_KEY is unrotatable in place.** Don't change it without
  re-running every OAuth script.
- **APScheduler timezone.** All cron triggers use `settings.timezone`
  (SGT by default). Don't mix naive UTC times with cron triggers.

---

## When in doubt

- Prefer the **simpler option** and leave a `# DESIGN NOTE:` comment.
- Don't add a service to compose without justifying why in-process won't
  work.
- Don't break ARM compatibility. If a dependency only has x86 wheels,
  pick a different one.
- Keep the bot **boring** — the user is a single human and reliability
  beats cleverness.
