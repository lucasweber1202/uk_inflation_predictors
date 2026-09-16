"""Versioned target crosswalk access and resolution gates."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_target_registry(path: str | Path = ROOT / "target_registry.csv") -> pd.DataFrame:
    registry = pd.read_csv(path, dtype=str).fillna("")
    required = {"target_key", "target_repository", "target_series_id", "verified"}
    if not required <= set(registry):
        raise ValueError(f"Target registry missing {sorted(required - set(registry))}")
    if registry["target_key"].duplicated().any():
        raise ValueError("target_key must be unique")
    return registry


def resolve_target(target_key: str, registry: pd.DataFrame | None = None) -> pd.Series:
    frame = registry if registry is not None else load_target_registry()
    matches = frame[frame["target_key"] == target_key]
    if len(matches) != 1:
        raise KeyError(f"Unknown or duplicate target key {target_key}")
    row = matches.iloc[0]
    if row["verified"].lower() != "true" or row["target_series_id"] == "PENDING_VERIFICATION":
        raise ValueError(f"Target {target_key} is not verified")
    return row
