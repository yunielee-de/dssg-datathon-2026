"""Live backend: queries the Federated Data Pool SPARQL endpoint.

The endpoint's default graph is the published (resolved) directory, so the
queries below need no GRAPH clause. Pipeline graphs such as provenance are
only needed for source/explain tools.
"""

import re

import httpx

from fdp_mcp.models import Address, Facility, Service
from fdp_mcp.repository import IN_BOUNDS_LIMIT

SCHEMA = "http://schema.org/"
FOAF = "http://xmlns.com/foaf/0.1/"
PREFIXES = """\
PREFIX schema: <http://schema.org/>
PREFIX org: <http://www.w3.org/ns/org#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
# Directory entity IRIs look like https://civic-data.de/federated-directory#org-dcd15d72996f
IRI_PATTERN = re.compile(r"^https://civic-data\.de/federated-directory#[A-Za-z0-9_-]+$")
MAX_DESCRIPTION_CHARS = 1500


def literal(value: str) -> str:
    """Escape user input as a SPARQL string literal (prevents query injection)."""

    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def check_iri(iri: str) -> str:
    if not IRI_PATTERN.match(iri):
        raise ValueError(f"Not a Federated Data Pool entity IRI: {iri!r}")
    return f"<{iri}>"


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class SparqlRepository:
    name = "sparql"

    def __init__(self, endpoint: str, timeout: float = 30.0):
        self.endpoint = endpoint
        self.client = httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/sparql-results+json"},
        )

    def query(self, sparql: str) -> list[dict[str, str]]:
        response = self.client.post(self.endpoint, data={"query": PREFIXES + sparql})
        response.raise_for_status()
        return [
            {var: cell["value"] for var, cell in row.items()}
            for row in response.json()["results"]["bindings"]
        ]

    # ------------------------------------------------------------------
    # Repository protocol
    # ------------------------------------------------------------------

    def search_facilities(self, text=None, postal_code=None, locality=None, limit=20):
        filters = []
        if text:
            needle = literal(text.lower())
            filters.append(
                f"""OPTIONAL {{ ?f schema:description ?d0 }}
                FILTER(CONTAINS(LCASE(STR(?n0)), {needle})
                       || (BOUND(?d0) && CONTAINS(LCASE(STR(?d0)), {needle})))"""
            )
        if postal_code or locality:
            filters.append("?f schema:address ?a0 .")
        if postal_code:
            filters.append(f"?a0 schema:postalCode {literal(postal_code.strip())} .")
        if locality:
            # Prefix match so "Berlin" also finds "Berlin-Mitte", "Berlin-Wedding".
            filters.append(
                f"?a0 schema:addressLocality ?l0 . "
                f"FILTER(STRSTARTS(LCASE(STR(?l0)), {literal(locality.strip().lower())}))"
            )

        rows = self.query(
            f"""
            SELECT ?f (SAMPLE(?n) AS ?name) (SAMPLE(?street) AS ?st) (SAMPLE(?pc) AS ?postal)
                   (SAMPLE(?loc) AS ?locality) (SAMPLE(?lat) AS ?la) (SAMPLE(?lon) AS ?lo)
                   (SAMPLE(?tel) AS ?phone)
            WHERE {{
              {{
                SELECT DISTINCT ?f WHERE {{
                  ?f a org:OrganizationalUnit ; schema:name ?n0 .
                  {" ".join(filters)}
                }}
                LIMIT {int(limit)}
              }}
              ?f schema:name ?n .
              OPTIONAL {{ ?f schema:telephone ?tel }}
              OPTIONAL {{
                ?f schema:address ?a .
                OPTIONAL {{ ?a schema:streetAddress ?street }}
                OPTIONAL {{ ?a schema:postalCode ?pc }}
                OPTIONAL {{ ?a schema:addressLocality ?loc }}
                OPTIONAL {{ ?a schema:latitude ?lat }}
                OPTIONAL {{ ?a schema:longitude ?lon }}
              }}
            }}
            GROUP BY ?f
            ORDER BY LCASE(STR(?name))
            """
        )
        return [self._summary(row) for row in rows]

    def get_facility(self, iri):
        subject = check_iri(iri)
        props = self.query(f"SELECT ?p ?o WHERE {{ {subject} ?p ?o }}")
        if not props:
            return None

        values: dict[str, list[str]] = {}
        for row in props:
            values.setdefault(row["p"], []).append(row["o"])

        def first(predicate):
            found = values.get(predicate)
            return found[0] if found else None

        address = None
        address_iri = first(SCHEMA + "address")
        if address_iri and IRI_PATTERN.match(address_iri):
            address = self._address(address_iri)

        description = first(SCHEMA + "description")
        if description and len(description) > MAX_DESCRIPTION_CHARS:
            description = description[:MAX_DESCRIPTION_CHARS] + " …"

        return Facility(
            iri=iri,
            name=first(SCHEMA + "name"),
            address=address,
            telephone=values.get(SCHEMA + "telephone", []),
            email=values.get(SCHEMA + "email", []),
            homepage=first(FOAF + "homepage") or first(SCHEMA + "mainEntityOfPage"),
            category=first(SCHEMA + "category"),
            opening_hours=values.get(SCHEMA + "openingHours", []),
            description=description,
            accessibility=first(SCHEMA + "accessibilitySummary"),
            services=self._services(subject),
        )

    def facilities_in_bounds(self, south, north, west, east, text=None, limit=IN_BOUNDS_LIMIT):
        name_filter = f"FILTER(CONTAINS(LCASE(STR(?n)), {literal(text.lower())}))" if text else ""
        rows = self.query(
            f"""
            SELECT ?f (SAMPLE(?n) AS ?name) (SAMPLE(?street) AS ?st) (SAMPLE(?pc) AS ?postal)
                   (SAMPLE(?loc) AS ?locality) (SAMPLE(?lat) AS ?la) (SAMPLE(?lon) AS ?lo)
                   (SAMPLE(?tel) AS ?phone)
            WHERE {{
              ?f a org:OrganizationalUnit ; schema:name ?n ; schema:address ?a .
              ?a schema:latitude ?lat ; schema:longitude ?lon .
              FILTER(xsd:double(?lat) >= {float(south)} && xsd:double(?lat) <= {float(north)} &&
                     xsd:double(?lon) >= {float(west)} && xsd:double(?lon) <= {float(east)})
              {name_filter}
              OPTIONAL {{ ?a schema:streetAddress ?street }}
              OPTIONAL {{ ?a schema:postalCode ?pc }}
              OPTIONAL {{ ?a schema:addressLocality ?loc }}
              OPTIONAL {{ ?f schema:telephone ?tel }}
            }}
            GROUP BY ?f
            LIMIT {int(limit)}
            """
        )
        return [self._summary(row) for row in rows]

    def postcode_centroid(self, postal_code):
        rows = self.query(
            f"""
            SELECT (AVG(xsd:double(?lat)) AS ?la) (AVG(xsd:double(?lon)) AS ?lo) (COUNT(?a) AS ?n)
            WHERE {{
              ?a schema:postalCode {literal(postal_code.strip())} ;
                 schema:latitude ?lat ; schema:longitude ?lon .
            }}
            """
        )
        if not rows or int(rows[0].get("n", 0)) == 0:
            return None
        return float(rows[0]["la"]), float(rows[0]["lo"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _summary(self, row: dict[str, str]) -> Facility:
        return Facility(
            iri=row["f"],
            name=row.get("name"),
            address=Address(
                street=row.get("st"),
                postal_code=row.get("postal"),
                locality=row.get("locality"),
                latitude=_float(row.get("la")),
                longitude=_float(row.get("lo")),
            ),
            telephone=[row["phone"]] if row.get("phone") else [],
        )

    def _address(self, address_iri: str) -> Address:
        rows = self.query(f"SELECT ?p ?o WHERE {{ <{address_iri}> ?p ?o }}")
        values = {row["p"]: row["o"] for row in rows}
        return Address(
            street=values.get(SCHEMA + "streetAddress"),
            postal_code=values.get(SCHEMA + "postalCode"),
            locality=values.get(SCHEMA + "addressLocality"),
            latitude=_float(values.get(SCHEMA + "latitude")),
            longitude=_float(values.get(SCHEMA + "longitude")),
        )

    def _services(self, subject: str) -> list[Service]:
        rows = self.query(
            f"""
            SELECT ?s (SAMPLE(?n) AS ?name) (SAMPLE(?c) AS ?category) (SAMPLE(?au) AS ?audience)
            WHERE {{
              {{ ?s schema:provider {subject} }} UNION {{ {subject} schema:availableService ?s }}
              FILTER(isIRI(?s))
              OPTIONAL {{ ?s schema:name ?n }}
              OPTIONAL {{ ?s schema:category ?c }}
              OPTIONAL {{ ?s schema:audience ?au }}
            }}
            GROUP BY ?s
            LIMIT 50
            """
        )
        return [
            Service(iri=row["s"], name=row.get("name"), category=row.get("category"),
                    audience=row.get("audience"))
            for row in rows
        ]
