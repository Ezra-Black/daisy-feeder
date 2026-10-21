#!/usr/bin/env bash
# Daisy Feeder installer for Raspberry Pi OS (Bookworm or newer).
# Usage (on the Pi, from this folder):   sudo bash install.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo:  sudo bash install.sh"; exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR=/opt/duckfeeder
ENV_FILE=/etc/duckfeeder.env
RUN_USER="${SUDO_USER:-pi}"

echo "==> Installing packages"
apt-get update -qq
apt-get install -y -qq python3-flask python3-gpiozero python3-lgpio >/dev/null

echo "==> Copying program to $APP_DIR"
install -d "$APP_DIR"
install -m 755 "$SRC_DIR/feeder.py" "$APP_DIR/feeder.py"
install -m 755 "$SRC_DIR/calibrate.py" "$APP_DIR/calibrate.py"
install -m 755 "$SRC_DIR/duckfeeder-info" /usr/local/bin/duckfeeder-info
install -m 755 "$SRC_DIR/duckfeeder-calibrate" /usr/local/bin/duckfeeder-calibrate

usermod -aG gpio "$RUN_USER" 2>/dev/null || true

if [[ -f "$ENV_FILE" ]]; then
  echo "==> Keeping existing settings in $ENV_FILE"
else
  echo "==> Creating settings file $ENV_FILE with a new random key"
  KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(12))')"
  sed "s|^FEEDER_KEY=.*|FEEDER_KEY=$KEY|" "$SRC_DIR/duckfeeder.env.example" > "$ENV_FILE"
  chmod 640 "$ENV_FILE"
  chown root:"$RUN_USER" "$ENV_FILE"
fi

echo "==> Installing system service (runs as $RUN_USER)"
sed "s|^User=.*|User=$RUN_USER|" "$SRC_DIR/duckfeeder.service" > /etc/systemd/system/duckfeeder.service
systemctl daemon-reload
systemctl enable --now duckfeeder
systemctl restart duckfeeder
sleep 2

duckfeeder-info
