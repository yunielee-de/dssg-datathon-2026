# Federated Data Pool: MCP Server (Tracks 1 + 2)

DSSG Berlin × DSSG NYC Datathon 2026 · Team working doc · last updated 2026-10-24

> **Deadline:** hacking ends **Sun 25 Oct, 15:00 CEST (22:00 KST / 09:00 EDT)**.
> Pitch slots are at 15:30, 16:00 and 16:30 CEST (22:30, 23:00 and 23:30 KST).
> Post the deck or demo link in Slack **before** our slot.

---

## 1. The challenge

**Partner:** Civic Data Lab (German Caritas Association), together with AWO and other welfare organisations. The data is MIT licensed and no NDA is needed.

**Problem:** Every welfare organisation keeps its own directory of support services. That makes it hard for people in need, and for those who help them, to find the right offer. The **Federated Data Pool** (Föderierter Datenpool) harmonises these sources into one shared directory and keeps growing:
- Caritas
- AWO
- DHS (addiction help)
- Sozialplattform
- Destatis (debt counselling)

**Mission:** Make this data usable by AI assistants through a **Model Context Protocol (MCP) server**.

### Data model

| Entity | File | Main fields | Links to |
|---|---|---|---|
| Einrichtung (facility) | `einrichtungSchema.csv` | name, category, phone, e-mail, opening hours, description, accessibility | address, Träger |
| Angebot (service offer) | `angebotSchema.csv` | name, category, code, audience, area served | provider → facility |
| Adresse (address) | `adresseSchema.csv` | street, postcode, locality, lat/lon | – |
| Träger (provider org) | `traegerSchema.csv` | name, homepage | address |

### Known data issues (useful pitch material)
- About **80% of facilities have no phone, e-mail or opening hours**.
- Opening hours and descriptions are **free text**, not structured values.
- The same city appears under several **locality variants** ("Berlin", "Berlin-Mitte", "Berlin-Wedding").
- Only four sources are integrated so far. More are planned.

### Example questions from the partner
- **Citizens:** "My son is withdrawn at school, where is the nearest youth counselling?" · "Is Kita XY open right now?" · "I can't pay my rent, who can help?"
- **Social organisations:** "Which of our records are incomplete or outdated, and what should we fix first?" · "Which districts have no youth counselling in our network?"
- **Journalists / administration:** "Where are the gaps in addiction-counselling coverage?" · "Where does this field value come from?"

### The four tracks (we do 1 + 2)

| # | Track | What | Level |
|---|---|---|---|
| **1** | **Working MCP server** | Base tools: search facilities, check opening hours, find nearest offer | Newcomers |
| **2** | **Data quality and the future of the pool** | Detect or repair poor records, rank records to fix, **map unstructured input or new sources onto the pool schema** | Newcomers / data practitioners |
| 3 | AI model benchmark | Answer correctness, tool choice, tokens and latency across LLMs | Experts |
| 4 | Dataset investigation | Gap map with external data (official statistics) | Data scientists |

For track 2, the partner suggests these candidate new sources: [bamf-navi](https://bamf-navi.bamf.de/en/), [ib-jmd](https://ib-jmd.de/unsere-standorte), [beratungsfinder](https://beratungsfinder.de/), [afeefa](https://afeefa.de/leipzig?l=en).
In their words: "It is not necessary that all of them will be integrated after the hackathon. **The important thing is to build the MCP tool for mapping new sources.**"

---

## 2. Resources

| What | Link |
|---|---|
| Official datathon repo (read-only for us, we don't push here) | https://github.com/dssg-berlin/2026-datathon-federated-datapool |
| Our work log + code | https://github.com/yunielee-de (personal repo) |
| Reference MCP server (FastMCP + CSVs) | https://github.com/Atrash87/awo-mcp-production |
| Data pool code, schema, SPARQL examples | https://github.com/foederierter-datenpool/sosuse-directory-builder |
| Federation web app / vocabulary / APIs | https://foederierter-datenpool.github.io/sosuse-directory-builder/ |
| Shared Drive folder | https://drive.google.com/drive/folders/1x90uX6JDGlqmEKCrZ446wQYgUDvw6Rjm |

### Live API (no data download needed)
Verified responding on 2026-10-24:
- **SPARQL:** `https://sosuse.correlaid.org/directory/sparql`
- **REST:** `https://sosuse.correlaid.org/collections/{collection}/items` ([Swagger UI](https://sosuse.correlaid.org/swagger-ui.html))
- **GraphQL:** `https://sosuse.correlaid.org/graphiql`
- **Full dump:** `https://sosuse.correlaid.org/directory.ttl`

The data pool repo has ready-made SPARQL queries under `webapp/content/queries/`. These include `by-postcode`, `search-by-name`, `within-bounds`, `explain-value` and `competing-values`, and they are reusable as tool backends.

### Reference server facts
- Stack: `mcp>=1.13.0`, `pandas>=2.2.0`, `fastmcp`
- Layout: `server.py` → `src/data_loader.py` → `src/data_repository.py`, with the CSVs in `data/`
- **It has no LICENSE file.** The challenge brief explicitly invites building on it, so we credit the author (Atrash87) in our README and pitch.

---

## 3. Our plan: Track 1 + Track 2

**Pitch story:** "An MCP server that answers real questions from **live** pool data, and that also helps the pool **fix itself and grow**."

### Target tools

| Track | Tool | Answers |
|---|---|---|
| 1 | `search_services(query, city/postcode, category, audience)` | "I can't pay my rent in Berlin, who can help?" |
| 1 | `find_nearest(lat/lon or postcode, category, limit)` | "Nearest youth counselling?" |
| 1 | `is_open_now(facility_id)` | "Is Kita XY open right now?" (parses free-text hours) |
| 1 | `get_facility(id)` | Full record with offers and provider |
| 2 | `data_quality_report(source?, city?)` | Completeness score per record and a **ranked list of what to fix first** |
| 2 | `normalize_locality(value)` | Maps variants such as "Berlin-Mitte" to "Berlin" plus district |
| 2 | `map_to_schema(raw_record or url)` | Maps an unstructured new-source entry (e.g. beratungsfinder) onto Einrichtung/Angebot/Adresse, validates it, and flags missing fields |
| 2 *(stretch)* | `explain_value(entity, field)` | "Where does this value come from?" (provenance, uses the existing SPARQL query) |

### Work order

**Step 0: Setup (everyone, ~30 min)**
1. Fork or clone the team repo and create a feature branch:
   ```bash
   git clone https://github.com/dssg-berlin/2026-datathon-federated-datapool.git
   cd 2026-datathon-federated-datapool
   git checkout -b feat/mcp-server
   ```
2. Clone the reference server **next to it**, for reading and reuse:
   ```bash
   git clone https://github.com/Atrash87/awo-mcp-production.git
   ```
3. Set up a Python env: `python -m venv .venv && source .venv/bin/activate && pip install -r awo-mcp-production/requirements.txt "mcp>=1.13,<2"`
   > ⚠️ **Pin `mcp<2`.** The reference `requirements.txt` says `mcp>=1.13.0`, so pip installs mcp 2.x. In 2.x, `from mcp.server.fastmcp import FastMCP` was removed (renamed to `MCPServer`), and `server.py` crashes on startup. With `mcp 1.30.0` the server runs and all 8 tools respond (verified 2026-10-24).
4. Run the reference server as-is and connect it to an AI client to confirm the end-to-end loop works:
   - Claude Code: `claude mcp add awo -- python /abs/path/awo-mcp-production/server.py`
   - or Claude Desktop: `claude_desktop_config.json`

**Step 1: Scaffold our server (MCP Core, ~1–2 h)**
1. Copy the reference `src/` structure into `mcp-server/` in the team repo and credit the author.
2. Put a **data access layer** behind an interface: `CsvRepository` (snapshot, offline fallback) and `SparqlRepository` (live pool). Tools only talk to the interface.
3. Commit early and open a draft PR so teammates can build on it.

**Step 2: Track 1 tools (~3–4 h, can run in parallel with Step 3)**
1. `search_services` and `get_facility` first. These are the demo backbone.
2. `find_nearest`: haversine distance on lat/lon, plus postcode → coordinate lookup.
3. `is_open_now`: parse the free-text hours. Return `"unknown"` honestly when they are missing (≈80% of records), and never guess.
4. Add one MCP **prompt**, e.g. "find help for a citizen", that chains the tools.

**Step 3: Track 2 tools (~3–4 h, parallel)**
1. **Profiling notebook** (`notebooks/`): measure completeness per field and per source, and collect locality variants.
2. `data_quality_report`: score each record (missing contact, hours, coordinates; free-text-only fields) and rank the records to fix first.
3. `normalize_locality`: a rule-based mapping table built from the profiling.
4. `map_to_schema`: take one new source (start with **beratungsfinder** or **afeefa**). Fetch a few entries, map them to the pool schema with LLM assistance, validate the required fields, and return a "ready / needs fixing" result.

**Step 4: Integration and demo (~2 h)**
1. Merge the branches, run all tools against live data, and keep a CSV fallback in case the API is down during the pitch.
2. Script **3 demo questions**: one citizen question (track 1), one "what to fix first" (track 2), one "add this new source" (track 2).
3. Record a short screen capture as a backup for the live demo.

**Step 5: Pitch (~1–2 h, finish before 15:00 CEST)**
Use the template slides: **Problem → Approach → Demo / Results → Impact & Next steps**.
- **Problem:** the fragmented directories and the "80% missing contact info" stat.
- **Approach:** an architecture diagram (pool API → MCP server → AI assistant) and the tool list.
- **Results:** demo screenshots, quality ranking numbers, the new source mapped.
- **Limitations:** free-text hours, coverage of only four sources, LLM mapping still needs human review.
- **Next steps:** hand-off to Civic Data Lab, a hosted deployment, and more sources.

### Suggested split
| Person / sub-team | Owns |
|---|---|
| MCP Core | Steps 0–1, repository layer, hosting, client config |
| Track 1 tools | `search_services`, `find_nearest`, `is_open_now`, prompt |
| Track 2: quality | profiling notebook, `data_quality_report`, `normalize_locality` |
| Track 2: new sources | `map_to_schema` with one external source |
| Demo / pitch | demo script, slides, backup recording |

---

## 4. Ground rules
- Code and the work log live in a personal repo, not the official `dssg-berlin` repo. The official repo is set as `upstream` with pushing disabled. Record decisions in `docs/worklog.md`.
- **No real personal data** in commits.
- Tools must cite their source and say "unknown" rather than invent values. The partner stresses trustworthy data with "clear sources, quality checks and honest limits".
- Watch out for **prompt injection** in scraped or free-text fields that get passed to the LLM, especially in `map_to_schema`.
