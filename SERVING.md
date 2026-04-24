# AMR Serving MVP

This repository now includes a minimal FastAPI backend for serving saved XGBoost AMR models.

## Expected artifacts

The backend expects exported artifacts under:

- `artifacts/models/<scope>/*.json`
- `artifacts/schemas/<scope>/*_features.json`
- `artifacts/metadata/<scope>/*_meta.json`

These are the files exported from Colab after fitting one final model per antibiotic.

## Install dependencies

```bash
pip install fastapi uvicorn python-multipart pandas xgboost
```

For FASTA preprocessing, install AMRFinderPlus separately and ensure `amrfinder` is on `PATH`.

## Run the API

From the repository root:

```bash
export PYTHONPATH="$(pwd)/src"
uvicorn serving_app:app --host 0.0.0.0 --port 8000
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
uvicorn serving_app:app --host 0.0.0.0 --port 8000
```

After startup, a demo frontend is available at:

```text
http://127.0.0.1:8000/
```

For a Streamlit demo UI aligned with the same backend APIs:

```bash
bash scripts/run_streamlit_demo.sh
```

## Endpoints

- `GET /health`
- `GET /models`
- `GET /status/{batch_id}`
- `GET /manifest/{batch_id}`
- `POST /predict`
- `POST /predict-csv`
- `POST /ingest-fasta-single`
- `POST /process-fasta-batch`

## Example JSON request

```json
{
  "scope": "all",
  "antibiotic": "ampicillin",
  "threshold": 0.5,
  "rows": [
    {
      "biosample": "demo_001",
      "features": {
        "blatem_1_lineage_match": 1,
        "blatem_1_identity": 99.5,
        "blatem_1_coverage": 100
      }
    }
  ]
}
```

## FASTA processing flow

For a single FASTA upload via API, first ingest it into staged storage:

```bash
curl -X POST "http://127.0.0.1:8000/ingest-fasta-single" \
  -F "biosample=demo_001" \
  -F "file=@/path/to/demo_001.fasta"
```

This only stores the file in `data/bronze/fasta_batches/<batch_id>/` and writes manifest/status metadata.

Batch status lifecycle now uses:

- `ingested`
- `processing`
- `completed`
- `failed`

Then trigger processing either from the demo UI/Streamlit app or directly via API:

```bash
curl -X POST "http://127.0.0.1:8000/process-fasta-batch" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "batch_001",
    "scope": "all",
    "antibiotic": "ampicillin"
  }'
```

The old shell entrypoint still works as an advanced/manual fallback:

```bash
python scripts/process_fasta_batch.py \
  --input-dir data/bronze/fasta_batches/batch_001 \
  --scope all \
  --antibiotic ampicillin \
  --batch-id batch_001
```

This writes:

- raw AMRFinder tables to `data/silver/amrfinder_outputs/<batch_id>/`
- feature-ready tables to `data/gold/feature_ready_batches/<batch_id>/`
- batch manifest/status files to `data/results/`

Use the generated feature-ready CSV with `POST /predict-csv`, or convert it to the `/predict` JSON shape if needed.
