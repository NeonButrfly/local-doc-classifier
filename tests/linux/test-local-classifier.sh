#!/usr/bin/env bash
set -euo pipefail

SERVER="192.168.50.196"
REPO_ROOT=""
TOKEN="${TOKEN:-}"
FETCH_TOKEN_OVER_SSH=0
SKIP_ASSERTIONS=0

usage() {
  cat <<'EOF'
Usage: tests/linux/test-local-classifier.sh [options]

Options:
  --server <host>             Classifier host. Default: 192.168.50.196
  --repo-root <path>          Repo root. Default: inferred from script location
  --token <token>             API token. Can also be provided via TOKEN env var
  --fetch-token-over-ssh      Read CLASSIFIER_API_TOKEN from kay@<server>:/opt/local-doc-classifier/.env
  --skip-assertions           Upload fixtures without label assertions
  --help                      Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server)
      SERVER="${2:?missing value for --server}"
      shift 2
      ;;
    --repo-root)
      REPO_ROOT="${2:?missing value for --repo-root}"
      shift 2
      ;;
    --token)
      TOKEN="${2:?missing value for --token}"
      shift 2
      ;;
    --fetch-token-over-ssh)
      FETCH_TOKEN_OVER_SSH=1
      shift
      ;;
    --skip-assertions)
      SKIP_ASSERTIONS=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

for cmd in curl jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Missing required command: $cmd" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi

API_BASE="http://${SERVER}:4319"
FIXTURE_DIR="${REPO_ROOT}/tests/fixtures"
OUT_DIR="${REPO_ROOT}/tests/_classifier-test-results"
EXPECTED_PATH="${FIXTURE_DIR}/expected-labels.json"

mkdir -p "${OUT_DIR}"

if [[ -z "$TOKEN" && "$FETCH_TOKEN_OVER_SSH" -eq 1 ]]; then
  TOKEN="$(ssh "kay@${SERVER}" "grep '^CLASSIFIER_API_TOKEN=' /opt/local-doc-classifier/.env | cut -d= -f2-")"
fi

if [[ -z "$TOKEN" ]]; then
  read -rsp "Paste CLASSIFIER_API_TOKEN: " TOKEN
  echo
fi

get_mime_type() {
  case "${1##*.}" in
    pdf) echo "application/pdf" ;;
    docx) echo "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ;;
    doc) echo "application/msword" ;;
    xlsx) echo "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ;;
    xls) echo "application/vnd.ms-excel" ;;
    png) echo "image/png" ;;
    jpg|jpeg) echo "image/jpeg" ;;
    webp) echo "image/webp" ;;
    bmp) echo "image/bmp" ;;
    tif|tiff) echo "image/tiff" ;;
    *) echo "application/octet-stream" ;;
  esac
}

assert_classification() {
  local fixture_name="$1"
  local fixture_json="$2"
  local response_path="$3"

  if [[ "$SKIP_ASSERTIONS" -eq 1 ]]; then
    return 0
  fi

  local ok
  ok="$(jq -r '.ok' "${response_path}")"
  if [[ "$ok" != "true" ]]; then
    echo "[ERROR] Fixture ${fixture_name} failed classification API call." >&2
    exit 1
  fi

  local primary
  primary="$(jq -r '.record.classification.primary_label // empty' "${response_path}")"
  if [[ -z "$primary" ]]; then
    echo "[ERROR] Fixture ${fixture_name} produced no primary_label." >&2
    exit 1
  fi

  if ! jq -e --arg primary "$primary" '
      (.acceptable_primary_labels // []) as $allowed
      | ($allowed | length == 0) or ($allowed | index($primary) != null)
    ' <<<"${fixture_json}" >/dev/null; then
    echo "[ERROR] Fixture ${fixture_name} primary_label '${primary}' not in acceptable list." >&2
    exit 1
  fi

  if jq -e --arg primary "$primary" '
      (.forbidden_primary_labels // []) | index($primary) != null
    ' <<<"${fixture_json}" >/dev/null; then
    echo "[ERROR] Fixture ${fixture_name} primary_label '${primary}' is forbidden." >&2
    exit 1
  fi

  mapfile -t secondary < <(jq -r '.record.classification.secondary_labels[]?' "${response_path}")
  mapfile -t expected_secondary < <(jq -r '.expected_secondary_any[]?' <<<"${fixture_json}")

  if [[ "${#expected_secondary[@]}" -gt 0 ]]; then
    local hit=0
    for label in "${expected_secondary[@]}"; do
      if [[ "$primary" == "$label" ]]; then
        hit=1
        break
      fi
      for actual in "${secondary[@]}"; do
        if [[ "$actual" == "$label" ]]; then
          hit=1
          break 2
        fi
      done
    done

    if [[ "$hit" -ne 1 ]]; then
      echo "[ERROR] Fixture ${fixture_name} did not include any expected secondary label." >&2
      echo "[ERROR] Primary='${primary}' Secondary='${secondary[*]-}'" >&2
      exit 1
    fi
  fi
}

echo "Testing classifier API at ${API_BASE}"
echo "Repo root: ${REPO_ROOT}"
echo "Fixture dir: ${FIXTURE_DIR}"

if [[ ! -d "${FIXTURE_DIR}" ]]; then
  echo "[ERROR] Fixture directory not found: ${FIXTURE_DIR}" >&2
  exit 1
fi

health_path="${OUT_DIR}/health.json"
curl -sS -H "X-API-Key: ${TOKEN}" "${API_BASE}/health" > "${health_path}"

if [[ "$(jq -r '.ok' "${health_path}")" != "true" ]]; then
  echo "[ERROR] Classifier health check failed. See ${health_path}" >&2
  exit 1
fi

echo "Health OK. Ollama OK: $(jq -r '.ollama_ok' "${health_path}")"

while IFS= read -r fixture_json; do
  file_name="$(jq -r '.file' <<<"${fixture_json}")"
  fixture_kind="$(jq -r '.kind' <<<"${fixture_json}")"
  file_path="${FIXTURE_DIR}/${file_name}"
  response_path="${OUT_DIR}/${fixture_kind}-upload-response.json"

  if [[ ! -f "${file_path}" ]]; then
    echo "[ERROR] Missing fixture: ${file_path}" >&2
    exit 1
  fi

  mime_type="$(get_mime_type "${file_path}")"
  echo "Uploading ${fixture_kind}: ${file_path}"

  curl -sS \
    -H "X-API-Key: ${TOKEN}" \
    -F "file=@${file_path};filename=${file_name};type=${mime_type}" \
    "${API_BASE}/classify/upload" > "${response_path}"

  if [[ "$(jq -r '.ok' "${response_path}")" == "true" ]]; then
    echo "PASS upload: ${file_name} => $(jq -r '.record.classification.primary_label' "${response_path}") confidence=$(jq -r '.record.classification.confidence' "${response_path}")"
    echo "Note: $(jq -r '.record.note_path' "${response_path}")"
  else
    echo "FAIL upload: ${file_name}" >&2
    echo "Error: $(jq -r '.record.error // empty' "${response_path}")" >&2
    echo "stderr_tail: $(jq -r '.stderr_tail // empty' "${response_path}")" >&2
  fi

  assert_classification "${file_name}" "${fixture_json}" "${response_path}"
done < <(jq -c '.fixtures[]' "${EXPECTED_PATH}")

recent_path="${OUT_DIR}/recent.json"
index_path="${OUT_DIR}/classification-index.md"
curl -sS -H "X-API-Key: ${TOKEN}" "${API_BASE}/recent?limit=10" > "${recent_path}"
curl -sS -H "X-API-Key: ${TOKEN}" "${API_BASE}/index?max_chars=30000" > "${index_path}"

echo
echo "Done. Results saved to: ${OUT_DIR}"
echo "Health: ${health_path}"
echo "Recent: ${recent_path}"
echo "Index: ${index_path}"
