from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def main() -> None:
    sns.set_theme(style="whitegrid")

    project_root = Path(__file__).resolve().parents[1]
    rule_output_root = project_root / "outputs_rule"
    figure_output_dir = project_root / "report" / "figures"
    figure_output_dir.mkdir(parents=True, exist_ok=True)

    strict_metrics = pd.read_csv(rule_output_root / "strict" / "metrics.csv")
    broad_metrics = pd.read_csv(rule_output_root / "broad" / "metrics.csv")
    rule_metrics = pd.concat([strict_metrics, broad_metrics], ignore_index=True)

    scope_order = ["broad", "strict"]
    scope_label_map = {"broad": "broad rule", "strict": "strict rule"}
    scope_palette = {"broad rule": "#e9c46a", "strict rule": "#e76f51"}
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

    plot_height = max(8, 0.7 * rule_metrics["Antibiotic"].nunique())
    x_ticks = [value / 10 for value in range(0, 11)]

    for metric_name, title, xlabel, filename in metric_specs:
        plot_df = rule_metrics[["Antibiotic", "scope", metric_name]].copy()
        plot_df["scope"] = pd.Categorical(
            plot_df["scope"], categories=scope_order, ordered=True
        )
        plot_df = plot_df.sort_values(["Antibiotic", "scope"]).reset_index(drop=True)
        plot_df["scope_label"] = plot_df["scope"].map(scope_label_map)

        fig, ax = plt.subplots(figsize=(15, plot_height))
        sns.barplot(
            data=plot_df,
            x=metric_name,
            y="Antibiotic",
            hue="scope_label",
            hue_order=["broad rule", "strict rule"],
            palette=scope_palette,
            ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Antibiotic")
        ax.set_xlim(0, 1)
        ax.set_xticks(x_ticks)
        ax.legend(title="Scope", loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0)

        plt.tight_layout(rect=(0, 0, 0.86, 1))
        fig.savefig(figure_output_dir / filename, dpi=300, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    main()
