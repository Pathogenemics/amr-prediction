# Next Steps

## Current status

This file tracks what has already been completed in the FASTA architecture refactor and what still remains.

For the canonical architecture as of now, see `CURRENT_ARCHITECTURE.md`.

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

No architecture-critical work remains from this refactor track.

The core target state is now in place:

- serving and processing are separated
- ingestion exists
- staged storage exists
- lifecycle states exist
- status/manifest lookup exists
- canonical orchestration exists
- canonical storage paths are defined

## Optional future enhancements

These are improvements, not remaining refactor obligations.

### 1. Operational hardening

- add retry/reprocess utilities
- add cleanup/archive scripts for old batches
- add richer failure diagnostics and recovery tooling

### 2. Performance improvements

- reduce `pandas` overhead in serving
- precompute feature alignment structures
- optimize large-batch processing behavior

### 3. Product/runtime improvements

- add prediction result history if needed
- add better job dashboards or monitoring
- add more automation around scheduled micro-batch execution

## Recommended next task

If more work is desired, choose based on project goal:

- for engineering quality: operational hardening
- for performance claims: serving/process optimization
- for demo value: dashboards or scheduled orchestration

## Short summary

The main architectural correction is complete:

- FASTA preprocessing is no longer part of FastAPI serving
- FASTA now enters through ingestion and batch processing
- serving consumes feature-ready inputs

The architecture refactor track is complete.
