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

### Why track 2 starts with profiling (decision)
- The MCP server can only answer as well as the data allows. Profiling shows **which** gaps are real, so we build tools for those rather than for assumed ones.
- We **can't edit the pool**: it is rebuilt from the providers' systems. Our output is a ranked "what to fix" list per provider.
- The numbers are the pitch's "Problem" slide.

### Step 2: data-quality profile and `data_quality_report` tool
- `fdp_mcp/quality.py` holds one set of checks and weights, used by both backends and by the profile script.

  | Check | Weight |
  |---|---|
  | phone | 3 |
  | map location | 3 |
  | opening hours | 2 |
  | hours contain actual times | 1 |
  | valid 5-digit postcode | 1 |
  | e-mail | 1 |
  | website | 1 |
  | no contact channel at all (no phone, e-mail or website) | +5 |

- Ranking is computed **inside SPARQL** over all 37k facilities, in 1–3 s per query.
- Per-source filtering joins published facilities → `matches.ttl` (hasMember) → `mapped.ttl` (fromSource).
- New MCP tool `data_quality_report(source, city, postal_code, limit)` returns:
  - coverage per check
  - recommended actions ordered by impact (records affected × weight)
  - the most common gap combinations
  - the worst records, with their sources
- `scripts/profile_quality.py` → [data_quality_profile.md](data_quality_profile.md) (about 30 s, live).
- Tests: 20 passing.

### Key findings (live pool, 2026-10-24)
- **Opening hours are the biggest gap:** only 7% of facilities have them (Caritas 3%). DHS is the exception at 83%.
  - Of the 2,622 facilities that do have hours, 221 contain no times at all (e.g. a contact name), and 533 say "nach Vereinbarung" (by appointment).
- **5,229 facilities (14%) have no phone, e-mail or website.** Nobody can contact them through the directory.
- **Destatis and AWO deliver no phone numbers.** After merging, 21% of Destatis facilities have one, which shows the value of federation.
- **Merging is rare:** 36,218 facilities come from 1 source, and only 1,123 combine 2–4 sources.
- **Berlin is spelled 23 ways.** 142 distinct locality values have stray spaces or hyphens ("Berlin- Tempelhof").
- **Postcodes are clean:** only 7 are not 5 digits, 3 of which lost a leading zero. Smaller than first thought, so the weight stays low.
- Some Caritas entries are not help services (e.g. a "Diözesanrat", a church council), and one facility is named just "Kontakt". This is a relevance problem, not yet measured.

### Step 3: `normalize_locality` and `locality_variants` tools
- **Splitting on hyphens is wrong.** Real pool examples:

  | Place name | What it actually is |
  |---|---|
  | `Berlin-Mitte` | Berlin + district |
  | `Castrop-Rauxel`, `Bietigheim-Bissingen` | one city |
  | `Frankfurt` (83 addresses) | Frankfurt am Main **or** Frankfurt (Oder) |
  | `Frankfurt/M.`, `Frankfurt a. M.`, `Frankfurt/Main` | Frankfurt am Main |
  | `Frankfurt a. d. Oder`, `Frankfurt(Oder)` | Frankfurt (Oder) |

- **Decision: use the pool's own addresses as the reference** (7,581 locality/postcode combinations, 1,696 known cities).
  - With a postcode, the most common city for that postcode is canonical. This fixes typos ("Glachau" + 8371 → Glauchau, 08371), resolves "Frankfurt", and flags conflicts ("Hamburg" + 10115 → conflicts with Berlin).
  - Without a postcode, only frequent cities (≥3 addresses) are split. Ambiguous names get a note.
  - An `OFFICIAL_NAMES` table covers names that rules cannot derive, such as Frankfurt (Oder), Mülheim an der Ruhr and Halle (Saale).
- Result: Berlin's **24 spellings fold into 1 city with 21 districts**.
- The index is built once per session in about 1 s, then cached.
- Tests: 38 passing, including 18 locality cases modelled on real spellings.

### Step 4: mapping new sources (`preview_source_mapping`, `validate_record`, prompt `map_new_source`)
- **Choosing a source.** I checked the four sources the partner suggested:
  - Beratungsfinder and afeefa both allow crawling (robots.txt).
  - **Beratungsfinder** (run by DAJEB) has a **public JSON API** behind its website: `POST /api/BeratungsstelleSearch` with `take`/`skip` paging and `location`/`umkreisKm` radius search. I read the request format from the site's own frontend code. No HTML scraping is needed, and it holds **14,097 counselling centres**.
  - Beratungsfinder was chosen.
- **Design: two paths.**
  1. **Structured source:** an adapter (`fdp_mcp/sources/beratungsfinder.py`) maps each API record to facility + address + services (one per counselling topic) + provider.
  2. **Unstructured input** (web page, flyer): the MCP prompt `map_new_source` has the AI client extract the records, and `validate_record` checks each one. No AI API key is needed on the server.
- **Validation** (`fdp_mcp/mapping.py`): fixes postcodes (8371 → 08371), normalises localities (reuses `normalize_locality`), validates e-mail and URL formats, and flags a missing street, contact or opening hours.
- **Duplicate check against the live pool** (same postcode). Statuses:

  | Status | Meaning |
  |---|---|
  | `already_in_pool` | name + contact match |
  | `same_organisation` | contact only: a department of an existing facility, so add it as a service |
  | `possible_duplicate` | name only |
  | `new` | no match |

  Iterations based on real results:
  - v1 marked departments sharing the umbrella's central phone as "already in pool", so I added `same_organisation`.
  - v2 word matching was fooled by umbrella names ("… Caritasverband Leipzig"), so umbrella words, organisation suffixes (*-verband*, *-stiftung* …) and place names are now ignored.
  - Compound words now match ("Jugenddrogenberatung" ~ "Jugenddrogenberatungsstelle").
- **Ethics: shelters.** Women's shelters keep their address secret to protect residents; the source itself publishes them as "Ort in Niedersachsen" or without a street. **Rule: confidential records are never geocoded, enriched or cross-matched,** and street and coordinates are dropped.
- **Privacy:** the source contains staff names in e-mail addresses. Raw records are **not committed**; tests use synthetic data, and docs contain aggregates only.
- **Result** ([new_source_beratungsfinder.md](new_source_beratungsfinder.md), sample of 400 spread across the source):
  - **73% are not in the pool**, about 10,300 centres. This is an upper bound: duplicates are only searched within the same postcode.
  - 11% are departments of existing facilities, 8% are already in the pool, and 4% are shelters.
  - Source quality is excellent (99% phone, 100% e-mail, 94% coordinates), but it has **no opening hours at all**.
- Tests: 44 passing (6 new mapping tests on synthetic data).

### Step 5: `is_open_now` and open-now filtering (track 1)
- **Input:** all 2,622 opening-hours texts from the live pool, analysed locally and not committed (some contain names).
  - median length 71 characters
  - 22% use day ranges ("Mo - Fr"), 20% mention "Vereinbarung" (by appointment), 15% are multi-line
  - mixes of opening, consultation ("Sprechstunde") and phone ("Telefonische Erreichbarkeit") hours
- **Design** (`fdp_mcp/hours.py`):
  - Find day expressions and attach the following time ranges to them.
  - Track the kind of hours: opening, consultation, phone, holidays.
  - **Never guess:** times without weekdays are reported, not assigned, and doubtful results are flagged `partial`.
- **Accuracy over coverage.** The first version parsed 79% of texts, but spot checks showed some **wrong** schedules. That's worse than "unknown", because it tells someone a place is open when it isn't. Fixed through two manual audits of 30 random results each:

  | Audit | Wrong results | Fixes |
  |---|---|---|
  | Audit 1 | 4/30 | "8: 00" read as 00:00; "außer freitags" ignored; school-holiday hours mixed into weekly hours; "Tel. Sprechzeiten" not seen as phone hours; a narrower day group now overrides an overlapping wider one ("Mo-Fr 8-19 … Fr 8-17") |
  | Audit 2 | 2/30 | misspelled weekdays ("Mitwoch") via fuzzy matching, guarded so "Dienst" and "Feiertag" are not weekdays; monthly patterns ("am 1. Freitag im Monat") are dropped, not read as weekly |

  Also handled:
  - " ? " in place of an en dash, from encoding damage in 35 source texts
  - "Mo-Mi-Do" read as a list of days
  - lowercase and uppercase day abbreviations, while the German word "so" is not read as Sunday
- **Result:** 79% read fully, 2% partial (flagged), 5% appointment only, 6% times without weekdays, and 8% not opening hours at all (phone numbers, addresses, bus directions).
  - Only **2,080 of 37,341 facilities (1 in 18)** can answer "open now?" automatically.
- **Tools:**
  - New `is_open_now(iri, at)`.
  - Search and nearest results carry an `open_now` status.
  - `find_nearest(open_now=True)` counts the excluded facilities (closed, unknown, appointment only), so the assistant can suggest calling the unknown ones. **Unknown never means closed.**
- **Live demo:** Monday 10:00, addiction counselling near 10551, open now → 3 open (nearest 0.47 km, until 17:00); 3 nearby facilities with unknown hours are reported separately.
- Tests: 80 passing (36 hours tests, including every audit regression).

### Next
- Demo script + pitch slides.
