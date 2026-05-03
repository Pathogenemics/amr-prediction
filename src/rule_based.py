from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from prepared_inputs import PreparedAntibioticInput


@dataclass(slots=True)
class RuleBasedResult:
    metrics: pd.DataFrame


def safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate_prepared_rule_baseline(
    prepared_inputs: list[PreparedAntibioticInput],
    scope_name: str | None = None,
) -> RuleBasedResult:
    metric_rows: list[dict[str, float | int | str]] = []

    for prepared_input in prepared_inputs:
        frame = prepared_input.frame.copy()
        feature_columns = [
            column
            for column in frame.columns
            if column not in ["BioSample", "Antibiotic", "Resistance phenotype", "y"]
        ]
        antibiotic = prepared_input.antibiotic
        y_true = frame["y"].astype(int)

        if feature_columns:
            feature_sum = frame[feature_columns].sum(axis=1)
            y_pred = (feature_sum > 0).astype(int)
            zero_hit_rows = int((feature_sum == 0).sum())
        else:
            y_pred = pd.Series(0, index=frame.index, dtype="int64")
            zero_hit_rows = int(len(frame))

        true_positive = int(((y_true == 1) & (y_pred == 1)).sum())
        true_negative = int(((y_true == 0) & (y_pred == 0)).sum())
        false_positive = int(((y_true == 0) & (y_pred == 1)).sum())
        false_negative = int(((y_true == 1) & (y_pred == 0)).sum())

        specificity = safe_divide(true_negative, true_negative + false_positive)
        accuracy = safe_divide(true_positive + true_negative, len(frame))
        precision = safe_divide(true_positive, true_positive + false_positive)
        recall = safe_divide(true_positive, true_positive + false_negative)

        metric_rows.append(
            {
                "scope": scope_name or "",
                "method_family": "rule_based",
                "rule_scope": scope_name or "",
                "Antibiotic": antibiotic,
                "n_samples": int(len(frame)),
                "n_susceptible": int((frame["Resistance phenotype"] == "susceptible").sum()),
                "n_resistant": int((frame["Resistance phenotype"] == "resistant").sum()),
                "n_positive": int(y_true.sum()),
                "n_negative": int(len(y_true) - int(y_true.sum())),
                "positive_label": "resistant",
                "positive_fraction": float(y_true.mean()) if len(y_true) else 0.0,
                "feature_count": int(len(feature_columns)),
                "zero_hit_rows": zero_hit_rows,
                "predicted_resistant": int(y_pred.sum()),
                "predicted_susceptible": int(len(y_pred) - int(y_pred.sum())),
                "accuracy": float(accuracy),
                "precision": float(precision),
                "recall": float(recall),
                "specificity": float(specificity),
                "true_positive": true_positive,
                "true_negative": true_negative,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "status": "evaluated",
            }
        )

    metrics = pd.DataFrame(metric_rows)
    if not metrics.empty:
        metrics = metrics.sort_values(["scope", "Antibiotic"], ascending=[True, True]).reset_index(drop=True)

    return RuleBasedResult(metrics=metrics)
