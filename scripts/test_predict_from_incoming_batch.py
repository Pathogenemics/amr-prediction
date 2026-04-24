from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib import error, request

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts"
BRONZE_CSV_BATCH_ROOT = PROJECT_ROOT / "data" / "bronze" / "incoming_csv_batches"
LEGACY_INCOMING_ROOT = PROJECT_ROOT / "data" / "incoming"


def antibiotic_to_safe_name(antibiotic: str) -> str:
    return antibiotic.replace("/", "_").replace(" ", "_")


def normalize_feature_base(name: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip().lower()).strip("_")
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def load_schema(scope: str, antibiotic: str) -> list[str]:
    safe_name = antibiotic_to_safe_name(antibiotic)
    schema_path = ARTIFACT_ROOT / "schemas" / scope / f"{safe_name}_features.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def resolve_batch_dir(batch_name: str, batch_dir: str | None = None) -> Path:
    if batch_dir:
        resolved = Path(batch_dir).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Batch directory not found: {resolved}")
        return resolved

    canonical_dir = BRONZE_CSV_BATCH_ROOT / batch_name
    if canonical_dir.exists():
        return canonical_dir

    legacy_dir = LEGACY_INCOMING_ROOT / batch_name
    if legacy_dir.exists():
        return legacy_dir

    raise FileNotFoundError(
        "Batch directory not found. "
        f"Tried canonical path {canonical_dir} and legacy path {legacy_dir}."
    )


def build_rows_from_incoming_batch(
    batch_dir: Path,
    scope: str,
    antibiotic: str,
    limit: int,
) -> tuple[list[dict[str, object]], pd.DataFrame]:
    genotype_path = batch_dir / "genotype_incoming.tsv"
    phenotype_path = batch_dir / "phenotype_incoming.tsv"

    if not genotype_path.exists():
        raise FileNotFoundError(f"Missing genotype input: {genotype_path}")
    if not phenotype_path.exists():
        raise FileNotFoundError(f"Missing phenotype input: {phenotype_path}")

    schema_columns = load_schema(scope, antibiotic)

    genotype = pd.read_csv(genotype_path, sep="\t")
    phenotype = pd.read_csv(phenotype_path, sep="\t")

    phenotype["Antibiotic"] = phenotype["Antibiotic"].astype(str).str.strip().str.lower()
    phenotype["Resistance phenotype"] = phenotype["Resistance phenotype"].astype(str).str.strip().str.lower()

    target_antibiotic = antibiotic.strip().lower()
    phenotype_subset = phenotype[phenotype["Antibiotic"] == target_antibiotic].copy()
    if phenotype_subset.empty:
        raise ValueError(f"No phenotype rows found for antibiotic={antibiotic!r} in {phenotype_path}")

    biosamples = phenotype_subset["BioSample"].dropna().astype(str).drop_duplicates().tolist()
    if limit > 0:
        biosamples = biosamples[:limit]

    genotype_subset = genotype[genotype["BioSample"].astype(str).isin(biosamples)].copy()
    genotype_subset["feature_base"] = genotype_subset["Element symbol"].map(normalize_feature_base)

    grouped = {
        biosample: frame.copy()
        for biosample, frame in genotype_subset.groupby("BioSample", dropna=False)
    }

    rows: list[dict[str, object]] = []
    for biosample in biosamples:
        sample_features: dict[str, float] = {}
        sample_genes = grouped.get(biosample)

        if sample_genes is not None:
            for _, gene_row in sample_genes.iterrows():
                base = str(gene_row["feature_base"])
                coverage_column = f"{base}_coverage"
                identity_column = f"{base}_identity"
                lineage_match_column = f"{base}_lineage_match"

                if coverage_column in schema_columns:
                    sample_features[coverage_column] = float(gene_row.get("% Coverage of reference", 0.0) or 0.0)
                if identity_column in schema_columns:
                    sample_features[identity_column] = float(gene_row.get("% Identity to reference", 0.0) or 0.0)
                if lineage_match_column in schema_columns:
                    sample_features[lineage_match_column] = 1.0

        rows.append(
            {
                "biosample": biosample,
                "features": sample_features,
            }
        )

    truth_subset = phenotype_subset[phenotype_subset["BioSample"].astype(str).isin(biosamples)].copy()
    truth_subset["BioSample"] = truth_subset["BioSample"].astype(str)
    return rows, truth_subset[["BioSample", "Resistance phenotype", "MIC (mg/L)"]].drop_duplicates()


def post_predict_request(base_url: str, payload: dict[str, object]) -> dict[str, object]:
    endpoint = base_url.rstrip("/") + "/predict"
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Request failed with status {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the AMR /predict endpoint using a saved CSV/genotype batch from staged storage."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL for the FastAPI backend.")
    parser.add_argument("--scope", default="all", help="Model scope to use.")
    parser.add_argument("--antibiotic", default="amoxicillin-clavulanic acid", help="Antibiotic model to test.")
    parser.add_argument(
        "--batch-name",
        default="batch_001",
        help="Batch folder name under data/bronze/incoming_csv_batches/ or legacy data/incoming/.",
    )
    parser.add_argument(
        "--batch-dir",
        default="",
        help="Optional explicit batch directory. Overrides --batch-name lookup.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of biosamples to include.")
    args = parser.parse_args()

    batch_dir = resolve_batch_dir(batch_name=args.batch_name, batch_dir=args.batch_dir or None)
    rows, truth = build_rows_from_incoming_batch(
        batch_dir=batch_dir,
        scope=args.scope,
        antibiotic=args.antibiotic,
        limit=args.limit,
    )

    payload = {
        "scope": args.scope,
        "antibiotic": args.antibiotic,
        "threshold": 0.5,
        "rows": rows,
    }

    print("Sending request with", len(rows), "rows")
    response = post_predict_request(args.base_url, payload)
    print(json.dumps(response, indent=2))

    prediction_frame = pd.DataFrame(response.get("rows", []))
    if not prediction_frame.empty:
        merged = prediction_frame.merge(truth, how="left", left_on="biosample", right_on="BioSample")
        merged = merged.drop(columns=["BioSample"], errors="ignore")
        print("\nPrediction vs ground truth:")
        print(merged.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
