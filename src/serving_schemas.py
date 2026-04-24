from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    artifact_root: str
    loaded_model_count: int


class ModelSummary(BaseModel):
    scope: str
    antibiotic: str
    safe_name: str
    n_features: int
    n_samples: int | None = None


class PredictRowInput(BaseModel):
    biosample: str | None = None
    features: dict[str, float | int | bool | None] = Field(default_factory=dict)


class PredictRequest(BaseModel):
    scope: str = "all"
    antibiotic: str
    threshold: float = 0.5
    rows: list[PredictRowInput]


class PredictSingleResponse(BaseModel):
    scope: str
    antibiotic: str
    threshold: float
    feature_count: int
    biosample: str
    probability_resistant: float
    predicted_label: str


class PredictRowOutput(BaseModel):
    biosample: str
    probability_resistant: float
    predicted_label: str


class PredictResponse(BaseModel):
    scope: str
    antibiotic: str
    threshold: float
    feature_count: int
    rows: list[PredictRowOutput]


class CsvPredictResponse(BaseModel):
    scope: str
    antibiotic: str
    threshold: float
    feature_count: int
    row_count: int
    rows: list[dict[str, Any]]


class IngestFastaResponse(BaseModel):
    batch_id: str
    biosample: str
    stored_fasta_path: str
    manifest_path: str
    status_path: str
    status: str


class ProcessBatchRequest(BaseModel):
    batch_id: str
    scope: str = "all"
    antibiotic: str
    input_dir: str | None = None


class ProcessBatchResponse(BaseModel):
    batch_id: str
    status: str
    scope: str
    antibiotic: str
    bronze_input_dir: str
    message: str
