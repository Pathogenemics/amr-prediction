from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from prepared_inputs import PreparedAntibioticInput
from rule_based import evaluate_prepared_rule_baseline


class EvaluatePreparedRuleBaselineTest(unittest.TestCase):
    def test_predicts_resistant_when_any_connected_feature_is_present(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "BioSample": "SAMN1",
                    "Antibiotic": "ampicillin",
                    "Resistance phenotype": "resistant",
                    "y": 1,
                    "bla_tem_1_coverage": 100.0,
                    "bla_tem_1_identity": 99.2,
                },
                {
                    "BioSample": "SAMN2",
                    "Antibiotic": "ampicillin",
                    "Resistance phenotype": "susceptible",
                    "y": 0,
                    "bla_tem_1_coverage": 0.0,
                    "bla_tem_1_identity": 0.0,
                },
                {
                    "BioSample": "SAMN3",
                    "Antibiotic": "ampicillin",
                    "Resistance phenotype": "susceptible",
                    "y": 0,
                    "bla_tem_1_coverage": 50.0,
                    "bla_tem_1_identity": 0.0,
                },
            ]
        )

        result = evaluate_prepared_rule_baseline(
            [PreparedAntibioticInput(antibiotic="ampicillin", table_path=Path("demo.csv"), frame=frame)],
            scope_name="strict",
        )

        metrics = result.metrics.iloc[0]
        self.assertEqual(metrics["predicted_resistant"], 2)
        self.assertEqual(metrics["predicted_susceptible"], 1)
        self.assertEqual(metrics["true_positive"], 1)
        self.assertEqual(metrics["false_positive"], 1)
        self.assertEqual(metrics["false_negative"], 0)
        self.assertEqual(metrics["zero_hit_rows"], 1)
        self.assertAlmostEqual(metrics["recall"], 1.0)
        self.assertAlmostEqual(metrics["precision"], 0.5)
        self.assertAlmostEqual(metrics["specificity"], 0.5)

    def test_handles_tables_without_feature_columns(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "BioSample": "SAMN1",
                    "Antibiotic": "ciprofloxacin",
                    "Resistance phenotype": "resistant",
                    "y": 1,
                },
                {
                    "BioSample": "SAMN2",
                    "Antibiotic": "ciprofloxacin",
                    "Resistance phenotype": "susceptible",
                    "y": 0,
                },
            ]
        )

        result = evaluate_prepared_rule_baseline(
            [PreparedAntibioticInput(antibiotic="ciprofloxacin", table_path=Path("demo.csv"), frame=frame)],
            scope_name="broad",
        )

        metrics = result.metrics.iloc[0]
        self.assertEqual(metrics["predicted_resistant"], 0)
        self.assertEqual(metrics["predicted_susceptible"], 2)
        self.assertEqual(metrics["zero_hit_rows"], 2)
        self.assertAlmostEqual(metrics["recall"], 0.0)
        self.assertAlmostEqual(metrics["specificity"], 1.0)


if __name__ == "__main__":
    unittest.main()
