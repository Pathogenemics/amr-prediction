# Refactor History

## 2026-04-24: FASTA architecture refactor

### Goal

Remove FASTA preprocessing from the FastAPI serving request path and move it into a separate micro-batch processing flow.

### Completed changes

#### Serving layer

- Kept FastAPI as the serving layer in `src/serving_app.py`
- Removed request-time FASTA prediction endpoints:
  - `POST /predict-fasta`
  - `POST /predict-fasta-single`
- Kept serving endpoints focused on:
  - `GET /health`
  - `GET /models`
  - `POST /predict`
  - `POST /predict-csv`

#### Ingestion layer

- Added `POST /ingest-fasta-single`
- This endpoint now:
  - accepts one FASTA file
  - stores it in `data/bronze/fasta_batches/<batch_id>/`
  - writes manifest and status metadata
  - returns `batch_id` and stored paths
- It does not run `AMRFinderPlus` or prediction inline

#### Processing layer

- Added `src/fasta_batch_processor.py`
- Added `scripts/process_fasta_batch.py`
- FASTA processing is now handled outside FastAPI as a batch job
- Processing flow now does:
  - discover FASTA files in a batch folder
  - run `AMRFinderPlus`
  - save raw AMRFinder output to `data/silver/amrfinder_outputs/<batch_id>/`
  - build feature-ready tables
  - save feature-ready CSV to `data/gold/feature_ready_batches/<batch_id>/`
  - write batch manifest/status files to `data/results/`

#### Shared logic

- Refactored `src/amrfinder_features.py`
- Split AMRFinder execution from frame-to-feature mapping so the processing layer can reuse it cleanly

#### Documentation and test commands

- Updated `SERVING.md` to describe the new architecture and flow
- Added `scripts/test_commands/run_fasta_architecture_test.sh`
- Added `scripts/test_commands/run_fasta_e2e_verification.sh`
- Added `scripts/test_commands/README.md`

### Tests added

- `tests/test_fasta_batch_processor.py`
  - verifies FASTA batch processing writes silver/gold/results outputs
  - verifies serving consumes feature-ready CSV instead of FASTA
- `tests/test_ingestion_service.py`
  - verifies single FASTA ingestion writes bronze/manifests/status correctly

### Verified status

The following test suite passed in the project venv:

```bash
/home/nghia/Desktop/BigData/.venv/bin/python -m unittest tests.test_ingestion_service tests.test_fasta_batch_processor
```

### Architectural result

The system is now aligned with a staged-storage micro-batch flow:

```text
single FASTA or FASTA batch
-> ingestion
-> bronze storage
-> batch processing
-> silver/gold staged outputs
-> serving from feature-ready input
```
