from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from xgboost import XGBClassifier


ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "artifacts"


@dataclass(slots=True)
class ModelBundle:
    scope: str
    antibiotic: str
    safe_name: str
    feature_columns: list[str]
    metadata: dict[str, object]
    model: XGBClassifier


def antibiotic_to_safe_name(antibiotic: str) -> str:
    return antibiotic.replace("/", "_").replace(" ", "_")


class ArtifactRegistry:
    def __init__(self, artifact_root: Path | None = None) -> None:
        self.artifact_root = artifact_root or ARTIFACT_ROOT
        self._bundles: dict[tuple[str, str], ModelBundle] = {}

    def load(self) -> None:
        self._bundles.clear()
        if not self.artifact_root.exists():
            return

        models_root = self.artifact_root / "models"
        schemas_root = self.artifact_root / "schemas"
        metadata_root = self.artifact_root / "metadata"

        if not models_root.exists():
            return

        for scope_dir in sorted(path for path in models_root.iterdir() if path.is_dir()):
            scope = scope_dir.name
            for model_path in sorted(scope_dir.glob("*.json")):
                safe_name = model_path.stem
                schema_path = schemas_root / scope / f"{safe_name}_features.json"
                metadata_path = metadata_root / scope / f"{safe_name}_meta.json"

                if not schema_path.exists() or not metadata_path.exists():
                    continue

                feature_columns = json.loads(schema_path.read_text(encoding="utf-8"))
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

                model = XGBClassifier()
                model.load_model(model_path)

                antibiotic = str(metadata.get("antibiotic", safe_name))
                bundle = ModelBundle(
                    scope=scope,
                    antibiotic=antibiotic,
                    safe_name=safe_name,
                    feature_columns=list(feature_columns),
                    metadata=metadata,
                    model=model,
                )
                self._bundles[(scope, antibiotic)] = bundle

    def ensure_loaded(self) -> None:
        if not self._bundles:
            self.load()

    def list_bundles(self, scope: str | None = None) -> list[ModelBundle]:
        self.ensure_loaded()
        bundles = list(self._bundles.values())
        if scope is not None:
            bundles = [bundle for bundle in bundles if bundle.scope == scope]
        return sorted(bundles, key=lambda bundle: (bundle.scope, bundle.antibiotic))

    def get_bundle(self, scope: str, antibiotic: str) -> ModelBundle:
        self.ensure_loaded()
        key = (scope, antibiotic)
        if key in self._bundles:
            return self._bundles[key]

        safe_name = antibiotic_to_safe_name(antibiotic)
        for bundle in self._bundles.values():
            if bundle.scope == scope and bundle.safe_name == safe_name:
                return bundle

        available = sorted(name for bundle_scope, name in self._bundles if bundle_scope == scope)
        available_text = ", ".join(available[:10]) if available else "(none)"
        raise KeyError(f"No model found for scope={scope!r}, antibiotic={antibiotic!r}. Available: {available_text}")
