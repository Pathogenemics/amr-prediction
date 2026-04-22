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

For FASTA inference, install AMRFinderPlus separately and ensure `amrfinder` is on `PATH`.

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

## Endpoints

- `GET /health`
- `GET /models`
- `POST /predict`
- `POST /predict-csv`
- `POST /predict-fasta`

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

## Example FASTA request

```bash
curl -X POST "http://127.0.0.1:8000/predict-fasta" \
  -F "scope=all" \
  -F "antibiotic=ampicillin" \
  -F "threshold=0.5" \
  -F "biosample=demo_001" \
  -F "file=@/path/to/isolate.fasta"
```
