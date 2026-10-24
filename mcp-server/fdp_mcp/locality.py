"""Locality normalisation, using the pool's own addresses as the reference.

Naive hyphen splitting is wrong: "Berlin-Mitte" is Berlin + district, but
"Castrop-Rauxel" is one city, and "Frankfurt" alone may be Frankfurt am Main
or Frankfurt (Oder). So:

1. With a postcode: the most common city among pool addresses with that
   postcode is canonical. This also catches typos ("Glachau" for 08371 -> Glauchau).
2. Without one: split only when the prefix is a city that is frequent in the pool,
   and flag names that are ambiguous without a postcode.
"""

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches

# A locality needs this many addresses in the pool to count as a known city.
MIN_CITY_COUNT = 3
# Similarity above which a differing spelling is treated as the postcode's city.
SAME_CITY_SIMILARITY = 0.6


# Official names of cities with a river or region suffix, which spelling rules cannot derive.
# Keys are casefolded spellings seen in the pool. Extend as new variants show up.
OFFICIAL_NAMES = {
    "frankfurt a. d. oder": "Frankfurt (Oder)",
    "frankfurt an der oder": "Frankfurt (Oder)",
    "frankfurt/oder": "Frankfurt (Oder)",
    "mülheim ruhr": "Mülheim an der Ruhr",
    "mülheim a. d. ruhr": "Mülheim an der Ruhr",
    "mülheim/ruhr": "Mülheim an der Ruhr",
    "halle/saale": "Halle (Saale)",
    "halle a. d. saale": "Halle (Saale)",
    "freiburg i. br.": "Freiburg im Breisgau",
    "freiburg i.br.": "Freiburg im Breisgau",
}


@dataclass
class NormalizedLocality:
    input: str
    cleaned: str
    city: str
    district: str | None = None
    postal_code: str | None = None
    method: str = "unchanged"  # postcode | known_city | split | fuzzy | unchanged
    confidence: str = "low"  # high | medium | low
    notes: list[str] = field(default_factory=list)


def clean(value: str) -> str:
    """Fix whitespace, hyphen spacing, bracket spacing and common Main abbreviations."""

    s = unicodedata.normalize("NFC", value)
    s = re.sub(r"\s+", " ", s).strip(" ,;")
    s = re.sub(r"\s*-\s*", "-", s)  # "Berlin - Mitte", "Berlin- Tempelhof" -> "Berlin-Mitte"
    s = re.sub(r"\s*\(\s*", " (", s)  # "Frankfurt(Oder)" -> "Frankfurt (Oder)"
    s = re.sub(r"\s*\)", ")", s)
    s = re.sub(r"(\s*/\s*M(ain)?\.?|\s+a\.\s*M\.?)$", " am Main", s)  # Frankfurt/M., Frankfurt a. M.
    s = s.strip()
    return OFFICIAL_NAMES.get(s.casefold(), s)


def clean_postcode(value: str | None) -> str | None:
    if not value:
        return None
    digits = value.strip()
    if re.fullmatch(r"[0-9]{4}", digits):
        return "0" + digits  # leading zero lost (e.g. Saxony 0xxxx)
    return digits if re.fullmatch(r"[0-9]{5}", digits) else None


def _split(cleaned: str, city: str) -> str | None:
    """District part if cleaned is '<city>-<District>' or '<city> <District>', else None."""

    if len(cleaned) <= len(city) or not cleaned.casefold().startswith(city.casefold()):
        return None
    rest = cleaned[len(city):]
    if rest.startswith("-") and len(rest) > 1:
        return rest[1:].strip()
    # Space split only before an uppercase word: keeps "Frankfurt am Main" intact.
    if rest.startswith(" ") and rest[1:2].isupper():
        return rest[1:].strip()
    return None


class LocalityIndex:
    def __init__(self, counts: list[tuple[str, str | None, int]]):
        """counts: (raw locality, raw postcode or None, number of addresses)."""

        self.raw_counts = counts
        totals: Counter[str] = Counter()
        self.by_postcode: dict[str, Counter[str]] = defaultdict(Counter)
        for locality, postcode, n in counts:
            cleaned = clean(locality)
            totals[cleaned] += n
            pc = clean_postcode(postcode)
            if pc:
                self.by_postcode[pc][cleaned] += n

        frequent = {loc for loc, n in totals.items() if n >= MIN_CITY_COUNT}
        # A frequent "<City>-<District>" is still a district of City, not a city of its own.
        self.cities = {
            loc for loc in frequent
            if not any(_split(loc, other) for other in frequent if other != loc)
        }
        self._cities_by_length = sorted(self.cities, key=len, reverse=True)
        self._postcode_city_cache: dict[str, str | None] = {}
        self._city_cache: dict[str, tuple[str, str | None, str]] = {}

    # ------------------------------------------------------------------

    def postcode_city(self, postal_code: str) -> str | None:
        """Most common city (districts folded in) among addresses with this postcode."""

        if postal_code not in self._postcode_city_cache:
            candidates = self.by_postcode.get(postal_code)
            folded: Counter[str] = Counter()
            for loc, n in (candidates or {}).items():
                folded[self._city_without_postcode(loc)[0]] += n
            self._postcode_city_cache[postal_code] = folded.most_common(1)[0][0] if folded else None
        return self._postcode_city_cache[postal_code]

    def normalize(self, locality: str, postal_code: str | None = None) -> NormalizedLocality:
        cleaned = clean(locality)
        result = NormalizedLocality(input=locality, cleaned=cleaned, city=cleaned)
        if cleaned != locality:
            result.notes.append(f"Cleaned spelling: {locality!r} -> {cleaned!r}")

        pc = clean_postcode(postal_code)
        if postal_code and pc != postal_code.strip():
            result.notes.append(
                f"Postcode {postal_code!r} is not a valid 5-digit postcode"
                + (f"; assuming {pc}" if pc else "")
            )
        result.postal_code = pc

        reference = self.postcode_city(pc) if pc else None
        if reference:
            district = _split(cleaned, reference)
            if cleaned.casefold() == reference.casefold() or district:
                result.city, result.district = reference, district
                result.method, result.confidence = "postcode", "high"
                return result
            own_city = self._city_without_postcode(cleaned)[0]
            similarity = SequenceMatcher(None, own_city.casefold(), reference.casefold()).ratio()
            if similarity >= SAME_CITY_SIMILARITY:
                result.city, result.method, result.confidence = reference, "postcode", "medium"
                result.notes.append(
                    f"Spelling differs from the usual city for postcode {pc}: {cleaned!r} -> {reference!r}"
                )
                return result
            result.notes.append(
                f"Conflicts with postcode {pc}, whose addresses are usually in {reference!r}. "
                "Check the postcode or the locality."
            )

        city, district, method = self._city_without_postcode(cleaned)
        result.city, result.district, result.method = city, district, method
        result.confidence = {"known_city": "medium", "split": "medium", "fuzzy": "low"}.get(method, "low")
        if method == "fuzzy":
            result.notes.append(f"Unknown locality; closest known city is {city!r}")
        ambiguous = sorted(
            c for c in self.cities
            if c != city and c.casefold().startswith(city.casefold() + " ") and not _split(c, city)
        )
        if ambiguous:
            result.notes.append(
                f"Ambiguous without a postcode: could also be {', '.join(ambiguous[:3])}"
            )
        return result

    def variants(self, city: str) -> dict:
        """All spellings in the pool that normalise to `city`, with counts."""

        target = clean(city).casefold()
        spellings: Counter[str] = Counter()
        districts: Counter[str] = Counter()
        total = 0
        for locality, postcode, n in self.raw_counts:
            normalized = self.normalize(locality, postcode)
            if normalized.city.casefold() != target:
                continue
            total += n
            spellings[locality] += n
            if normalized.district:
                districts[normalized.district] += n
        return {
            "city": city,
            "addresses": total,
            "distinct_spellings": len(spellings),
            "spellings": [{"locality": s, "addresses": n} for s, n in spellings.most_common()],
            "districts": [{"district": d, "addresses": n} for d, n in districts.most_common()],
        }

    # ------------------------------------------------------------------

    def _city_without_postcode(self, cleaned: str) -> tuple[str, str | None, str]:
        """(city, district, method) using only the list of known cities."""

        if cleaned not in self._city_cache:
            self._city_cache[cleaned] = self._resolve_city(cleaned)
        return self._city_cache[cleaned]

    def _resolve_city(self, cleaned: str) -> tuple[str, str | None, str]:
        if cleaned in self.cities:
            return cleaned, None, "known_city"
        for city in self._cities_by_length:
            district = _split(cleaned, city)
            if district:
                return city, district, "split"
        close = get_close_matches(cleaned, self._cities_by_length, n=1, cutoff=0.88)
        if close:
            return close[0], None, "fuzzy"
        return cleaned, None, "unchanged"
