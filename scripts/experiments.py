"""Reproducible CLI for one-predictor expanding-window experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.config import load_config
from scripts.evaluation import (
    benchmark_forecasts,
    compare_to_benchmark,
    expanding_forecast,
    metrics,
)
from scripts.features import aggregate_monthly, transformations
from scripts.point_in_time import get_predictor_as_of


def run_from_frames(
    config_path: str | Path,
    target_frame: pd.DataFrame,
    predictor_frame: pd.DataFrame,
    as_of: str,
) -> pd.DataFrame:
    """Run comparable configs against supplied persisted-contract extracts."""
    config = load_config(config_path)
    target_rows = target_frame[target_frame["series_id"] == config.target].copy()
    target_rows["reference_date"] = pd.to_datetime(target_rows["reference_date"])
    target = target_rows.sort_values(["reference_date", "vintage_date"]).drop_duplicates("reference_date", keep="last")
    target_level = pd.Series(target["value"].to_numpy(dtype=float), index=target["reference_date"])
    target_mom = target_level.pct_change().dropna()
    records: list[dict[str, object]] = []
    for pit_mode in config.pit_modes:
        for predictor_id in config.predictors:
            pit = get_predictor_as_of(predictor_frame, predictor_id, as_of, pit_mode)
            for feature in config.features:
                if feature not in {"monthly_mean", "monthly_last", "monthly_median", "monthly_min", "monthly_max"}:
                    continue
                level = aggregate_monthly(pit, feature)
                candidates = {feature: level, f"{feature}_mom": transformations(level)["mom"], f"{feature}_yoy": transformations(level)["yoy"]}
                for feature_name, values in candidates.items():
                    for order in config.ar_orders:
                        benchmarks = benchmark_forecasts(target_mom, config.minimum_train_months, (order,))
                        benchmark_name = f"AR{order}"
                        benchmark_score = metrics(target_mom, benchmarks[benchmark_name])
                        for lag in config.predictor_lags:
                            forecast = expanding_forecast(target_mom, values, order, lag, config.minimum_train_months)
                            if len(forecast) < config.minimum_oos_predictions:
                                continue
                            score = metrics(target_mom, forecast)
                            comparison = compare_to_benchmark(score, benchmark_score)
                            records.append(
                                {
                                    "target": config.target,
                                    "predictor": predictor_id,
                                    "feature": feature_name,
                                    "cutoff": "AS_OF",
                                    "ar_order": order,
                                    "predictor_lag": lag,
                                    "train_start": str(target_mom.index.min().date()),
                                    "oos_start": str(forecast.index.min().date()),
                                    "n_predictions": int(score["n_predictions"]),
                                    "rmse": score["rmse"],
                                    "mae": score["mae"],
                                    "bias": score["bias"],
                                    "directional_accuracy": score["directional_accuracy"],
                                    "benchmark": benchmark_name,
                                    "benchmark_rmse": benchmark_score["rmse"],
                                    "rmse_improvement": comparison["rmse_improvement"],
                                    "benchmark_mae": benchmark_score["mae"],
                                    "mae_improvement": comparison["mae_improvement"],
                                    "pit_mode": pit_mode,
                                }
                            )
    return pd.DataFrame.from_records(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--target-csv", required=True)
    parser.add_argument("--predictor-csv", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_from_frames(
        args.config, pd.read_csv(args.target_csv), pd.read_csv(args.predictor_csv), args.as_of
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    output.with_suffix(".json").write_text(
        json.dumps({"config": args.config, "as_of": args.as_of, "rows": len(result)}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
