"""DESNZ extractor entrypoint for the standalone collector."""
from __future__ import annotations
from scripts.extract_desnz_road_fuels import collect as _collect
from scripts.govuk import SourceData, build_client

def collect() -> SourceData:
    with build_client() as client:
        return _collect(client)
