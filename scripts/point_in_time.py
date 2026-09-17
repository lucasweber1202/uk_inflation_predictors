"""Point-in-time selection independent of collector implementation code."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

STRICT_BASES = frozenset({"official_timestamp", "official_date", "archived_release", "first_seen"})
RECONSTRUCTED_BASES = STRICT_BASES | {"inferred"}
REQUIRED = frozenset(
    {"series_id", "reference_date", "vintage_date", "value", "available_at", "availability_basis"}
)


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"PIT input missing columns: {sorted(missing)}")
    result = frame.copy()
    for column in ("reference_date", "vintage_date", "available_at"):
        result[column] = pd.to_datetime(result[column], utc=True)
    if result.duplicated(["series_id", "reference_date", "vintage_date"]).any():
        raise ValueError("Duplicate predictor vintage keys")
    return result


def get_predictor_as_of(
    observations: pd.DataFrame,
    series_id: str,
    as_of: str | pd.Timestamp,
    mode: str = "strict",
) -> pd.DataFrame:
    """Return the latest vintage actually available at ``as_of`` for each date."""
    if mode not in {"strict", "reconstructed"}:
        raise ValueError("mode must be strict or reconstructed")
    frame = _normalise(observations)
    cutoff = pd.Timestamp(as_of)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    allowed = STRICT_BASES if mode == "strict" else RECONSTRUCTED_BASES
    selected = frame[
        (frame["series_id"] == series_id)
        & frame["availability_basis"].isin(allowed)
        & (frame["available_at"] <= cutoff)
    ].copy()
    selected = selected.sort_values(["reference_date", "available_at", "vintage_date"])
    selected = selected.drop_duplicates(["series_id", "reference_date"], keep="last")
    selected["pit_mode"] = mode
    selected["is_reconstructed"] = selected["availability_basis"].eq("inferred")
    if mode == "strict" and selected["is_reconstructed"].any():
        raise AssertionError("Strict PIT selection admitted inferred availability")
    if (selected["available_at"] > cutoff).any():
        raise AssertionError("Future availability leaked through PIT selection")
    return selected.reset_index(drop=True)


def get_target_as_of(
    observations: pd.DataFrame,
    series_id: str,
    as_of: str | pd.Timestamp,
    mode: str = "strict",
) -> pd.DataFrame:
    """Select target vintages with the same fail-closed rules as predictors."""
    return get_predictor_as_of(observations, series_id, as_of, mode)


def build_as_of_panel(
    observations: pd.DataFrame,
    as_of: str | pd.Timestamp,
    mode: str = "strict",
    series_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    ids = tuple(series_ids or sorted(observations["series_id"].unique()))
    panels = [get_predictor_as_of(observations, series_id, as_of, mode) for series_id in ids]
    nonempty = [frame for frame in panels if not frame.empty]
    if not nonempty:
        return pd.DataFrame(columns=[*REQUIRED, "pit_mode", "is_reconstructed"])
    result = pd.concat(nonempty, ignore_index=True)
    if result["pit_mode"].nunique() != 1:
        raise AssertionError("PIT modes were mixed")
    return result


def build_multi_source_panel(
    sources: Mapping[str, pd.DataFrame],
    as_of: str | pd.Timestamp,
    mode: str = "strict",
) -> pd.DataFrame:
    frames = []
    for repository, observations in sources.items():
        panel = build_as_of_panel(observations, as_of, mode)
        panel["source_repository"] = repository
        frames.append(panel)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
