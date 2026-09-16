"""Forecast cutoffs derived from persisted official CPI release timestamps."""

from __future__ import annotations

import re

import pandas as pd

_CUTOFF = re.compile(r"^T-(1|5|10)$")


def release_calendar(target_vintages: pd.DataFrame) -> pd.Series:
    """Return one first official publication timestamp per target month."""
    if "reference_date" not in target_vintages:
        raise ValueError("target vintages require reference_date")
    release_column = next(
        (name for name in ("available_at", "release_at", "collected_at", "vintage_date") if name in target_vintages),
        None,
    )
    if release_column is None:
        raise ValueError("No persisted target release timestamp is available")
    frame = target_vintages.copy()
    frame["reference_date"] = pd.to_datetime(frame["reference_date"]).dt.to_period("M").dt.to_timestamp()
    frame[release_column] = pd.to_datetime(frame[release_column], utc=True)
    releases = frame.groupby("reference_date")[release_column].min().sort_index()
    if releases.index.duplicated().any() or releases.isna().any():
        raise ValueError("Invalid target release calendar")
    return releases


def forecast_cutoffs(target_vintages: pd.DataFrame, label: str) -> pd.Series:
    match = _CUTOFF.fullmatch(label)
    if match is None:
        raise ValueError("Cutoff must be T-10, T-5 or T-1")
    return release_calendar(target_vintages) - pd.to_timedelta(int(match.group(1)), unit="D")
