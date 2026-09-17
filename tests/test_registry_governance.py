from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_STATUSES = {
    "implemented_verified",
    "implementation_pr_open",
    "implementation_branch",
    "planned",
    "candidate",
    "blocked",
    "blocked_license",
}
AUTOMATION_STATUSES = {
    "implemented",
    "not_implemented",
    "blocked",
    "blocked_license",
}


def _rows(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_registry_keys_and_statuses_are_unique_and_known() -> None:
    collectors = _rows("collector_registry.csv")
    sources = _rows("source_registry.csv")

    assert len({row["source_family"] for row in collectors}) == len(collectors)
    assert len({row["source_id"] for row in sources}) == len(sources)
    assert {row["status"] for row in collectors} <= COLLECTOR_STATUSES
    assert {row["automation_status"] for row in sources} <= AUTOMATION_STATUSES


def test_license_blocked_sources_have_no_predictor_contract() -> None:
    blocked = {
        row["source_family"]
        for row in _rows("collector_registry.csv")
        if row["status"] == "blocked_license"
    }
    predictor_ids = {row["predictor_series_id"].lower() for row in _rows("predictor_map.csv")}

    assert blocked == {"brc", "cbi"}
    assert not any(predictor.startswith(("brc_", "cbi_")) for predictor in predictor_ids)
