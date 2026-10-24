# New source assessment: beratungsfinder

Generated 2026-10-24 by `mcp-server/scripts/estimate_source_overlap.py` from an evenly spread sample of **400 of 14,097** records (https://beratungsfinder.de). Aggregate numbers only.

## 1. Would it add new facilities?

| Pool match | Records | Share |
|---|---|---|
| new | 293 | 73% |
| same_organisation | 44 | 11% |
| already_in_pool | 30 | 8% |
| possible_duplicate | 18 | 4% |
| not_checked | 15 | 4% |

Extrapolated: about **10,326 counselling centres not yet in the pool**.
`same_organisation` records share phone or e-mail with an existing facility. They are likely departments that should become services (Angebote) of that facility, not new facilities.

**Caveat:** duplicates are searched only among pool facilities with the same postcode, so `new` is an upper bound. A centre listed in the pool under a different postcode counts as new. Shelters (`not_checked`) are never cross-matched, to protect their location.

## 2. Field coverage of the source

| Field | Records | Share |
|---|---|---|
| phone | 397 | 99% |
| e-mail | 399 | 100% |
| website | 396 | 99% |
| street address | 382 | 96% |
| coordinates | 377 | 94% |
| opening hours | 0 | 0% |
| topics (categories) | 400 | 100% |

## 3. Validation issues

| Issue | Records |
|---|---|
| no opening hours | 400 |
| locality normalised | 24 |
| confidential location | 15 |
| missing street address | 3 |
| missing or invalid postcode | 1 |
| invalid e-mail | 1 |

## 4. Most common topics

| Topic | Records |
|---|---|
| Krisenintervention | 191 |
| Beratung für Menschen mit Behinderung | 189 |
| Beratung für Seniorinnen & Senioren | 189 |
| Psychosoziale Beratung bei Krankheit | 189 |
| Beratung für Kinder und Jugendliche | 186 |
| Sozialberatung | 172 |
| Familienberatung | 152 |
| Alleinerziehende Mütter | 138 |
| Lebensberatung | 137 |
| Frauenberatung | 131 |
| Ehe- und Partnerschaftsberatung | 118 |
| Alleinerziehende Väter | 107 |
| Trennung und Scheidung | 95 |
| Beratung für junge Migrant*innen (12 bis 27 Jahre) | 94 |
| Beratung für erwachsene Migrant*innen (ab 27 Jahre) | 93 |
