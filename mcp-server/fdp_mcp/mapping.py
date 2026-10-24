"""Map records from new sources onto the pool's target schema, validate them,
and check whether the pool already contains them.

Target schema (from https://sosuse.correlaid.org/collections):
  einrichtungSchema (facility), adresseSchema (address),
  angebotSchema (service offer), traegerSchema (provider organisation).
Only the fields a new source can realistically fill are modelled here.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from fdp_mcp.locality import LocalityIndex, clean_postcode

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL = re.compile(r"^https?://\S+\.\S+")
# Shelters keep their location secret to protect residents: never geocode, enrich or cross-match them.
CONFIDENTIAL = re.compile(r"frauen\s*\(?schutz\)?\s*haus|frauenhaus|schutzhaus|schutzwohnung|schutzeinrichtung", re.I)
NAME_MATCH_SIMILARITY = 0.85


@dataclass
class MappedAddress:
    streetAddress: str | None = None
    postalCode: str | None = None
    addressLocality: str | None = None
    addressCountry: str = "DE"
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class MappedService:
    name: str
    category: str | None = None
    language: list[str] = field(default_factory=list)
    audience: str | None = None


@dataclass
class MappedFacility:
    """One source record mapped to einrichtung + adresse + angebote + traeger."""

    source: str
    source_id: str
    name: str
    address: MappedAddress = field(default_factory=MappedAddress)
    telephone: list[str] = field(default_factory=list)
    email: list[str] = field(default_factory=list)
    homepage: str | None = None
    description: str | None = None
    category: list[str] = field(default_factory=list)
    accessibilitySummary: str | None = None
    openingHours: list[str] = field(default_factory=list)
    provider_name: str | None = None
    parentOrgClassification: str | None = None
    services: list[MappedService] = field(default_factory=list)
    confidential_location: bool = False
    issues: list[str] = field(default_factory=list)
    pool_match: dict | None = None


def _digits(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return "0" + digits[2:] if digits.startswith("49") else digits


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9äöüß ]", " ", name.casefold()).strip()


# Words that do not identify a facility: filler, legal forms, and umbrella organisations
# (a department of "Caritasverband Leipzig" is not the same facility as the Caritasverband itself).
GENERIC_WORDS = {
    "und", "für", "der", "die", "das", "den", "dem", "von", "im", "in", "am", "e", "v", "ev", "gmbh", "ggmbh", "mbh",
    "caritasverband", "caritas", "diakonie", "diakonisches", "werk", "awo", "arbeiterwohlfahrt",
    "kreisverband", "stadtverband", "landesverband", "bezirksverband", "ortsverein", "erzbistum", "bistum",
    "verbraucherzentrale", "paritätische", "paritätischer", "drk", "landkreis", "stadt", "zentrum",
}


# Organisation words in general ("Musterverband", "Förderverein", "Bürgerstiftung").
ORGANISATION_SUFFIXES = ("verband", "verein", "stiftung", "gesellschaft", "werk")


def _significant_words(key: str, place_words: set[str]) -> set[str]:
    return {
        w for w in key.split()
        if len(w) > 2 and w not in GENERIC_WORDS and w not in place_words and not w.endswith(ORGANISATION_SUFFIXES)
    }


def _same_word(a: str, b: str) -> bool:
    # Compound variants: "jugenddrogenberatung" ~ "jugenddrogenberatungsstelle"
    return a == b or (min(len(a), len(b)) >= 8 and (a.startswith(b) or b.startswith(a)))


def name_similarity(a: str, b: str, place: str | None = None) -> float:
    """Max of character similarity and word containment: the share of the shorter name's
    identifying words (ignoring umbrella organisations and the place name) found in the other."""

    key_a, key_b = _name_key(a), _name_key(b)
    chars = SequenceMatcher(None, key_a, key_b).ratio()
    place_words = set(_name_key(place or "").replace("-", " ").split())
    words_a = _significant_words(key_a, place_words)
    words_b = _significant_words(key_b, place_words)
    if not words_a or not words_b:
        return chars
    shorter, longer = sorted((words_a, words_b), key=len)
    shared = sum(1 for w in shorter if any(_same_word(w, x) for x in longer))
    return max(chars, shared / len(shorter))


def is_confidential(record: MappedFacility) -> bool:
    texts = [record.name, *record.category, *(s.name for s in record.services)]
    return any(CONFIDENTIAL.search(t or "") for t in texts)


def validate(record: MappedFacility, localities: LocalityIndex | None = None) -> MappedFacility:
    """Normalise fields in place and list problems a maintainer should look at."""

    issues = []
    record.name = (record.name or "").strip()
    if not record.name:
        issues.append("missing name")

    record.confidential_location = record.confidential_location or is_confidential(record)
    address = record.address
    raw_pc = address.postalCode
    address.postalCode = clean_postcode(raw_pc)
    if raw_pc and address.postalCode != raw_pc.strip():
        issues.append(f"postcode not 5 digits: {raw_pc!r}" + (f" corrected to {address.postalCode}" if address.postalCode else ""))
    if not address.postalCode:
        issues.append("missing or invalid postcode")

    if record.confidential_location:
        # Keep only what the source chose to publish; drop anything that pinpoints the house.
        address.streetAddress, address.latitude, address.longitude = None, None, None
        issues.append("confidential location: shelter address kept coarse on purpose; do not geocode or enrich")
    elif localities and address.addressLocality:
        normalized = localities.normalize(address.addressLocality, address.postalCode)
        if normalized.city != address.addressLocality:
            issues.append(f"locality normalised: {address.addressLocality!r} -> {normalized.city!r}")
        address.addressLocality = normalized.city
        if not address.streetAddress:
            issues.append("missing street address")

    record.telephone = [t.strip() for t in record.telephone if t and t.strip()]
    record.email = [e.strip() for e in record.email if e and e.strip()]
    bad_emails = [e for e in record.email if not EMAIL.match(e)]
    if bad_emails:
        issues.append(f"invalid e-mail: {bad_emails}")
    if record.homepage and not URL.match(record.homepage):
        issues.append(f"invalid website: {record.homepage!r}")
    if not (record.telephone or record.email or record.homepage):
        issues.append("no contact channel (phone, e-mail or website)")
    if not record.openingHours:
        issues.append("no opening hours")

    record.issues = issues
    return record


def issue_key(issue: str) -> str:
    """Stable issue type for counting: the text before the first colon."""

    return issue.split(":", 1)[0]


def match_against_pool(records: list[MappedFacility], candidates: list[dict]) -> None:
    """Set record.pool_match by comparing with pool facilities in the same postcodes.

    candidates: [{"iri", "name", "postal_code", "telephone": [...], "email": [...]}].
    Status:
      already_in_pool    similar name AND shared phone/e-mail
      same_organisation  shared phone/e-mail only: likely a department or service of an
                         existing facility -> add as an Angebot there, not a new Einrichtung
      possible_duplicate similar name only -> needs a human look
      new                nothing in the same postcode matches
    Confidential records are never cross-matched.
    """

    by_postcode: dict[str, list[dict]] = {}
    for c in candidates:
        by_postcode.setdefault(c["postal_code"], []).append(c)

    for record in records:
        if record.confidential_location:
            record.pool_match = {"status": "not_checked", "reason": "confidential location"}
            continue
        best = None  # (rank, candidate, status, reasons)
        phones = {_digits(t) for t in record.telephone if len(_digits(t)) >= 6}
        emails = {e.casefold() for e in record.email}
        for c in by_postcode.get(record.address.postalCode or "", []):
            reasons = []
            similarity = name_similarity(record.name, c["name"] or "", record.address.addressLocality)
            similar_name = similarity >= NAME_MATCH_SIMILARITY
            if similar_name:
                reasons.append(f"name similarity {similarity:.2f}")
            shared_contact = False
            if phones & {_digits(t) for t in c.get("telephone", [])}:
                reasons.append("same phone")
                shared_contact = True
            if emails & {e.casefold() for e in c.get("email", [])}:
                reasons.append("same e-mail")
                shared_contact = True
            if similar_name and shared_contact:
                rank, status = 3, "already_in_pool"
            elif shared_contact:
                rank, status = 2, "same_organisation"
            elif similar_name:
                rank, status = 1, "possible_duplicate"
            else:
                continue
            if best is None or (rank, len(reasons)) > (best[0], len(best[3])):
                best = (rank, c, status, reasons)
        if best is None:
            record.pool_match = {"status": "new"}
        else:
            _, c, status, reasons = best
            record.pool_match = {"status": status, "iri": c["iri"], "pool_name": c["name"], "reasons": reasons}
