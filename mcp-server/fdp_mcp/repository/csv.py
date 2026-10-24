"""Offline backend: reads the CSV snapshot in data/snapshot/.

The snapshot is a small sample of the pool (≈180 facilities). Use it for
offline development, tests, and as a demo fallback if the endpoint is down.
"""

from pathlib import Path

import pandas as pd

import re
from collections import Counter

from fdp_mcp import quality
from fdp_mcp.models import Address, Facility, QualityRecord, QualitySummary, Service
from fdp_mcp.repository import IN_BOUNDS_LIMIT

POSTCODE = re.compile(r"^[0-9]{5}$")


def _clean(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _float(value) -> float | None:
    try:
        return float(value) if _clean(value) is not None else None
    except ValueError:
        return None


class CsvRepository:
    name = "csv"

    def __init__(self, data_dir: Path):
        read = lambda stem: pd.read_csv(data_dir / f"{stem}.csv", dtype=str, encoding="utf-8")
        self.facilities = read("einrichtungSchema")
        self.services = read("angebotSchema")
        self.addresses = {
            row["iri"]: Address(
                street=_clean(row["schema:streetAddress"]),
                postal_code=_clean(row["schema:postalCode"]),
                locality=_clean(row["schema:addressLocality"]),
                latitude=_float(row["schema:latitude"]),
                longitude=_float(row["schema:longitude"]),
            )
            for _, row in read("adresseSchema").iterrows()
        }

    # ------------------------------------------------------------------
    # Repository protocol
    # ------------------------------------------------------------------

    def search_facilities(self, text=None, postal_code=None, locality=None, limit=20):
        results = []
        for _, row in self.facilities.iterrows():
            address = self.addresses.get(row["schema:address"])
            if text:
                haystack = f"{_clean(row['schema:name']) or ''} {_clean(row.get('schema:description')) or ''}"
                if text.lower() not in haystack.lower():
                    continue
            if postal_code and (not address or address.postal_code != postal_code.strip()):
                continue
            if locality and (
                not address
                or not (address.locality or "").lower().startswith(locality.strip().lower())
            ):
                continue
            results.append(self._summary(row, address))
        results.sort(key=lambda f: (f.name or "").lower())
        return results[:limit]

    def get_facility(self, iri):
        match = self.facilities[self.facilities["iri"] == iri]
        if match.empty:
            return None
        row = match.iloc[0]
        facility = self._summary(row, self.addresses.get(row["schema:address"]))
        facility.email = [_clean(row["schema:email"])] if _clean(row["schema:email"]) else []
        facility.homepage = _clean(row["foaf:homepage"]) or _clean(row["schema:mainEntityOfPage"])
        facility.category = _clean(row["schema:category"])
        facility.opening_hours = [_clean(row["schema:openingHours"])] if _clean(row["schema:openingHours"]) else []
        facility.accessibility = _clean(row["schema:accessibilitySummary"])
        offered = self.services[self.services["schema:provider"] == iri]
        facility.services = [
            Service(
                iri=s["iri"],
                name=_clean(s["schema:name"]),
                category=_clean(s["schema:category"]),
                audience=_clean(s["schema:audience"]),
            )
            for _, s in offered.iterrows()
        ]
        return facility

    def facilities_in_bounds(self, south, north, west, east, text=None, limit=IN_BOUNDS_LIMIT):
        results = []
        for _, row in self.facilities.iterrows():
            address = self.addresses.get(row["schema:address"])
            if not address or address.latitude is None or address.longitude is None:
                continue
            if text and text.lower() not in (_clean(row["schema:name"]) or "").lower():
                continue
            if south <= address.latitude <= north and west <= address.longitude <= east:
                results.append(self._summary(row, address))
        return results[:limit]

    def postcode_centroid(self, postal_code):
        points = [
            (a.latitude, a.longitude)
            for a in self.addresses.values()
            if a.postal_code == postal_code.strip() and a.latitude is not None and a.longitude is not None
        ]
        if not points:
            return None
        return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)

    def quality_summary(self, source=None, locality=None, postal_code=None):
        scoped = self._quality_scope(source, locality, postal_code)
        patterns = Counter(tuple(quality.missing_labels(ok)) for _, _, ok in scoped)
        return QualitySummary(
            total=len(scoped),
            passing={k: sum(ok[k] for _, _, ok in scoped) for k in quality.CHECK_KEYS},
            gap_patterns=[
                {"missing": list(missing), "records": n} for missing, n in patterns.most_common(8)
            ],
        )

    def records_to_fix(self, source=None, locality=None, postal_code=None, limit=20):
        scoped = self._quality_scope(source, locality, postal_code)
        records = [
            QualityRecord(
                iri=row["iri"],
                name=_clean(row["schema:name"]),
                locality=address.locality if address else None,
                postal_code=address.postal_code if address else None,
                score=quality.score(ok),
                missing=quality.missing_labels(ok),
            )
            for row, address, ok in scoped
        ]
        records.sort(key=lambda r: (-r.score, r.iri))
        return records[:limit]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _quality_scope(self, source, locality, postal_code):
        """(row, address, ok-flags) for every facility in scope."""

        if quality.resolve_source(source):
            raise ValueError("The CSV snapshot has no source attribution; use the live (sparql) backend.")
        scoped = []
        for _, row in self.facilities.iterrows():
            address = self.addresses.get(row["schema:address"])
            if postal_code and (not address or address.postal_code != postal_code.strip()):
                continue
            if locality and (
                not address
                or not (address.locality or "").lower().startswith(locality.strip().lower())
            ):
                continue
            hours = _clean(row["schema:openingHours"])
            ok = {
                "telephone": _clean(row["schema:telephone"]) is not None,
                "coordinates": bool(address and address.latitude is not None),
                "opening_hours": hours is not None,
                "opening_hours_has_times": hours is None or any(ch.isdigit() for ch in hours),
                "postal_code_valid": bool(address and POSTCODE.match(address.postal_code or "")),
                "email": _clean(row["schema:email"]) is not None,
                "homepage": _clean(row["foaf:homepage"]) is not None,
            }
            scoped.append((row, address, ok))
        return scoped

    @staticmethod
    def _summary(row, address: Address | None) -> Facility:
        phone = _clean(row["schema:telephone"])
        return Facility(
            iri=row["iri"],
            name=_clean(row["schema:name"]),
            address=address,
            telephone=[phone] if phone else [],
        )
