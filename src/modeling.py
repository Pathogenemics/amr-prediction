from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.metrics import accuracy_score, average_precision_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from tqdm.auto import tqdm
from xgboost import XGBClassifier

from config import PipelineConfig
from prepared_inputs import PreparedAntibioticInput


@dataclass(slots=True)
class ModelingResult:
    metrics: pd.DataFrame
    top_features: pd.DataFrame


TOP_FEATURE_COLUMNS = [
    "scope",
    "Antibiotic",
    "rank",
    "feature",
    "feature_base",
    "feature_type",
    "importance",
]


def train_models(
    phenotype: pd.DataFrame,
    features: pd.DataFrame,
    config: PipelineConfig,
) -> ModelingResult:
    metric_rows: list[dict[str, float | int | str]] = []
    feature_rows: list[dict[str, float | int | str]] = []
    antibiotics = sorted(phenotype["Antibiotic"].unique())
    antibiotic_iterator = tqdm(
        antibiotics,
        desc="Antibiotics",
        unit="drug",
        disable=not config.show_progress,
    )

    for antibiotic in antibiotic_iterator:
        label_frame = phenotype[phenotype["Antibiotic"] == antibiotic][["BioSample", "label"]].copy()
        X = features.reindex(label_frame["BioSample"]).reset_index(drop=True)
        y = label_frame["label"].astype(int).reset_index(drop=True)

        positive_count = int(y.sum())
        negative_count = int(len(y) - positive_count)
        if min(positive_count, negative_count) < max(config.cv_folds, config.min_class_count):
            if config.show_progress:
                antibiotic_iterator.set_postfix_str(f"skip {antibiotic}")
            continue

        probabilities = pd.Series(index=range(len(label_frame)), dtype="float64")
        predictions = pd.Series(index=range(len(label_frame)), dtype="int64")
        fold_scores: list[float] = []

        splitter = StratifiedKFold(
            n_splits=config.cv_folds,
            shuffle=True,
            random_state=config.random_state,
        )

        fold_iterator = splitter.split(X, y)
        if config.show_fold_progress:
            fold_iterator = tqdm(
                fold_iterator,
                total=config.cv_folds,
                desc=f"Folds: {antibiotic}",
                unit="fold",
                leave=False,
            )

        for train_idx, test_idx in fold_iterator:
            X_train = X.iloc[train_idx]
            X_test = X.iloc[test_idx]
            y_train = y.iloc[train_idx]
            y_test = y.iloc[test_idx]

            model = build_model(config, y_train)
            model.fit(X_train, y_train)

            fold_probabilities = pd.Series(model.predict_proba(X_test)[:, 1], index=X_test.index)
            fold_predictions = (fold_probabilities >= 0.5).astype(int)

            probabilities.iloc[test_idx] = fold_probabilities.to_numpy()
            predictions.iloc[test_idx] = fold_predictions.to_numpy()
            fold_scores.append(float(roc_auc_score(y_test, fold_probabilities)))

        average_precision = float(average_precision_score(y, probabilities))
        precision = float(precision_score(y, predictions, zero_division=0))
        recall = float(recall_score(y, predictions, zero_division=0))
        roc_auc = float(roc_auc_score(y, probabilities))

        metric_rows.append(
            {
                "Antibiotic": antibiotic,
                "n_samples": int(len(y)),
                "n_resistant": positive_count,
                "n_susceptible": negative_count,
                "resistant_fraction": positive_count / len(y),
                "roc_auc": roc_auc,
                "average_precision": average_precision,
                "precision": precision,
                "recall": recall,
                "mean_fold_roc_auc": sum(fold_scores) / len(fold_scores),
            }
        )
        if config.show_progress:
            antibiotic_iterator.set_postfix(
                samples=len(y),
                resistant=positive_count,
                roc_auc=f"{roc_auc:.3f}",
            )

        fitted_model = build_model(config, y)
        fitted_model.fit(X, y)
        importances = pd.Series(fitted_model.feature_importances_, index=X.columns, dtype="float64")
        importances = importances[importances > 0].sort_values(ascending=False).head(config.top_feature_count)

        for rank, (feature_name, importance) in enumerate(importances.items(), start=1):
            feature_rows.append(
                {
                    "Antibiotic": antibiotic,
                    "rank": rank,
                    "feature": feature_name,
                    "importance": float(importance),
                }
            )

    metrics = pd.DataFrame(metric_rows)
    if not metrics.empty:
        metrics = metrics.sort_values("roc_auc", ascending=False).reset_index(drop=True)

    top_features = pd.DataFrame(feature_rows)
    if not top_features.empty:
        top_features = top_features.sort_values(["Antibiotic", "rank"]).reset_index(drop=True)

    return ModelingResult(metrics=metrics, top_features=top_features)


def build_model(config: PipelineConfig, y: pd.Series) -> XGBClassifier:
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    scale_pos_weight = negatives / positives if positives else 1.0

    return XGBClassifier(
        n_estimators=config.n_estimators,
        learning_rate=config.learning_rate,
        max_depth=config.max_depth,
        subsample=config.subsample,
        colsample_bytree=config.colsample_bytree,
        random_state=config.random_state,
        eval_metric="logloss",
        scale_pos_weight=scale_pos_weight,
        n_jobs=1,
    )


def split_feature_column(feature_name: str) -> tuple[str, str]:
    if feature_name.endswith("_coverage"):
        return feature_name[: -len("_coverage")], "coverage"
    if feature_name.endswith("_identity"):
        return feature_name[: -len("_identity")], "identity"
    if feature_name.endswith("_lineage_match"):
        return feature_name[: -len("_lineage_match")], "lineage_match"
    return feature_name, "other"


def train_prepared_models(
    prepared_inputs: list[PreparedAntibioticInput],
    config: PipelineConfig,
    scope_name: str | None = None,
) -> ModelingResult:
    metric_rows: list[dict[str, float | int | str]] = []
    feature_rows: list[dict[str, float | int | str]] = []

    iterator = tqdm(
        prepared_inputs,
        desc=f"Antibiotics ({scope_name})" if scope_name else "Antibiotics",
        unit="drug",
        disable=not config.show_progress,
    )

    for prepared_input in iterator:
        frame = prepared_input.frame.copy()
        feature_columns = [
            column
            for column in frame.columns
            if column not in ["BioSample", "Antibiotic", "Resistance phenotype", "y"]
        ]
        antibiotic = prepared_input.antibiotic
        X = frame[feature_columns].copy()
        y = frame["y"].astype(int).reset_index(drop=True)

        if not feature_columns:
            metric_rows.append(
                {
                    "scope": scope_name or "",
                    "Antibiotic": antibiotic,
                    "n_samples": int(len(frame)),
                    "n_susceptible": int((frame["Resistance phenotype"] == "susceptible").sum()),
                    "n_resistant": int((frame["Resistance phenotype"] == "resistant").sum()),
                    "n_positive": int(y.sum()),
                    "n_negative": int(len(y) - int(y.sum())),
                    "positive_label": "resistant",
                    "positive_fraction": float(y.mean()) if len(y) else 0.0,
                    "feature_count": 0,
                    "zero_feature_rows": int(len(frame)),
                    "roc_auc": pd.NA,
                    "average_precision": pd.NA,
                    "accuracy": pd.NA,
                    "precision": pd.NA,
                    "recall": pd.NA,
                    "mean_fold_roc_auc": pd.NA,
                    "status": "skipped_no_features",
                }
            )
            if config.show_progress:
                iterator.set_postfix_str(f"skip {antibiotic}: no features")
            continue

        positive_count = int(y.sum())
        negative_count = int(len(y) - positive_count)
        if min(positive_count, negative_count) < max(config.cv_folds, 2):
            metric_rows.append(
                {
                    "scope": scope_name or "",
                    "Antibiotic": antibiotic,
                    "n_samples": int(len(frame)),
                    "n_susceptible": int((frame["Resistance phenotype"] == "susceptible").sum()),
                    "n_resistant": int((frame["Resistance phenotype"] == "resistant").sum()),
                    "n_positive": positive_count,
                    "n_negative": negative_count,
                    "positive_label": "resistant",
                    "positive_fraction": positive_count / len(frame),
                    "feature_count": int(len(feature_columns)),
                    "zero_feature_rows": int((X.sum(axis=1) == 0).sum()),
                    "roc_auc": pd.NA,
                    "average_precision": pd.NA,
                    "accuracy": pd.NA,
                    "precision": pd.NA,
                    "recall": pd.NA,
                    "mean_fold_roc_auc": pd.NA,
                    "status": "skipped_class_too_small",
                }
            )
            if config.show_progress:
                iterator.set_postfix_str(f"skip {antibiotic}")
            continue

        probabilities = pd.Series(index=range(len(frame)), dtype="float64")
        predictions = pd.Series(index=range(len(frame)), dtype="int64")
        fold_scores: list[float] = []

        splitter = StratifiedKFold(
            n_splits=config.cv_folds,
            shuffle=True,
            random_state=config.random_state,
        )

        fold_iterator = splitter.split(X, y)
        if config.show_fold_progress:
            fold_iterator = tqdm(
                fold_iterator,
                total=config.cv_folds,
                desc=f"Folds: {antibiotic}",
                unit="fold",
                leave=False,
            )

        for train_idx, test_idx in fold_iterator:
            X_train = X.iloc[train_idx]
            X_test = X.iloc[test_idx]
            y_train = y.iloc[train_idx]
            y_test = y.iloc[test_idx]

            model = build_model(config, y_train)
            model.fit(X_train, y_train)

            fold_probabilities = pd.Series(model.predict_proba(X_test)[:, 1], index=X_test.index)
            fold_predictions = (fold_probabilities >= 0.5).astype(int)

            probabilities.iloc[test_idx] = fold_probabilities.to_numpy()
            predictions.iloc[test_idx] = fold_predictions.to_numpy()
            fold_scores.append(float(roc_auc_score(y_test, fold_probabilities)))

        n_susceptible = int((frame["Resistance phenotype"] == "susceptible").sum())
        n_resistant = int((frame["Resistance phenotype"] == "resistant").sum())
        zero_feature_rows = int((X.sum(axis=1) == 0).sum()) if not X.empty else int(len(frame))

        metric_rows.append(
            {
                "scope": scope_name or "",
                "Antibiotic": antibiotic,
                "n_samples": int(len(frame)),
                "n_susceptible": n_susceptible,
                "n_resistant": n_resistant,
                "n_positive": positive_count,
                "n_negative": negative_count,
                "positive_label": "resistant",
                "positive_fraction": positive_count / len(frame),
                "feature_count": int(len(feature_columns)),
                "zero_feature_rows": zero_feature_rows,
                "roc_auc": float(roc_auc_score(y, probabilities)),
                "average_precision": float(average_precision_score(y, probabilities)),
                "accuracy": float(accuracy_score(y, predictions)),
                "precision": float(precision_score(y, predictions, zero_division=0)),
                "recall": float(recall_score(y, predictions, zero_division=0)),
                "mean_fold_roc_auc": sum(fold_scores) / len(fold_scores),
                "status": "trained",
            }
        )

        fitted_model = build_model(config, y)
        fitted_model.fit(X, y)
        importances = pd.Series(fitted_model.feature_importances_, index=X.columns, dtype="float64")
        importances = importances[importances > 0].sort_values(ascending=False).head(config.top_feature_count)

        for rank, (feature_name, importance) in enumerate(importances.items(), start=1):
            feature_base, feature_type = split_feature_column(feature_name)
            feature_rows.append(
                {
                    "scope": scope_name or "",
                    "Antibiotic": antibiotic,
                    "rank": rank,
                    "feature": feature_name,
                    "feature_base": feature_base,
                    "feature_type": feature_type,
                    "importance": float(importance),
                }
            )

        if config.show_progress:
            iterator.set_postfix(
                samples=len(frame),
                positive=positive_count,
                roc_auc=f"{metric_rows[-1]['roc_auc']:.3f}",
            )

    metrics = pd.DataFrame(metric_rows)
    if not metrics.empty:
        metrics = metrics.sort_values(["scope", "roc_auc", "Antibiotic"], ascending=[True, False, True]).reset_index(drop=True)

    top_features = pd.DataFrame(feature_rows, columns=TOP_FEATURE_COLUMNS)
    if not top_features.empty:
        top_features = top_features.sort_values(["scope", "Antibiotic", "rank"]).reset_index(drop=True)

    return ModelingResult(metrics=metrics, top_features=top_features)
