from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fasta_batch_processor import process_fasta_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process a batch of FASTA files into feature-ready tables outside the FastAPI serving path."
    )
    parser.add_argument("--input-dir", required=True, help="Directory containing FASTA files for one batch.")
    parser.add_argument("--scope", default="all", help="Feature schema scope to use.")
    parser.add_argument("--antibiotic", required=True, help="Antibiotic schema to build features for.")
    parser.add_argument("--batch-id", help="Batch identifier. Defaults to the input directory name.")
    parser.add_argument(
        "--data-root",
        default=str(PROJECT_ROOT / "data"),
        help="Root staged-storage directory containing silver/gold/results subdirectories.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_dir = Path(args.input_dir).resolve()
    batch_id = args.batch_id or input_dir.name

    batch = process_fasta_batch(
        input_dir=input_dir,
        scope=args.scope,
        antibiotic=args.antibiotic,
        batch_id=batch_id,
        data_root=Path(args.data_root).resolve(),
    )

    print(json.dumps(
        {
            "batch_id": batch.batch_id,
            "scope": batch.scope,
            "antibiotic": batch.antibiotic,
            "sample_count": batch.sample_count,
            "feature_ready_path": batch.feature_ready_path,
            "manifest_path": batch.manifest_path,
            "status_path": batch.status_path,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
