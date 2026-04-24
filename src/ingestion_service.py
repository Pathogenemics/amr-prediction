from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


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
    manifest_dir = data_root / "results" / "manifests"
    status_dir = data_root / "results" / "status"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    status_dir.mkdir(parents=True, exist_ok=True)

    stored_fasta_path = bronze_dir / f"{effective_biosample}{suffix}"
    stored_fasta_path.write_bytes(fasta_bytes)

    manifest_path = manifest_dir / f"{effective_batch_id}.json"
    status_path = status_dir / f"{effective_batch_id}.json"
    ingested_at = datetime.now(UTC).isoformat()

    manifest_payload = {
        "batch_id": effective_batch_id,
        "ingested_at": ingested_at,
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
    status_payload = {
        "batch_id": effective_batch_id,
        "status": "ingested",
        "ingested_at": ingested_at,
        "sample_count": 1,
        "next_step": "Run scripts/process_fasta_batch.py for this batch.",
        "bronze_input_dir": str(bronze_dir),
    }

    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")
    status_path.write_text(json.dumps(status_payload, indent=2), encoding="utf-8")

    return IngestedFastaBatch(
        batch_id=effective_batch_id,
        biosample=effective_biosample,
        stored_fasta_path=str(stored_fasta_path),
        manifest_path=str(manifest_path),
        status_path=str(status_path),
        status="ingested",
    )
