"""Data access layer.

Tools talk only to the Repository protocol, so the backend (live SPARQL endpoint
or offline CSV snapshot) can be swapped with the FDP_BACKEND env variable.
"""

import os
from pathlib import Path
from typing import Protocol

from fdp_mcp.models import Facility, QualityRecord, QualitySummary

DEFAULT_SPARQL_ENDPOINT = "https://sosuse.correlaid.org/directory/sparql"
DEFAULT_SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "snapshot"
# Upper bound for candidates fetched before distance sorting; hitting it means results may be incomplete.
IN_BOUNDS_LIMIT = 2000


class Repository(Protocol):
    name: str

    def search_facilities(
        self,
        text: str | None = None,
        postal_code: str | None = None,
        locality: str | None = None,
        limit: int = 20,
    ) -> list[Facility]:
        """Facilities whose name or description contains text, filtered by postcode/locality."""

    def get_facility(self, iri: str) -> Facility | None:
        """One facility with full details and linked services."""

    def facilities_in_bounds(
        self,
        south: float,
        north: float,
        west: float,
        east: float,
        text: str | None = None,
        limit: int = IN_BOUNDS_LIMIT,
    ) -> list[Facility]:
        """Facilities whose address coordinates fall inside the box (and whose name contains text)."""

    def postcode_centroid(self, postal_code: str) -> tuple[float, float] | None:
        """Mean coordinates of all pool addresses with this postcode."""

    def quality_summary(
        self, source: str | None = None, locality: str | None = None, postal_code: str | None = None
    ) -> QualitySummary:
        """How many facilities in scope pass each quality check (see fdp_mcp.quality)."""

    def records_to_fix(
        self,
        source: str | None = None,
        locality: str | None = None,
        postal_code: str | None = None,
        limit: int = 20,
    ) -> list[QualityRecord]:
        """Facilities in scope ranked by quality score, worst first."""

    def locality_counts(self) -> list[tuple[str, str | None, int]]:
        """(locality, postcode, number of addresses) for every combination in the pool."""

    def facilities_in_postcodes(self, postal_codes: list[str]) -> list[dict]:
        """Pool facilities in these postcodes, for duplicate checks:
        [{"iri", "name", "postal_code", "telephone": [...], "email": [...]}]."""


def get_repository() -> Repository:
    backend = os.environ.get("FDP_BACKEND", "sparql").lower()
    if backend == "csv":
        from fdp_mcp.repository.csv import CsvRepository

        return CsvRepository(Path(os.environ.get("FDP_SNAPSHOT_DIR", DEFAULT_SNAPSHOT_DIR)))
    if backend == "sparql":
        from fdp_mcp.repository.sparql import SparqlRepository

        return SparqlRepository(os.environ.get("FDP_SPARQL_ENDPOINT", DEFAULT_SPARQL_ENDPOINT))
    raise ValueError(f"Unknown FDP_BACKEND {backend!r}; use 'sparql' or 'csv'")
