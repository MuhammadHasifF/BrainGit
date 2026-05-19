# CLAUDE.md — brainbot

Notes for future Claude Code sessions working in this repo. Full
contributor guide will be filled in at Phase 12. The minimum you need
right now:

- This is a single-user Telegram bot. The user is the only authorized
  speaker (see `ALLOWED_USER_IDS`).
- Stack is documented in [README.md](README.md).
- Deploy target is Oracle Cloud Always Free (ARM Ubuntu 22.04) via Docker
  Compose. Don't introduce anything that won't run on ARM.
- Free tier across the board — no paid services, no managed databases.
- Async everywhere. No blocking IO inside request handlers.
- All secrets via env vars; OAuth tokens encrypted at rest with Fernet.
- Convention: `ruff format`, `ruff check`, type hints everywhere,
  conventional commits, modules under ~300 lines.

When adding a new agent or tool, see [SETUP.md](SETUP.md) — full
developer playbook lives there once Phase 12 is complete.
