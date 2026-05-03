from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import PipelineConfig
from prepared_inputs import load_prepared_inputs
from rule_based import evaluate_prepared_rule_baseline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amr",
        description="AMR prediction helper for training one binary model per antibiotic from prepared model-input tables.",
    )
    add_prepared_input_args(parser)
    add_model_args(parser)
    return parser


def add_prepared_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--prepared-input-dir",
        default="data/model_inputs/broad",
        help="Train from a directory of prepared model_input__*.csv tables instead of raw TSV files.",
    )
    parser.add_argument(
        "--prepared-input-root",
        default="",
        help="Train every prepared-input subdirectory under this root and write one output subdirectory per scope.",
    )


def add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", default="outputs", help="Directory for training outputs.")
    parser.add_argument(
        "--run-mode",
        choices=["model", "rule"],
        default="model",
        help="Choose whether to train ML models or evaluate the determinant-based rule baseline.",
    )
    parser.add_argument("--cv-folds", type=int, default=5, help="Number of stratified CV folds.")
    parser.add_argument(
        "--top-feature-count",
        type=int,
        default=20,
        help="Maximum number of feature-importance rows to export per antibiotic.",
    )
    parser.add_argument(
        "--antibiotic",
        action="append",
        dest="antibiotics",
        default=[],
        help="Restrict training to one antibiotic. Repeat the flag to select several.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bars during training.",
    )
    parser.add_argument(
        "--progress-folds",
        action="store_true",
        help="Show fold-level progress bars inside each antibiotic run.",
    )


def build_config(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        output_dir=Path(args.output_dir),
        prepared_input_dir=Path(args.prepared_input_dir) if args.prepared_input_dir else None,
        prepared_input_root=Path(args.prepared_input_root) if args.prepared_input_root else None,
        run_mode=args.run_mode,
        cv_folds=args.cv_folds,
        top_feature_count=args.top_feature_count,
        show_progress=not args.no_progress,
        show_fold_progress=args.progress_folds,
        antibiotics=args.antibiotics,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = build_config(args)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    prepared_input_root = config.prepared_input_root
    prepared_input_dir = config.prepared_input_dir

    if prepared_input_root is not None:
        run_prepared_root(config, prepared_input_root)
        return

    if prepared_input_dir is None:
        raise ValueError("Provide --prepared-input-dir or --prepared-input-root.")

    run_prepared_directory(config, prepared_input_dir, resolve_scope_output_dir(config.output_dir, prepared_input_dir.name))


def run_prepared_directory(config: PipelineConfig, input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = load_prepared_inputs(input_dir, config.antibiotics)
    scope_name = input_dir.name
    metrics_path = output_dir / "metrics.csv"
    summary_path = output_dir / "dataset_summary.json"
    config_path = output_dir / "run_config.json"
    run_config = config.to_dict()

    if config.run_mode == "rule":
        results = evaluate_prepared_rule_baseline(artifacts.inputs, scope_name=scope_name)
        results.metrics.to_csv(metrics_path, index=False)
    else:
        from modeling import train_prepared_models

        results = train_prepared_models(artifacts.inputs, config, scope_name=scope_name)
        top_features_path = output_dir / "top_features.csv"
        results.metrics.to_csv(metrics_path, index=False)
        results.top_features.to_csv(top_features_path, index=False)

    summary = {
        "prepared_input_dir": str(input_dir),
        "scope": scope_name,
        "run_mode": config.run_mode,
        "selected_antibiotics": artifacts.summary["Antibiotic"].tolist(),
        "prepared_input_summary": artifacts.summary.to_dict(orient="records"),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    config_path.write_text(json.dumps(run_config, indent=2), encoding="utf-8")

    print(f"Prepared scope: {scope_name}")
    print(f"Run mode: {config.run_mode}")
    print(f"Selected antibiotics: {len(artifacts.summary)}")
    print(f"Metrics written to: {metrics_path}")
    if config.run_mode != "rule":
        print(f"Top features written to: {top_features_path}")


def resolve_scope_output_dir(base_output_dir: Path, scope_name: str) -> Path:
    if base_output_dir.name == scope_name:
        return base_output_dir
    return base_output_dir / scope_name


def run_prepared_root(config: PipelineConfig, input_root: Path) -> None:
    scope_dirs = sorted(path for path in input_root.iterdir() if path.is_dir())

    for scope_dir in scope_dirs:
        scope_output_dir = resolve_scope_output_dir(config.output_dir, scope_dir.name)
        run_prepared_directory(config, scope_dir, scope_output_dir)


if __name__ == "__main__":
    main()
