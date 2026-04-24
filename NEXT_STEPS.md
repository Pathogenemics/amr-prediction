# Next Steps

## Current status

This file tracks what has already been completed in the FASTA architecture refactor and what still remains.

## Completed

### 1. FASTA preprocessing removed from FastAPI request-time prediction

- Removed direct FASTA prediction flow from the serving path
- Removed the old request-time FASTA prediction endpoints from FastAPI
- FastAPI no longer runs `AMRFinderPlus` during prediction requests

### 2. FastAPI kept as the serving layer

- FastAPI remains the backend entrypoint in `src/serving_app.py`
- Serving is now focused on:
  - `GET /health`
  - `GET /models`
  - `POST /predict`
  - `POST /predict-csv`

### 3. Single FASTA ingestion added in the correct architectural layer

- Added `POST /ingest-fasta-single`
- This endpoint:
  - accepts one FASTA file
  - stores it in bronze storage
  - writes batch metadata
  - returns `batch_id`
- It does not do inline preprocessing or inline prediction

### 4. Separate batch processing entrypoint added

- Added `scripts/process_fasta_batch.py`
- Added `src/fasta_batch_processor.py`
- Processing is now explicitly outside FastAPI

### 5. Staged storage flow introduced

- Bronze:
  - `data/bronze/fasta_batches/...`
- Silver:
  - `data/silver/amrfinder_outputs/...`
- Gold:
  - `data/gold/feature_ready_batches/...`
- Results:
  - `data/results/manifests/...`
  - `data/results/status/...`

### 6. Batch metadata added

- Each ingested or processed batch now writes structured metadata
- Metadata includes batch identifiers, paths, timestamps, sample counts, and status

### 7. Lifecycle states standardized

- Batch status now follows a consistent lifecycle:
  - `ingested`
  - `processing`
  - `completed`
  - `failed`
- Status files now use a more consistent structure with:
  - `batch_id`
  - `status`
  - `created_at`
  - `updated_at`
  - optional scope/antibiotic/input/output/error fields

### 8. Shared AMRFinder logic refactored

- `src/amrfinder_features.py` now cleanly supports:
  - running `AMRFinderPlus`
  - mapping AMRFinder tables into feature-ready schema values

### 9. Tests added for the new architecture

- Added `tests/test_ingestion_service.py`
- Added `tests/test_fasta_batch_processor.py`
- Verified test pass in the project venv

### 10. Test scripts added

- Added `scripts/test_commands/run_fasta_architecture_test.sh`
- Added `scripts/test_commands/run_fasta_e2e_verification.sh`
- Added `scripts/test_commands/README.md`

### 11. Documentation updated

- Updated `SERVING.md`
- Added `REFACTOR_HISTORY.md`

## Remaining work

### 1. Batch status lookup endpoints added

Implemented:

- `GET /status/{batch_id}`
- `GET /manifest/{batch_id}`

Reason:

- the system already creates `batch_id`
- metadata files already exist
- API lookup completes the batch lifecycle story

### 2. CSV batch layout partially unified

Canonical layout is now:

- `data/bronze/incoming_csv_batches/<batch_id>/`

Legacy compatibility still exists for:

- `data/incoming/<batch_id>/`

The script `scripts/test_predict_from_incoming_batch.py` now prefers the canonical bronze path and only falls back to the legacy path when needed.

The helper `scripts/migrate_incoming_batch_to_bronze.py` can copy legacy incoming batches into the canonical bronze layout.

### 4. Review old scripts that still assume the prototype flow

Especially:

- `scripts/test_predict_from_incoming_batch.py`

This script still targets the prepared `/predict` flow rather than the FASTA batch flow.
That is acceptable, but it should now be treated as the CSV-batch serving check, not the main FASTA architecture path.

### 5. Optionally add orchestration for full batch flow

Possible next enhancement:

- one script or job that chains:
  - ingest
  - process
  - predict

This is optional, but would make the micro-batch workflow easier to operate.

### 6. Clean up docs to remove mixed architectural signals

Need to make sure the repo does not look like it has two competing architectures:

- old direct prototype path
- new staged micro-batch path

## Recommended next task

If only one task should be done next, choose:

### Review legacy scripts and notebooks

Why:

- lifecycle states and lookup endpoints now exist
- the biggest remaining inconsistency is in older scripts and notebooks that still narrate the prototype path more heavily than the staged pipeline

## Short summary

The main architectural correction is complete:

- FASTA preprocessing is no longer part of FastAPI serving
- FASTA now enters through ingestion and batch processing
- serving consumes feature-ready inputs

The next phase is pipeline completion and cleanup, not another major refactor.
