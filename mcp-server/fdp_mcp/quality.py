"""Data-quality rules shared by every backend.

A record is ranked by how much its gaps hurt someone looking for help:
can they find it (map location), reach it (phone, e-mail, website), and know
when to go (opening hours)? Weights are deliberately simple so providers can
understand why a record ranks high.
"""

from dataclasses import dataclass

# Short source keys -> local name of the source IRI (https://civic-data.de/pipeline#<name>).
SOURCES = {
    "caritas": "caritasSource",
    "dhs": "dhsSource",
    "awo": "awoSource",
    "destatis": "destatisSource",
    "sozialplattform": "sozialplattformSource",
}
SOURCE_BY_IRI_NAME = {name: key for key, name in SOURCES.items()}


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    weight: int
    fix: str


CHECKS = (
    Check("telephone", "phone number", 3, "Add a phone number"),
    Check("coordinates", "map location", 3, "Add a complete street address so it can be geocoded"),
    Check("opening_hours", "opening hours", 2, "Add opening hours"),
    Check("opening_hours_has_times", "opening hours with actual times", 1,
          "Replace opening-hours text that contains no times (e.g. a contact name) with real hours"),
    Check("postal_code_valid", "valid 5-digit postcode", 1,
          "Add or correct the postcode (5 digits; leading zeros are often lost, e.g. 8371 -> 08371)"),
    Check("email", "e-mail address", 1, "Add an e-mail address"),
    Check("homepage", "website", 1, "Add a website"),
)
CHECK_KEYS = tuple(c.key for c in CHECKS)
CONTACT_KEYS = ("telephone", "email", "homepage")
# Extra penalty when there is no way at all to contact the facility.
NO_CONTACT_PENALTY = 5


def resolve_source(source: str | None) -> str | None:
    if source is None:
        return None
    key = source.strip().lower()
    if key not in SOURCES:
        raise ValueError(f"Unknown source {source!r}. Use one of: {', '.join(SOURCES)}")
    return key


def score(ok: dict[str, bool]) -> int:
    """Higher = fix first. `ok` maps check key -> passes."""

    total = sum(c.weight for c in CHECKS if not ok.get(c.key, False))
    if not any(ok.get(k, False) for k in CONTACT_KEYS):
        total += NO_CONTACT_PENALTY
    return total


def missing_labels(ok: dict[str, bool]) -> list[str]:
    return [c.label for c in CHECKS if not ok.get(c.key, False)]


def recommended_actions(total: int, passing: dict[str, int]) -> list[dict]:
    """Aggregate fixes, ordered by impact (weight x records affected)."""

    actions = []
    for check in CHECKS:
        affected = total - passing.get(check.key, 0)
        if affected > 0:
            actions.append({
                "action": check.fix,
                "records_affected": affected,
                "share_affected_pct": round(100 * affected / total, 1) if total else 0.0,
                "impact": affected * check.weight,
            })
    return sorted(actions, key=lambda a: a["impact"], reverse=True)
