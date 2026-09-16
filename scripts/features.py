"""PIT-safe frequency alignment and economically interpretable features."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _series(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if frame["series_id"].nunique() != 1:
        raise ValueError("Feature builder accepts one raw series at a time")
    ordered = frame.sort_values("reference_date")
    return pd.Series(
        ordered["value"].astype(float).to_numpy(),
        index=pd.to_datetime(ordered["reference_date"]).dt.tz_localize(None),
    )


def aggregate_monthly(frame: pd.DataFrame, statistic: str) -> pd.Series:
    values = _series(frame)
    monthly = values.groupby(values.index.to_period("M"))
    aggregators = {
        "monthly_mean": monthly.mean,
        "monthly_last": monthly.last,
        "monthly_median": monthly.median,
        "monthly_min": monthly.min,
        "monthly_max": monthly.max,
    }
    if statistic not in aggregators:
        raise ValueError(f"Unsupported monthly statistic {statistic}")
    result = aggregators[statistic]()
    result.index = result.index.to_timestamp()
    return result.sort_index()


def trailing_feature(frame: pd.DataFrame, as_of: str | pd.Timestamp, days: int, statistic: str = "mean") -> float:
    if days not in {7, 14, 21}:
        raise ValueError("Trailing window must be 7, 14 or 21 days")
    values = _series(frame)
    cutoff = pd.Timestamp(as_of).tz_localize(None)
    window = values[(values.index <= cutoff) & (values.index > cutoff - pd.Timedelta(days=days))]
    if window.empty:
        return float("nan")
    return float(window.mean() if statistic == "mean" else window.iloc[-1])


def mtd_feature(frame: pd.DataFrame, as_of: str | pd.Timestamp, statistic: str = "mean") -> float:
    values = _series(frame)
    cutoff = pd.Timestamp(as_of).tz_localize(None)
    month_start = cutoff.replace(day=1).normalize()
    window = values[(values.index >= month_start) & (values.index <= cutoff)]
    if window.empty:
        return float("nan")
    if statistic == "mean":
        return float(window.mean())
    if statistic == "last":
        return float(window.iloc[-1])
    raise ValueError("MTD statistic must be mean or last")


def transformations(level: pd.Series) -> pd.DataFrame:
    level = level.sort_index().astype(float)
    return pd.DataFrame(
        {"level": level, "difference": level.diff(), "mom": level.pct_change(), "yoy": level.pct_change(12)}
    ).replace([np.inf, -np.inf], np.nan)


def elexon_provider_daily(frame: pd.DataFrame, weighted: bool = False) -> pd.DataFrame:
    """Aggregate SP series by provider/day without allowing sparse providers to dominate."""
    required = {"provider", "measure", "reference_date", "value"}
    if not required <= set(frame):
        raise ValueError(f"Elexon frame missing {sorted(required - set(frame))}")
    prices = frame[frame["measure"] == "PRICE"].copy()
    volumes = frame[frame["measure"] == "VOLUME"].copy()
    keys = ["provider", "reference_date", "settlement_period"]
    if weighted:
        joined = prices.merge(volumes[keys + ["value"]], on=keys, suffixes=("_price", "_volume"), validate="one_to_one")
        if (joined["value_volume"] < 0).any():
            raise ValueError("Negative Elexon volume cannot be used as a weight")
        joined["weighted"] = joined["value_price"] * joined["value_volume"]
        grouped = joined.groupby(["provider", "reference_date"])
        result = grouped.agg(weighted_sum=("weighted", "sum"), volume=("value_volume", "sum"))
        result["price"] = result["weighted_sum"] / result["volume"].replace(0, np.nan)
        return result.reset_index()[["provider", "reference_date", "price"]]
    grouped = prices.groupby(["provider", "reference_date"])["value"]
    return grouped.agg(price="mean", median="median", minimum="min", maximum="max", volatility="std").reset_index()
