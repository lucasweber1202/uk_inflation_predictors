"""Transparent ordinary-least-squares models: AR(p) and AR(p)+one predictor."""

from __future__ import annotations

import numpy as np
import pandas as pd


def design_matrix(target: pd.Series, ar_order: int, predictor: pd.Series | None = None, predictor_lag: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    if ar_order < 0 or predictor_lag < 0:
        raise ValueError("Lags cannot be negative")
    data = pd.DataFrame({"target": target.astype(float)})
    for lag in range(1, ar_order + 1):
        data[f"ar{lag}"] = target.shift(lag)
    if predictor is not None:
        data["predictor"] = predictor.reindex(data.index).shift(predictor_lag)
    data = data.dropna()
    return data.drop(columns="target"), data["target"]


def fit_ols(x: pd.DataFrame, y: pd.Series) -> np.ndarray:
    if len(x) != len(y) or len(y) <= x.shape[1] + 1:
        raise ValueError("Insufficient observations for OLS")
    matrix = np.column_stack([np.ones(len(x)), x.to_numpy(dtype=float)])
    return np.linalg.lstsq(matrix, y.to_numpy(dtype=float), rcond=None)[0]


def predict_ols(coefficients: np.ndarray, row: pd.Series) -> float:
    return float(np.dot(coefficients, np.r_[1.0, row.to_numpy(dtype=float)]))
