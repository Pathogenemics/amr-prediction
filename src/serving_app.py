from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from serving_loader import ArtifactRegistry
from serving_schemas import CsvPredictResponse, HealthResponse, ModelSummary, PredictRequest, PredictResponse
from serving_service import predict_from_csv_bytes, predict_from_request


registry = ArtifactRegistry()

app = FastAPI(
    title="AMR Prediction Serving API",
    version="0.1.0",
    description="MVP backend for serving AMR prediction models exported from training artifacts.",
)


@app.on_event("startup")
def startup_event() -> None:
    registry.load()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    bundles = registry.list_bundles()
    return HealthResponse(
        status="ok",
        artifact_root=str(registry.artifact_root),
        loaded_model_count=len(bundles),
    )


@app.get("/models", response_model=list[ModelSummary])
def list_models(scope: str | None = None) -> list[ModelSummary]:
    bundles = registry.list_bundles(scope=scope)
    return [
        ModelSummary(
            scope=bundle.scope,
            antibiotic=bundle.antibiotic,
            safe_name=bundle.safe_name,
            n_features=len(bundle.feature_columns),
            n_samples=(
                int(bundle.metadata["n_samples"])
                if bundle.metadata.get("n_samples") is not None
                else None
            ),
        )
        for bundle in bundles
    ]


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    try:
        return predict_from_request(registry, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/predict-csv", response_model=CsvPredictResponse)
async def predict_csv(
    scope: str = Form("all"),
    antibiotic: str = Form(...),
    threshold: float = Form(0.5),
    file: UploadFile = File(...),
) -> CsvPredictResponse:
    try:
        file_bytes = await file.read()
        return predict_from_csv_bytes(registry, scope=scope, antibiotic=antibiotic, file_bytes=file_bytes, threshold=threshold)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
