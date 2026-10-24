"""Profile data quality of the live Federated Data Pool and write a Markdown report.

Usage (from mcp-server/):  python scripts/profile_quality.py [output.md]
Default output: ../docs/data_quality_profile.md
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fdp_mcp import hours, quality  # noqa: E402
from fdp_mcp.repository import DEFAULT_SPARQL_ENDPOINT  # noqa: E402
from fdp_mcp.repository.sparql import MAPPED_GRAPH, MATCHES_GRAPH, SparqlRepository  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "data_quality_profile.md"


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "–"


def coverage_table(repo: SparqlRepository) -> list[str]:
    scopes = [("**All (published)**", None)] + [(key, key) for key in quality.SOURCES]
    header = "| Scope | Facilities | " + " | ".join(c.label for c in quality.CHECKS) + " |"
    lines = [header, "|" + "---|" * (len(quality.CHECKS) + 2)]
    for label, source in scopes:
        s = repo.quality_summary(source=source)
        cells = [pct(s.passing[c.key], s.total) for c in quality.CHECKS]
        lines.append(f"| {label} | {s.total:,} | " + " | ".join(cells) + " |")
    return lines


def raw_source_contacts(repo: SparqlRepository) -> list[str]:
    """Contacts as delivered by each source, before merging."""

    rows = repo.query(
        f"""
        SELECT ?src (COUNT(DISTINCT ?r) AS ?records) (COUNT(DISTINCT ?t) AS ?phone) (COUNT(DISTINCT ?h) AS ?hours)
        WHERE {{ GRAPH {MAPPED_GRAPH} {{
          ?r a org:OrganizationalUnit ; cdp:fromSource ?src .
          OPTIONAL {{ ?r schema:telephone [] . BIND(?r AS ?t) }}
          OPTIONAL {{ ?r schema:openingHours [] . BIND(?r AS ?h) }}
        }} }}
        GROUP BY ?src ORDER BY DESC(?records)
        """
    )
    lines = ["| Source | Records delivered | with phone | with opening hours |", "|---|---|---|---|"]
    for row in rows:
        name = quality.SOURCE_BY_IRI_NAME.get(row["src"].rsplit("#", 1)[-1], row["src"])
        n = int(row["records"])
        lines.append(
            f"| {name} | {n:,} | {pct(int(row['phone']), n)} | {pct(int(row['hours']), n)} |"
        )
    return lines


def merge_stats(repo: SparqlRepository) -> list[str]:
    rows = repo.query(
        f"""
        SELECT ?k (COUNT(?f) AS ?n) WHERE {{
          {{ SELECT ?f (COUNT(DISTINCT ?src) AS ?k) WHERE {{
              ?f a org:OrganizationalUnit .
              GRAPH {MATCHES_GRAPH} {{ ?f cdp:hasMember ?r }}
              GRAPH {MAPPED_GRAPH} {{ ?r cdp:fromSource ?src }}
          }} GROUP BY ?f }}
        }} GROUP BY ?k ORDER BY ?k
        """
    )
    lines = ["| Sources merged into one facility | Facilities |", "|---|---|"]
    lines += [f"| {row['k']} | {int(row['n']):,} |" for row in rows]
    return lines


def text_field_stats(repo: SparqlRepository) -> list[str]:
    def count(where: str) -> int:
        return int(repo.query(f"SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE {{ {where} }}")[0]["n"])

    facility_hours = "?x a org:OrganizationalUnit ; schema:openingHours ?h ."
    hours_total = count(facility_hours)
    hours_no_digit = count(f'{facility_hours} FILTER(!REGEX(STR(?h), "[0-9]"))')
    hours_appointment = count(f'{facility_hours} FILTER(CONTAINS(LCASE(STR(?h)), "vereinbarung"))')
    pc_total = count("?x a schema:PostalAddress ; schema:postalCode ?p")
    pc_bad = count('?x a schema:PostalAddress ; schema:postalCode ?p FILTER(!REGEX(STR(?p), "^[0-9]{5}$"))')
    pc_four = count('?x a schema:PostalAddress ; schema:postalCode ?p FILTER(REGEX(STR(?p), "^[0-9]{4}$"))')
    berlin_variants = count(
        '?a schema:addressLocality ?x FILTER(STRSTARTS(LCASE(STR(?x)), "berlin"))'
    )
    spacing = count(
        '?a schema:addressLocality ?x FILTER(REGEX(STR(?x), "( -|- |  |^ | $)"))'
    )
    return [
        "| Check | Count |",
        "|---|---|",
        f"| Facilities with opening hours | {hours_total:,} |",
        f"| … whose hours text contains no digit (not actual hours) | {hours_no_digit:,} |",
        f"| … mentioning \"nach Vereinbarung\" (by appointment) | {hours_appointment:,} |",
        f"| Addresses with a postcode | {pc_total:,} |",
        f"| … postcode not 5 digits | {pc_bad:,} ({pct(pc_bad, pc_total)}) |",
        f"| … of which 4 digits (leading zero lost, e.g. 8371 → 08371) | {pc_four:,} |",
        f"| Distinct locality spellings starting with \"Berlin\" | {berlin_variants:,} |",
        f"| Distinct locality values with stray spaces/hyphens (\"Berlin- Tempelhof\") | {spacing:,} |",
    ]


def hours_readability(repo: SparqlRepository) -> list[str]:
    """How many opening-hours texts the is_open_now parser can turn into a weekly schedule."""

    rows = repo.query("SELECT ?f ?h WHERE { ?f a org:OrganizationalUnit ; schema:openingHours ?h }")
    by_facility: dict[str, list[str]] = {}
    for row in rows:
        by_facility.setdefault(row["f"], []).append(row["h"])
    outcome = {"weekly schedule read": 0, "read, but partial": 0, "appointment only": 0,
               "times without weekdays": 0, "not opening hours (phone numbers, addresses, ...)": 0}
    typos = damaged = 0
    for texts in by_facility.values():
        text = "\n".join(texts)
        s = hours.parse(text)
        typos += any(n.startswith("read misspelled") for n in s.notes)
        damaged += " ? " in text
        key = ("read, but partial" if s.partial else "weekly schedule read" if s.parsed
               else "appointment only" if s.appointment else "times without weekdays" if s.times_without_days
               else "not opening hours (phone numbers, addresses, ...)")
        outcome[key] += 1
    n = len(by_facility)
    lines = ["| Outcome | Facilities | Share |", "|---|---|---|"]
    lines += [f"| {k} | {v:,} | {pct(v, n)} |" for k, v in outcome.items()]
    lines += ["", f"Also found: {typos} texts with misspelled weekdays (e.g. \"Mitwoch\"), and {damaged} with an "
              "en dash lost to an encoding error (\"Mo ? Do\")."]
    return lines


def worst_records(repo: SparqlRepository) -> list[str]:
    lines = ["| Score | Facility | Place | Sources | Missing |", "|---|---|---|---|---|"]
    for r in repo.records_to_fix(limit=10):
        place = " ".join(p for p in (r.postal_code, r.locality) if p) or "–"
        lines.append(
            f"| {r.score} | {r.name or '–'} | {place} | {', '.join(r.sources)} | {', '.join(r.missing)} |"
        )
    return lines


def main(out: Path):
    repo = SparqlRepository(DEFAULT_SPARQL_ENDPOINT, timeout=180)
    weights = ", ".join(f"{c.label} {c.weight}" for c in quality.CHECKS)
    sections = [
        "# Data-quality profile: Federated Data Pool",
        "",
        f"Generated {date.today().isoformat()} from the live endpoint `{DEFAULT_SPARQL_ENDPOINT}` "
        "by `mcp-server/scripts/profile_quality.py`. Re-run it to refresh the numbers.",
        "",
        "## 1. Coverage of published facilities, per source",
        "Share of facilities passing each check. A merged facility counts for every source that contributed to it.",
        "",
        *coverage_table(repo),
        "",
        "## 2. What each source delivers before merging",
        "",
        *raw_source_contacts(repo),
        "",
        "Comparing tables 1 and 2 shows the value of federation. For example, Destatis delivers no phone numbers, "
        "but some of its facilities gain one by being merged with records from other sources.",
        "",
        "## 3. How many sources were merged per facility",
        "",
        *merge_stats(repo),
        "",
        "## 4. Free-text and format problems",
        "",
        *text_field_stats(repo),
        "",
        "## 5. Can opening hours be read by a machine?",
        f"Of the {quality.CHECKS[2].label} that exist, how many the `is_open_now` parser turns into a weekly schedule.",
        "",
        *hours_readability(repo),
        "",
        "## 6. Ten records to fix first",
        f"Score = sum of weights of failed checks ({weights}), "
        f"+{quality.NO_CONTACT_PENALTY} if there is no phone, e-mail or website at all.",
        "",
        *worst_records(repo),
        "",
    ]
    out.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT)
