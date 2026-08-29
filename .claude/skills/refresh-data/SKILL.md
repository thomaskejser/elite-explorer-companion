---
name: refresh-data
description: Refresh the Elite Dangerous model from the providers and score the predictions against reality. Downloads the Spansh/EDSM/EDAstro deltas, merges them into system_known and system_body, rebuilds system_predicted, then reports what the window revealed - which predictions resolved, whether the model ranked them correctly, and whether the commander's own discoveries reached the official dumps. Use when asked to refresh, update, re-ingest or pull new data, or to test/validate the prediction model.
---

# Refresh the model and score it

Run the steps in order. Every step merges and resumes, so a re-run after a failure
continues rather than repeating. Budget **60-90 minutes**, nearly all of it in the two
big merges.

## 0. Take the lock, and take the before-picture

**Close the overlay.** DuckDB allows one writer and a read-only reader still blocks it.
Record the command line first so it can be restarted identically at the end.

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like "*app.main*" } |
  ForEach-Object { $_.CommandLine; Stop-Process -Id $_.ProcessId -Force }
```

**Snapshot, or the model cannot be tested.** `build_system_predicted.py` DELETES rows
whose systems have since been explored — exactly the rows worth scoring. Both tables are
dated, both live in `staging`, and both need a `COMMENT ON` saying which refresh they
precede:

```sql
CREATE OR REPLACE TABLE staging.pred_snapshot_<YYYYMMDD>  AS SELECT * FROM system_predicted;
CREATE OR REPLACE TABLE staging.scanned_before_<YYYYMMDD> AS SELECT DISTINCT system_id FROM system_body;
```

Without the second, "newly scanned" has no definition once the merge is done.

## 1. Download → staging

```bash
python scripts/ingest_sources.py --incremental --window 1month --only spansh
python scripts/ingest_sources.py --incremental --only edsm_star_system,edsm_celestial_body,edastro_star_system,edastro_star,edastro_planet
python scripts/ingest_sources.py --list        # every role must show today's date
```

Spansh publishes `1day` / `7days` / `1month`; every other provider publishes a 7-day
window only and ignores `--window`. The Spansh monthly is ~5.9 GB and parses in about
5 minutes at ~11k systems/s.

**Confirm the download really happened.** Deltas are size-checked against the server with
a HEAD request and re-fetched on mismatch, because the provider rewrites the same filename
every day and a cached copy would silently re-ingest a window already merged. Look for
`GET` or `is stale ... refetching` on every delta; a bare `have` line means the bytes
matched exactly, which is possible but worth a glance.

## 2. Merge staging → main, IN THIS ORDER

```bash
python etl/build_sector.py                                  # FIRST. see below
python etl/build_system_known.py --all                      # ~20 min
python etl/build_system_body.py --delta --all --rebuild-staging   # ~10 min
python etl/build_system_predicted.py --build                # ~15 min
python scripts/score_predictions.py
```

**`build_sector.py` must run first.** New sectors appear as people explore — 27 of them in
one month. `build_system_known` resolves a procedural name against `sector`, and a missing
sector used to send the system to the `sector_id = 0` sentinel with its prefix stripped, so
`Pria Scrio AA-H d10-0` was filed as a hand-named system called `AA-H d10-0`. Two of those
in different unknown sectors then collide on the primary key and the merge dies. There is
now a guard that excludes and reports such rows instead, but the fix is still to build the
sectors first.

**`--rebuild-staging` is required on the body merge.** Phase 1 is skipped whenever
`staging.src_body` exists, which is the right default mid-load and exactly wrong on a
refresh: without it the merge re-merges the PREVIOUS window and reports success. The tell
is a tiny insert count — 1,562 rows instead of 5.2 million.

Run the merges in the background with a log and wait on it, since they outlast a
foreground call. Each script ends in `DONE_<NAME>`; grep for `Traceback` too, so a crash is
not mistaken for still-running:

```bash
nohup python etl/build_system_known.py --all > merge_known.log 2>&1 &
until grep -qE "DONE_BUILD_SYSTEM_KNOWN|Traceback" merge_known.log; do sleep 20; done
```

## 3. Verify, do not assume

**Stale predictions left the table.** The builder prints `DELETED n stale prediction(s)`.
Check it independently — this must return 0:

```sql
SELECT count(*) FROM staging.pred_snapshot_<date> p
JOIN system_known k ON k.id64 = p.system_id64
WHERE EXISTS (SELECT 1 FROM system_body b WHERE b.system_id = k.system_id)
  AND EXISTS (SELECT 1 FROM system_predicted s WHERE s.system = p.system);
```

**No sentinel corruption.** Must be 0; if not, a sector was missing during the merge:

```sql
SELECT count(*) FROM system_known
WHERE sector_id = 0 AND regexp_matches(system_in_sector, '^[A-Z][A-Z]-[A-Z] [a-h][0-9]');
```

**The commander's finds.** `elite_mapping_v2_current.duckdb` holds `system_visited`,
`system_confirmed` and `system_seen`. Resolve their names against the refreshed
`system_known` — parse `<sector> <AB-C d1-234>` and join `sector`, do NOT use
`staging.sys_bridge`, which is stale until the next full rebuild. A confirmed find that
was absent and is now present is the commander's own upload completing the round trip
through EDDN to the providers.

## 4. Reading the score

`scripts/score_predictions.py` prints predicted-vs-found and a decile calibration table.
The result that matters is **monotonicity** — higher predicted probability giving a higher
observed hit rate — because ranking is all the overlay asks of the model. Three caveats
belong in any summary, and they are in the script's own docstring:

- **The resolved set is not random.** Commanders scan what already looks interesting, so
  observed rates run high for reasons unrelated to the model.
- **Every "not found" is a lower bound.** A system counts as scanned on its first reported
  body and no source carries a DSS/mapped flag, so an unreported object and an absent one
  are indistinguishable.
- **The boxel-predicted layer barely resolves.** `is_catalog = FALSE` rows are in no dump;
  near-zero resolutions there means "not yet testable", never "wrong".

## 5. Afterwards

Restart the overlay with the recorded command line, and report plainly: systems added,
bodies added, predictions deleted and added, predictions resolved, how the calibration
came out, and which of the commander's finds are now public.

## Known cost traps

- **Bucket counts follow the staged set size.** Both big merges anti-join the whole target
  table once per bucket, so 64/128 buckets on a 3.8M-row delta pays that join dozens of
  times to insert a few thousand rows each — hours instead of minutes. Both builders now
  pick 4 (systems) or 8 (bodies) for a delta and expose `--buckets N`.
- **Never union full sources to look up a handful of rows.** A probe of the full Spansh
  plus EDSM tables to recover 54 names materialises ~290M rows and dies at the memory
  limit; filter by the ids you actually need.
