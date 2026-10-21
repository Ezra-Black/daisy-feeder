#!/usr/bin/env bash
# Removes the Daisy Feeder service and program. Keeps /etc/duckfeeder.env unless --purge.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }
systemctl disable --now duckfeeder 2>/dev/null || true
rm -f /etc/systemd/system/duckfeeder.service
systemctl daemon-reload
rm -rf /opt/duckfeeder
rm -f /usr/local/bin/duckfeeder-info /usr/local/bin/duckfeeder-calibrate
if [[ "${1:-}" == "--purge" ]]; then rm -f /etc/duckfeeder.env; rm -rf /var/lib/duckfeeder; fi
echo "Daisy Feeder removed."
