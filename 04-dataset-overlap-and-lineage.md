# Dataset overlap and lineage: EDAstro validation

Research validated 2026-07-10.

## Conclusion

**EDAstro is not an aggregate of all Elite Dangerous datasets.** It is a major
derived data and visualisation service whose core system/body corpus is built
from **real-time EDDN** submissions, supplemented by a periodic **EDSM body-dump
pull**. It then adds selected specialist sources and its own direct submissions.
It is a broad and valuable *overlap/derived layer*, but neither its own
documentation nor the available interfaces support treating it as complete or
as the canonical master for EDSM, Spansh, Canonn, Inara or all player data.

## Confirmed lineage

```text
Game Journal
    |\
    | +--> EDDN relay --------------------+--> EDAstro (main near-real-time feed)
    |                                     +--> EDSM, Spansh and other listeners
    +----> direct tool uploads -----------> EDSM / Spansh / Inara / Canonn

EDSM body dump ------------------------------> EDAstro (periodic gap backfill)
EDAstro direct API --------------------------> EDAstro (Codex, organic, carrier gaps)
Specialist lists (GMP, DSSA, IGAU, etc.) ----> EDAstro selected overlays/POIs
```

EDAstro explicitly says its bulk data is received in real time from EDDN, that
an EDSM pull runs every few days to fill outages/gaps, and that its direct API
fills data that cannot be easily obtained through those feeds — notably Codex,
Odyssey organic genetic scans and fleet-carrier information. Its journal upload
page is even more specific: **all body/system data comes from EDDN and EDSM**.

## What overlaps, and why it matters

| Dataset/service | Relationship to EDAstro | What is *not* safe to assume |
| --- | --- | --- |
| Game Journal | Upstream original observation; some events reach EDAstro via EDDN or direct upload | A local Journal event was uploaded, received, parsed or retained by EDAstro. |
| EDDN | EDAstro's primary live system/body ingest | EDDN is a complete historical archive or every client submits. Listener outages and unsubmitted Journals create gaps. |
| EDSM | EDAstro periodically imports its body dump as reliability backfill; strong overlap | Identical timing, fields, corrections, completeness or provenance. EDSM is also independently populated. |
| Spansh | Listed by EDAstro as an additional source; both also consume community data/EDDN ecosystem | All Spansh system/body records appear in EDAstro, or vice versa. Spansh exposes its own full-galaxy dumps/API. |
| Canonn / IGAU Codex | EDAstro lists IGAU Codex and offers direct Codex ingest | Full Canonn science/POI corpus, research annotations and missions are imported. |
| Galactic Mapping Project / DSSA / nebulae / GGG lists | Selected additional EDAstro sources and combined POI outputs | Their current source catalogues are fully mirrored, reconciled or independently verified. |
| Inara | Additional source | Inara's commander/station/economy and timing coverage is duplicated. |

## Important directionality correction

EDDN is a **relay/network**, not a database that necessarily subsumes EDSM or
Spansh. A single Journal-derived scan can fan out to several listeners, while
each listener may also receive direct uploads, preserve older history, apply
different validation, or miss events during downtime. Therefore overlapping
records are often *correlated observations*, not independent confirmations.

EDAstro began from EDSM dumps and later moved to EDDN as its main feed. That
history explains its large coverage and EDSM-shaped overlap; it does not mean
EDAstro contains every record in EDSM or every record submitted to any other
community project.

## Consequence for Elite Mapping database design

1. Use **Spansh full-galaxy dumps** or a directly licensed equivalent as the
   bulk known-body bootstrap; use EDSM nightly/full-access data where authorised
   for reconciliation. Do not replace either solely with EDAstro exports.
2. Ingest **EDDN** continuously for freshness, but retain raw events and an
   event/source fingerprint to deduplicate fan-out copies.
3. Use **EDAstro** particularly for discovery-density, curated POI overlays,
   direct Codex/organic visibility and convenient rare-body subsets. Attribute
   each record to EDAstro and, where exposed, its underlying source.
4. Ingest **Canonn/IGAU/GMP** as separately versioned curated sources. Merge by
   `system_id64` and body/coordinates, but preserve source-specific site IDs and
   descriptions.
5. Model source coverage, `observed_at`, `ingested_at`, `galaxy_version` and
   record-level provenance. A union view should select the latest/highest-
   confidence fact, not erase its lineage.

## Practical overlap audit before modelling

For a fixed snapshot date, calculate by stable ID:

- system/body counts per source;
- intersections and source-only counts (EDAstro ∩ EDSM, EDAstro ∩ Spansh,
  EDSM ∩ Spansh);
- field-level agreement for class, coordinates, rings, signal counts and scan
  time;
- lag from Journal/EDDN event to each service;
- POI intersection by `id64`, parent body and surface coordinates; and
- an `unknown` bucket for systems lacking a full FSS/DSS observation.

Do this separately for Live and Legacy.  Report both raw intersections and
source-attributable intersections, because a record received from EDDN and later
backfilled from EDSM is one correlated observation lineage, not two discoveries.

## Primary supporting pages

- [EDAstro Data Sources](https://edastro.com/datasources.html) — identifies
  EDDN and EDSM as main sources, EDSM gap-fill cadence, and the additional list.
- [EDAstro data submission](https://edastro.com/journals/upload.html) — states
  body/system data comes from EDDN and EDSM; lists direct-only event areas.
- [EDAstro API information](https://edastro.com/api-info.html) — explains the
  Codex/organic/carrier gaps and direct API purpose.
- [EDAstro map/data files](https://edastro.com/mapcharts/files.html) — declares
  scan statistics are based on EDDN/EDSM and identifies combined POI exports.
- [Spansh API](https://docs.spansh.co.uk/) and [Spansh acknowledgements](https://spansh.co.uk/thanks)
  — evidence of independent data access/dumps and community data lineage.
