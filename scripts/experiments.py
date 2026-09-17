"""Release-relative, point-in-time pseudo-OOS experiment runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.config import load_config
from scripts.cutoffs import forecast_cutoffs
from scripts.features import feature_series_as_of
from scripts.models import fit_ols, predict_ols
from scripts.point_in_time import get_predictor_as_of, get_target_as_of
from scripts.quality import validate_model_inputs


def _monthly_level(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    dates = pd.to_datetime(frame["reference_date"], utc=True).dt.tz_localize(None)
    index = dates.dt.to_period("M").dt.to_timestamp()
    result = pd.Series(frame["value"].to_numpy(dtype=float), index=index)
    if result.index.duplicated().any():
        raise ValueError("Duplicate target monthly keys")
    return result.sort_index()


def _first_release_actuals(frame: pd.DataFrame, series_id: str) -> pd.Series:
    selected = frame[frame["series_id"] == series_id].copy()
    selected["available_at"] = pd.to_datetime(selected["available_at"], utc=True)
    selected = selected.sort_values(["reference_date", "available_at", "vintage_date"])
    return _monthly_level(selected.drop_duplicates("reference_date", keep="first"))


def _row_for_origin(
    target: pd.Series,
    predictor: pd.Series,
    month: pd.Timestamp,
    ar_order: int,
    predictor_lag: int,
    minimum_train_months: int,
) -> tuple[float, int]:
    data = pd.DataFrame({"target": target.astype(float)})
    for lag in range(1, ar_order + 1):
        data[f"ar{lag}"] = target.shift(lag)
    data["predictor"] = predictor.reindex(data.index).shift(predictor_lag)
    train = data.loc[data.index < month].dropna()
    if len(train) < minimum_train_months:
        raise ValueError("Insufficient train sample")
    forecast_row = pd.Series(
        {
            **{
                f"ar{lag}": target.get(month - pd.DateOffset(months=lag), np.nan)
                for lag in range(1, ar_order + 1)
            },
            "predictor": predictor.shift(predictor_lag).get(month, np.nan),
        }
    )
    if forecast_row.isna().any():
        raise ValueError("Forecast-origin features are incomplete")
    coefficients = fit_ols(train.drop(columns="target"), train["target"])
    return predict_ols(coefficients, forecast_row), len(train)


def _benchmark(
    target: pd.Series, month: pd.Timestamp, name: str, minimum_train_months: int
) -> tuple[float, int]:
    history = target.loc[target.index < month].dropna()
    if len(history) < minimum_train_months:
        raise ValueError("Insufficient train sample")
    if name == "historical_mean":
        return float(history.mean()), len(history)
    if name == "last_observation":
        return float(history.iloc[-1]), len(history)
    order = int(name.removeprefix("AR"))
    data = pd.DataFrame({"target": history})
    for lag in range(1, order + 1):
        data[f"ar{lag}"] = history.shift(lag)
    train = data.dropna()
    row = pd.Series(
        {
            f"ar{lag}": history.get(month - pd.DateOffset(months=lag), np.nan)
            for lag in range(1, order + 1)
        }
    )
    if row.isna().any():
        raise ValueError("Benchmark-origin lags are incomplete")
    coefficients = fit_ols(train.drop(columns="target"), train["target"])
    return predict_ols(coefficients, row), len(train)


def run_from_frames(
    config_path: str | Path,
    target_frame: pd.DataFrame,
    predictor_frame: pd.DataFrame,
    as_of: str | None = None,
) -> pd.DataFrame:
    """Reconstruct every forecast origin independently; ``as_of`` is an optional ceiling."""
    config = load_config(config_path)
    target_source = target_frame[target_frame["series_id"] == config.target].copy()
    if target_source.empty:
        raise ValueError(f"Unresolved target: {config.target}")
    actual_level = _first_release_actuals(target_source, config.target)
    actual = actual_level.pct_change()
    ceiling = pd.Timestamp(as_of) if as_of is not None else None
    ceiling = (
        ceiling.tz_localize("UTC") if ceiling is not None and ceiling.tzinfo is None else ceiling
    )
    records: list[dict[str, object]] = []

    for cutoff_label in config.cutoffs:
        cutoffs = forecast_cutoffs(target_source, cutoff_label)
        for month, cutoff in cutoffs.items():
            month = pd.Timestamp(month).to_period("M").to_timestamp()
            if ceiling is not None and cutoff > ceiling:
                continue
            if pd.isna(actual.get(month)):
                continue
            for pit_mode in config.pit_modes:
                target_pit = get_target_as_of(target_source, config.target, cutoff, pit_mode)
                target = _monthly_level(target_pit).pct_change()
                if len(target.loc[target.index < month].dropna()) < config.minimum_train_months:
                    continue
                for predictor_id in config.predictors:
                    predictor_pit = get_predictor_as_of(
                        predictor_frame, predictor_id, cutoff, pit_mode
                    )
                    for feature in config.features:
                        values = feature_series_as_of(predictor_pit, cutoff, feature, month)
                        for order in config.ar_orders:
                            benchmark_names = (
                                "historical_mean",
                                "last_observation",
                                "AR1",
                                "AR2",
                                "AR3",
                                "AR6",
                                "AR12",
                            )
                            for predictor_lag in config.predictor_lags:
                                try:
                                    validate_model_inputs(
                                        target.loc[target.index < month],
                                        values.loc[values.index < month],
                                        target_series_id=config.target,
                                        cutoff=cutoff,
                                        availability=predictor_pit["available_at"],
                                        minimum_months=config.minimum_train_months,
                                        max_nan_fraction=config.max_nan_fraction,
                                    )
                                    forecast, n_train = _row_for_origin(
                                        target,
                                        values,
                                        month,
                                        order,
                                        predictor_lag,
                                        config.minimum_train_months,
                                    )
                                except ValueError as exc:
                                    if "Insufficient train sample" in str(
                                        exc
                                    ) or "incomplete" in str(exc):
                                        continue
                                    raise
                                observed = float(actual.loc[month])
                                error = forecast - observed
                                for benchmark_name in benchmark_names:
                                    try:
                                        benchmark_forecast, _ = _benchmark(
                                            target,
                                            month,
                                            benchmark_name,
                                            config.minimum_train_months,
                                        )
                                    except ValueError as exc:
                                        if "Insufficient" in str(exc) or "incomplete" in str(exc):
                                            continue
                                        raise
                                    benchmark_error = benchmark_forecast - observed
                                    records.append(
                                        {
                                            "target": config.target,
                                            "forecast_month": month.date().isoformat(),
                                            "forecast_timestamp": cutoff.isoformat(),
                                            "cutoff": cutoff_label,
                                            "pit_mode": pit_mode,
                                            "predictor": predictor_id,
                                            "feature": feature,
                                            "predictor_lag": predictor_lag,
                                            "ar_order": order,
                                            "benchmark": benchmark_name,
                                            "n_train": n_train,
                                            "forecast": forecast,
                                            "actual": observed,
                                            "error": error,
                                            "benchmark_forecast": benchmark_forecast,
                                            "benchmark_error": benchmark_error,
                                        }
                                    )
    return pd.DataFrame.from_records(records)


def summarize_results(results: pd.DataFrame) -> pd.DataFrame:
    """Summarise model rows without mixing strict and reconstructed scores."""
    keys = [
        "target",
        "cutoff",
        "pit_mode",
        "predictor",
        "feature",
        "predictor_lag",
        "ar_order",
        "benchmark",
    ]
    rows: list[dict[str, object]] = []
    for key, group in results.groupby(keys, dropna=False):
        error = group["error"].astype(float)
        benchmark_error = group["benchmark_error"].astype(float)
        rmse = float(np.sqrt(np.mean(error**2)))
        benchmark_rmse = float(np.sqrt(np.mean(benchmark_error**2)))
        mae = float(np.mean(np.abs(error)))
        benchmark_mae = float(np.mean(np.abs(benchmark_error)))
        rows.append(
            dict(
                zip(keys, key, strict=True),
                n_predictions=len(group),
                RMSE=rmse,
                MAE=mae,
                bias=float(error.mean()),
                directional_accuracy=float(
                    np.mean(np.sign(group["forecast"]) == np.sign(group["actual"]))
                ),
                benchmark_RMSE=benchmark_rmse,
                benchmark_MAE=benchmark_mae,
                relative_RMSE=rmse / benchmark_rmse,
                RMSE_improvement=1 - rmse / benchmark_rmse,
                MAE_improvement=1 - mae / benchmark_mae,
            )
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--target-csv", required=True)
    parser.add_argument("--predictor-csv", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_from_frames(
        args.config,
        pd.read_csv(args.target_csv),
        pd.read_csv(args.predictor_csv),
        args.as_of,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    summarize_results(result).to_csv(output.with_name(f"{output.stem}_summary.csv"), index=False)
    output.with_suffix(".json").write_text(
        json.dumps(
            {"config": args.config, "as_of_ceiling": args.as_of, "rows": len(result)},
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
