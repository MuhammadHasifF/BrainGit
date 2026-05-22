# brainbot — setup from scratch

This guide walks you from nothing to a running bot. It assumes:

- You're on macOS or Linux locally. Windows works but commands use bash syntax.
- You've never used Docker, OAuth consoles, or SSH before.
- You're OK with the terminal (you can `cd`, `ls`, paste commands).

**Total time:** about 2½ to 3½ hours, spread across waiting for OAuth approvals,
DNS, and Let's Encrypt. Active work is ~90 minutes.

> Tip: do the entire setup once when you have an uninterrupted block. Half-setup
> states are painful to debug. If you hit a wall, scroll to the relevant
> **Common failures** box.

---

## Table of contents

1. [What you'll end up with](#0-what-youll-end-up-with)
2. [Step 1 — Get a domain name](#step-1--get-a-domain-name-15-min)
3. [Step 2 — Create the Telegram bot and group](#step-2--create-the-telegram-bot-and-group-15-min)
4. [Step 3 — Get a Gemini API key](#step-3--get-a-gemini-api-key-3-min)
5. [Step 4 — Set up Google Cloud (×3 Gmail accounts)](#step-4--set-up-google-cloud-x3-gmail-accounts-30-min)
6. [Step 5 — Register a Microsoft Azure app (school Outlook)](#step-5--register-a-microsoft-azure-app-school-outlook-15-min)
7. [Step 6 — Generate FERNET_KEY and TELEGRAM_WEBHOOK_SECRET](#step-6--generate-fernet_key-and-telegram_webhook_secret-2-min)
8. [Step 7 — Create the Oracle Cloud VM](#step-7--create-the-oracle-cloud-vm-30-min)
9. [Step 8 — SSH in and bootstrap the server](#step-8--ssh-in-and-bootstrap-the-server-15-min)
10. [Step 9 — Point the domain at the VM](#step-9--point-the-domain-at-the-vm-5-min--dns-wait)
11. [Step 10 — Bring the stack up](#step-10--bring-the-stack-up-10-min)
12. [Step 11 — Discover the topic IDs](#step-11--discover-the-topic-ids-5-min)
13. [Step 12 — Run the OAuth scripts locally](#step-12--run-the-oauth-scripts-locally-15-min)
14. [Step 13 — Register the Telegram webhook](#step-13--register-the-telegram-webhook-2-min)
15. [Step 14 — Test in each topic](#step-14--test-in-each-topic-5-min)
16. [Day-to-day operations](#day-to-day-operations)
17. [Architecture](#architecture)
18. [Things you still need to provide / decide](#things-you-still-need-to-provide--decide)

---

## 0. What you'll end up with

- A Telegram group with topics where you talk to the bot.
- An always-on Oracle Cloud ARM VM running:
  - Caddy (HTTPS reverse proxy, free Let's Encrypt cert).
  - The bot (FastAPI + APScheduler).
  - Postgres 16 with pgvector.
- A morning brief at 7am SGT and an evening recap at 10pm SGT.
- Bot can read/send across 4 inboxes, manage 2 calendars, manage todos,
  and search your second-brain notes semantically.

You also need a domain name (Caddy needs one for Let's Encrypt). You can
buy a `.xyz` for ~$1/yr.

---

## Step 1 — Get a domain name (~15 min)

You need a domain so Caddy can fetch a free SSL cert. Telegram only
talks to webhooks over HTTPS.

1. Go to **Namecheap, Porkbun, or Cloudflare Registrar**. Pick any
   cheap TLD — `.xyz`, `.click`, `.lol`. Buy one. Examples below use
   `bot.example.com`.
2. You don't need to set DNS yet — we'll do that in Step 9 after you
   have the VM's IP.

✅ **You should now have:** a registered domain you can edit DNS for.

---

## Step 2 — Create the Telegram bot and group (~15 min)

### 2a. Create the bot

1. Open Telegram. Search for `@BotFather` and start a chat.
2. Send `/newbot`. Pick a name (e.g. "brainbot") and a username ending in `bot`.
3. **BotFather replies with an HTTP token like** `123456:ABC-...`.
   Copy it. This is `TELEGRAM_BOT_TOKEN`.
4. Send `/setprivacy` → pick your bot → `Disable`. This lets the bot
   see all group messages, not just ones mentioning it.
5. Send `/setjoingroups` → pick your bot → `Enable`.

### 2b. Create the group

1. In Telegram → **New Group**.
2. Add **any one** contact (you must — Telegram requires this). You can
   remove them right after.
3. Name the group "brainbot" (or whatever).
4. After creating, open group info → **Topics** → toggle **Enable Topics** on.
5. Promote your bot to admin: group info → Administrators → Add admin →
   pick your bot. Tick "Manage topics" and "Delete messages".

### 2c. Add the topics

In the group, **create one topic per area** with exactly these names:

```
Daily Routine
Evening Recap
Emails
Calendar
Todos
Second Brain
Quick Notes
General
```

Send any message in **each** topic. This is important — `seed_topics.py`
discovers IDs from your recent messages.

### 2d. Find your Telegram user ID

This is the only Telegram account allowed to talk to the bot.

1. In Telegram, message `@userinfobot`.
2. It replies with your numeric ID. Copy it — this is `ALLOWED_USER_IDS`.

### 2e. Find the group chat ID

1. Message `@userinfobot` again, but **forward** any message from the
   brainbot group to it.
2. It will reply with the **chat ID** for the group (starts with `-100`).
   Copy it — this is `TELEGRAM_GROUP_CHAT_ID`.

✅ **You should now have:** `TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS`,
`TELEGRAM_GROUP_CHAT_ID`, and a group with 8 topics, each containing at
least one message.

**Common failures**

- *"Bot doesn't see my messages"* — privacy mode is still on. Re-do step 2a step 4.
- *"Can't find topic IDs"* — you forgot to send a message in each topic
  *after* adding the bot.

---

## Step 3 — Get a Gemini API key (~3 min)

1. Open <https://aistudio.google.com/app/apikey>.
2. Sign in with any Google account.
3. Click **Create API Key**. Copy the key — this is `GEMINI_API_KEY`.

The free tier gives you generous quotas on Gemini 2.5 Flash and Pro
plus text-embedding-004.

✅ **You should now have:** `GEMINI_API_KEY`.

---

## Step 4 — Set up Google Cloud (×3 Gmail accounts) (~30 min)

You need to do this **once per Google account** you want the bot to read
(your main Gmail + the two spam Gmails). The easiest way is to create
**one** OAuth project and add all three accounts as test users.

### 4a. Create the project

1. Open <https://console.cloud.google.com/>.
2. Sign in with your main Google account.
3. Top bar → **Select a project** → **New Project**.
4. Name it `brainbot`. Click Create.

### 4b. Enable Gmail + Calendar APIs

1. Left menu → **APIs & Services** → **Library**.
2. Search **Gmail API** → Enable.
3. Search **Google Calendar API** → Enable.

### 4c. Configure the consent screen

1. Left menu → **APIs & Services** → **OAuth consent screen**.
2. User type: **External**. Create.
3. App name: `brainbot`. User support email + dev contact: any email of yours.
4. Skip scopes (we set them programmatically). Save.
5. **Test users** → Add → enter all three Google email addresses
   (main + spam1 + spam2). Save.

This keeps the app in "Testing" mode forever (refresh tokens still work)
since you're the only user.

### 4d. Create the OAuth client

1. Left menu → **APIs & Services** → **Credentials**.
2. **Create Credentials** → **OAuth client ID**.
3. Application type: **Desktop app**. Name: `brainbot-desktop`. Create.
4. Click **Download JSON** on the new client. Save it as
   `secrets/google_client.json` in the repo *on your laptop*
   (we'll use it locally to do the OAuth dance).
5. Also copy the client ID + secret strings — those go in `.env` as
   `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

✅ **You should now have:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
and a saved `google_client.json` you'll use locally.

**Common failures**

- *"This app isn't verified"* during OAuth — that's fine, click
  **Advanced → Go to brainbot (unsafe)**. You created it, it's safe.
- *"App is blocked"* — you forgot to add the account as a test user.

---

## Step 5 — Register a Microsoft Azure app (school Outlook) (~15 min)

1. Open <https://entra.microsoft.com/> (sign in with your **school**
   Microsoft account).
2. Left menu → **Applications** → **App registrations** → **New registration**.
3. Name: `brainbot`. Supported account types:
   **Accounts in any organizational directory and personal Microsoft
   accounts**. Redirect URI: leave blank for now. Register.
4. On the app's page, copy **Application (client) ID** → this is `MS_CLIENT_ID`.
5. Left menu of the app → **Authentication** → **Allow public client
   flows** → set to **Yes**. Save.
6. Left menu of the app → **API permissions** → **Add a permission** →
   **Microsoft Graph** → **Delegated permissions** → add all of:
   - `Mail.ReadWrite`
   - `Mail.Send`
   - `Calendars.ReadWrite`
   - `User.Read`
   - `offline_access`
7. Click **Grant admin consent** if available (school admin may need to;
   if you can't, the device-code flow will still work but you'll see a
   consent prompt for each scope on first auth).

> If `MS_TENANT_ID` matters for your school: copy "Directory (tenant)
> ID" from the app overview. Use `common` if you want to keep things
> generic. School deployments often restrict to a specific tenant.

✅ **You should now have:** `MS_CLIENT_ID` (and optionally `MS_TENANT_ID`).

---

## Step 6 — Generate FERNET_KEY and TELEGRAM_WEBHOOK_SECRET (~2 min)

On your laptop, in a terminal:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# -> e.g. 8k5J9d... <- this is your FERNET_KEY

python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# -> e.g. Lk_3J... <- this is your TELEGRAM_WEBHOOK_SECRET
```

If you don't have `cryptography` installed locally, you can also do this
later inside the Docker container. Just keep both values safe.

> **Critical**: never rotate `FERNET_KEY` once tokens are saved — old
> tokens will become unreadable and you'll have to re-authorise everything.

✅ **You should now have:** `FERNET_KEY` and `TELEGRAM_WEBHOOK_SECRET`.

---

## Step 7 — Create the Oracle Cloud VM (~30 min)

Oracle's Always Free tier includes 4 ARM cores + 24 GB RAM. That's
massive overkill for brainbot — we'll use a small slice.

1. Sign up at <https://signup.oracle.com/>. **Important:** during
   sign-up, **double-check your home region** — you can only create
   resources in your selected home region, and it cannot be changed.
   Pick something close to Singapore (Tokyo, Singapore, Mumbai).
2. After sign-up, in the OCI console → **Compute** → **Instances** →
   **Create Instance**.
3. Name: `brainbot`.
4. Image: click **Edit** → **Change image** → Canonical Ubuntu →
   **Ubuntu 22.04**.
5. Shape: **Edit** → **Change shape** → **Ambassador** → select
   **VM.Standard.A1.Flex** → set 2 OCPUs and 6 GB memory (you can use
   more if Oracle has capacity).
6. **Networking** — leave defaults; a public IPv4 will be assigned.
7. **Add SSH keys** — if you've never made one:
   - On your laptop: `ssh-keygen -t ed25519` (press enter at every prompt).
   - This creates `~/.ssh/id_ed25519` (private) and `~/.ssh/id_ed25519.pub` (public).
   - In OCI, choose **Paste public keys** and paste the contents of `~/.ssh/id_ed25519.pub`.
8. **Boot volume** — leave 50GB default. Free tier covers it.
9. Click **Create**.

After ~2 minutes the instance will show as **Running** with a **Public
IPv4 address** — copy it.

### 7a. Open ports 80 + 443 in the cloud firewall

OCI VCNs deny inbound traffic by default.

1. In the instance page, click the **Subnet** link under "Primary VNIC".
2. **Security Lists** → click the default one.
3. **Add Ingress Rule**:
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: TCP
   - Destination Port Range: `80,443`
   - Click Add.

✅ **You should now have:** an Ubuntu VM, its public IP, and ports 80/443
allowed in the VCN.

**Common failures**

- *"Out of capacity"* on A1.Flex — ARM Always Free is popular. Retry every
  few hours, or try a different home region (you have to sign up again).
- *"I lost my SSH key"* — you can't recover it. Terminate the instance
  and recreate it with a fresh key.

---

## Step 8 — SSH in and bootstrap the server (~15 min)

On your laptop:

```bash
ssh ubuntu@<your-vm-ip>
# Type 'yes' the first time to accept the host key.
```

You should see the Ubuntu welcome banner. Now run:

```bash
curl -fsSL https://raw.githubusercontent.com/<your-github-username>/braingit/main/infra/oracle_setup.sh | bash
```

(Or `scp infra/oracle_setup.sh ubuntu@<ip>:` and run it directly — fine
if your repo is private.)

The script:
- Installs Docker + Compose plugin.
- Configures UFW + the local iptables (Oracle's default rules block
  80/443 *inside* the VM — the script fixes this).
- Enables fail2ban.
- Ensures a 2GB swapfile exists.
- Creates `~/brainbot/`.

When it finishes, **log out and SSH back in** so your shell picks up
docker group membership.

```bash
exit
ssh ubuntu@<your-vm-ip>
docker run --rm hello-world  # smoke test; should pull and print "Hello from Docker"
```

✅ **You should now have:** a working Docker daemon you can run without `sudo`.

---

## Step 9 — Point the domain at the VM (~5 min + DNS wait)

In your domain registrar's DNS panel:

1. Add an **A record**:
   - Name: `bot` (or `@` if you want the apex)
   - Value: your VM's public IPv4
   - TTL: 300

2. Wait 1–10 minutes. Verify from your laptop:
   ```bash
   dig +short bot.example.com
   # Should print your VM's IP. If empty, wait longer.
   ```

✅ **You should now have:** `bot.example.com` (or whatever) resolving to your VM.

---

## Step 10 — Bring the stack up (~10 min)

### 10a. Clone the repo onto the VM

```bash
ssh ubuntu@<your-vm-ip>
git clone https://github.com/<you>/braingit.git ~/brainbot
cd ~/brainbot
```

### 10b. Make your .env

On your laptop (so you can paste secrets without leaking them to logs):

```bash
cp .env.example .env
# Open .env in your editor and fill in EVERY value collected above.
# Leave the topic IDs at their defaults for now — we'll fix them in Step 11.
# PUBLIC_BASE_URL must be your https://bot.example.com.
```

Copy `.env` and your `google_client.json` to the VM:

```bash
scp .env ubuntu@<your-vm-ip>:~/brainbot/.env
scp secrets/google_client.json ubuntu@<your-vm-ip>:~/brainbot/secrets/
```

> Permissions: `chmod 600 ~/brainbot/.env` on the VM to keep it private.

### 10c. First start

On the VM:

```bash
cd ~/brainbot
docker compose up -d
docker compose ps   # all 3 services should be 'running'
docker compose logs -f bot
```

You should see startup logs ending in `Uvicorn running on 0.0.0.0:8000`.

Run migrations:

```bash
docker compose exec bot alembic upgrade head
```

Check the public endpoint:

```bash
curl -i https://bot.example.com/healthz
# HTTP/2 200 with body {"status":"ok"}
```

Caddy might take 30–60 seconds the first time to provision the cert.
If you see `HTTP/1.1 302` or a self-signed cert, give it another minute.

✅ **You should now have:** a publicly reachable, HTTPS-protected `/healthz`.

**Common failures**

- *Caddy log: "no such host"* — DNS hasn't propagated yet. Wait.
- *Caddy log: "challenge failed"* — port 80/443 not open. Re-check Step 7a and
  that UFW allows them: `sudo ufw status`.
- *Bot in restart loop* — `docker compose logs bot` will explain. Almost
  always a missing or malformed `.env` value.

---

## Step 11 — Discover the topic IDs (~5 min)

You need to find each topic's `message_thread_id`. The included script
does this via `getUpdates`, which only works **before** you set the
webhook.

On your **laptop** (not the VM, since you have python locally):

```bash
# In the repo root
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Make sure TELEGRAM_BOT_TOKEN is set in your local .env
python scripts/seed_topics.py
```

You'll see something like:

```
Found topics. Paste these into your .env:
  thread_id=2     topic=Daily Routine
  thread_id=3     topic=Evening Recap
  ...
```

Edit your `.env` (locally) and fill in `TOPIC_*` values accordingly. Then
**copy the updated .env to the VM again** and restart the bot:

```bash
scp .env ubuntu@<your-vm-ip>:~/brainbot/.env
ssh ubuntu@<your-vm-ip>
cd ~/brainbot && docker compose restart bot
```

✅ **You should now have:** all 8 `TOPIC_*` env vars filled in.

---

## Step 12 — Run the OAuth scripts locally (~15 min)

Authorising is easier on your laptop because OAuth opens a browser.

> The OAuth scripts write encrypted tokens directly to your Postgres
> on the VM. The easiest way is to forward the DB port over SSH:

```bash
ssh -L 5433:localhost:5432 ubuntu@<your-vm-ip>
# Leave that SSH session open.
```

In a *second* local terminal:

```bash
source .venv/bin/activate
export DATABASE_URL="postgresql+asyncpg://brainbot:<password>@localhost:5433/brainbot"

# Google: do all three accounts
python scripts/auth_google.py --label main --credentials secrets/google_client.json
python scripts/auth_google.py --label spam1 --credentials secrets/google_client.json
python scripts/auth_google.py --label spam2 --credentials secrets/google_client.json

# Microsoft (device-code flow)
python scripts/auth_microsoft.py
```

For each Google run: a browser tab opens. Sign in with the relevant
Google account. You'll see "This app isn't verified" — click
**Advanced → Go to brainbot (unsafe)** (it's your own app). Approve.

For Microsoft: you'll see something like

```
To sign in, use a web browser to open https://microsoft.com/devicelogin
and enter the code ABCD-1234 to authenticate.
```

Open that URL in any browser, paste the code, sign in with your **school**
account. Approve.

Each script ends with `Saved.` if it worked. After all four are done,
restart the bot:

```bash
ssh ubuntu@<your-vm-ip>
cd ~/brainbot && docker compose restart bot
```

✅ **You should now have:** 4 rows in `account_tokens` (3 Google + 1 Microsoft).
Verify with:

```bash
docker compose exec postgres psql -U brainbot -d brainbot -c "select account_label, provider from account_tokens;"
```

---

## Step 13 — Register the Telegram webhook (~2 min)

Tell Telegram to push updates to your bot:

```bash
TOKEN="<your bot token>"
SECRET="<your TELEGRAM_WEBHOOK_SECRET>"
URL="https://bot.example.com/telegram/webhook"

curl -sS "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -d "url=${URL}" \
  -d "secret_token=${SECRET}"
# {"ok":true,"result":true,"description":"Webhook was set"}
```

Confirm:

```bash
curl -sS "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"
```

The response should show your URL and `pending_update_count: 0`.

✅ **You should now have:** Telegram sending updates to your VM.

---

## Step 14 — Test in each topic (~5 min)

In your Telegram group:

| Topic         | Send                              | Expected bot reply                    |
|---------------|-----------------------------------|----------------------------------------|
| General       | `hello`                           | Friendly reply                         |
| Todos         | `add: buy milk tomorrow 5pm`      | Confirms todo added, returns id        |
| Todos         | `list open todos`                 | Bullet list                            |
| Quick Notes   | `idea: try parallel reductions`   | "Saved as note #1."                    |
| Second Brain  | `what notes do I have?`           | Lists notes / says none yet            |
| Emails        | `unread in main`                  | Lists unread Gmails in main account    |
| Calendar      | `what's on today across both?`    | Merged events from main + school       |

If any of these don't work:

```bash
docker compose logs --tail 200 bot
```

The structured JSON logs make the failure obvious.

---

## Day-to-day operations

### Logs
```bash
docker compose logs -f bot
docker compose logs --since 1h bot
```

### Update the code
```bash
cd ~/brainbot
git pull
docker compose build bot
docker compose up -d
docker compose exec bot alembic upgrade head
```

### Database access
```bash
docker compose exec postgres psql -U brainbot -d brainbot
```

### Backup
The whole state lives in `~/brainbot/postgres_data/`. Either snapshot
the directory with `tar` or `pg_dump`:

```bash
docker compose exec postgres pg_dump -U brainbot brainbot > backup-$(date +%F).sql
```

### Restart everything
```bash
docker compose restart
```

### If you ever rotate FERNET_KEY
You can't, without re-authorising every account. Don't.

---

## Architecture

```
            ┌──────────────────┐
            │  Telegram (you)  │
            └────────┬─────────┘
                     │ HTTPS webhook
            ┌────────▼─────────┐
            │   Caddy (TLS)    │  Let's Encrypt cert, auto-renew
            └────────┬─────────┘
                     │ HTTP (Docker network)
            ┌────────▼─────────┐
            │   bot (FastAPI)  │  agent router + Gemini function calling
            │  + APScheduler   │  morning 7am / evening 10pm SGT
            └────┬────────┬────┘
        Gemini   │        │   Gmail / Calendar / Graph
                 │        ▼
                 │  ┌──────────────┐
                 │  │  Postgres 16 │  todos, notes (pgvector),
                 │  │  + pgvector  │  encrypted account_tokens
                 └──┴──────────────┘
```

Each agent is a `BaseAgent` subclass with a `ToolRegistry`. The LLM
client drives a function-calling loop (≤8 turns): model asks for tool,
handler runs, result feeds back, repeat until the model returns text.

---

## Things you still need to provide / decide

The code intentionally stubs a few things you'll want to tweak later:

1. **"Urgent" mail filter.** Right now the morning brief surfaces all
   unread mail and lets Gemini decide what's urgent. If you want
   sender-based prioritisation, add a `URGENT_SENDERS` env var and filter
   in `routine_agent._gather_morning`.

2. **RRULE support for recurring todos.** Only `FREQ=DAILY` and
   `FREQ=WEEKLY` are handled. Add proper RRULE expansion via the `dateutil.rrule`
   module in `todo_agent._next_recurrence` if you start using complex recurrences.

3. **Multi-line topic system prompts.** Each agent's system prompt is
   inline in its file. If you find yourself editing them often, move
   them to `prompts/*.md` and load on import.

4. **Forward-to-Telegram for emails.** The Email agent has tools for
   read/send/delete/label but no "send gist of this email to the Emails
   topic" tool yet. Add a one-line tool that summarises with Gemini and
   `send_text(...)`s the result.

5. **Backups.** The compose file doesn't schedule pg_dump. Add a daily
   cron on the VM or a small `apscheduler` job if losing notes scares you.

6. **Token rotation.** Microsoft refresh tokens age out after ~90 days
   of inactivity. If your school IT enforces shorter, just re-run
   `auth_microsoft.py` when refresh starts failing.
