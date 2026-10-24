# Data-quality profile: Federated Data Pool

Generated 2026-10-24 from the live endpoint `https://sosuse.correlaid.org/directory/sparql` by `mcp-server/scripts/profile_quality.py`. Re-run it to refresh the numbers.

## 1. Coverage of published facilities, per source
Share of facilities passing each check. A merged facility counts for every source that contributed to it.

| Scope | Facilities | phone number | map location | opening hours | opening hours with actual times | valid 5-digit postcode | e-mail address | website |
|---|---|---|---|---|---|---|---|---|
| **All (published)** | 37,341 | 76% | 98% | 7% | 99% | 99% | 73% | 60% |
| caritas | 32,326 | 80% | 98% | 3% | 100% | 99% | 77% | 63% |
| dhs | 2,126 | 100% | 96% | 83% | 95% | 100% | 100% | 95% |
| awo | 46 | 2% | 89% | 2% | 100% | 98% | 2% | 83% |
| destatis | 1,348 | 21% | 95% | 6% | 99% | 100% | 20% | 15% |
| sozialplattform | 2,766 | 37% | 95% | 24% | 98% | 100% | 36% | 25% |

## 2. What each source delivers before merging

| Source | Records delivered | with phone | with opening hours |
|---|---|---|---|
| caritas | 32,326 | 80% | 2% |
| sozialplattform | 2,866 | 14% | 6% |
| dhs | 2,126 | 100% | 83% |
| destatis | 1,361 | 0% | 0% |
| awo | 47 | 0% | 0% |

Comparing tables 1 and 2 shows the value of federation. For example, Destatis delivers no phone numbers, but some of its facilities gain one by being merged with records from other sources.

## 3. How many sources were merged per facility

| Sources merged into one facility | Facilities |
|---|---|
| 1 | 36,218 |
| 2 | 981 |
| 3 | 136 |
| 4 | 6 |

## 4. Free-text and format problems

| Check | Count |
|---|---|
| Facilities with opening hours | 2,622 |
| … whose hours text contains no digit (not actual hours) | 221 |
| … mentioning "nach Vereinbarung" (by appointment) | 533 |
| Addresses with a postcode | 25,871 |
| … postcode not 5 digits | 7 (0%) |
| … of which 4 digits (leading zero lost, e.g. 8371 → 08371) | 3 |
| Distinct locality spellings starting with "Berlin" | 23 |
| Distinct locality values with stray spaces/hyphens ("Berlin- Tempelhof") | 142 |

## 5. Ten records to fix first
Score = sum of weights of failed checks (phone number 3, map location 3, opening hours 2, opening hours with actual times 1, valid 5-digit postcode 1, e-mail address 1, website 1), +5 if there is no phone, e-mail or website at all.

| Score | Facility | Place | Sources | Missing |
|---|---|---|---|---|
| 16 | Kontakt | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Schuldnerberatung Zwickau | 8371 Glachau | sozialplattform | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Katholisches Jugendreferat | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Betreute Wohngemeinschaft des Caritasverbandes Darmstadt | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Suchtberatung - Psychosoziale Beratung, ambulante Behandlung Konstanz | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Caritas-Suchthilfe, Mettmann | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Seniorenpflegeheim Bilhildis | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Seniorenwohngemeinschaft | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Adaptionhaus in Heppenheim Facheinrichtung der Klinik Schloß Falkenhof | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
| 16 | Katholische Akademie Regensburg | – | caritas | phone number, map location, opening hours, valid 5-digit postcode, e-mail address, website |
