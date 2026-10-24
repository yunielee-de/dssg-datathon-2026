# Federated Data Pool: MCP Server

An MCP server that lets AI assistants search the [Federated Data Pool](https://civic-data.de/machen/werkstattboxen/foederierter-datenpool/), the harmonised German social-services directory (Caritas, AWO, DHS, Sozialplattform, Destatis).

It queries the **live** pool by default: about 37k facilities, 4k services and 26k addresses, via `https://sosuse.correlaid.org/directory/sparql`. A small CSV snapshot is included for offline work and as a demo fallback.

## Quick start

```bash
cd mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -m "not live"      # offline tests
pytest                    # + tests against the live endpoint
```

> **Keep `mcp<2`.** mcp 2.x removed `mcp.server.fastmcp`, so the server will not start on it.

### Connect an AI client

**Claude Code** (from any folder):
```bash
claude mcp add fdp -- /ABS/PATH/mcp-server/.venv/bin/python /ABS/PATH/mcp-server/server.py
```

**Claude Desktop**: add this to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "fdp": {
      "command": "/ABS/PATH/mcp-server/.venv/bin/python",
      "args": ["/ABS/PATH/mcp-server/server.py"]
    }
  }
}
```

### Backends

| `FDP_BACKEND` | Data | Use for |
|---|---|---|
| `sparql` (default) | Live pool. Override the URL with `FDP_SPARQL_ENDPOINT` | Real answers, demo |
| `csv` | `data/snapshot/*.csv` (≈180 facilities) | Offline dev, tests, demo fallback |

## Tools

| Tool | Example question |
|---|---|
| `search_facilities(query, postal_code, city, limit)` | "I can't pay my rent in Berlin, who can help?" → `query="Schuldnerberatung", city="Berlin"` |
| `get_facility(iri)` | Full record: contacts, opening hours, description, services |
| `find_nearest(latitude/longitude or postal_code, query, radius_km)` | "Nearest addiction counselling to 10551?" |
| `data_quality_report(source, city, postal_code, limit)` | "Which Destatis records should we fix first?" · "How complete is the data for Berlin?" |

`data_quality_report` checks each facility for phone, map location, opening hours (present and containing actual times), a valid 5-digit postcode, e-mail and website. It ranks records by how much their gaps hurt someone looking for help; the weights are in `fdp_mcp/quality.py`. The `source` filter works only with the live backend, because the CSV snapshot has no source attribution.

### Data-quality profile
`python scripts/profile_quality.py` regenerates [`docs/data_quality_profile.md`](../docs/data_quality_profile.md) from the live pool in about 30 s. It contains per-source coverage, what each source delivers before merging, merge statistics, free-text and format problems, and the top records to fix.

Notes:
- **City is a prefix match.** "Berlin" also matches "Berlin-Mitte" and "Berlin-Wedding".
- **Postcode → coordinates** uses the mean position of the pool's own addresses with that postcode. No external geocoder is needed.
- **Distances are straight-line** (haversine), not travel time.

## Layout

```
mcp-server/
├── server.py                  # entry point for MCP clients
├── fdp_mcp/
│   ├── server.py              # tool definitions (FastMCP)
│   ├── models.py              # Facility / Address / Service
│   ├── geo.py                 # haversine, bounding box
│   ├── quality.py             # data-quality checks, weights, ranking
│   └── repository/
│       ├── __init__.py        # Repository protocol + backend factory
│       ├── sparql.py          # live backend
│       └── csv.py             # snapshot backend
├── scripts/profile_quality.py # writes docs/data_quality_profile.md
├── data/snapshot/             # CSV sample of the pool
└── tests/
```

### Adding a tool
1. If it needs new data, add a method to the `Repository` protocol and implement it in **both** `sparql.py` and `csv.py`. The `csv` backend may return a simplified result.
2. Add the tool in `fdp_mcp/server.py`. Write the docstring for the LLM: say what it answers and give German example terms.
3. Add a test: offline in `tests/test_offline.py`, live in `tests/test_live.py`.

Useful SPARQL to build on: `sosuse-directory-builder/webapp/content/queries/` (provenance via `explain-value.sparql`, sources via `sources-of.sparql`).

## Safety
- User input is escaped before going into SPARQL (`literal()`), and IRIs are validated against the pool's namespace (`check_iri()`).
- Text fields come from third-party sources. The server instructions tell the model to treat them as data, not instructions.

## Credits
The structure and CSV snapshot are adapted from [Atrash87/awo-mcp-production](https://github.com/Atrash87/awo-mcp-production). The data comes from the Federated Data Pool by [Civic Data Lab](https://civic-data.de/english/) (MIT).
