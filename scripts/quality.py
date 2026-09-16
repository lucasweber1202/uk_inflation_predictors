"""Research-layer fail-closed data-quality gates."""

from __future__ import annotations

import pandas as pd


def validate_model_inputs(
    target: pd.Series,
    predictor: pd.Series,
    *,
    target_series_id: str,
    cutoff: pd.Timestamp | None = None,
    availability: pd.Series | None = None,
    minimum_months: int = 24,
    max_nan_fraction: float = 0.35,
) -> None:
    if target_series_id == "PENDING_VERIFICATION":
        raise ValueError("Unresolved targets cannot enter experiments")
    if target.index.duplicated().any() or predictor.index.duplicated().any():
        raise ValueError("Duplicate monthly keys")
    aligned = pd.concat([target, predictor], axis=1)
    if len(aligned.dropna()) < minimum_months:
        raise ValueError("Insufficient aligned sample")
    if predictor.dropna().nunique() <= 1:
        raise ValueError("Predictor is constant")
    if aligned.isna().mean().max() > max_nan_fraction:
        raise ValueError("NaN fraction exceeds configured threshold")
    if cutoff is not None and availability is not None:
        timestamps = pd.to_datetime(availability, utc=True)
        limit = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        if (timestamps > limit).any():
            raise ValueError("available_at exceeds forecast cutoff")
