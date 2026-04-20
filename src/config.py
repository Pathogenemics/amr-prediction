from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PipelineConfig:
    output_dir: Path = Path("outputs")
    prepared_input_dir: Path | None = None
    prepared_input_root: Path | None = None
    cv_folds: int = 5
    top_feature_count: int = 20
    random_state: int = 42
    n_estimators: int = 250
    learning_rate: float = 0.05
    max_depth: int = 5
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    show_progress: bool = True
    show_fold_progress: bool = False
    antibiotics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["output_dir"] = str(self.output_dir)
        payload["prepared_input_dir"] = str(self.prepared_input_dir) if self.prepared_input_dir is not None else None
        payload["prepared_input_root"] = str(self.prepared_input_root) if self.prepared_input_root is not None else None
        return payload
