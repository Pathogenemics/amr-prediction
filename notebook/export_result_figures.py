from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import pandas as pd
import seaborn as sns


def load_ml_metrics(output_root: Path) -> pd.DataFrame:
    frames = []
    for scope in ["strict", "broad", "all"]:
        metrics_path = output_root / scope / "metrics.csv"
        frame = pd.read_csv(metrics_path)
        frame["scope"] = scope
        frames.append(frame)

    metrics = pd.concat(frames, ignore_index=True)
    return metrics


def load_rule_metrics(rule_output_root: Path) -> pd.DataFrame:
    frames = []
    for scope in ["strict", "broad"]:
        metrics_path = rule_output_root / scope / "metrics.csv"
        frame = pd.read_csv(metrics_path)
        frame["scope"] = scope
        frames.append(frame)

    return pd.concat(frames, ignore_index=True)


def save_scope_barplots(
    metrics: pd.DataFrame,
    metric_specs: list[tuple[str, str, str, str]],
    scope_order: list[str],
    scope_palette: dict[str, str],
    figure_output_dir: Path,
) -> None:
    plot_height = max(9, 0.85 * metrics["Antibiotic"].nunique())
    x_ticks = [value / 10 for value in range(0, 11)]

    for metric_name, title, xlabel, filename in metric_specs:
        plot_df = metrics[["Antibiotic", "scope", metric_name]].copy()
        plot_df["scope"] = pd.Categorical(
            plot_df["scope"], categories=scope_order, ordered=True
        )
        plot_df = plot_df.sort_values(["Antibiotic", "scope"]).reset_index(drop=True)

        fig, ax = plt.subplots(figsize=(15, plot_height))
        sns.barplot(
            data=plot_df,
            x=metric_name,
            y="Antibiotic",
            hue="scope",
            hue_order=scope_order,
            palette=scope_palette,
            ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Antibiotic")
        ax.set_xlim(0, 1)
        ax.set_xticks(x_ticks)
        legend_handles = [
            Patch(facecolor=scope_palette[scope], label=scope) for scope in scope_order
        ]
        ax.legend(
            handles=legend_handles,
            title="Scope",
            loc="upper left",
            bbox_to_anchor=(1.02, 1),
            borderaxespad=0,
        )

        plt.tight_layout(rect=(0, 0, 0.86, 1))
        fig.savefig(figure_output_dir / filename, dpi=300, bbox_inches="tight")
        plt.close(fig)


def save_rule_barplots(rule_metrics: pd.DataFrame, figure_output_dir: Path) -> None:
    rule_scope_order = ["broad", "strict"]
    rule_label_map = {"broad": "broad rule", "strict": "strict rule"}
    rule_palette = {"broad rule": "#e9c46a", "strict rule": "#e76f51"}
    metric_specs = [
        (
            "recall",
            "Rule-Based Recall Comparison By Antibiotic And Scope",
            "Recall",
            "rule_recall_by_scope.png",
        ),
        (
            "precision",
            "Rule-Based Precision Comparison By Antibiotic And Scope",
            "Precision",
            "rule_precision_by_scope.png",
        ),
    ]

    plot_height = max(9, 0.85 * rule_metrics["Antibiotic"].nunique())
    x_ticks = [value / 10 for value in range(0, 11)]

    for metric_name, title, xlabel, filename in metric_specs:
        plot_df = rule_metrics[["Antibiotic", "scope", metric_name]].copy()
        plot_df["scope"] = pd.Categorical(
            plot_df["scope"], categories=rule_scope_order, ordered=True
        )
        plot_df = plot_df.sort_values(["Antibiotic", "scope"]).reset_index(drop=True)
        plot_df["scope_label"] = plot_df["scope"].map(rule_label_map)

        fig, ax = plt.subplots(figsize=(15, plot_height))
        sns.barplot(
            data=plot_df,
            x=metric_name,
            y="Antibiotic",
            hue="scope_label",
            hue_order=["broad rule", "strict rule"],
            palette=rule_palette,
            ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Antibiotic")
        ax.set_xlim(0, 1)
        ax.set_xticks(x_ticks)
        legend_handles = [
            Patch(facecolor=rule_palette[label], label=label)
            for label in ["broad rule", "strict rule"]
        ]
        ax.legend(
            handles=legend_handles,
            title="Scope",
            loc="upper left",
            bbox_to_anchor=(1.02, 1),
            borderaxespad=0,
        )

        plt.tight_layout(rect=(0, 0, 0.86, 1))
        fig.savefig(figure_output_dir / filename, dpi=300, bbox_inches="tight")
        plt.close(fig)


def main() -> None:
    sns.set_theme(style="whitegrid")

    project_root = Path(__file__).resolve().parents[1]
    output_root = project_root / "outputs"
    rule_output_root = project_root / "outputs_rule"
    figure_output_dir = project_root / "report" / "figures"
    figure_output_dir.mkdir(parents=True, exist_ok=True)

    ml_metrics = load_ml_metrics(output_root)
    save_scope_barplots(
        metrics=ml_metrics,
        metric_specs=[
            ("recall", "Recall Comparison By Antibiotic And Scope", "Recall", "recall_by_scope.png"),
            (
                "precision",
                "Precision Comparison By Antibiotic And Scope",
                "Precision",
                "precision_by_scope.png",
            ),
            ("roc_auc", "ROC AUC Comparison By Antibiotic And Scope", "ROC AUC", "roc_auc_by_scope.png"),
        ],
        scope_order=["all", "broad", "strict"],
        scope_palette={"all": "#2a9d8f", "broad": "#e9c46a", "strict": "#e76f51"},
        figure_output_dir=figure_output_dir,
    )

    rule_metrics = load_rule_metrics(rule_output_root)
    save_rule_barplots(rule_metrics=rule_metrics, figure_output_dir=figure_output_dir)


if __name__ == "__main__":
    main()
