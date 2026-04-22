from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from serving_loader import ModelBundle
from serving_schemas import PredictSingleResponse
from serving_service import predict_single_from_fasta_bytes


class DummyModel:
    def predict_proba(self, features):  # noqa: ANN001
        class Probabilities:
            def __getitem__(self, key):
                if key == (slice(None, None, None), 1):
                    return [0.8]
                raise KeyError(key)

        return Probabilities()


class DummyRegistry:
    def get_bundle(self, scope: str, antibiotic: str) -> ModelBundle:
        return ModelBundle(
            scope=scope,
            antibiotic=antibiotic,
            safe_name=antibiotic,
            feature_columns=["gene_a_lineage_match"],
            metadata={},
            model=DummyModel(),
        )


class DummyFeatureBuilder:
    def build_from_fasta_bytes(self, fasta_bytes: bytes, schema_columns: list[str], fasta_name: str = "sample.fasta"):
        class ParsedResult:
            features = {schema_columns[0]: 1.0}
            hit_count = 1

        return ParsedResult()


class PredictSingleFromFastaBytesTest(unittest.TestCase):
    def test_returns_single_response_without_rows_wrapper(self) -> None:
        response = predict_single_from_fasta_bytes(
            DummyRegistry(),
            scope="all",
            antibiotic="ampicillin",
            fasta_bytes=b">contig_1\nATGC\n",
            threshold=0.5,
            biosample="demo_001",
            fasta_name="demo_001.fna",
            feature_builder=DummyFeatureBuilder(),
        )

        self.assertIsInstance(response, PredictSingleResponse)
        self.assertEqual(response.scope, "all")
        self.assertEqual(response.antibiotic, "ampicillin")
        self.assertEqual(response.feature_count, 1)
        self.assertEqual(response.biosample, "demo_001")
        self.assertEqual(response.predicted_label, "resistant")
        self.assertAlmostEqual(response.probability_resistant, 0.8)


if __name__ == "__main__":
    unittest.main()
