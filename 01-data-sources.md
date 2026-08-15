# Data sources for Elite Dangerous planetary and system information

## Acquisition hierarchy

1. **In-game Player Journal — first-party telemetry.** On PC, Elite Dangerous
   writes line-delimited JSON to `Saved Games\\Frontier Developments\\Elite
   Dangerous`. Important exploration events include `FSDJump`, `Scan`,
   `SAASignalsFound`, `CodexEntry`, `ScanOrganic`, and location/navigation
   events. `Scan` supplies the richest body facts: star/planet class, mass,
   radius, temperatures, orbital parameters, atmosphere, volcanism, materials,
   rings, parents, discovery/mapping flags and timestamps (fields vary by body
   and game version). Capture the original event JSON as immutable provenance.

2. **EDDN — near-real-time community event relay.** The Elite Dangerous Data
   Network broadcasts Journal-derived, market, outfitting and carrier messages
   to listeners. Subscribe to `journal` messages for fresh scans; retain schema
   reference/version and deduplicate by commander-independent event identity.
   It is the best ingest stream, not a historical complete archive.

3. **EDSM — broad, queryable community star/body database.** EDSM stores
   coordinates, systems, bodies, factions and exploration records; it publishes
   APIs and nightly dumps. Its public site reported ~97.7m systems and ~468.8m
   celestial bodies on 2026-07-10. Use it as the principal historical feature
   warehouse, but regard `known` as “reported to EDSM,” not ground truth.

4. **Spansh — bulk galaxy data and practical API.** Spansh OpenAPI documents
   system/body lookups and `dump/{id64}` for all relevant data in a system.
   Its downloadable galaxy/system dumps are valuable for offline model builds.
   Join by `id64`; do not rely on system names alone.

5. **EDAstro / IGAU — discovery-distribution and exploration overlays.** Its
   interactive maps expose merged exploration, biological/life-form and NSP
   layers, and draw contributions from EDDN, EDSM and direct tooling. Use these
   maps to study sampling bias and validate spatial predictions, rather than as
   the sole training source.

6. **Canonn Research Group — specialist points of interest and research.**
   Canonn's Codex/site catalogue is the best domain source for Guardian,
   Thargoid, archaeological, biological and unusual-site research. Preserve
   source URL, coordinates, body, site layout, discoverer/date and a confidence
   field; community POIs may be corrected later.

7. **EDGIS — system-neighbour and procedural-name helper.** EDGIS provides a
   system map, nearby-system queries, body retrieval and a `Predict system`
   capability. It is useful for candidate enumeration around a known system and
   for testing procedural-name/id logic; treat it as a supplementary service.

8. **EDCD tools/standards.** ED Market Connector reads Journals and can submit
   scan data to EDDN, EDSM and Inara. EDCD repositories and the Journal manual
   are the schema authority in practice. Capture `gameversion` and `build`.

## Supplementary sources (useful, but not primary training truth)

| Source | Best use | Caution |
| --- | --- | --- |
| Inara | Commander-contributed system/station context and user-facing checks | Access/terms and coverage vary; mainly Live today. |
| EDDB historical dumps / EliteBGS mirror | Historical station/economy references | EDDB is no longer the preferred active exploration backend; do not assume freshness. |
| Elite Dangerous Wiki / Fandom | Names, descriptions, category cross-checks | Community prose; verify locations with telemetry or Canonn. |
| Official Galnet / Frontier articles | Canonical event history (e.g., 3308 anomalies) | Narrative, not a structured galaxy dataset. |
| Player tools (EDDiscovery, Elite Observatory, EDMC plugins) | Collection agents and heuristic comparison | Their predictions are not independent ground truth. |

## Recommended collection architecture

```text
Player Journal --+--> raw event store --> parser/normalizer --> relational body facts
                |                                            +-> observation facts
EDDN ------------+                                            +-> provenance/events
EDSM nightly dump ---> batch reconciler ----------------------> spatial feature store
Spansh dump/API -----> backfill & candidate body/system data --> model feature view
Canonn / EDAstro ----> curated POI labels & validation set ----> label registry
```

Store `source`, retrieval time, raw payload checksum, game version and source
record ID with every fact.  Conflicting values should be versioned, not silently
overwritten.  A body may be scanned, mapped, visited, first-discovered and
first-footfall separately.

## Critical coverage biases

- Human traffic is concentrated near Sol, Colonia, Sagittarius A*, nebulae,
  carriers, neutron highways and named POIs; it is not a random galaxy sample.
- “No phenomenon reported” is normally **unknown**, not a negative label. A
  system may be unvisited, only honked, incompletely FSS-scanned, or absent from
  a particular uploader.
- Codex regions are discrete game regions, so region-level entries must not be
  treated as exact coordinates.
- Legacy and Live records must never be merged without a `galaxy_version` key.
