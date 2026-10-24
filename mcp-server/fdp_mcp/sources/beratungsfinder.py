"""Adapter for beratungsfinder.de (DAJEB), a nationwide directory of ~14k counselling centres.

Uses the public JSON API behind the website (no login, robots.txt allows crawling).
Request body fields were read from the site's own frontend: take/skip for paging,
location + umkreisKm for a radius search.
"""

import httpx

from fdp_mcp.mapping import MappedAddress, MappedFacility, MappedService

NAME = "beratungsfinder"
HOMEPAGE = "https://beratungsfinder.de"
API = "https://daj-prod-backend-a4gmc7asa8gtaeab.germanywestcentral-01.azurewebsites.net/api/BeratungsstelleSearch"
USER_AGENT = "FederatedDataPool-MCP (DSSG Berlin datathon; dssgber@gmail.com)"
MAX_TAKE = 50


def fetch(location: str | None = None, radius_km: float | None = None, take: int = 10, skip: int = 0) -> dict:
    body: dict = {"take": min(max(take, 1), MAX_TAKE), "skip": max(skip, 0)}
    if location:
        body["location"] = location
        body["umkreisKm"] = radius_km or 10
    response = httpx.post(API, json=body, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.json()


def _labels(items) -> list[str]:
    return [i["label"] for i in items or [] if i.get("label")]


def to_mapped(raw: dict) -> MappedFacility:
    topics = _labels(raw.get("beratungsschwerpunkte"))
    languages = _labels(raw.get("sprachen"))
    formats = _labels(raw.get("beratungsformate"))
    accessibility = _labels(raw.get("barrierefreiheitsangebote"))
    phone = raw.get("telefon1")
    email = raw.get("email")
    description = raw.get("beschreibung") or None
    if formats:
        description = " ".join(filter(None, [description, f"Formats: {', '.join(formats)}."]))
    return MappedFacility(
        source=NAME,
        source_id=raw["id"],
        name=raw.get("name") or "",
        address=MappedAddress(
            streetAddress=raw.get("strasseHausnummer") or None,
            postalCode=raw.get("postleitzahl") or None,
            addressLocality=raw.get("ort") or None,
            latitude=raw.get("latitude"),
            longitude=raw.get("longitude"),
        ),
        telephone=[phone] if phone else [],
        email=[email] if email else [],
        homepage=raw.get("url") or None,
        description=description,
        category=topics,
        accessibilitySummary=", ".join(accessibility) or None,
        provider_name=raw.get("traegerName") or None,
        parentOrgClassification=(raw.get("traegerArt") or {}).get("label"),
        services=[MappedService(name=topic, category=topic, language=languages) for topic in topics],
    )
