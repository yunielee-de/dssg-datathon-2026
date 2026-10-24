"""Offline tests: geo helpers, SPARQL escaping, CSV backend. No network needed."""

import pytest

from fdp_mcp import quality
from fdp_mcp.geo import bounding_box, haversine_km
from fdp_mcp.repository import DEFAULT_SNAPSHOT_DIR
from fdp_mcp.repository.csv import CsvRepository
from fdp_mcp.repository.sparql import check_iri, literal


def test_haversine_berlin_hamburg():
    assert haversine_km(52.5200, 13.4050, 53.5511, 9.9937) == pytest.approx(255, abs=3)


def test_bounding_box_contains_radius():
    south, north, west, east = bounding_box(52.52, 13.405, 5)
    assert haversine_km(52.52, 13.405, north, 13.405) == pytest.approx(5, rel=0.01)
    assert haversine_km(52.52, 13.405, 52.52, east) == pytest.approx(5, rel=0.01)
    assert south < 52.52 < north and west < 13.405 < east


def test_literal_escapes_injection():
    assert literal('a" } DROP ALL #') == '"a\\" } DROP ALL #"'
    assert literal("back\\slash\nline") == '"back\\\\slash\\nline"'


@pytest.mark.parametrize(
    "bad", ["https://evil.example/x", "https://civic-data.de/federated-directory#org-1> } #", ""]
)
def test_check_iri_rejects_foreign_or_malformed(bad):
    with pytest.raises(ValueError):
        check_iri(bad)


@pytest.fixture(scope="module")
def csv_repo():
    return CsvRepository(DEFAULT_SNAPSHOT_DIR)


def test_csv_search_city_prefix(csv_repo):
    results = csv_repo.search_facilities(locality="Berlin", limit=500)
    assert results
    assert all(f.address.locality.lower().startswith("berlin") for f in results)


def test_csv_get_facility_with_services(csv_repo):
    facility = csv_repo.get_facility("https://civic-data.de/federated-directory#org-34e986356c61")
    assert facility is not None
    assert len(facility.services) == 2


def test_csv_get_facility_unknown(csv_repo):
    assert csv_repo.get_facility("https://civic-data.de/federated-directory#org-doesnotexist") is None


def test_quality_score_weights():
    all_ok = {k: True for k in quality.CHECK_KEYS}
    assert quality.score(all_ok) == 0
    only_hours_missing = {**all_ok, "opening_hours": False}
    assert quality.score(only_hours_missing) == 2
    unreachable = {**all_ok, "telephone": False, "email": False, "homepage": False}
    assert quality.score(unreachable) == 3 + 1 + 1 + quality.NO_CONTACT_PENALTY


def test_recommended_actions_ordered_by_impact():
    passing = {k: 100 for k in quality.CHECK_KEYS} | {"telephone": 90, "opening_hours": 10, "email": 50}
    actions = quality.recommended_actions(100, passing)
    # impacts: hours 90 x 2 = 180, e-mail 50 x 1 = 50, phone 10 x 3 = 30
    assert [a["action"] for a in actions] == ["Add opening hours", "Add an e-mail address", "Add a phone number"]
    with pytest.raises(ValueError):
        quality.resolve_source("unknown-source")


def test_csv_quality_summary_and_ranking(csv_repo):
    summary = csv_repo.quality_summary()
    assert summary.total == len(csv_repo.facilities)
    assert all(0 <= n <= summary.total for n in summary.passing.values())
    records = csv_repo.records_to_fix(limit=5)
    scores = [r.score for r in records]
    assert scores == sorted(scores, reverse=True)
    with pytest.raises(ValueError):
        csv_repo.records_to_fix(source="caritas")


def test_csv_postcode_centroid_and_bounds(csv_repo):
    centre = csv_repo.postcode_centroid("13407")
    assert centre is not None
    nearby = csv_repo.facilities_in_bounds(*bounding_box(*centre, 2))
    assert nearby
