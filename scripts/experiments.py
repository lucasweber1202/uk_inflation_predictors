"""Forecast-origin-specific, revision-safe pseudo-OOS experiments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.config import load_config
from scripts.cutoffs import forecast_cutoffs
from scripts.evaluation import metrics
from scripts.features import feature_series
from scripts.models import fit_ols, predict_ols
from scripts.point_in_time import get_predictor_as_of, get_target_as_of
from scripts.quality import validate_model_inputs


def _monthly(values: pd.Series) -> pd.Series:
    result = values.copy()
    result.index = pd.to_datetime(result.index).tz_localize(None).to_period("M").to_timestamp()
    return result.sort_index()

def _target_change(rows: pd.DataFrame) -> pd.Series:
    level = pd.Series(rows["value"].to_numpy(dtype=float), index=pd.to_datetime(rows["reference_date"]).dt.tz_localize(None))
    return _monthly(level).pct_change().dropna()

def _fit_one(target: pd.Series, predictor: pd.Series | None, month: pd.Timestamp, ar_order: int, predictor_lag: int, minimum_train: int) -> tuple[float, int]:
    history = target[target.index < month].sort_index()
    rows: list[dict[str, float]] = []
    outcomes: list[float] = []
    for position, stamp in enumerate(history.index):
        if position < ar_order:
            continue
        row = {f"ar{lag}": float(history.iloc[position-lag]) for lag in range(1, ar_order+1)}
        if predictor is not None:
            value = predictor.get(stamp - pd.DateOffset(months=predictor_lag), np.nan)
            if pd.isna(value):
                continue
            row["predictor"] = float(value)
        rows.append(row)
        outcomes.append(float(history.loc[stamp]))
    x, y = pd.DataFrame(rows), pd.Series(outcomes, dtype=float)
    if len(y) < minimum_train:
        raise ValueError("Insufficient train sample")
    forecast_row = {f"ar{lag}": float(history.iloc[-lag]) for lag in range(1, ar_order+1)}
    if predictor is not None:
        value = predictor.get(month - pd.DateOffset(months=predictor_lag), np.nan)
        if pd.isna(value):
            raise ValueError("Predictor unavailable at forecast origin")
        forecast_row["predictor"] = float(value)
    return predict_ols(fit_ols(x, y), pd.Series(forecast_row)[x.columns]), len(y)

def _benchmark(name: str, target: pd.Series, month: pd.Timestamp, minimum_train: int) -> tuple[float, int]:
    history = target[target.index < month].dropna().sort_index()
    if len(history) < minimum_train:
        raise ValueError("Insufficient train sample")
    if name == "historical_mean":
        return float(history.mean()), len(history)
    if name == "last_observation":
        return float(history.iloc[-1]), len(history)
    if name.startswith("AR"):
        return _fit_one(target, None, month, int(name[2:]), 0, minimum_train)
    raise ValueError(f"Unsupported benchmark: {name}")

def _actuals(frame: pd.DataFrame, target_id: str) -> pd.Series:
    rows = frame[frame["series_id"] == target_id].copy()
    rows["reference_date"] = pd.to_datetime(rows["reference_date"], utc=True)
    rows["vintage_date"] = pd.to_datetime(rows["vintage_date"], utc=True)
    final = rows.sort_values(["reference_date", "vintage_date"]).drop_duplicates("reference_date", keep="last")
    return _target_change(final)

def run_from_frames(config_path: str | Path, target_frame: pd.DataFrame, predictor_frame: pd.DataFrame, as_of: str | None = None) -> pd.DataFrame:
    config = load_config(config_path)
    target_rows = target_frame[target_frame["series_id"] == config.target].copy()
    if target_rows.empty:
        raise ValueError(f"Target {config.target} is absent")
    actual = _actuals(target_frame, config.target)
    records: list[dict[str, object]] = []
    benchmark_names = ("historical_mean", "last_observation", *(f"AR{x}" for x in config.ar_orders))
    for cutoff_label in config.cutoffs:
        origins = forecast_cutoffs(target_rows, cutoff_label)
        if as_of:
            ceiling = pd.Timestamp(as_of)
            ceiling = ceiling.tz_localize("UTC") if ceiling.tzinfo is None else ceiling.tz_convert("UTC")
            origins = origins[origins <= ceiling]
        for forecast_month, timestamp in origins.items():
            month = pd.Timestamp(forecast_month).tz_localize(None).to_period("M").to_timestamp()
            if month not in actual.index:
                continue
            for pit_mode in config.pit_modes:
                target = _target_change(get_target_as_of(target_frame, config.target, timestamp, pit_mode))
                for predictor_id in config.predictors:
                    pit = get_predictor_as_of(predictor_frame, predictor_id, timestamp, pit_mode)
                    for feature in config.features:
                        predictor = _monthly(feature_series(pit, feature, timestamp))
                        try:
                            validate_model_inputs(target, predictor, target_series_id=config.target, cutoff=pd.Timestamp(timestamp), availability=pit["available_at"], minimum_months=config.minimum_train_months, max_nan_fraction=config.max_nan_fraction)
                        except ValueError:
                            continue
                        for order in config.ar_orders:
                            for lag in config.predictor_lags:
                                try:
                                    forecast, n_train = _fit_one(target, predictor, month, order, lag, config.minimum_train_months)
                                except ValueError:
                                    continue
                                for benchmark_name in benchmark_names:
                                    try:
                                        benchmark, _ = _benchmark(benchmark_name, target, month, config.minimum_train_months)
                                    except ValueError:
                                        continue
                                    value = float(actual.loc[month])
                                    records.append({"target": config.target, "forecast_month": month, "forecast_timestamp": timestamp, "cutoff": cutoff_label, "pit_mode": pit_mode, "predictor": predictor_id, "feature": feature, "predictor_lag": lag, "ar_order": order, "benchmark": benchmark_name, "n_train": n_train, "forecast": forecast, "benchmark_forecast": benchmark, "actual": value, "error": forecast-value, "benchmark_error": benchmark-value})
    result = pd.DataFrame.from_records(records)
    if result.empty:
        return result
    keys = ["target","cutoff","pit_mode","predictor","feature","predictor_lag","ar_order","benchmark"]
    counts = result.groupby(keys)["forecast_month"].transform("count")
    return result[counts >= config.minimum_oos_predictions].reset_index(drop=True)

def summarise(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    keys = ["target","cutoff","pit_mode","predictor","feature","predictor_lag","ar_order","benchmark"]
    rows: list[dict[str, object]] = []
    for values, group in results.groupby(keys, dropna=False):
        indexed = group.set_index("forecast_month")
        model = metrics(indexed["actual"], indexed["forecast"])
        base = metrics(indexed["actual"], indexed["benchmark_forecast"])
        rows.append(dict(zip(keys, values)) | {"n_predictions": int(model["n_predictions"]), "RMSE": model["rmse"], "MAE": model["mae"], "bias": model["bias"], "directional_accuracy": model["directional_accuracy"], "benchmark_RMSE": base["rmse"], "benchmark_MAE": base["mae"], "relative_RMSE": model["rmse"]/base["rmse"], "RMSE_improvement": 1-model["rmse"]/base["rmse"], "MAE_improvement": 1-model["mae"]/base["mae"]})
    return pd.DataFrame(rows)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--target-csv", required=True)
    parser.add_argument("--predictor-csv", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    detail = run_from_frames(args.config, pd.read_csv(args.target_csv), pd.read_csv(args.predictor_csv), args.as_of)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    summarise(detail).to_csv(output, index=False)
    detail.to_csv(output.with_name(f"{output.stem}_forecasts.csv"), index=False)
    output.with_suffix(".json").write_text(json.dumps({"config": args.config, "rows": len(detail)}, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
