from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


def normalize_feature_base(name: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip().lower()).strip("_")
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def _pick_column(columns: list[str], candidates: list[str]) -> str | None:
    lowered = {column.casefold(): column for column in columns}
    for candidate in candidates:
        matched = lowered.get(candidate.casefold())
        if matched is not None:
            return matched
    return None


@dataclass(slots=True)
class ParsedAmrFinderResult:
    features: dict[str, float]
    hit_count: int


class AmrFinderFeatureBuilder:
    def __init__(self, executable: str = "amrfinder") -> None:
        self.executable = executable

    def build_from_fasta_bytes(
        self,
        fasta_bytes: bytes,
        schema_columns: list[str],
        fasta_name: str = "sample.fasta",
    ) -> ParsedAmrFinderResult:
        if not fasta_bytes.strip():
            raise ValueError("Uploaded FASTA file is empty.")

        executable_path = shutil.which(self.executable)
        if executable_path is None:
            raise RuntimeError(
                "amrfinder executable was not found on PATH. Install AMRFinderPlus and make sure `amrfinder` is available."
            )

        suffix = Path(fasta_name).suffix or ".fasta"
        with tempfile.TemporaryDirectory(prefix="amrfinder_") as temp_dir:
            temp_root = Path(temp_dir)
            fasta_path = temp_root / f"input{suffix}"
            output_path = temp_root / "amrfinder.tsv"
            fasta_path.write_bytes(fasta_bytes)

            command = [
                executable_path,
                "-n",
                str(fasta_path),
                "-o",
                str(output_path),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                stderr = completed.stderr.strip() or completed.stdout.strip() or "Unknown amrfinder error."
                raise RuntimeError(f"amrfinder failed for {fasta_name}: {stderr}")

            if not output_path.exists():
                raise RuntimeError("amrfinder did not produce an output table.")

            frame = pd.read_csv(output_path, sep="\t", comment="#")
            return self.build_from_amrfinder_frame(frame, schema_columns)

    def build_from_amrfinder_frame(
        self,
        frame: pd.DataFrame,
        schema_columns: list[str],
    ) -> ParsedAmrFinderResult:
        if frame.empty:
            return ParsedAmrFinderResult(features={}, hit_count=0)

        columns = frame.columns.tolist()
        symbol_column = _pick_column(
            columns,
            [
                "Element symbol",
                "Gene symbol",
                "Gene symbol(s)",
                "Sequence name",
                "Name",
            ],
        )
        if symbol_column is None:
            raise ValueError("AMRFinder output is missing a gene symbol column.")

        coverage_column = _pick_column(
            columns,
            [
                "% Coverage of reference",
                "% Coverage of reference sequence",
            ],
        )
        identity_column = _pick_column(
            columns,
            [
                "% Identity to reference",
                "% Identity to reference sequence",
            ],
        )

        features: dict[str, float] = {}
        hit_count = 0
        schema_set = set(schema_columns)

        for _, row in frame.iterrows():
            symbol = row.get(symbol_column)
            if pd.isna(symbol):
                continue

            base = normalize_feature_base(str(symbol))
            if not base:
                continue

            hit_count += 1

            lineage_match_column = f"{base}_lineage_match"
            if lineage_match_column in schema_set:
                features[lineage_match_column] = 1.0

            if coverage_column is not None:
                coverage_value = pd.to_numeric(pd.Series([row.get(coverage_column)]), errors="coerce").iloc[0]
                coverage_feature = f"{base}_coverage"
                if coverage_feature in schema_set and pd.notna(coverage_value):
                    features[coverage_feature] = max(float(coverage_value), features.get(coverage_feature, 0.0))

            if identity_column is not None:
                identity_value = pd.to_numeric(pd.Series([row.get(identity_column)]), errors="coerce").iloc[0]
                identity_feature = f"{base}_identity"
                if identity_feature in schema_set and pd.notna(identity_value):
                    features[identity_feature] = max(float(identity_value), features.get(identity_feature, 0.0))

        return ParsedAmrFinderResult(features=features, hit_count=hit_count)
