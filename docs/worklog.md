# Work log: Federated Data Pool MCP server

DSSG Berlin × DSSG NYC Datathon 2026 · Tracks 1 (working MCP server) + 2 (data quality and new sources)
Plan and challenge analysis: [analysis_and_plan.md](analysis_and_plan.md)

---

## 2026-10-24

### Challenge analysis
- The pitch deck (`03_Pitch_Presentations_Datathon2026.pptx`) is only the template and schedule. The real brief is in the shared Drive (`challenge_brief_design.pdf`) and the official repo README.
- Chose **track 1 + track 2**. Track 2's key ask from the partner: "build the MCP tool for mapping new sources".

### Step 0: setup
- Cloned three repos: the official datathon repo, the reference server `Atrash87/awo-mcp-production`, and the pool builder `foederierter-datenpool/sosuse-directory-builder` (shallow, read-only).
- **Gotcha:** the reference `requirements.txt` has `mcp>=1.13.0`, so pip installs mcp 2.x, where `mcp.server.fastmcp` no longer exists. The server crashes on startup. **Fix: pin `mcp<2`** (1.30.0 works).
- Verified the reference server end-to-end with a stdio MCP client: 8 tools, `count_facilities("Berlin")` = 151.

### Findings about the data
- The live pool is far bigger than the reference CSV snapshot:

  | | CSV snapshot | Live pool |
  |---|---|---|
  | Facilities (`org:OrganizationalUnit`) | ~180 | 37,341 |
  | Services (`schema:Service`) | 99 | 4,004 |
  | Addresses | 108 | 25,871 |

- The SPARQL default graph equals the published (`resolved.ttl`) directory, so no `GRAPH` clause is needed. Pipeline graphs (`mapped`, `matches`, `provenance`) are needed only for source and provenance questions.
- `pipeline#fromSource` exists in `mapped.ttl`, so data quality can be broken down **per source**. This matters for track 2.
- Field coverage in the published directory, out of 37,341 facilities:

  | Field | Facilities with it | Coverage |
  |---|---|---|
  | phone | 28,193 | 76% |
  | e-mail | 27,087 | 73% |
  | opening hours | 2,622 | **7%** |
  | category | 2,142 | 6% |

  The brief's "80% missing" refers to opening hours and contact data together. Recheck this per source.
- Live query latency: name search ~0.2 s, map-area (bounding box) query ~0.9 s, description search ~0.8 s.

### Step 1: MCP server scaffold (`mcp-server/`)
- `Repository` protocol with two backends: `sparql` (live, default) and `csv` (snapshot, offline/demo fallback). Selected with `FDP_BACKEND`.
- Tools: `search_facilities`, `get_facility`, `find_nearest`.
  - `find_nearest` turns a postcode into a location by averaging the coordinates of the pool's own addresses with that postcode. No external geocoder.
- **Decision:** the keyword filter for `find_nearest` runs inside SPARQL, not in Python after fetching, and the candidate cap is 2000 with a warning when it's hit. Before this, a large radius could silently drop matches.
- **Safety:** SPARQL literal escaping and an IRI allow-list (tested). The server instructions tell the model to treat third-party text as data, not instructions.
- Tests: 16 passing (11 offline, 5 live, plus 1 end-to-end over stdio).
- Live demo check:
  - "Schuldnerberatung" + Berlin → 3 real offices.
  - Nearest "sucht" to 10551 → Ambulante Suchtberatung Mitte, 0.47 km.

### Repo decision
- We don't push to the official `dssg-berlin` repo. That remote is renamed `upstream`, with its push URL disabled.
- Code and this log go to a personal GitHub repo (`yunielee-de`).

### Next
- Track 1: `is_open_now` (parse free-text opening hours, return "unknown" when missing), plus one MCP prompt.
- Track 2: profiling notebook (coverage per source) → `data_quality_report` → `normalize_locality` → `map_to_schema` for one new source (beratungsfinder or afeefa).
