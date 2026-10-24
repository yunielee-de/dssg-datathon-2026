"""Estimate how much a new source would add to the pool, from an evenly spread sample.

Usage (from mcp-server/):  python scripts/estimate_source_overlap.py [pages] [page_size]
Writes aggregate numbers only (no records, no personal data) to
../docs/new_source_<source>.md.
"""

import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fdp_mcp import mapping  # noqa: E402
from fdp_mcp.locality import LocalityIndex  # noqa: E402
from fdp_mcp.repository import DEFAULT_SPARQL_ENDPOINT  # noqa: E402
from fdp_mcp.repository.sparql import SparqlRepository  # noqa: E402
from fdp_mcp.sources import beratungsfinder as source  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[2] / "docs"


def pct(n: int, total: int) -> str:
    return f"{100 * n / total:.0f}%" if total else "–"


def main(pages: int = 10, page_size: int = 50):
    repo = SparqlRepository(DEFAULT_SPARQL_ENDPOINT, timeout=180)
    index = LocalityIndex(repo.locality_counts())
    total = source.fetch(take=1)["totalItemCount"]
    step = max(total // pages, page_size)

    records = []
    for skip in range(0, step * pages, step):
        records += [source.to_mapped(raw) for raw in source.fetch(take=page_size, skip=skip)["results"]]
        time.sleep(1)  # be polite to the source
    for r in records:
        mapping.validate(r, index)
    mapping.match_against_pool(records, repo.facilities_in_postcodes([r.address.postalCode for r in records]))

    n = len(records)
    status = Counter(r.pool_match["status"] for r in records)
    issues = Counter(mapping.issue_key(i) for r in records for i in r.issues)
    fields = {
        "phone": sum(bool(r.telephone) for r in records),
        "e-mail": sum(bool(r.email) for r in records),
        "website": sum(bool(r.homepage) for r in records),
        "street address": sum(bool(r.address.streetAddress) for r in records),
        "coordinates": sum(r.address.latitude is not None for r in records),
        "opening hours": sum(bool(r.openingHours) for r in records),
        "topics (categories)": sum(bool(r.category) for r in records),
    }
    topics = Counter(t for r in records for t in r.category)
    new_share = status["new"] / n if n else 0

    lines = [
        f"# New source assessment: {source.NAME}",
        "",
        f"Generated {date.today().isoformat()} by `mcp-server/scripts/estimate_source_overlap.py` "
        f"from an evenly spread sample of **{n} of {total:,}** records ({source.HOMEPAGE}). "
        "Aggregate numbers only.",
        "",
        "## 1. Would it add new facilities?",
        "",
        "| Pool match | Records | Share |",
        "|---|---|---|",
        *[f"| {s} | {c} | {pct(c, n)} |" for s, c in status.most_common()],
        "",
        f"Extrapolated: about **{round(new_share * total):,} counselling centres not yet in the pool**.",
        "`same_organisation` records share phone or e-mail with an existing facility. They are likely "
        "departments that should become services (Angebote) of that facility, not new facilities.",
        "",
        "**Caveat:** duplicates are searched only among pool facilities with the same postcode, so `new` is an "
        "upper bound. A centre listed in the pool under a different postcode counts as new. "
        "Shelters (`not_checked`) are never cross-matched, to protect their location.",
        "",
        "## 2. Field coverage of the source",
        "",
        "| Field | Records | Share |",
        "|---|---|---|",
        *[f"| {f} | {c} | {pct(c, n)} |" for f, c in fields.items()],
        "",
        "## 3. Validation issues",
        "",
        "| Issue | Records |",
        "|---|---|",
        *[f"| {i} | {c} |" for i, c in issues.most_common()],
        "",
        "## 4. Most common topics",
        "",
        "| Topic | Records |",
        "|---|---|",
        *[f"| {t} | {c} |" for t, c in topics.most_common(15)],
        "",
    ]
    out = OUT_DIR / f"new_source_{source.NAME}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:3]]
    main(*args)
