from __future__ import annotations

from dataclasses import asdict
import logging
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fasta_batch_processor import process_fasta_batch
from ingestion_service import DATA_ROOT, ingest_single_fasta, read_batch_manifest, read_batch_status, write_batch_status
from serving_loader import ArtifactRegistry
from serving_schemas import (
    CsvPredictResponse,
    HealthResponse,
    IngestFastaResponse,
    ModelSummary,
    PredictRequest,
    PredictResponse,
    ProcessBatchRequest,
    ProcessBatchResponse,
)
from serving_service import predict_from_csv_bytes, predict_from_request


registry = ArtifactRegistry()
FRONTEND_ROOT = Path(__file__).resolve().parent.parent / "frontend"
ASSETS_ROOT = FRONTEND_ROOT / "assets"
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AMR Prediction Serving API",
    version="0.1.0",
    description="MVP backend for serving AMR prediction models exported from training artifacts.",
)

if ASSETS_ROOT.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_ROOT), name="assets")


@app.on_event("startup")
def startup_event() -> None:
    registry.load()


@app.get("/", include_in_schema=False)
def frontend_index() -> FileResponse:
    return FileResponse(FRONTEND_ROOT / "index.html")


def _resolve_batch_input_dir(batch_id: str, requested_input_dir: str | None = None) -> Path:
    if requested_input_dir:
        input_dir = Path(requested_input_dir)
    else:
        status_payload: dict[str, Any] = {}
        manifest_payload: dict[str, Any] = {}
        try:
            status_payload = read_batch_status(batch_id)
        except FileNotFoundError:
            pass
        try:
            manifest_payload = read_batch_manifest(batch_id)
        except FileNotFoundError:
            pass

        if not status_payload and not manifest_payload:
            raise FileNotFoundError(f"No batch metadata found for batch_id={batch_id!r}")

        bronze_input_dir = (
            status_payload.get("bronze_input_dir")
            or manifest_payload.get("bronze_input_dir")
            or DATA_ROOT / "bronze" / "fasta_batches" / batch_id
        )
        input_dir = Path(bronze_input_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    return input_dir


def _run_processing_job(*, batch_id: str, input_dir: Path, scope: str, antibiotic: str) -> None:
    try:
        process_fasta_batch(
            input_dir=input_dir,
            scope=scope,
            antibiotic=antibiotic,
            batch_id=batch_id,
            data_root=DATA_ROOT,
        )
    except Exception:
        logger.exception("Background processing failed for batch_id=%s", batch_id)


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


@app.get("/status/{batch_id}", response_model=dict[str, Any])
def get_batch_status(batch_id: str) -> dict[str, Any]:
    try:
        return read_batch_status(batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/manifest/{batch_id}", response_model=dict[str, Any])
def get_batch_manifest(batch_id: str) -> dict[str, Any]:
    try:
        return read_batch_manifest(batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@app.post("/ingest-fasta-single", response_model=IngestFastaResponse)
async def ingest_fasta_single(
    batch_id: str | None = Form(None),
    biosample: str | None = Form(None),
    file: UploadFile = File(...),
) -> IngestFastaResponse:
    try:
        file_bytes = await file.read()
        ingested = ingest_single_fasta(
            fasta_bytes=file_bytes,
            fasta_name=file.filename or "sample.fasta",
            batch_id=batch_id,
            biosample=biosample,
        )
        return IngestFastaResponse.model_validate(asdict(ingested))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/process-fasta-batch", response_model=ProcessBatchResponse, status_code=202)
def trigger_fasta_batch_processing(
    request: ProcessBatchRequest,
    background_tasks: BackgroundTasks,
) -> ProcessBatchResponse:
    try:
        existing_status = read_batch_status(request.batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if existing_status.get("status") == "processing":
        raise HTTPException(status_code=409, detail=f"Batch {request.batch_id!r} is already processing.")

    try:
        input_dir = _resolve_batch_input_dir(request.batch_id, request.input_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    write_batch_status(
        request.batch_id,
        status="processing",
        data_root=DATA_ROOT,
        bronze_input_dir=str(input_dir),
        scope=request.scope,
        antibiotic=request.antibiotic,
        next_step="Wait for processing to complete, then use /predict-csv or /predict.",
    )
    background_tasks.add_task(
        _run_processing_job,
        batch_id=request.batch_id,
        input_dir=input_dir,
        scope=request.scope,
        antibiotic=request.antibiotic,
    )
    return ProcessBatchResponse(
        batch_id=request.batch_id,
        status="processing",
        scope=request.scope,
        antibiotic=request.antibiotic,
        bronze_input_dir=str(input_dir),
        message="Batch processing started in the background.",
    )
