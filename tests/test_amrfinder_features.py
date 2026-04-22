from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from amrfinder_features import AmrFinderFeatureBuilder, normalize_feature_base


class NormalizeFeatureBaseTest(unittest.TestCase):
    def test_normalizes_amrfinder_symbols(self) -> None:
        self.assertEqual(normalize_feature_base("aac(3)-VIa"), "aac_3_via")
        self.assertEqual(normalize_feature_base("acrB_R717Q"), "acrb_r717q")


class AmrFinderFeatureBuilderTest(unittest.TestCase):
    def test_maps_amrfinder_frame_into_schema_features(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "Element symbol": "aac(3)-VIa",
                    "% Coverage of reference": 100.0,
                    "% Identity to reference": 99.2,
                },
                {
                    "Element symbol": "aac(3)-VIa",
                    "% Coverage of reference": 82.0,
                    "% Identity to reference": 97.0,
                },
                {
                    "Element symbol": "tet(A)",
                    "% Coverage of reference": 91.0,
                    "% Identity to reference": 96.5,
                },
            ]
        )
        schema_columns = [
            "aac_3_via_coverage",
            "aac_3_via_identity",
            "aac_3_via_lineage_match",
            "tet_a_coverage",
            "tet_a_identity",
            "tet_a_lineage_match",
        ]

        parsed = AmrFinderFeatureBuilder().build_from_amrfinder_frame(frame, schema_columns)

        self.assertEqual(parsed.hit_count, 3)
        self.assertEqual(parsed.features["aac_3_via_coverage"], 100.0)
        self.assertEqual(parsed.features["aac_3_via_identity"], 99.2)
        self.assertEqual(parsed.features["aac_3_via_lineage_match"], 1.0)
        self.assertEqual(parsed.features["tet_a_coverage"], 91.0)
        self.assertEqual(parsed.features["tet_a_identity"], 96.5)
        self.assertEqual(parsed.features["tet_a_lineage_match"], 1.0)

    def test_accepts_alternate_amrfinder_column_names(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "Gene symbol": "blaTEM-1",
                    "% Coverage of reference sequence": 100.0,
                    "% Identity to reference sequence": 100.0,
                }
            ]
        )

        parsed = AmrFinderFeatureBuilder().build_from_amrfinder_frame(
            frame,
            ["blatem_1_coverage", "blatem_1_identity", "blatem_1_lineage_match"],
        )

        self.assertEqual(
            parsed.features,
            {
                "blatem_1_coverage": 100.0,
                "blatem_1_identity": 100.0,
                "blatem_1_lineage_match": 1.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
