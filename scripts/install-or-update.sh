#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/local-doc-classifier}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERROR] Run with sudo/root."
  exit 1
fi

apt-get update

packages=(docker.io curl jq git openssl)

# Ubuntu package names for Docker Compose vary by release, and some hosts
# already have a working `docker compose` command.
if ! docker compose version >/dev/null 2>&1; then
  if apt-cache show docker-compose-plugin >/dev/null 2>&1; then
    packages+=(docker-compose-plugin)
  elif apt-cache show docker-compose-v2 >/dev/null 2>&1; then
    packages+=(docker-compose-v2)
  fi
fi

apt-get install -y "${packages[@]}"

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] Docker Compose v2 is required, but no working 'docker compose' command is available after package installation."
  exit 1
fi

mkdir -p "${APP_DIR}"
mkdir -p "${APP_DIR}/input" "${APP_DIR}/output" "${APP_DIR}/vault" "${APP_DIR}/ollama" "${APP_DIR}/cache" "${APP_DIR}/logs" "${APP_DIR}/tmp" "${APP_DIR}/config"

cp -a "${SRC_DIR}/docker-compose.yml" "${APP_DIR}/docker-compose.yml"
rm -rf "${APP_DIR}/classifier" "${APP_DIR}/taxonomy-router"
mkdir -p "${APP_DIR}/classifier" "${APP_DIR}/taxonomy-router"
cp -a "${SRC_DIR}/classifier/." "${APP_DIR}/classifier/"
cp -a "${SRC_DIR}/taxonomy-router/." "${APP_DIR}/taxonomy-router/" 2>/dev/null || true
cp -a "${SRC_DIR}/scripts/docclass" "${APP_DIR}/docclass" 2>/dev/null || true
cp -a "${SRC_DIR}/scripts/taxcat" "${APP_DIR}/taxcat" 2>/dev/null || true
cp -a "${SRC_DIR}/scripts/sync-public-categories.py" "${APP_DIR}/sync-public-categories.py" 2>/dev/null || true

cp -n "${SRC_DIR}/config/categories.local.txt" "${APP_DIR}/config/categories.local.txt" 2>/dev/null || true
cp -n "${SRC_DIR}/config/category-groups.json" "${APP_DIR}/config/category-groups.json" 2>/dev/null || true
cp -n "${SRC_DIR}/config/taxonomy-sources.json" "${APP_DIR}/config/taxonomy-sources.json" 2>/dev/null || true

if [[ ! -f "${APP_DIR}/.env" ]]; then
  TOKEN="$(openssl rand -hex 32)"
  cat > "${APP_DIR}/.env" <<ENV
APP_DIR=${APP_DIR}
CLASSIFY_MODEL=qwen2.5:3b
VISION_MODEL=qwen2.5vl:3b
PULL_VISION_MODEL=1
TZ=America/Anchorage
OLLAMA_PORT=11434
CLASSIFIER_API_PORT=4319
CLASSIFIER_API_BIND=0.0.0.0
CLASSIFIER_API_TOKEN=${TOKEN}
ENV
fi

chmod +x "${APP_DIR}/docclass" 2>/dev/null || true
chmod +x "${APP_DIR}/taxcat" 2>/dev/null || true
chmod +x "${APP_DIR}/sync-public-categories.py" 2>/dev/null || true

mkdir -p "${APP_DIR}/vault/.obsidian"
mkdir -p "${APP_DIR}/vault/00 Inbox" "${APP_DIR}/vault/01 Classified" "${APP_DIR}/vault/02 Needs Review" "${APP_DIR}/vault/90 Attachments" "${APP_DIR}/vault/_system/templates" "${APP_DIR}/vault/_system/extracted-markdown" "${APP_DIR}/vault/_system/classifications"

if [[ ! -f "${APP_DIR}/vault/Home.md" ]]; then
  cat > "${APP_DIR}/vault/Home.md" <<'MD'
---
type: vault-home
system: local-document-classifier
---

# Local Document Classifier

Generated Obsidian vault.
MD
fi

if [[ ! -f "${APP_DIR}/vault/Classification Index.md" ]]; then
  cat > "${APP_DIR}/vault/Classification Index.md" <<'MD'
---
type: classification-index
system: local-document-classifier
---

# Classification Index

## Recent notes

MD
fi

cd "${APP_DIR}"
docker compose build classifier
docker compose build taxonomy-router || true
docker compose up -d ollama api
docker compose --profile init run --rm model-init || true

echo "[DONE] Installed/updated ${APP_DIR}"
echo "[INFO] API token:"
grep '^CLASSIFIER_API_TOKEN=' "${APP_DIR}/.env" || true
