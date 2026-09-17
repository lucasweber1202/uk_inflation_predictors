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
    "ready_with_environment_gate",
}
AUTOMATION_STATUSES = {
    "implemented",
    "not_implemented",
    "blocked",
    "blocked_license",
    "ready_with_environment_gate",
}
# A source whose only remaining blocker is environment-bound. The collector
# exists, is complete and is tested offline; what is missing is a corporate
# entitlement, the vendor identifiers that can only be confirmed inside it, and
# a live certification run.
ENVIRONMENT_GATED = {"brc", "cbi"}


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
    """A source with no persisted data contract has no predictor rows.

    brc and cbi were both `blocked_license` until 2026-09-17. That status
    asserted that lawful collection was impossible, which conflated the
    publisher's licensing with the desk's access: both are reachable through
    licensed delivery providers the desk already holds. They are now
    `ready_with_environment_gate` and do have predictor rows, so this test
    guards the remaining licence-blocked set — currently empty — rather than
    naming them.
    """
    blocked = {
        row["source_family"]
        for row in _rows("collector_registry.csv")
        if row["status"] == "blocked_license"
    }
    predictor_ids = {row["predictor_series_id"].lower() for row in _rows("predictor_map.csv")}

    assert not blocked & ENVIRONMENT_GATED
    for family in blocked:
        assert not any(predictor.startswith(f"{family}_") for predictor in predictor_ids)


def test_environment_gated_collectors_have_repositories_and_hypotheses() -> None:
    """The registry must not still claim no repository was created."""
    collectors = {row["source_family"]: row for row in _rows("collector_registry.csv")}
    predictors = _rows("predictor_map.csv")

    for family in ENVIRONMENT_GATED:
        row = collectors[family]
        assert row["status"] == "ready_with_environment_gate"
        assert row["repository"] == f"collector_{family}_uk"
        assert "No repository was created" not in row["notes"]
        assert any(
            predictor["predictor_series_id"].lower().startswith(f"{family}_")
            for predictor in predictors
        ), f"{family} is implemented but has no predictor hypotheses"


def test_environment_gated_predictors_are_hypotheses_not_findings() -> None:
    """Nothing may claim predictive power before a live vendor query has run."""
    for row in _rows("predictor_map.csv"):
        family = row["predictor_series_id"].split("_")[0].lower()
        if family not in ENVIRONMENT_GATED:
            continue
        assert row["research_status"] == "not_started", row["predictor_series_id"]
        # A vendor backfill carries no publication timestamp, so the honest
        # point-in-time quality is first_seen, never `official`.
        assert row["point_in_time_quality"] == "first_seen", row["predictor_series_id"]


def test_environment_gated_sources_are_not_marked_implemented() -> None:
    """`implemented` would claim a live certification that has not happened."""
    families = {"brc": "brc_shop_price_monitor", "cbi": "cbi_economic_surveys"}
    sources = {row["source_id"]: row for row in _rows("source_registry.csv")}
    for source_id in families.values():
        assert sources[source_id]["automation_status"] == "ready_with_environment_gate"
