"""Mapping, validation and pool matching on synthetic records (no real personal data)."""

from fdp_mcp.locality import LocalityIndex
from fdp_mcp.mapping import MappedAddress, MappedFacility, match_against_pool, name_similarity, validate
from fdp_mcp.sources import beratungsfinder

INDEX = LocalityIndex([("Leipzig", "04109", 40), ("Glauchau", "08371", 3)])

POOL = [
    {"iri": "https://civic-data.de/federated-directory#org-a", "name": "Musterverband Leipzig e.V.",
     "postal_code": "04109", "telephone": ["+49 341 1111111"], "email": ["info@example.org"]},
    {"iri": "https://civic-data.de/federated-directory#org-b", "name": "Jugenddrogenberatungsstelle Beispiel",
     "postal_code": "04109", "telephone": ["0341 2222222"], "email": ["jdb@example.org"]},
    {"iri": "https://civic-data.de/federated-directory#org-c", "name": "Schuldner- und Insolvenzberatung Leipzig",
     "postal_code": "04109", "telephone": ["0341 3333333"], "email": []},
]


def record(name, phone=None, email=None, postcode="04109", locality="Leipzig", street="Beispielstr. 1", **kw):
    return MappedFacility(
        source="test", source_id="1", name=name,
        address=MappedAddress(streetAddress=street, postalCode=postcode, addressLocality=locality),
        telephone=[phone] if phone else [], email=[email] if email else [], **kw,
    )


def test_validate_fixes_postcode_and_locality():
    r = validate(record("Beratung X", phone="0375 1", postcode="8371", locality="Glachau"), INDEX)
    assert r.address.postalCode == "08371" and r.address.addressLocality == "Glauchau"
    assert any("corrected to 08371" in i for i in r.issues)


def test_validate_flags_missing_contact_and_bad_email():
    r = validate(record("Beratung X", email="not-an-email"), INDEX)
    assert any("invalid e-mail" in i for i in r.issues)
    r = validate(record("Beratung Y"), INDEX)
    assert "no contact channel (phone, e-mail or website)" in r.issues


def test_shelter_address_is_kept_coarse_and_never_matched():
    r = validate(record("Frauenhaus Beispielstadt", phone="0341 1111111"), INDEX)
    r.address.latitude = 51.3
    validate(r, INDEX)
    assert r.confidential_location
    assert r.address.streetAddress is None and r.address.latitude is None
    match_against_pool([r], POOL)
    assert r.pool_match["status"] == "not_checked"


def test_match_statuses():
    same = record("Jugenddrogenberatung Beispiel", phone="0341 2222222", email="jdb@example.org")
    dept = record("Migrationsberatung Musterverband Leipzig", phone="0341 1111111", email="info@example.org")
    name_only = record("Insolvenz- und Schuldnerberatung", phone="0341 9999999")
    new = record("Familienberatung Neu", phone="0341 7777777")
    records = [validate(r, INDEX) for r in (same, dept, name_only, new)]
    match_against_pool(records, POOL)
    assert [r.pool_match["status"] for r in records] == [
        "already_in_pool", "same_organisation", "possible_duplicate", "new"]


def test_umbrella_and_place_words_do_not_count():
    assert name_similarity("Beratungsstelle für Flüchtlinge Musterverband Leipzig",
                           "Caritasverband Leipzig e.V.", "Leipzig") < 0.85
    assert name_similarity("Jugenddrogenberatung Beispiel", "Jugenddrogenberatungsstelle Beispiel") == 1.0


def test_beratungsfinder_mapping():
    raw = {
        "id": "abc", "name": "Familienberatung Beispiel", "strasseHausnummer": "Beispielweg 2",
        "postleitzahl": "04109", "ort": "Leipzig", "telefon1": "0341 5555555", "email": "kontakt@example.org",
        "url": "https://example.org", "beschreibung": "", "traegerName": "Beispielträger e.V.",
        "traegerArt": {"label": "Freier nicht-konfessioneller Träger"},
        "beratungsschwerpunkte": [{"label": "Erziehungsberatung"}, {"label": "Paarberatung"}],
        "beratungsformate": [{"label": "Online-Beratung"}], "sprachen": [{"label": "Deutsch"}],
        "barrierefreiheitsangebote": [{"label": "Barrierefreier Zugang zum Gebäude"}],
    }
    m = beratungsfinder.to_mapped(raw)
    assert m.name == "Familienberatung Beispiel" and m.address.postalCode == "04109"
    assert m.category == ["Erziehungsberatung", "Paarberatung"]
    assert [s.name for s in m.services] == ["Erziehungsberatung", "Paarberatung"]
    assert m.services[0].language == ["Deutsch"]
    assert m.provider_name == "Beispielträger e.V." and "Online-Beratung" in m.description
