# Sources

Every source the project reads, what it feeds, how the sources overlap, and what each can and cannot prove.
Web services, schemas and coverage change: check terms, API limits and licence before bulk downloading from a new one.
`staging.ingest_manifest` records every download (URL, bytes, rows, role, time, staging table).

## What the ETL downloads

| provider | download | feeds |
| --- | --- | --- |
| Spansh | `downloads.spansh.co.uk/galaxy{,_1month,_7days,_1day}.json.gz` | `system_known`, `system_body` (`common/spansh.py`) |
| Spansh | `downloads.spansh.co.uk/galaxy_stations.json.gz` | `station` |
| Spansh | `spansh.co.uk/api/stations/search` | `station_service` |
| EDSM | `edsm.net/dump/systemsWithCoordinates{,7days}.json.gz` | `system_known` |
| EDSM | `edsm.net/dump/bodies7days.json.gz` | `system_body` |
| EDSM | `edsm.net/dump/codex.json.gz` | `codex_sighting`, `system_phenomenon` (`common/codex.py`) |
| EDAstro | `edastro.com/mapcharts/files/sector-list.csv` | `sector` |
| EDAstro | `edastro_systems7days.jsonl.gz` | `system_known` |
| EDAstro | `edastro_planets7days.jsonl.gz`, `Black-Holes.csv`, `Wolf-Rayet-stars.csv`, `neutron-stars.csv` | `system_body` |
| EDAstro | `fleetcarriers.csv` | `carrier` |
| EDAstro | `edastro.com/gec/json/combined` (points of interest) | `poi`, `system_phenomenon` |
| Canonn | `storage.googleapis.com/canonn-downloads/codex.json.gz` | `region`, `exobio_odds`, `exobio_genus_odds`, `exobio_species`, `codex_sighting`, `system_phenomenon` |
| klightspeed | [EliteDangerousRegionMap](https://github.com/klightspeed/EliteDangerousRegionMap) `RegionMapData.json` (MIT) | `region_map` |
| Silarn | [EDMC-BioScan](https://github.com/Silarn/EDMC-BioScan) and [EDMC-ExploData](https://github.com/Silarn/EDMC-ExploData) (GPL-2.0) | `input/exobio_species.parquet`, once, by `etl/exobio_species/seed.py` |
| NASA Exoplanet Archive, VizieR, SIMBAD | TAP queries | `input/system_catalog.parquet` and `input/system_catalog_alias.parquet`, once, by their `seed.py` |

- Staging tables are named after the download, so a 7-day slice can never be read as a catalogue (`ETL.md`).
- Raw files under `raw/` are deleted once staged; a refresh downloads again what it needs.

## What the overlay reads

- **The game's journal**, `Status.json` and `NavRoute.json` under Saved Games: the commander's position, jumps, scans, route and fuel.
  The [journal manual](https://elite-journal.readthedocs.io/en/latest/File%20Format.html) is the event reference; `gameversion` and `build` are in every file header.
- **Spansh** `api/dump` and `api/stations/search`, and **EDSM** `api-v1/system` and `api-system-v1/bodies`: live lookups for a jump target, carriers and markets.
- **Compiled-in tables**, fetched at build time by `overlay/*.py`: EDCD's [FDevIDs](https://github.com/EDCD/FDevIDs) and [coriolis-data](https://github.com/EDCD/coriolis-data) (engineers and modules), the [Elite Dangerous Wiki](https://elite-dangerous.fandom.com/) (Guardian and Thargoid sites), and [Elite Dangerous Utilities](https://elitedangerousutilities.azurewebsites.net/) (Sirius brokers).
- **The FSS spectrum's ranges** come from [Deep Space Network: in-depth spectral analysis](https://ed-dsn.net/en/in-depth-spectral-analysis/): each body and signal type's range on the bar, LOW to HIGH, and its icon.
  The ranges are drawn in the page's 2018 images (`AFreq_EN_*.png`, `landables_bodies_EN.png`, `gaz_giants_EN.png`), not stated as numbers; `bands::RANGES` holds them as measured from those images on 2026-11-01, and `overlay/DESIGN.md` (*The FSS spectrum's ranges*) says how.
  Checked against the commander's own resolved icons the same day: every label but one fell inside its type's range, within about 0.005.

## How the sources relate

```text
Game journal
    |\
    | +--> EDDN relay --------------------+--> EDAstro (main near-real-time feed)
    |                                     +--> EDSM, Spansh and other listeners
    +----> direct tool uploads -----------> EDSM / Spansh / Inara / Canonn

EDSM body dump ------------------------------> EDAstro (periodic gap backfill)
EDAstro direct API --------------------------> EDAstro (codex, organic, carrier gaps)
Specialist lists (GMP, DSSA, IGAU, ...) -----> EDAstro selected overlays and POIs
```

- **EDDN** is a relay, not an archive: listener outages and journals never uploaded leave gaps, and nothing here listens to it directly.
- **EDAstro is not an aggregate of every dataset.**
  Its system and body data come from EDDN in real time, backfilled from EDSM's body dump every few days ([data sources](https://edastro.com/datasources.html), [journal upload](https://edastro.com/journals/upload.html)); its own API fills codex, organic scan and carrier data the feeds lack ([API](https://edastro.com/api-info.html)).
- **EDSM** is populated independently as well as through EDDN, so it overlaps EDAstro strongly without matching it in timing, fields or corrections.
- **Spansh** publishes its own full-galaxy dumps ([API](https://docs.spansh.co.uk/), [acknowledgements](https://spansh.co.uk/thanks)); neither it nor EDAstro contains the other.
- **Canonn** is the domain source for codex reports and Guardian, Thargoid and biological sites; EDAstro carries only selected codex data from it.
- One journal scan fans out to several listeners, so records that agree across sources are often **correlated copies of one observation**, not independent confirmations.

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

## What each source can prove

- **The commander's journal** is first-party and the strongest evidence for what this commander saw; `Scan` carries the richest body facts and the discovery and mapping flags no community source has.
- **EDSM, Spansh and EDAstro** are community-mediated copies of journal events: broad, but "known" means "reported to that source", never ground truth.
- **Canonn and wiki records** are curated knowledge, strongest for unique sites; community prose should be corroborated with telemetry.
- **An in-game codex entry** is region-level: it does not prove every system in the region holds it, and a region is not a coordinate.
- **"Nothing reported" is unknown, not absent.**
  A system may be unvisited, only honked, incompletely scanned, or never uploaded.
- **Traffic is not a random sample**: it concentrates near Sol, Colonia, Sagittarius A*, nebulae, carriers, the neutron highways and named sites.
- **No dump separates Live from Legacy** (`galaxy_version` is unknown).

## Consulted, not ingested

- [Notable Stellar Phenomena](https://elite-dangerous.fandom.com/wiki/Notable_Stellar_Phenomena) and [Ancient Ruins](https://elite-dangerous.fandom.com/wiki/Ancient_Ruins) on the Elite Dangerous Wiki: site placement and entity lists.
- [Frontier Galnet: Deep Space Anomalies](https://www.elitedangerous.com/en-US/news/galnet/deep-space-anomalies-generate-discussion): the moving 3308 anomaly event.
- [Canonn stellar-phenomena distribution map (PDF)](https://canonn.science/wp-content/uploads/2019/08/Stellar_Dist.pdf): historical spatial research, not a complete dataset.
- [EDGIS](https://edgis.elitedangereuse.fr/): system, body and neighbour lookups and procedural-name prediction.
- Inara, EDDB's historical dumps, and player tools (EDDiscovery, Elite Observatory, EDMC plugins): their predictions are not independent ground truth.
