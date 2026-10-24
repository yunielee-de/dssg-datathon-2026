"""Tests against the live SPARQL endpoint. Skipped with: pytest -m "not live"."""

import pytest

from fdp_mcp.repository import DEFAULT_SPARQL_ENDPOINT
from fdp_mcp.repository.sparql import SparqlRepository

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def repo():
    return SparqlRepository(DEFAULT_SPARQL_ENDPOINT)


def test_search_by_keyword_and_city(repo):
    results = repo.search_facilities(text="schuldner", locality="Berlin", limit=10)
    assert results
    assert all(f.address.locality.lower().startswith("berlin") for f in results)


def test_get_facility_roundtrip(repo):
    first = repo.search_facilities(text="sucht", limit=1)[0]
    facility = repo.get_facility(first.iri)
    assert facility is not None and facility.name


def test_postcode_centroid_in_berlin(repo):
    lat, lon = repo.postcode_centroid("10551")
    assert 52.4 < lat < 52.6 and 13.2 < lon < 13.5


def test_bounds_keyword_filter(repo):
    results = repo.facilities_in_bounds(52.40, 52.65, 13.10, 13.75, text="sucht", limit=200)
    assert results
    assert all("sucht" in f.name.lower() for f in results)


def test_bounds_returns_coordinates(repo):
    results = repo.facilities_in_bounds(52.50, 52.54, 13.36, 13.43, limit=20)
    assert results
    assert all(52.50 <= f.address.latitude <= 52.54 for f in results)
