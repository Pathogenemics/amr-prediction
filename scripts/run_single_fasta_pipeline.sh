#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"
VENV_PYTHON="${VENV_PYTHON:-$WORKSPACE_ROOT/.venv/bin/python}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
SCOPE="${SCOPE:-all}"
ANTIBIOTIC="${ANTIBIOTIC:-ampicillin}"
FASTA_PATH="${FASTA_PATH:-$PROJECT_ROOT/data/GCA_032124935.1_PDT001903532.1_genomic.fna}"
BIOSAMPLE="${BIOSAMPLE:-demo_single_fasta}"
BATCH_ID="${BATCH_ID:-batch_run_$(date +%Y%m%d_%H%M%S)}"

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

REQUEST_TMP="$(mktemp -d)"
trap 'rm -rf "$REQUEST_TMP"' EXIT
INGEST_RESPONSE_FILE="$REQUEST_TMP/ingest.json"
PREDICT_RESPONSE_FILE="$REQUEST_TMP/predict.json"

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

echo "Using interpreter: $VENV_PYTHON"
echo "Using FASTA: $FASTA_PATH"
echo "Using batch_id: $BATCH_ID"

run_curl_to_file "$INGEST_RESPONSE_FILE" -X POST "$BASE_URL/ingest-fasta-single" \
  -F "batch_id=$BATCH_ID" \
  -F "biosample=$BIOSAMPLE" \
  -F "file=@$FASTA_PATH"

BRONZE_INPUT_DIR="$("$VENV_PYTHON" -c 'import json,sys; data=json.load(open(sys.argv[1])); print(data["stored_fasta_path"].rsplit("/", 1)[0])' "$INGEST_RESPONSE_FILE")"

echo "Ingested batch:"
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
  -F "file=@$FEATURE_READY_CSV"

echo "Prediction response:"
cat "$PREDICT_RESPONSE_FILE"
echo

echo "Status lookup:"
curl -fsS "$BASE_URL/status/$BATCH_ID"
echo

echo "Manifest lookup:"
curl -fsS "$BASE_URL/manifest/$BATCH_ID"
echo
