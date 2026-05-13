#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/local-doc-classifier}"
TOKEN="$(grep '^CLASSIFIER_API_TOKEN=' "${APP_DIR}/.env" | cut -d= -f2-)"

echo "[INFO] Docker compose status"
cd "${APP_DIR}"
docker compose ps

echo
echo "[INFO] API health"
curl -sS -H "X-API-Key: ${TOKEN}" http://127.0.0.1:4319/health | jq

echo
echo "[INFO] Recent records"
curl -sS -H "X-API-Key: ${TOKEN}" http://127.0.0.1:4319/recent?limit=5 | jq

echo
echo "[INFO] Category counts"
wc -l "${APP_DIR}/config/categories.txt" "${APP_DIR}/config/categories.full.txt" 2>/dev/null || true
