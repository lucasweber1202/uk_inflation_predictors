"""Small, explicit configuration objects for reproducible experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

PIT_MODES = frozenset({"strict", "reconstructed"})
CUTOFFS = frozenset({"T-10", "T-5", "T-1"})


@dataclass(frozen=True)
class ExperimentConfig:
    target: str
    predictors: tuple[str, ...]
    features: tuple[str, ...] = ("monthly_mean", "monthly_last", "mom", "yoy")
    cutoffs: tuple[str, ...] = ("T-10", "T-5", "T-1")
    pit_modes: tuple[str, ...] = ("strict", "reconstructed")
    ar_orders: tuple[int, ...] = (1, 2, 3, 6, 12)
    predictor_lags: tuple[int, ...] = (0, 1, 2, 3)
    minimum_train_months: int = 60
    minimum_oos_predictions: int = 12
    max_nan_fraction: float = 0.35
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.target or self.target == "PENDING_VERIFICATION":
            raise ValueError("An experiment requires a verified target")
        if not self.predictors:
            raise ValueError("At least one predictor is required")
        unknown_modes = set(self.pit_modes) - PIT_MODES
        unknown_cutoffs = set(self.cutoffs) - CUTOFFS
        if unknown_modes or unknown_cutoffs:
            raise ValueError(f"Unknown modes/cutoffs: {unknown_modes or unknown_cutoffs}")
        if self.minimum_train_months < 12 or self.minimum_oos_predictions < 1:
            raise ValueError("Sample thresholds are too small")
        if not 0 <= self.max_nan_fraction < 1:
            raise ValueError("max_nan_fraction must be in [0, 1)")


def load_config(path: str | Path) -> ExperimentConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("Experiment config must be a mapping")
    config = ExperimentConfig(
        target=str(raw["target"]),
        predictors=tuple(str(value) for value in raw["predictors"]),
        features=tuple(str(value) for value in raw.get("features", ExperimentConfig.features)),
        cutoffs=tuple(str(value) for value in raw.get("cutoffs", ExperimentConfig.cutoffs)),
        pit_modes=tuple(str(value) for value in raw.get("pit_modes", ExperimentConfig.pit_modes)),
        ar_orders=tuple(int(value) for value in raw.get("ar_orders", ExperimentConfig.ar_orders)),
        predictor_lags=tuple(
            int(value) for value in raw.get("predictor_lags", ExperimentConfig.predictor_lags)
        ),
        minimum_train_months=int(raw.get("minimum_train_months", 60)),
        minimum_oos_predictions=int(raw.get("minimum_oos_predictions", 12)),
        max_nan_fraction=float(raw.get("max_nan_fraction", 0.35)),
        metadata=dict(raw.get("metadata", {})),
    )
    config.validate()
    return config
