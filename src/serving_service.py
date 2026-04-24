from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from amrfinder_features import AmrFinderFeatureBuilder
from serving_loader import ArtifactRegistry, ModelBundle
from serving_schemas import (
    CsvPredictResponse,
    FastaScreenPrediction,
    FastaScreenResponse,
    PredictRequest,
    PredictResponse,
    PredictRowOutput,
)


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


def screen_fasta_bytes(
    registry: ArtifactRegistry,
    *,
    scope: str,
    fasta_bytes: bytes,
    fasta_name: str,
    biosample: str | None = None,
    threshold: float,
    feature_builder: AmrFinderFeatureBuilder | None = None,
) -> FastaScreenResponse:
    bundles = registry.list_bundles(scope=scope)
    if not bundles:
        raise ValueError(f"No models loaded for scope={scope!r}.")

    builder = feature_builder or AmrFinderFeatureBuilder()
    frame = builder.run_amrfinder(fasta_bytes=fasta_bytes, fasta_name=fasta_name)
    effective_biosample = biosample or Path(fasta_name).stem or "sample_0001"

    predictions: list[FastaScreenPrediction] = []
    hit_count = 0
    for bundle in bundles:
        parsed = builder.build_from_amrfinder_frame(frame, bundle.feature_columns)
        hit_count = max(hit_count, parsed.hit_count)

        aligned = pd.DataFrame(0.0, index=[0], columns=bundle.feature_columns)
        for column, value in parsed.features.items():
            if column in aligned.columns:
                aligned.at[0, column] = float(value)

        result = run_prediction(bundle, aligned, [effective_biosample], threshold)[0]
        predictions.append(
            FastaScreenPrediction(
                antibiotic=bundle.antibiotic,
                probability_resistant=result.probability_resistant,
                predicted_label=result.predicted_label,
            )
        )

    predictions.sort(
        key=lambda item: (
            0 if item.predicted_label == "resistant" else 1,
            -item.probability_resistant,
            item.antibiotic,
        )
    )
    resistant = [item for item in predictions if item.predicted_label == "resistant"]
    susceptible = [item for item in predictions if item.predicted_label == "susceptible"]

    return FastaScreenResponse(
        scope=scope,
        threshold=threshold,
        biosample=effective_biosample,
        hit_count=hit_count,
        resistant_antibiotics=resistant,
        susceptible_antibiotics=susceptible,
        all_predictions=predictions,
    )
