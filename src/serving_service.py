from __future__ import annotations

import io

import pandas as pd

from amrfinder_features import AmrFinderFeatureBuilder
from serving_loader import ArtifactRegistry, ModelBundle
from serving_schemas import CsvPredictResponse, PredictRequest, PredictResponse, PredictRowOutput, PredictSingleResponse


def _normalize_feature_value(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(value)
    try:
        if pd.isna(value):
            return 0.0
    except TypeError:
        pass
    return float(value)


def build_feature_frame_from_request(bundle: ModelBundle, request: PredictRequest) -> tuple[pd.DataFrame, list[str]]:
    if not request.rows:
        raise ValueError("Request must include at least one row.")

    biosamples: list[str] = []
    payload_rows: list[dict[str, float]] = []

    for index, row in enumerate(request.rows, start=1):
        biosamples.append(row.biosample or f"sample_{index:04d}")
        payload_rows.append({key: _normalize_feature_value(value) for key, value in row.features.items()})

    payload_frame = pd.DataFrame(payload_rows)
    aligned = pd.DataFrame(0.0, index=range(len(payload_rows)), columns=bundle.feature_columns)

    shared_columns = [column for column in payload_frame.columns if column in aligned.columns]
    if shared_columns:
        aligned.loc[:, shared_columns] = payload_frame[shared_columns].astype(float)

    return aligned, biosamples


def run_prediction(bundle: ModelBundle, features: pd.DataFrame, biosamples: list[str], threshold: float) -> list[PredictRowOutput]:
    probabilities = bundle.model.predict_proba(features)[:, 1]
    outputs: list[PredictRowOutput] = []

    for biosample, probability in zip(biosamples, probabilities, strict=True):
        predicted_label = "resistant" if float(probability) >= threshold else "susceptible"
        outputs.append(
            PredictRowOutput(
                biosample=biosample,
                probability_resistant=float(probability),
                predicted_label=predicted_label,
            )
        )
    return outputs


def build_single_response(
    scope: str,
    antibiotic: str,
    threshold: float,
    feature_count: int,
    row: PredictRowOutput,
) -> PredictSingleResponse:
    return PredictSingleResponse(
        scope=scope,
        antibiotic=antibiotic,
        threshold=threshold,
        feature_count=feature_count,
        biosample=row.biosample,
        probability_resistant=row.probability_resistant,
        predicted_label=row.predicted_label,
    )


def predict_from_request(registry: ArtifactRegistry, request: PredictRequest) -> PredictResponse:
    bundle = registry.get_bundle(request.scope, request.antibiotic)
    features, biosamples = build_feature_frame_from_request(bundle, request)
    rows = run_prediction(bundle, features, biosamples, request.threshold)
    return PredictResponse(
        scope=bundle.scope,
        antibiotic=bundle.antibiotic,
        threshold=request.threshold,
        feature_count=len(bundle.feature_columns),
        rows=rows,
    )


def predict_single_from_fasta_bytes(
    registry: ArtifactRegistry,
    scope: str,
    antibiotic: str,
    fasta_bytes: bytes,
    threshold: float,
    biosample: str | None = None,
    fasta_name: str = "sample.fasta",
    feature_builder: AmrFinderFeatureBuilder | None = None,
) -> PredictSingleResponse:
    response = predict_from_fasta_bytes(
        registry,
        scope=scope,
        antibiotic=antibiotic,
        fasta_bytes=fasta_bytes,
        threshold=threshold,
        biosample=biosample,
        fasta_name=fasta_name,
        feature_builder=feature_builder,
    )
    row = response.rows[0]
    return build_single_response(
        scope=response.scope,
        antibiotic=response.antibiotic,
        threshold=response.threshold,
        feature_count=response.feature_count,
        row=row,
    )


def predict_from_fasta_bytes(
    registry: ArtifactRegistry,
    scope: str,
    antibiotic: str,
    fasta_bytes: bytes,
    threshold: float,
    biosample: str | None = None,
    fasta_name: str = "sample.fasta",
    feature_builder: AmrFinderFeatureBuilder | None = None,
) -> PredictResponse:
    bundle = registry.get_bundle(scope, antibiotic)
    builder = feature_builder or AmrFinderFeatureBuilder()
    parsed = builder.build_from_fasta_bytes(
        fasta_bytes=fasta_bytes,
        schema_columns=bundle.feature_columns,
        fasta_name=fasta_name,
    )

    request = PredictRequest(
        scope=scope,
        antibiotic=antibiotic,
        threshold=threshold,
        rows=[
            {
                "biosample": biosample or fasta_name.rsplit(".", 1)[0],
                "features": parsed.features,
            }
        ],
    )
    return predict_from_request(registry, request)


def predict_from_csv_bytes(
    registry: ArtifactRegistry,
    scope: str,
    antibiotic: str,
    file_bytes: bytes,
    threshold: float,
) -> CsvPredictResponse:
    bundle = registry.get_bundle(scope, antibiotic)
    frame = pd.read_csv(io.BytesIO(file_bytes))
    if frame.empty:
        raise ValueError("Uploaded CSV is empty.")

    if "BioSample" in frame.columns:
        biosamples = frame["BioSample"].fillna("").astype(str).replace("", pd.NA)
        biosample_values = [
            value if pd.notna(value) else f"sample_{index:04d}"
            for index, value in enumerate(biosamples.tolist(), start=1)
        ]
    else:
        biosample_values = [f"sample_{index:04d}" for index in range(1, len(frame) + 1)]

    aligned = pd.DataFrame(0.0, index=range(len(frame)), columns=bundle.feature_columns)
    shared_columns = [column for column in frame.columns if column in aligned.columns]
    if shared_columns:
        aligned.loc[:, shared_columns] = frame[shared_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    rows = run_prediction(bundle, aligned, biosample_values, threshold)
    return CsvPredictResponse(
        scope=bundle.scope,
        antibiotic=bundle.antibiotic,
        threshold=threshold,
        feature_count=len(bundle.feature_columns),
        row_count=len(rows),
        rows=[row.model_dump() for row in rows],
    )
