from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
LIFECYCLE_STATES = {"ingested", "processing", "completed", "failed"}


def _normalize_name(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z._-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "sample"


@dataclass(slots=True)
class IngestedFastaBatch:
    batch_id: str
    biosample: str
    stored_fasta_path: str
    manifest_path: str
    status_path: str
    status: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _results_dir(category: str, data_root: Path = DATA_ROOT) -> Path:
    output_dir = data_root / "results" / category
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def build_status_payload(
    *,
    batch_id: str,
    status: str,
    created_at: str | None = None,
    updated_at: str | None = None,
    sample_count: int | None = None,
    bronze_input_dir: str | None = None,
    scope: str | None = None,
    antibiotic: str | None = None,
    feature_ready_path: str | None = None,
    error_message: str | None = None,
    next_step: str | None = None,
) -> dict[str, object]:
    if status not in LIFECYCLE_STATES:
        raise ValueError(f"Unsupported lifecycle state: {status}")

    effective_created_at = created_at or _now_iso()
    payload: dict[str, object] = {
        "batch_id": batch_id,
        "status": status,
        "created_at": effective_created_at,
        "updated_at": updated_at or _now_iso(),
    }
    if sample_count is not None:
        payload["sample_count"] = sample_count
    if bronze_input_dir is not None:
        payload["bronze_input_dir"] = bronze_input_dir
    if scope is not None:
        payload["scope"] = scope
    if antibiotic is not None:
        payload["antibiotic"] = antibiotic
    if feature_ready_path is not None:
        payload["feature_ready_path"] = feature_ready_path
    if error_message is not None:
        payload["error_message"] = error_message
    if next_step is not None:
        payload["next_step"] = next_step
    return payload


def write_batch_status(
    batch_id: str,
    *,
    status: str,
    data_root: Path = DATA_ROOT,
    created_at: str | None = None,
    sample_count: int | None = None,
    bronze_input_dir: str | None = None,
    scope: str | None = None,
    antibiotic: str | None = None,
    feature_ready_path: str | None = None,
    error_message: str | None = None,
    next_step: str | None = None,
) -> dict[str, object]:
    existing_payload: dict[str, object] = {}
    status_path = _results_dir("status", data_root=data_root) / f"{batch_id}.json"
    if status_path.exists():
        existing_payload = json.loads(status_path.read_text(encoding="utf-8"))

    payload = build_status_payload(
        batch_id=batch_id,
        status=status,
        created_at=created_at or existing_payload.get("created_at"),
        sample_count=sample_count if sample_count is not None else existing_payload.get("sample_count"),
        bronze_input_dir=bronze_input_dir if bronze_input_dir is not None else existing_payload.get("bronze_input_dir"),
        scope=scope if scope is not None else existing_payload.get("scope"),
        antibiotic=antibiotic if antibiotic is not None else existing_payload.get("antibiotic"),
        feature_ready_path=feature_ready_path if feature_ready_path is not None else existing_payload.get("feature_ready_path"),
        error_message=error_message,
        next_step=next_step,
    )
    _write_json_atomic(status_path, payload)
    return payload


def ingest_single_fasta(
    fasta_bytes: bytes,
    fasta_name: str,
    data_root: Path = DATA_ROOT,
    batch_id: str | None = None,
    biosample: str | None = None,
) -> IngestedFastaBatch:
    if not fasta_bytes.strip():
        raise ValueError("Uploaded FASTA file is empty.")

    suffix = Path(fasta_name).suffix or ".fasta"
    effective_biosample = _normalize_name(biosample or Path(fasta_name).stem)
    effective_batch_id = batch_id or f"batch_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"

    bronze_dir = data_root / "bronze" / "fasta_batches" / effective_batch_id
    manifest_dir = _results_dir("manifests", data_root=data_root)
    bronze_dir.mkdir(parents=True, exist_ok=True)

    stored_fasta_path = bronze_dir / f"{effective_biosample}{suffix}"
    stored_fasta_path.write_bytes(fasta_bytes)

    manifest_path = manifest_dir / f"{effective_batch_id}.json"
    status_path = _results_dir("status", data_root=data_root) / f"{effective_batch_id}.json"
    ingested_at = _now_iso()

    manifest_payload = {
        "batch_id": effective_batch_id,
        "created_at": ingested_at,
        "updated_at": ingested_at,
        "sample_count": 1,
        "input_type": "single_fasta_upload",
        "bronze_input_dir": str(bronze_dir),
        "samples": [
            {
                "biosample": effective_biosample,
                "fasta_path": str(stored_fasta_path),
            }
        ],
    }
    _write_json_atomic(manifest_path, manifest_payload)
    write_batch_status(
        effective_batch_id,
        status="ingested",
        data_root=data_root,
        created_at=ingested_at,
        sample_count=1,
        bronze_input_dir=str(bronze_dir),
        next_step="Run scripts/process_fasta_batch.py for this batch.",
    )

    return IngestedFastaBatch(
        batch_id=effective_batch_id,
        biosample=effective_biosample,
        stored_fasta_path=str(stored_fasta_path),
        manifest_path=str(manifest_path),
        status_path=str(status_path),
        status="ingested",
    )


def _read_batch_metadata(batch_id: str, category: str, data_root: Path = DATA_ROOT) -> dict[str, object]:
    metadata_path = data_root / "results" / category / f"{batch_id}.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Batch {category[:-1]} not found for batch_id={batch_id!r}: {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def read_batch_status(batch_id: str, data_root: Path = DATA_ROOT) -> dict[str, object]:
    return _read_batch_metadata(batch_id=batch_id, category="status", data_root=data_root)


def read_batch_manifest(batch_id: str, data_root: Path = DATA_ROOT) -> dict[str, object]:
    return _read_batch_metadata(batch_id=batch_id, category="manifests", data_root=data_root)
