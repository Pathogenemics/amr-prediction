from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(slots=True)
class PreparedAntibioticInput:
    antibiotic: str
    table_path: Path
    frame: pd.DataFrame


@dataclass(slots=True)
class PreparedInputArtifacts:
    inputs: list[PreparedAntibioticInput]
    summary: pd.DataFrame


REQUIRED_COLUMNS = {"BioSample", "Antibiotic", "Resistance phenotype", "y"}


def load_prepared_inputs(input_dir: Path, selected_antibiotics: list[str] | None = None) -> PreparedInputArtifacts:
    table_paths = sorted(
        path
        for path in input_dir.glob("model_input__*.csv")
        if "__feature_key" not in path.name and path.name != "model_input_manifest.csv"
    )

    selected = set(selected_antibiotics or [])
    prepared_inputs: list[PreparedAntibioticInput] = []
    summary_rows: list[dict[str, int | str]] = []

    for table_path in table_paths:
        frame = pd.read_csv(table_path)
        missing_columns = REQUIRED_COLUMNS - set(frame.columns)
        if missing_columns:
            missing_text = ", ".join(sorted(missing_columns))
            raise ValueError(f"{table_path} is missing required columns: {missing_text}")

        antibiotic_values = frame["Antibiotic"].dropna().astype(str).unique().tolist()
        if len(antibiotic_values) != 1:
            raise ValueError(f"{table_path} should contain exactly one antibiotic, found: {antibiotic_values}")

        antibiotic = antibiotic_values[0]
        if selected and antibiotic not in selected:
            continue

        feature_columns = [
            column
            for column in frame.columns
            if column not in ["BioSample", "Antibiotic", "Resistance phenotype", "y"]
        ]
        zero_feature_rows = int((frame[feature_columns].sum(axis=1) == 0).sum()) if feature_columns else int(len(frame))

        prepared_inputs.append(PreparedAntibioticInput(antibiotic=antibiotic, table_path=table_path, frame=frame))
        summary_rows.append(
            {
                "Antibiotic": antibiotic,
                "table_path": str(table_path),
                "n_samples": int(len(frame)),
                "n_susceptible": int((frame["Resistance phenotype"] == "susceptible").sum()),
                "n_resistant": int((frame["Resistance phenotype"] == "resistant").sum()),
                "feature_count": int(len(feature_columns)),
                "zero_feature_rows": zero_feature_rows,
            }
        )

    summary = pd.DataFrame(summary_rows)
    if not summary.empty:
        summary = summary.sort_values(["n_samples", "Antibiotic"], ascending=[False, True]).reset_index(drop=True)

    return PreparedInputArtifacts(inputs=prepared_inputs, summary=summary)
