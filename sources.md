# Source register

Sources were retrieved and checked on 2026-07-10.
Web services, schemas and coverage change: check terms, robots/API limits and licence before automated bulk ingestion.

## Primary and operational sources

- [Elite Dangerous Journal documentation](https://elite-journal.readthedocs.io/en/latest/File%20Format.html) — line-delimited JSON format, local path and event reference.
- [EDDN / EDCD ecosystem via ED Market Connector](https://github.com/EDCD/EDMarketConnector/wiki) — Journal collection, EDDN relay role and Live/Legacy caveat.
- [EDSM](https://www.edsm.net/) — system/body database, APIs and nightly dumps; live coverage statistics.
- [Spansh OpenAPI](https://docs.spansh.co.uk/) — system, body and dump endpoints.
- [EDAstro interactive map](https://edastro.com/galmap/cgi/fetch?custom=URL) — merged exploration and biological/NSP spatial visualisation; contribution routes.
- [EDGIS](https://edgis.elitedangereuse.fr/) — system/body/neighbour lookup and prediction utility.
- [Canonn Research Group](https://canonn.science/) — specialist research/POI catalogue.

## Taxonomy and canonical context

- [Notable Stellar Phenomena reference](https://elite-dangerous.fandom.com/wiki/Notable_Stellar_Phenomena) — site placement, scan interaction and entity list.
  Community-maintained; corroborate individual records.
- [Frontier Galnet: Deep Space Anomalies](https://www.elitedangerous.com/en-US/news/galnet/deep-space-anomalies-generate-discussion) — official account of the moving 3308 anomaly event.
- [Ancient Ruins reference](https://elite-dangerous.fandom.com/wiki/Ancient_Ruins) — example of curated Guardian POI metadata and Canonn-maintained location lists.
- [Canonn stellar-phenomena distribution map (PDF)](https://canonn.science/wp-content/uploads/2019/08/Stellar_Dist.pdf) — historical spatial research; use as context, not a current complete dataset.

## How a system without bodies enters a source

A plotted route, not a visit, puts most body-less systems into Spansh and EDAstro.
Checked against the sources on 2026-10-22.

- **Plotting a route publishes every system on it.**
  The game writes `NavRoute.json`, and the commander's tools send it to EDDN as the [`navroute` schema](https://github.com/EDCD/EDDN/blob/live/schemas/navroute-README.md).
  Each hop carries the name, id64, coordinates and arrival-star class, and nothing else: no bodies, no body count.
- **Spansh and EDAstro keep those systems.**
  [EDAstro](https://edastro.com/datasources.html) splits its 205,722,682 systems into 100,354,305 visited and 105,368,377 route-only.
  For Spansh, the only statements are community ones ([Frontier forum](https://forums.frontier.co.uk/threads/neutron-router-and-unexplored-systems.617713)): route uploads are why its neutron router offers undiscovered stars.
- **EDSM does not.** Its journal API [discards](https://www.edsm.net/api-journal-v1/discard) `NavRoute`, so its systems are visited ones.
  That fits its coordinate dump holding 97M systems against Spansh's 195M.
- **Targeting a system or browsing the galaxy map publishes nothing.**
  EDDN has [no schema](https://api.github.com/repos/EDCD/EDDN/contents/schemas?ref=live) for `FSDTarget`.
- **A visit adds the arrival star, not the body count.**
  A jump (`FSDJump`, `Location`, `CarrierJump` in the [`journal` schema](https://raw.githubusercontent.com/EDCD/EDDN/live/schemas/journal-README.md)) gives coordinates, and the arrival star is scanned automatically.
- **Only the honk gives a body count.** [`fssdiscoveryscan`](https://github.com/EDCD/EDDN/blob/live/schemas/fssdiscoveryscan-README.md) carries `BodyCount` and `NonBodyCount`, and is sent only from inside the system.
  `system_known.body_count` comes from Spansh's `declared_body_count` and EDAstro's `body_count`; EDSM's coordinate dump has none.

What that leaves in the model (2026-10-22, read-only queries over `main.system_known`, `main.system_body` and the full Spansh and EDSM dumps in `staging`):

| | systems |
|---|---|
| in `system_known` | 204,535,137 |
| with a body count | 29,389,489 (14.4%) |
| with no `system_body` row | 127,288,541 (62.2%) |
| … only in Spansh, with no count and no scanned bodies: the shape a plotted route leaves | 99,906,055 |
| … in Spansh and EDSM, no count and no scans: visited, never honked | 19,010,154 |
| … in neither full dump: newer than the dumps | 5,682,514 |
| … only in EDSM | 2,677,768 |
| with body rows but no count: visited, never honked | 47,869,922 |

- Reading "only in Spansh, no count, no scans" as "added by a plotted route" is inference: no source flags route-only systems except EDAstro's totals, which it matches.
- A body-less system is therefore not evidence of an empty or unvisited system, only of one nobody honked.

## Evidence strength

- First-party Journal events are strongest for observations made by a specific client.
- EDDN and EDSM are community-mediated reproductions and aggregations of such events: highly useful at scale but incomplete.
- Canonn and wiki records are valuable curated knowledge, especially for unique POIs, but should carry provenance and a review status.
- In-game Codex entries distinguish region-level rumour, reporting and discovery; they do not prove that every system in the region contains the entry.
