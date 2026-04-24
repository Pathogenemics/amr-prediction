from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fasta_batch_processor import process_fasta_batch
from serving_service import predict_from_csv_bytes


class DummyFeatureBuilder:
    def run_amrfinder(self, fasta_bytes: bytes, fasta_name: str = "sample.fasta") -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Gene symbol": "gene_a",
                    "% Coverage of reference": 100.0,
                    "% Identity to reference": 99.5,
                }
            ]
        )

    def build_from_amrfinder_frame(self, frame: pd.DataFrame, schema_columns: list[str]):  # noqa: ANN001
        class ParsedResult:
            hit_count = len(frame)
            features = {
                column: value
                for column, value in {
                    "gene_a_lineage_match": 1.0,
                    "gene_a_coverage": 100.0,
                    "gene_a_identity": 99.5,
                }.items()
                if column in schema_columns
            }

        return ParsedResult()


class DummyModel:
    def predict_proba(self, features):  # noqa: ANN001
        probabilities = [0.8 for _ in range(len(features))]

        class Probabilities:
            def __getitem__(self, key):
                if key == (slice(None, None, None), 1):
                    return probabilities
                raise KeyError(key)

        return Probabilities()


@dataclass(slots=True)
class DummyBundle:
    scope: str
    antibiotic: str
    safe_name: str
    feature_columns: list[str]
    metadata: dict[str, object]
    model: DummyModel


class DummyRegistry:
    def __init__(self, bundle: DummyBundle) -> None:
        self.bundle = bundle

    def get_bundle(self, scope: str, antibiotic: str) -> DummyBundle:
        if self.bundle.scope != scope or self.bundle.antibiotic != antibiotic:
            raise KeyError(f"Missing bundle for scope={scope!r}, antibiotic={antibiotic!r}")
        return self.bundle


class ProcessFastaBatchTest(unittest.TestCase):
    def _build_processed_batch(self, temp_root: Path):
        input_dir = temp_root / "incoming" / "batch_001"
        input_dir.mkdir(parents=True)
        (input_dir / "demo_001.fasta").write_text(">contig_1\nATGC\n", encoding="utf-8")

        artifact_root = temp_root / "artifacts"
        schema_dir = artifact_root / "schemas" / "all"
        schema_dir.mkdir(parents=True)
        schema_columns = [
            "gene_a_lineage_match",
            "gene_a_coverage",
            "gene_a_identity",
        ]
        (schema_dir / "ampicillin_features.json").write_text(
            json.dumps(schema_columns),
            encoding="utf-8",
        )

        data_root = temp_root / "data"
        batch = process_fasta_batch(
            input_dir=input_dir,
            scope="all",
            antibiotic="ampicillin",
            batch_id="batch_001",
            data_root=data_root,
            artifact_root=artifact_root,
            feature_builder=DummyFeatureBuilder(),
        )
        return batch, schema_columns

    def test_writes_feature_ready_outputs_outside_serving_layer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            batch, _ = self._build_processed_batch(temp_root)

            feature_frame = pd.read_csv(batch.feature_ready_path)
            self.assertEqual(batch.sample_count, 1)
            self.assertEqual(feature_frame.loc[0, "BioSample"], "demo_001")
            self.assertEqual(feature_frame.loc[0, "gene_a_lineage_match"], 1.0)
            self.assertEqual(feature_frame.loc[0, "gene_a_coverage"], 100.0)
            self.assertEqual(feature_frame.loc[0, "gene_a_identity"], 99.5)

            manifest = json.loads(Path(batch.manifest_path).read_text(encoding="utf-8"))
            status = json.loads(Path(batch.status_path).read_text(encoding="utf-8"))

            self.assertEqual(manifest["batch_id"], "batch_001")
            self.assertEqual(manifest["sample_count"], 1)
            self.assertEqual(status["status"], "completed")
            self.assertTrue(Path(manifest["samples"][0]["amrfinder_output_path"]).exists())

    def test_serving_consumes_feature_ready_csv_instead_of_fasta(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            batch, schema_columns = self._build_processed_batch(temp_root)

            registry = DummyRegistry(
                DummyBundle(
                    scope="all",
                    antibiotic="ampicillin",
                    safe_name="ampicillin",
                    feature_columns=schema_columns,
                    metadata={},
                    model=DummyModel(),
                )
            )

            response = predict_from_csv_bytes(
                registry=registry,
                scope="all",
                antibiotic="ampicillin",
                file_bytes=Path(batch.feature_ready_path).read_bytes(),
                threshold=0.5,
            )

            self.assertEqual(response.scope, "all")
            self.assertEqual(response.antibiotic, "ampicillin")
            self.assertEqual(response.row_count, 1)
            self.assertEqual(response.rows[0]["biosample"], "demo_001")
            self.assertEqual(response.rows[0]["predicted_label"], "resistant")
            self.assertAlmostEqual(response.rows[0]["probability_resistant"], 0.8)


if __name__ == "__main__":
    unittest.main()
