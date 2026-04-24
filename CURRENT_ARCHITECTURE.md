# Current Architecture

This file describes the canonical architecture of the repository as it exists now.

## Canonical flow

### FASTA flow

```text
single FASTA or FASTA batch
-> ingestion
-> data/bronze/fasta_batches/<batch_id>/
-> processing job
-> data/silver/amrfinder_outputs/<batch_id>/
-> data/gold/feature_ready_batches/<batch_id>/
-> serving via /predict or /predict-csv
```

Operational orchestration script:

- `scripts/run_single_fasta_pipeline.sh`

### CSV batch flow

```text
prepared CSV/genotype batch
-> data/bronze/incoming_csv_batches/<batch_id>/
-> serving check via scripts/test_predict_from_incoming_batch.py
-> /predict
```

## Canonical storage layout

```text
data/
  bronze/
    fasta_batches/
    incoming_csv_batches/
  silver/
    amrfinder_outputs/
  gold/
    feature_ready_batches/
  results/
    manifests/
    status/
```

## Canonical FastAPI role

FastAPI is the serving layer.

It is responsible for:

- `GET /health`
- `GET /models`
- `GET /status/{batch_id}`
- `GET /manifest/{batch_id}`
- `POST /predict`
- `POST /predict-csv`
- `POST /ingest-fasta-single`

FastAPI is not responsible for:

- running `AMRFinderPlus` inline during prediction
- preprocessing raw FASTA during a prediction request
- combining serving and biological processing in one request path

## Lifecycle states

Batch status is standardized to:

- `ingested`
- `processing`
- `completed`
- `failed`

## Legacy compatibility

The repository still contains some older prototype artifacts and references.

### Legacy migration source

- `data/incoming/<batch_id>/`

This should now be treated as migration-only legacy data.
The canonical CSV batch path is:

- `data/bronze/incoming_csv_batches/<batch_id>/`

### Historical documents

- `ARCHITECTURE_HANDOFF.md` describes the original architectural gap and desired direction
- `REFACTOR_HISTORY.md` records what has already been changed
- `NEXT_STEPS.md` tracks what still remains

### Legacy-oriented assets still present

- `scripts/test_predict_from_incoming_batch.py` remains useful, but should be understood as a CSV-batch serving check, not the main FASTA processing path

## Recommended interpretation

If there is any conflict between older prototype references and newer staged-storage flow, treat this document as the current canonical architecture.
