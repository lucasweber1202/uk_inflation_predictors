from __future__ import annotations

import pandas as pd
import pytest

from scripts.quality import validate_model_inputs
from scripts.targets import load_target_registry, resolve_target


def test_target_registry_is_unique_and_verified() -> None:
    registry = load_target_registry()
    assert not registry["target_key"].duplicated().any()
    assert resolve_target("fruit", registry)["target_series_id"] == "CPI_COICOP_C0116_D7DA"


def test_pending_target_fails_closed() -> None:
    index = pd.date_range("2020-01-01", periods=30, freq="MS")
    with pytest.raises(ValueError, match="Unresolved"):
        validate_model_inputs(
            pd.Series(range(30), index=index),
            pd.Series(range(30), index=index),
            target_series_id="PENDING_VERIFICATION",
        )
