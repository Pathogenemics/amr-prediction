from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from amrfinder_features import AmrFinderFeatureBuilder
from serving_loader import ARTIFACT_ROOT, antibiotic_to_safe_name


FASTA_SUFFIXES = {".fa", ".faa", ".fasta", ".fna"}


@dataclass(slots=True)
class ProcessedFastaSample:
    biosample: str
    fasta_path: str
    amrfinder_output_path: str
    hit_count: int
    feature_count: int


@dataclass(slots=True)
class ProcessedFastaBatch:
    batch_id: str
    scope: str
    antibiotic: str
    feature_ready_path: str
    manifest_path: str
    status_path: str
    sample_count: int
    processed_at: str
    samples: list[ProcessedFastaSample]


def load_schema_columns(scope: str, antibiotic: str, artifact_root: Path = ARTIFACT_ROOT) -> list[str]:
    safe_name = antibiotic_to_safe_name(antibiotic)
    schema_path = artifact_root / "schemas" / scope / f"{safe_name}_features.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    return list(json.loads(schema_path.read_text(encoding="utf-8")))


def discover_fasta_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    fasta_files = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in FASTA_SUFFIXES
    )
    if not fasta_files:
        raise ValueError(f"No FASTA files found in {input_dir}")
    return fasta_files


def build_feature_ready_frame(
    input_dir: Path,
    scope: str,
    antibiotic: str,
    silver_output_dir: Path,
    artifact_root: Path = ARTIFACT_ROOT,
    feature_builder: AmrFinderFeatureBuilder | None = None,
) -> tuple[pd.DataFrame, list[ProcessedFastaSample]]:
    schema_columns = load_schema_columns(scope=scope, antibiotic=antibiotic, artifact_root=artifact_root)
    builder = feature_builder or AmrFinderFeatureBuilder()
    silver_output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, float | str]] = []
    samples: list[ProcessedFastaSample] = []

    for fasta_path in discover_fasta_files(input_dir):
        biosample = fasta_path.stem
        frame = builder.run_amrfinder(
            fasta_bytes=fasta_path.read_bytes(),
            fasta_name=fasta_path.name,
        )
        amrfinder_output_path = silver_output_dir / f"{biosample}.tsv"
        frame.to_csv(amrfinder_output_path, sep="\t", index=False)

        parsed = builder.build_from_amrfinder_frame(frame, schema_columns)
        row = {"BioSample": biosample}
        for column in schema_columns:
            row[column] = float(parsed.features.get(column, 0.0))
        rows.append(row)
        samples.append(
            ProcessedFastaSample(
                biosample=biosample,
                fasta_path=str(fasta_path),
                amrfinder_output_path=str(amrfinder_output_path),
                hit_count=parsed.hit_count,
                feature_count=len(parsed.features),
            )
        )

    feature_frame = pd.DataFrame(rows, columns=["BioSample", *schema_columns])
    return feature_frame, samples


def write_batch_outputs(
    batch_id: str,
    input_dir: Path,
    scope: str,
    antibiotic: str,
    feature_frame: pd.DataFrame,
    samples: list[ProcessedFastaSample],
    data_root: Path,
) -> ProcessedFastaBatch:
    safe_name = antibiotic_to_safe_name(antibiotic)
    gold_output_dir = data_root / "gold" / "feature_ready_batches" / batch_id
    manifest_dir = data_root / "results" / "manifests"
    status_dir = data_root / "results" / "status"

    gold_output_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    status_dir.mkdir(parents=True, exist_ok=True)

    feature_ready_path = gold_output_dir / f"{safe_name}__features.csv"
    manifest_path = manifest_dir / f"{batch_id}.json"
    status_path = status_dir / f"{batch_id}.json"
    processed_at = datetime.now(UTC).isoformat()

    feature_frame.to_csv(feature_ready_path, index=False)

    batch = ProcessedFastaBatch(
        batch_id=batch_id,
        scope=scope,
        antibiotic=antibiotic,
        feature_ready_path=str(feature_ready_path),
        manifest_path=str(manifest_path),
        status_path=str(status_path),
        sample_count=len(samples),
        processed_at=processed_at,
        samples=samples,
    )

    manifest_payload = {
        "batch_id": batch_id,
        "scope": scope,
        "antibiotic": antibiotic,
        "input_dir": str(input_dir),
        "feature_ready_path": str(feature_ready_path),
        "sample_count": len(samples),
        "processed_at": processed_at,
        "samples": [asdict(sample) for sample in samples],
    }
    status_payload = {
        "batch_id": batch_id,
        "status": "completed",
        "processed_at": processed_at,
        "scope": scope,
        "antibiotic": antibiotic,
        "sample_count": len(samples),
        "feature_ready_path": str(feature_ready_path),
    }

    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")
    status_path.write_text(json.dumps(status_payload, indent=2), encoding="utf-8")
    return batch


def process_fasta_batch(
    input_dir: Path,
    scope: str,
    antibiotic: str,
    batch_id: str,
    data_root: Path,
    artifact_root: Path = ARTIFACT_ROOT,
    feature_builder: AmrFinderFeatureBuilder | None = None,
) -> ProcessedFastaBatch:
    silver_output_dir = data_root / "silver" / "amrfinder_outputs" / batch_id
    feature_frame, samples = build_feature_ready_frame(
        input_dir=input_dir,
        scope=scope,
        antibiotic=antibiotic,
        silver_output_dir=silver_output_dir,
        artifact_root=artifact_root,
        feature_builder=feature_builder,
    )
    return write_batch_outputs(
        batch_id=batch_id,
        input_dir=input_dir,
        scope=scope,
        antibiotic=antibiotic,
        feature_frame=feature_frame,
        samples=samples,
        data_root=data_root,
    )
