#!/usr/bin/env bash
# Hermes Oracle — one-shot installer for a fresh Hetzner Ubuntu 24.04 VPS.
#
# Run as root via the Hetzner Cloud Console:
#   curl -fsSL https://raw.githubusercontent.com/dream0x/Hermes-Tarot/main/scripts/install_hetzner.sh -o /tmp/install.sh && bash /tmp/install.sh
#
# After this script finishes, you must:
#   1. Edit /opt/hermes-tarot/.env  (paste secrets)   ->  nano /opt/hermes-tarot/.env
#   2. Start the bot:   systemctl start hermes-tarot
#   3. Watch logs:      journalctl -u hermes-tarot -f
set -euo pipefail

REPO_URL="https://github.com/dream0x/Hermes-Tarot.git"
INSTALL_DIR="/opt/hermes-tarot"
SERVICE_USER="hermes"
PYTHON_BIN="python3.12"   # Ubuntu 24.04 default

say() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
warn() { printf "\n\033[1;33m!! %s\033[0m\n" "$*"; }
die() { printf "\n\033[1;31mxx %s\033[0m\n" "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run as root (you are $(whoami))"

# ----------- 1. System packages -----------
say "1/6  apt update + install basics"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl git \
  python3 python3-venv python3-pip python3-dev \
  build-essential ufw \
  fonts-dejavu-core
# (We don't need solc system-wide; py-solc-x downloads it inside the venv.)

# ----------- 2. Firewall — SSH only -----------
say "2/6  ufw firewall (SSH only)"
ufw allow OpenSSH > /dev/null
ufw --force enable > /dev/null

# ----------- 3. Service user -----------
say "3/6  service user '$SERVICE_USER'"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$SERVICE_USER"
fi

# ----------- 4. Clone + venv -----------
say "4/6  clone repo + create venv"
if [ -d "$INSTALL_DIR/.git" ]; then
  warn "$INSTALL_DIR exists — pulling latest"
  sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" pull --ff-only
else
  rm -rf "$INSTALL_DIR"
  sudo -u "$SERVICE_USER" git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

sudo -u "$SERVICE_USER" bash -lc "
  cd '$INSTALL_DIR' && \
  $PYTHON_BIN -m venv .venv && \
  source .venv/bin/activate && \
  pip install --quiet --upgrade pip && \
  pip install --quiet -r requirements.txt
"

# ----------- 5. .env stub -----------
say "5/6  .env stub (you must edit this with real secrets)"
if [ ! -f "$INSTALL_DIR/.env" ]; then
  sudo -u "$SERVICE_USER" cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
fi

# ----------- 6. systemd unit -----------
say "6/6  systemd unit"
cat > /etc/systemd/system/hermes-tarot.service <<EOF
[Unit]
Description=Hermes Oracle — Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/.venv/bin/python -u bot.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$INSTALL_DIR/data $INSTALL_DIR/logs $INSTALL_DIR/tarot/cache $INSTALL_DIR/nft/build
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable hermes-tarot.service > /dev/null

# Pre-create runtime dirs as service user
sudo -u "$SERVICE_USER" mkdir -p \
  "$INSTALL_DIR/data" \
  "$INSTALL_DIR/logs" \
  "$INSTALL_DIR/tarot/cache" \
  "$INSTALL_DIR/nft/build"

cat <<EOF


============================================================
  Hermes Oracle install complete.
============================================================

NEXT STEPS (do them now):

  1. Paste real secrets into the .env:
       nano $INSTALL_DIR/.env

  2. Start the bot:
       systemctl start hermes-tarot

  3. Watch the logs (Ctrl+C to detach, the bot keeps running):
       journalctl -u hermes-tarot -f

  4. Pre-render the 22 Major Arcana into the cache (one-time, ~\$1):
       sudo -u $SERVICE_USER bash -lc 'cd $INSTALL_DIR && source .venv/bin/activate && python -m tarot.render --prewarm-major'

  5. (Optional) Verify status:
       systemctl status hermes-tarot

To stop:    systemctl stop hermes-tarot
To update:  cd $INSTALL_DIR && sudo -u $SERVICE_USER git pull && systemctl restart hermes-tarot

EOF
