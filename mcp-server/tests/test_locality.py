"""Locality normalisation on a small synthetic index modelled on real pool spellings."""

import pytest

from fdp_mcp.locality import LocalityIndex, clean, clean_postcode

COUNTS = [
    ("Berlin", "10115", 50), ("Berlin", "10551", 30), ("Berlin-Mitte", "10115", 2),
    ("Berlin- Tempelhof", "12101", 1), ("Berl Berlin", "10115", 1),
    ("Frankfurt am Main", "60311", 20), ("Frankfurt", "60311", 10), ("Frankfurt/M.", "60311", 5),
    ("Frankfurt (Oder)", "15230", 4), ("Frankfurt a. d. Oder", "15230", 3),
    ("Castrop-Rauxel", "44575", 40), ("Glauchau", "08371", 3), ("Köln", "50667", 30), ("Köln-Porz", "51143", 3),
    ("Mülheim an der Ruhr", "45468", 31), ("Mülheim Ruhr", "45468", 2),
]


@pytest.fixture(scope="module")
def index():
    return LocalityIndex(COUNTS)


@pytest.mark.parametrize("raw, expected", [
    ("Berlin- Tempelhof", "Berlin-Tempelhof"),
    ("  Berlin  -  Mitte ", "Berlin-Mitte"),
    ("Frankfurt(Oder)", "Frankfurt (Oder)"),
    ("Frankfurt/M.", "Frankfurt am Main"),
    ("Frankfurt a. M.", "Frankfurt am Main"),
    ("Frankfurt a. d. Oder", "Frankfurt (Oder)"),
    ("Mülheim Ruhr", "Mülheim an der Ruhr"),
])
def test_clean(raw, expected):
    assert clean(raw) == expected


def test_clean_postcode():
    assert clean_postcode("8371") == "08371"
    assert clean_postcode("10115") == "10115"
    assert clean_postcode("1011") == "01011"
    assert clean_postcode("abc") is None


@pytest.mark.parametrize("locality, postcode, city, district", [
    ("Berlin- Tempelhof", None, "Berlin", "Tempelhof"),
    ("Berl Berlin", "10115", "Berlin", None),           # typo fixed via postcode
    ("Glachau", "8371", "Glauchau", None),              # typo + lost leading zero
    ("Frankfurt", "60311", "Frankfurt am Main", None),  # ambiguous name resolved by postcode
    ("Frankfurt", "15230", "Frankfurt (Oder)", None),
    ("Castrop-Rauxel", None, "Castrop-Rauxel", None),   # hyphenated city stays whole
    ("Köln-Porz", None, "Köln", "Porz"),
])
def test_normalize(index, locality, postcode, city, district):
    result = index.normalize(locality, postcode)
    assert (result.city, result.district) == (city, district)


def test_ambiguous_without_postcode(index):
    result = index.normalize("Frankfurt")
    assert any("Ambiguous" in note for note in result.notes)


def test_conflicting_postcode_is_flagged(index):
    result = index.normalize("Köln", "10115")
    assert result.city == "Köln"
    assert any("Conflicts with postcode 10115" in note for note in result.notes)


def test_variants_fold_all_berlin_spellings(index):
    variants = index.variants("Berlin")
    assert variants["distinct_spellings"] == 4
    assert variants["addresses"] == 84
    assert {d["district"] for d in variants["districts"]} == {"Mitte", "Tempelhof"}
