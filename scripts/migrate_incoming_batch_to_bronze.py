from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_INCOMING_ROOT = PROJECT_ROOT / "data" / "incoming"
BRONZE_CSV_BATCH_ROOT = PROJECT_ROOT / "data" / "bronze" / "incoming_csv_batches"


def migrate_batch(batch_name: str, source_dir: Path | None = None) -> Path:
    source = source_dir or (LEGACY_INCOMING_ROOT / batch_name)
    if not source.exists():
        raise FileNotFoundError(f"Legacy batch directory not found: {source}")

    destination = BRONZE_CSV_BATCH_ROOT / batch_name
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        target = destination / item.name
        if item.is_file():
            shutil.copy2(item, target)
        elif item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)

    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy a legacy data/incoming batch into the canonical bronze CSV batch layout."
    )
    parser.add_argument("--batch-name", default="batch_001", help="Batch directory name to migrate.")
    parser.add_argument("--source-dir", default="", help="Optional explicit legacy source directory.")
    args = parser.parse_args()

    destination = migrate_batch(
        batch_name=args.batch_name,
        source_dir=Path(args.source_dir).expanduser().resolve() if args.source_dir else None,
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
