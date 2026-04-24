#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKSPACE_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"
VENV_PYTHON="${VENV_PYTHON:-$WORKSPACE_ROOT/.venv/bin/python}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
SCOPE="${SCOPE:-all}"
ANTIBIOTIC="${ANTIBIOTIC:-ampicillin}"
FASTA_PATH="${FASTA_PATH:-$PROJECT_ROOT/data/GCA_032124935.1_PDT001903532.1_genomic.fna}"
BIOSAMPLE="${BIOSAMPLE:-demo_single_fasta}"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Python interpreter not found: $VENV_PYTHON" >&2
  echo "Set VENV_PYTHON=/path/to/venv/bin/python and run again." >&2
  exit 1
fi

if [[ ! -f "$FASTA_PATH" ]]; then
  echo "FASTA file not found: $FASTA_PATH" >&2
  echo "Set FASTA_PATH=/path/to/sample.fasta and run again." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required for this script." >&2
  exit 1
fi

if ! command -v amrfinder >/dev/null 2>&1; then
  echo "amrfinder is not available on PATH." >&2
  echo "Install AMRFinderPlus or export PATH so process_fasta_batch.py can run." >&2
  exit 1
fi

cd "$PROJECT_ROOT"

SERVER_STARTED_BY_SCRIPT=0
SERVER_PID=""

cleanup() {
  if [[ "$SERVER_STARTED_BY_SCRIPT" -eq 1 && -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

ensure_backend_supports_ingest() {
  if curl -fsS "$BASE_URL/openapi.json" | grep -q '"/ingest-fasta-single"'; then
    return 0
  fi

  if [[ "$SERVER_STARTED_BY_SCRIPT" -eq 1 ]]; then
    echo "Backend started by script, but /ingest-fasta-single is still missing." >&2
    echo "Check /tmp/amr_serving_e2e.log for startup errors." >&2
    exit 1
  fi

  echo "A backend is already running at $BASE_URL, but it does not expose /ingest-fasta-single." >&2
  echo "Stop the old server and rerun this script, or use BASE_URL to point at the updated backend." >&2
  exit 1
}

run_curl_to_file() {
  local output_file="$1"
  shift

  local http_code
  http_code="$(curl -sS -o "$output_file" -w "%{http_code}" "$@")"
  if [[ "$http_code" =~ ^2 ]]; then
    return 0
  fi

  echo "HTTP request failed with status $http_code" >&2
  if [[ -s "$output_file" ]]; then
    echo "Response body:" >&2
    cat "$output_file" >&2
    echo >&2
  fi
  return 1
}

if ! curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
  echo "Backend not detected at $BASE_URL. Starting local uvicorn server."
  export PYTHONPATH="$PROJECT_ROOT/src"
  "$VENV_PYTHON" -m uvicorn serving_app:app --host 127.0.0.1 --port 8000 >/tmp/amr_serving_e2e.log 2>&1 &
  SERVER_PID="$!"
  SERVER_STARTED_BY_SCRIPT=1

  for _ in $(seq 1 30); do
    if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    echo "Failed to start backend. Check /tmp/amr_serving_e2e.log" >&2
    exit 1
  fi
fi

ensure_backend_supports_ingest

BATCH_ID="batch_e2e_$(date +%Y%m%d_%H%M%S)"
INGEST_RESPONSE_FILE="$(mktemp)"
PREDICT_RESPONSE_FILE="$(mktemp)"
trap 'rm -f "$INGEST_RESPONSE_FILE" "$PREDICT_RESPONSE_FILE"; cleanup' EXIT

echo "Using interpreter: $VENV_PYTHON"
echo "Using FASTA: $FASTA_PATH"
echo "Batch id: $BATCH_ID"

run_curl_to_file "$INGEST_RESPONSE_FILE" -X POST "$BASE_URL/ingest-fasta-single" \
  -F "batch_id=$BATCH_ID" \
  -F "biosample=$BIOSAMPLE" \
  -F "file=@$FASTA_PATH" \
  || exit 1

BRONZE_INPUT_DIR="$("$VENV_PYTHON" -c 'import json,sys; data=json.load(open(sys.argv[1])); print(data["stored_fasta_path"].rsplit("/", 1)[0])' "$INGEST_RESPONSE_FILE")"

echo "Ingest response:"
cat "$INGEST_RESPONSE_FILE"
echo

"$VENV_PYTHON" scripts/process_fasta_batch.py \
  --input-dir "$BRONZE_INPUT_DIR" \
  --scope "$SCOPE" \
  --antibiotic "$ANTIBIOTIC" \
  --batch-id "$BATCH_ID"

FEATURE_READY_CSV="$PROJECT_ROOT/data/gold/feature_ready_batches/$BATCH_ID/${ANTIBIOTIC// /_}__features.csv"

if [[ ! -f "$FEATURE_READY_CSV" ]]; then
  echo "Expected feature-ready CSV not found: $FEATURE_READY_CSV" >&2
  exit 1
fi

run_curl_to_file "$PREDICT_RESPONSE_FILE" -X POST "$BASE_URL/predict-csv" \
  -F "scope=$SCOPE" \
  -F "antibiotic=$ANTIBIOTIC" \
  -F "threshold=0.5" \
  -F "file=@$FEATURE_READY_CSV" \
  || exit 1

echo "Prediction response:"
cat "$PREDICT_RESPONSE_FILE"
echo

echo "E2E verification completed."
