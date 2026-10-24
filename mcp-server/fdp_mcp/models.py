"""Plain data objects shared by every repository backend and the MCP tools."""

from dataclasses import asdict, dataclass, field


@dataclass
class Address:
    street: str | None = None
    postal_code: str | None = None
    locality: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class Service:
    iri: str
    name: str | None = None
    category: str | None = None
    audience: str | None = None


@dataclass
class Facility:
    iri: str
    name: str | None = None
    address: Address | None = None
    telephone: list[str] = field(default_factory=list)
    email: list[str] = field(default_factory=list)
    homepage: str | None = None
    category: str | None = None
    opening_hours: list[str] = field(default_factory=list)
    description: str | None = None
    accessibility: str | None = None
    services: list[Service] = field(default_factory=list)
    # Filled in by find_nearest only.
    distance_km: float | None = None


@dataclass
class QualityRecord:
    iri: str
    name: str | None
    locality: str | None
    postal_code: str | None
    score: int
    missing: list[str]
    sources: list[str] = field(default_factory=list)


@dataclass
class QualitySummary:
    total: int
    # check key -> number of records passing it
    passing: dict[str, int]
    # most common combinations of failed checks: {"missing": [...], "records": n}
    gap_patterns: list[dict]


def to_dict(obj) -> dict:
    """Convert a dataclass to a dict, dropping empty values to save LLM context."""

    def prune(value):
        if isinstance(value, dict):
            return {k: prune(v) for k, v in value.items() if v not in (None, [], "", {})}
        if isinstance(value, list):
            return [prune(v) for v in value]
        return value

    return prune(asdict(obj))
