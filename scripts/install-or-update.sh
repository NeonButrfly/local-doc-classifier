#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR_OVERRIDE="${APP_DIR:-}"
VAULT_DIR_OVERRIDE="${VAULT_DIR:-}"
VAULT_NFS_REMOTE_OVERRIDE="${VAULT_NFS_REMOTE:-}"
VAULT_NFS_MOUNT_DIR_OVERRIDE="${VAULT_NFS_MOUNT_DIR:-}"
VAULT_NFS_OPTIONS_OVERRIDE="${VAULT_NFS_OPTIONS:-}"
APP_DIR="${APP_DIR_OVERRIDE:-/opt/local-doc-classifier}"

if [[ -f "${APP_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${APP_DIR}/.env"
  set +a
fi

APP_DIR="${APP_DIR_OVERRIDE:-${APP_DIR:-/opt/local-doc-classifier}}"
VAULT_NFS_REMOTE="${VAULT_NFS_REMOTE_OVERRIDE:-${VAULT_NFS_REMOTE:-}}"
VAULT_NFS_MOUNT_DIR="${VAULT_NFS_MOUNT_DIR_OVERRIDE:-${VAULT_NFS_MOUNT_DIR:-/mnt/cloud-vault}}"
VAULT_NFS_OPTIONS="${VAULT_NFS_OPTIONS_OVERRIDE:-${VAULT_NFS_OPTIONS:-defaults,_netdev,nofail,x-systemd.automount,x-systemd.idle-timeout=600,x-systemd.device-timeout=30,timeo=14,retrans=3}}"

if [[ -n "${VAULT_NFS_REMOTE}" ]]; then
  VAULT_DIR="${VAULT_DIR_OVERRIDE:-${VAULT_DIR:-${VAULT_NFS_MOUNT_DIR}/local-doc-classifier-vault}}"
else
  VAULT_DIR="${VAULT_DIR_OVERRIDE:-${VAULT_DIR:-${APP_DIR}/vault}}"
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERROR] Run with sudo/root."
  exit 1
fi

apt-get update

packages=(docker.io curl jq git openssl)
if [[ -n "${VAULT_NFS_REMOTE}" ]]; then
  packages+=(nfs-common)
fi

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

upsert_env_var() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  local tmp_file
  tmp_file="$(mktemp)"

  awk -F= -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    $1 == key {
      print key "=" value
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) {
        print key "=" value
      }
    }
  ' "${env_file}" > "${tmp_file}"

  mv "${tmp_file}" "${env_file}"
}

upsert_fstab_nfs_mount() {
  local remote_path="$1"
  local mount_dir="$2"
  local mount_options="$3"
  local tmp_file
  tmp_file="$(mktemp)"

  awk -v remote_path="$remote_path" -v mount_dir="$mount_dir" -v mount_options="$mount_options" '
    BEGIN { updated = 0 }
    $2 == mount_dir && $3 == "nfs" {
      print remote_path, mount_dir, "nfs", mount_options, 0, 0
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) {
        print remote_path, mount_dir, "nfs", mount_options, 0, 0
      }
    }
  ' /etc/fstab > "${tmp_file}"

  mv "${tmp_file}" /etc/fstab
}

ensure_nfs_vault_mount() {
  local remote_path="$1"
  local mount_dir="$2"
  local mount_options="$3"
  local legacy_vault_dir="${APP_DIR}/vault"

  mkdir -p "${mount_dir}"
  upsert_fstab_nfs_mount "${remote_path}" "${mount_dir}" "${mount_options}"

  if ! mountpoint -q "${mount_dir}"; then
    mount "${mount_dir}"
  fi

  mkdir -p "${VAULT_DIR}"
  if [[ "${VAULT_DIR}" != "${legacy_vault_dir}" && -d "${legacy_vault_dir}" ]]; then
    if [[ -z "$(find "${VAULT_DIR}" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
      cp -a "${legacy_vault_dir}/." "${VAULT_DIR}/" 2>/dev/null || true
    fi
  fi
}

mkdir -p "${APP_DIR}"
mkdir -p "${APP_DIR}/input" "${APP_DIR}/output" "${APP_DIR}/ollama" "${APP_DIR}/cache" "${APP_DIR}/logs" "${APP_DIR}/tmp" "${APP_DIR}/config"

if [[ -n "${VAULT_NFS_REMOTE}" ]]; then
  ensure_nfs_vault_mount "${VAULT_NFS_REMOTE}" "${VAULT_NFS_MOUNT_DIR}" "${VAULT_NFS_OPTIONS}"
fi

mkdir -p "${VAULT_DIR}"

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
VAULT_DIR=${VAULT_DIR}
VAULT_NFS_REMOTE=${VAULT_NFS_REMOTE}
VAULT_NFS_MOUNT_DIR=${VAULT_NFS_MOUNT_DIR}
VAULT_NFS_OPTIONS=${VAULT_NFS_OPTIONS}
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

upsert_env_var "${APP_DIR}/.env" "APP_DIR" "${APP_DIR}"
upsert_env_var "${APP_DIR}/.env" "VAULT_DIR" "${VAULT_DIR}"
upsert_env_var "${APP_DIR}/.env" "VAULT_NFS_REMOTE" "${VAULT_NFS_REMOTE}"
upsert_env_var "${APP_DIR}/.env" "VAULT_NFS_MOUNT_DIR" "${VAULT_NFS_MOUNT_DIR}"
upsert_env_var "${APP_DIR}/.env" "VAULT_NFS_OPTIONS" "${VAULT_NFS_OPTIONS}"

chmod +x "${APP_DIR}/docclass" 2>/dev/null || true
chmod +x "${APP_DIR}/taxcat" 2>/dev/null || true
chmod +x "${APP_DIR}/sync-public-categories.py" 2>/dev/null || true

mkdir -p "${VAULT_DIR}/.obsidian"
mkdir -p "${VAULT_DIR}/00 Inbox" "${VAULT_DIR}/01 Classified" "${VAULT_DIR}/02 Needs Review" "${VAULT_DIR}/90 Attachments" "${VAULT_DIR}/_system/templates" "${VAULT_DIR}/_system/extracted-markdown" "${VAULT_DIR}/_system/classifications"

if [[ ! -f "${VAULT_DIR}/Home.md" ]]; then
  cat > "${VAULT_DIR}/Home.md" <<'MD'
---
type: vault-home
system: local-document-classifier
---

# Local Document Classifier

Generated Obsidian vault.
MD
fi

if [[ ! -f "${VAULT_DIR}/Classification Index.md" ]]; then
  cat > "${VAULT_DIR}/Classification Index.md" <<'MD'
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
echo "[INFO] Vault dir: ${VAULT_DIR}"
if [[ -n "${VAULT_NFS_REMOTE}" ]]; then
  echo "[INFO] Vault NFS remote: ${VAULT_NFS_REMOTE}"
  echo "[INFO] Vault NFS mount dir: ${VAULT_NFS_MOUNT_DIR}"
fi
echo "[INFO] API token stored in ${APP_DIR}/.env"
