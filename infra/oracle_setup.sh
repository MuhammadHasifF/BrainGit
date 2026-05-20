#!/usr/bin/env bash
# Oracle Cloud Always Free — Ubuntu 22.04 (ARM) bootstrap for brainbot.
#
# Run this ONCE on a fresh VM as the default `ubuntu` user.
# It installs Docker + Compose, opens the right firewall ports, and
# prepares the directory layout. After it finishes, you clone the repo,
# copy your .env in, and run `docker compose up -d`.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<you>/braingit/main/infra/oracle_setup.sh | bash
#   # or, from a checkout:
#   bash infra/oracle_setup.sh
#
# Idempotent: re-running is safe.

set -euo pipefail

log() { printf "\033[1;34m[setup]\033[0m %s\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1"; exit 1; }; }

if [ "$EUID" -eq 0 ]; then
  echo "Run as the 'ubuntu' user, not root."
  exit 1
fi

# ── 1. System packages ───────────────────────────────────────────────────
log "Updating apt and installing base packages..."
sudo apt-get update -y
sudo apt-get install -y \
    ca-certificates curl gnupg lsb-release \
    git ufw fail2ban tmux htop unzip

# ── 2. Docker + Compose plugin ───────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker..."
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                          docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  log "Docker installed. You may need to log out + back in for group membership."
fi

# ── 3. Firewall ──────────────────────────────────────────────────────────
log "Configuring UFW (22, 80, 443)..."
sudo ufw allow OpenSSH || true
sudo ufw allow 80/tcp || true
sudo ufw allow 443/tcp || true
sudo ufw --force enable

# Oracle's iptables also blocks 80/443 by default — fix it.
log "Adding iptables rules for 80/443 (Oracle defaults block these)..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save || sudo apt-get install -y iptables-persistent

# ── 4. fail2ban (light SSH hardening) ────────────────────────────────────
log "Enabling fail2ban..."
sudo systemctl enable --now fail2ban

# ── 5. Swap (Oracle ARM micro instance ships with 1GB swap by default;
#         we just check and warn) ────────────────────────────────────────
if [ "$(awk '/SwapTotal/ {print $2}' /proc/meminfo)" -lt 100000 ]; then
  log "No swap detected. Creating a 2GB swapfile..."
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo "/swapfile swap swap defaults 0 0" | sudo tee -a /etc/fstab
fi

# ── 6. App dir ───────────────────────────────────────────────────────────
APP_DIR="$HOME/brainbot"
if [ ! -d "$APP_DIR" ]; then
  log "Creating $APP_DIR (clone the repo into it next)."
  mkdir -p "$APP_DIR"
fi

cat <<EOF

[setup] All done.

Next steps:
  1) Log out and back in (so docker group takes effect):
       exit
       ssh ubuntu@<your-ip>

  2) Clone the repo into $APP_DIR (replace with your fork):
       git clone https://github.com/<you>/braingit.git "$APP_DIR"
       cd "$APP_DIR"

  3) Copy your .env in (from your laptop):
       scp .env ubuntu@<your-ip>:$APP_DIR/.env

  4) Bring everything up:
       docker compose up -d
       docker compose exec bot alembic upgrade head

  5) Tail logs to confirm:
       docker compose logs -f bot

EOF
