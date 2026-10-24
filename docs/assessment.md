# Honest assessment: what have we actually solved?

Written 2026-10-24, after tracks 1 and 2 were built. All numbers are from the live pool.

## 1. The partner's real problem

The Civic Data Lab is not missing a search API. Their pool already has SPARQL, REST and GraphQL interfaces. It also has a config-driven federation pipeline with:
- weighted match rules
- per-field conflict-resolution strategies
- **statement-level provenance**
- a manual curation file

Their engineers are strong. What they cannot do with engineering alone:

1. **Make the pool usable and trustworthy for AI agents.** The brief asks for this "with clear sources, quality checks and honest limits".
2. **Keep quality up and grow the pool without manual work that does not scale.**

## 2. Scorecard of what we built

| What we built | Works? | New for the partner? | Honest verdict |
|---|---|---|---|
| `search_facilities`, `get_facility`, `find_nearest` | Yes, live | **No** | Thin wrappers around their own example queries (`by-postcode`, `within-bounds`, `search-by-name`). Also has a **correctness gap**: see 3A. |
| `data_quality_report` | Yes | **Little** | Completeness counts they can see themselves. The ranking weights are our opinion. It ignores the quality dimensions that matter in a *federated* pool: conflicts, staleness, uncertain matches, name quality. |
| `normalize_locality` | Yes | **Little** | 98% of facilities already have coordinates from their geocoder. Spelling of place names matters little for them. |
| New-source mapping (beratungsfinder) | Yes | **Partly** | Useful findings: a public API, about 73% of its centres are not in the pool, and shelter safety. But the code runs **outside their pipeline**: their sources are `fetch.js` + `extract.sparql` + `federation.ttl`. Our duplicate check is a cruder copy of their matcher. Not adoptable as is. |
| `is_open_now` | Yes, audited | **Yes** | A genuinely new capability, with careful accuracy work. But only 1 in 18 facilities have readable hours. As a pipeline step it could produce structured `schema:OpeningHoursSpecification`. |
| Findings | – | **Yes** | Only 1 in 18 facilities can answer "open now?". The shelter-safety rule. Departments vs facilities (`same_organisation`). |

**Bottom line:** solid, tested engineering, but mostly things the partner could have built, or already has. It does not yet touch what they could not solve.

## 3. Problems we found that are really unsolved

### A. "What kind of help is this?" is unanswerable for 88% of the pool
- Only **4,310 of 37,341 facilities (11.5%)** have a category, directly or through a linked service.
- **3,338 facilities share the same name and phone number with other entries.** Example: "Caritasverband für Stadt und Landkreis Hildesheim e.V." appears as **15 facilities** at one address. In reality they are 15 different services: debt counselling, parenting counselling, addiction help, gambling prevention, "Young Finance" and more. The real service name sits in `alternateName`, and our search does not read that field.
- **Consequence:** the partner's core citizen question ("nearest youth counselling") and the track 4 question ("districts without youth counselling") **cannot be answered correctly**. Today they are approximated by keyword matching on names.

### B. Curation does not scale
- The manual curation file has **11 entries in total**: 7 sameAs, 2 differentFrom, 2 value corrections.
- **92 match decisions sit within 0.05 of the threshold**, waiting for review.
- **98 facilities have conflicting phone numbers** across sources.
- Their engineers built the curation format but have no capacity to fill it.

### C. Their best asset is invisible in our answers
- The pool records, for every value, which source record it came from. That makes it trustworthy.
- None of our tools shows this.
- "Where does this field value come from?" is literally one of the partner's example questions, and we did not implement it.

### D. Freshness is unknown
- About **5,000 facilities were last modified before 2018**, 1,327 of them in 2009.
- **No record** has a `lastReviewed` date.
- "Which records are outdated?" is a partner question that we have not addressed.

## 4. What would be non-obvious and adoptable

| Idea | Solves | Why the partner could not easily do it | Effort |
|---|---|---|---|
| **Service classification:** classify all facilities into a help taxonomy from name, `alternateName` and description, with confidence and provenance, as a reviewable layer | A, and makes track 4 possible | Needs language understanding at scale; 33k records cannot be labelled by hand | High |
| **AI-assisted curation:** for uncertain matches, conflicts and suspected duplicates, gather the evidence and draft entries **in their own `curation.ttl` format** for one-click human approval | B | Fits directly into their pipeline; turns their unused curation format into a workflow | Medium |
| **Provenance-aware answers:** every answer cites its source and last change, plus an `explain_value` tool | C | Uses their unique asset; this is the "trustworthy for AI" requirement | Low to medium |
| **Staleness detection:** record age + website/detail-page liveness check → "likely outdated" ranking | D | Needs live checks across thousands of URLs | Medium |
| **Quick fix:** search `alternateName` too | A (partly) | – | Low |

## 5. How this connects to tracks 3 and 4
- **Track 4 (gap map)** depends on A. Without knowing which facilities are youth counselling, a coverage map is wrong.
- **Track 3 (benchmark)** is most convincing if it measures whether models answer **the partner's own example questions** correctly. That would show the difference before and after A–C.
