#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERROR] Run as root."
  exit 1
fi

cat > /etc/systemd/system/local-doc-classifier-taxonomy-sync.service <<'UNIT'
[Unit]
Description=Sync public classification taxonomies and retrain taxonomy router
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/local-doc-classifier
ExecStart=/usr/bin/python3 /opt/local-doc-classifier/sync-public-categories.py
ExecStartPost=/bin/sh -lc 'cd /opt/local-doc-classifier && docker compose --profile tools run --rm --entrypoint python taxonomy-router /router/train_taxonomy_router.py >/opt/local-doc-classifier/logs/taxonomy-router-train.log 2>&1 || true'
ExecStartPost=/bin/sh -lc 'cd /opt/local-doc-classifier && docker compose rm -sf api >/dev/null 2>&1 || true; docker ps -aq --filter name=local-doc-classifier-api | xargs -r docker rm -f >/dev/null 2>&1 || true; docker compose up -d --build api >/opt/local-doc-classifier/logs/restart-api-after-taxonomy-sync.log 2>&1 || true'
UNIT

cat > /etc/systemd/system/local-doc-classifier-taxonomy-sync.timer <<'UNIT'
[Unit]
Description=Occasionally refresh classifier public taxonomies

[Timer]
OnBootSec=15min
OnCalendar=Sun *-*-* 03:23:00
RandomizedDelaySec=45min
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now local-doc-classifier-taxonomy-sync.timer
systemctl list-timers | grep local-doc-classifier || true
