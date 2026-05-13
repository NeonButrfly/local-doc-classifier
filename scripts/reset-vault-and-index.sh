#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/local-doc-classifier}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/local-doc-classifier-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/reset-${STAMP}"

echo "[INFO] This will reset generated classifier index/vault outputs."
echo "[INFO] App dir: ${APP_DIR}"
echo "[INFO] Backup dir: ${BACKUP_DIR}"

mkdir -p "${BACKUP_DIR}"

echo "[INFO] Backing up vault, output, and input..."
tar -czf "${BACKUP_DIR}/vault-output-input-${STAMP}.tar.gz" \
  -C "${APP_DIR}" \
  vault \
  output \
  input \
  2>/dev/null || true

echo "[INFO] Stopping API to avoid writes during reset..."
cd "${APP_DIR}"
docker compose stop api >/dev/null 2>&1 || true

echo "[INFO] Clearing generated Obsidian vault content..."
rm -rf "${APP_DIR}/vault/01 Classified"
rm -rf "${APP_DIR}/vault/02 Needs Review"
rm -rf "${APP_DIR}/vault/90 Attachments"
rm -rf "${APP_DIR}/vault/_system/classifications"
rm -rf "${APP_DIR}/vault/_system/extracted-markdown"
rm -f  "${APP_DIR}/vault/Classification Index.md"

mkdir -p "${APP_DIR}/vault/01 Classified"
mkdir -p "${APP_DIR}/vault/02 Needs Review"
mkdir -p "${APP_DIR}/vault/90 Attachments"
mkdir -p "${APP_DIR}/vault/_system/classifications"
mkdir -p "${APP_DIR}/vault/_system/extracted-markdown"
mkdir -p "${APP_DIR}/vault/_system/templates"

cat > "${APP_DIR}/vault/Classification Index.md" <<'MD'
---
type: classification-index
system: local-document-classifier
---

# Classification Index

Last reset: RESET_TIMESTAMP

## Recent notes

MD

python3 - <<PY
from pathlib import Path
from datetime import datetime
p = Path("${APP_DIR}/vault/Classification Index.md")
s = p.read_text()
s = s.replace("RESET_TIMESTAMP", datetime.now().astimezone().isoformat(timespec="seconds"))
p.write_text(s)
PY

echo "[INFO] Clearing output manifest and API staging input..."
rm -f "${APP_DIR}/output/manifest.jsonl"
rm -rf "${APP_DIR}/input/api"
mkdir -p "${APP_DIR}/input/api"
touch "${APP_DIR}/output/manifest.jsonl"

echo "[INFO] Preserving config/corrections/categories/models."
echo "[INFO] Restarting API..."
docker compose up -d api

echo "[DONE] Reset complete."
echo "[DONE] Backup saved at: ${BACKUP_DIR}"
