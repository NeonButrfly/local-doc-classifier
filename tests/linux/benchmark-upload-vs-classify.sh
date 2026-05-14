#!/usr/bin/env bash
set -euo pipefail

SERVER="192.168.50.196"
TOKEN="${TOKEN:-}"
FILE_PATH=""
REPEATS=3
FETCH_TOKEN_OVER_SSH=0

usage() {
  cat <<'EOF'
Usage: tests/linux/benchmark-upload-vs-classify.sh --file <path> [options]

Options:
  --server <host>             Classifier host. Default: 192.168.50.196
  --token <token>             API token. Can also be provided via TOKEN env var
  --fetch-token-over-ssh      Read CLASSIFIER_API_TOKEN from kay@<server>:/opt/local-doc-classifier/.env
  --file <path>               File to upload for the benchmark
  --repeats <count>           Number of runs for each endpoint. Default: 3
  --help                      Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server)
      SERVER="${2:?missing value for --server}"
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
    --file)
      FILE_PATH="${2:?missing value for --file}"
      shift 2
      ;;
    --repeats)
      REPEATS="${2:?missing value for --repeats}"
      shift 2
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

for cmd in curl jq python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Missing required command: $cmd" >&2
    exit 2
  fi
done

if [[ -z "${FILE_PATH}" ]]; then
  echo "[ERROR] --file is required." >&2
  usage >&2
  exit 2
fi

if [[ ! -f "${FILE_PATH}" ]]; then
  echo "[ERROR] File not found: ${FILE_PATH}" >&2
  exit 1
fi

if [[ -z "$TOKEN" && "$FETCH_TOKEN_OVER_SSH" -eq 1 ]]; then
  TOKEN="$(ssh "kay@${SERVER}" "grep '^CLASSIFIER_API_TOKEN=' /opt/local-doc-classifier/.env | cut -d= -f2-")"
fi

if [[ -z "$TOKEN" ]]; then
  read -rsp "Paste CLASSIFIER_API_TOKEN: " TOKEN
  echo
fi

API_BASE="http://${SERVER}:4319"
FILE_NAME="$(basename "${FILE_PATH}")"
FILE_EXT="${FILE_NAME##*.}"

case "${FILE_EXT,,}" in
  pdf) MIME_TYPE="application/pdf" ;;
  docx) MIME_TYPE="application/vnd.openxmlformats-officedocument.wordprocessingml.document" ;;
  doc) MIME_TYPE="application/msword" ;;
  xlsx) MIME_TYPE="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ;;
  xls) MIME_TYPE="application/vnd.ms-excel" ;;
  png) MIME_TYPE="image/png" ;;
  jpg|jpeg) MIME_TYPE="image/jpeg" ;;
  webp) MIME_TYPE="image/webp" ;;
  bmp) MIME_TYPE="image/bmp" ;;
  tif|tiff) MIME_TYPE="image/tiff" ;;
  txt) MIME_TYPE="text/plain" ;;
  md|markdown) MIME_TYPE="text/markdown" ;;
  csv) MIME_TYPE="text/csv" ;;
  *) MIME_TYPE="application/octet-stream" ;;
esac

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "Benchmarking ${FILE_NAME} against ${API_BASE}"
echo "Runs per endpoint: ${REPEATS}"
echo

run_benchmark() {
  local label="$1"
  local endpoint="$2"
  local extra_form_name="$3"
  local extra_form_value="$4"

  local client_times=()
  local server_upload_times=()
  local server_classify_times=()
  local server_total_times=()

  echo "[${label}]"

  for run in $(seq 1 "${REPEATS}"); do
    local body_path="${TMP_DIR}/${label// /_}-${run}.json"
    local metrics_path="${TMP_DIR}/${label// /_}-${run}.txt"

    if [[ -n "${extra_form_name}" ]]; then
      curl -sS \
        -o "${body_path}" \
        -w "time_total=%{time_total}\nsize_upload=%{size_upload}\nspeed_upload=%{speed_upload}\nhttp_code=%{http_code}\n" \
        -H "X-API-Key: ${TOKEN}" \
        -F "${extra_form_name}=${extra_form_value}" \
        -F "file=@${FILE_PATH};filename=${FILE_NAME};type=${MIME_TYPE}" \
        "${endpoint}" > "${metrics_path}"
    else
      curl -sS \
        -o "${body_path}" \
        -w "time_total=%{time_total}\nsize_upload=%{size_upload}\nspeed_upload=%{speed_upload}\nhttp_code=%{http_code}\n" \
        -H "X-API-Key: ${TOKEN}" \
        -F "file=@${FILE_PATH};filename=${FILE_NAME};type=${MIME_TYPE}" \
        "${endpoint}" > "${metrics_path}"
    fi

    local client_total
    client_total="$(awk -F= '$1 == "time_total" { print $2 }' "${metrics_path}")"
    local size_upload
    size_upload="$(awk -F= '$1 == "size_upload" { print $2 }' "${metrics_path}")"
    local speed_upload
    speed_upload="$(awk -F= '$1 == "speed_upload" { print $2 }' "${metrics_path}")"
    local http_code
    http_code="$(awk -F= '$1 == "http_code" { print $2 }' "${metrics_path}")"

    if [[ "${http_code}" != "200" ]]; then
      echo "  run ${run}: HTTP ${http_code}" >&2
      cat "${body_path}" >&2
      exit 1
    fi

    local server_upload
    server_upload="$(jq -r '.upload_ms // 0' "${body_path}")"
    local server_classify
    server_classify="$(jq -r '.classify_ms // 0' "${body_path}")"
    local server_total
    server_total="$(jq -r '.total_ms // 0' "${body_path}")"

    client_times+=("${client_total}")
    server_upload_times+=("${server_upload}")
    server_classify_times+=("${server_classify}")
    server_total_times+=("${server_total}")

    echo "  run ${run}: client_total=${client_total}s size_upload=${size_upload}B speed_upload=${speed_upload}B/s server_upload_ms=${server_upload} server_classify_ms=${server_classify} server_total_ms=${server_total}"
  done

  python3 - "$label" "${client_times[*]}" "${server_upload_times[*]}" "${server_classify_times[*]}" "${server_total_times[*]}" <<'PY'
import statistics
import sys

label = sys.argv[1]
client = [float(x) for x in sys.argv[2].split()] if sys.argv[2].strip() else []
server_upload = [float(x) for x in sys.argv[3].split()] if sys.argv[3].strip() else []
server_classify = [float(x) for x in sys.argv[4].split()] if sys.argv[4].strip() else []
server_total = [float(x) for x in sys.argv[5].split()] if sys.argv[5].strip() else []

def summary(values):
    if not values:
        return "n/a"
    return f"avg={statistics.mean(values):.3f} min={min(values):.3f} max={max(values):.3f}"

print(f"  summary client_total_s: {summary(client)}")
print(f"  summary server_upload_ms: {summary(server_upload)}")
print(f"  summary server_classify_ms: {summary(server_classify)}")
print(f"  summary server_total_ms: {summary(server_total)}")
PY

  echo
}

run_benchmark "upload_only" "${API_BASE}/benchmark/upload-only" "cleanup" "true"
run_benchmark "full_classify" "${API_BASE}/classify/upload" "" ""
