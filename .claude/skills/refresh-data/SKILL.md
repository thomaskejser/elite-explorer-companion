---
name: refresh-data
description: Refresh the Elite Dangerous model from the providers and score the predictions against reality. Runs every table's etl/<table>/refresh.py in dependency order (sector, system_known, body, system_body, system_predicted, POIs, carriers, phenomena, catalogues), rebuilds the overlay's app-state mirror, and reports what the window revealed - which predictions resolved and whether the model ranked them correctly. Use when asked to refresh, update, re-ingest or pull new data, or to test/validate the prediction model.
---

# Refresh the model and score it

Every `etl/<table>/refresh.py` downloads its own source, stages it and merges it, and every
merge resumes: re-running the identical command after a failure continues rather than
repeating. Run the steps in order; later tables resolve against earlier ones.

Log each step to a file in the scratchpad and **start the next step only after the previous
one's process has exited** — a loader keeps the file open while it prints its closing
report, and a second process started then dies on `being used by another process`.

## 0. Before anything

1. **No handle on the model.** DuckDB allows one writer, and a read-only attach from
   another process blocks it too:

   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='duckdb.exe'" |
     Select-Object ProcessId, CommandLine
   ```

   The overlay (`app.main`) holds only `elite_mapping_v2_current.duckdb`, so it may keep
   running until step 9.
2. **Other sessions.** `ListAgents`; ask any live session in this repo to keep off both
   database files until you say the refresh is done.
3. **Memory.** The loaders cap DuckDB at 4–8 GB. If a background job is killed with
   "the system is running low on memory", the session was not started with
   `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1` — report it and ask before restarting
   anything. The game plus Firefox is what pushes the machine over.
4. **A leftover `elite_mapping_v2.duckdb.wal`** after a crash can make the file refuse to
   open at all. Replay it without losing anything:

   ```python
   con = duckdb.connect()
   con.execute("ATTACH 'elite_mapping_v2.duckdb' AS m")
   con.execute("CHECKPOINT m")
   ```

## 1. Snapshot, or the model cannot be tested

`system_predicted` DELETES the predictions a refresh resolves — exactly the rows worth
scoring — so take both before-pictures first, dated, each with a comment:

```sql
CREATE OR REPLACE TABLE staging.pred_snapshot_<YYYYMMDD>  AS SELECT * FROM system_predicted;
CREATE OR REPLACE TABLE staging.scanned_before_<YYYYMMDD> AS SELECT DISTINCT system_id FROM system_body;
COMMENT ON TABLE staging.pred_snapshot_<YYYYMMDD> IS 'WORK TABLE: main.system_predicted as it stood on <date>, BEFORE that day''s refresh. Input to scripts/score_predictions.py.';
COMMENT ON TABLE staging.scanned_before_<YYYYMMDD> IS 'WORK TABLE: every system_id holding a system_body row on <date>, BEFORE that day''s refresh. Defines newly scanned for scripts/score_predictions.py.';
```

## 2. The model, in this order

```bash
python etl/sector/refresh.py
python etl/system_known/refresh.py
python etl/body/refresh.py
python etl/system_body/refresh.py --limit 1
python etl/system_body/refresh.py
python etl/system_predicted/refresh.py --refresh-value
python etl/region/refresh.py
python etl/poi/refresh.py
python etl/system_known/poi.py
python etl/system_body/poi.py
python etl/poi/load.py
python etl/system_poi/refresh.py
python etl/carrier/refresh.py
python etl/carrier_position/refresh.py
python etl/station_service/refresh.py
python etl/system_phenomenon/refresh.py
python etl/system_catalog_alias/refresh.py
python etl/system_catalog/refresh.py
python etl/system_unfound/refresh.py
```

What each must print, and what to do when it does not:

- **`sector` first**: `system_known` resolves a procedural name's sector by name, and a
  system whose sector is missing is EXCLUDED, not corrupted. Its report lists new sectors
  whose published id is already held (resolve by hand) and sectors where EDAstro's cell
  differs from the stored id — Juenae and Aucopp are known and correct as stored.
- **`system_known`** picks its window from the gap since the last insert: Spansh
  `1day`/`7days`/`1month`/`full`, EDSM `7days`/`full`, EDAstro `7days`. It must end with
  every reference at 0 dangling. An `*** N procedural system(s) EXCLUDED` block names the
  missing sectors; if they exist in `sector` under another spelling, the stored name is
  not `clean_sector_name()`-clean — fix the name, re-run both.
  **After an interrupted `system_known` load, re-run with an explicit `--window`** equal
  to the one it staged: the batches that merged moved `max(first_seen)` forward, so the
  automatic window undercounts the gap and leaves a hole.
- **`system_body --limit 1`** merges one bucket of eight and skips the primary cascade,
  so its `systems with >1 is_primary row ... BROKEN` line is expected. The full run
  reuses the Spansh window `system_known` merged, and must end with that line at `0 (ok)`.
- **`system_predicted --refresh-value`** after every `system_body` load: the per-system
  scan values are cached in `staging.sys_value` and are stale otherwise. It prints
  `DELETED n prediction(s)` — the resolved ones — and must end `rows missing a rate or
  value: 0`. Updating nearly every row is normal: new bodies move every fitted rate.
- **`system_catalog`** clears every alias-resolved `system_id` and re-derives it on each
  run, so its `reset to NULL for recomputation` count is never 0. What must hold still is
  the `by identity: N resolved` count and the `ALL` total line between two runs.
- **`station_service`** re-queries a live API, so its counts move between runs and its
  idempotency check is `etl/station_service/load.py` run twice, not `refresh.py`. A
  station that drops out of the pull is kept with `is_listed = FALSE`, never deleted.
- **`system_unfound`** reads `staging.catalog_parallax`, which no script creates. If it
  is ever missing, stop and say so — do not invent a source for it.

Every merge prints `merged <table>: I inserted, U updated, before -> after rows`. A line
`counts.sql predicted N insert(s) but the table grew by M` means the count and the merge
disagree — stop and find out why before trusting either.

## 3. Idempotency, whenever a loader changed

Run any loader whose code changed a second time. The second run must report
`0 inserted, 0 updated`; anything else is a float, `<>` or ordering bug in its merge.
`system_body` and `system_known` have no key constraint at all — the merge is the only
thing keeping them unique — so this also checks:

```sql
SELECT count(*) - count(DISTINCT system_id) FROM system_known;                       -- 0
SELECT count(*) - count(DISTINCT (system_body, system_id, body_no)) FROM system_body; -- 0
```

## 4. Score

```bash
python scripts/score_predictions.py            # the newest snapshot
```

It scores only systems that gained a **surveyed** body; systems that gained only a
catalogue hit (the EDAstro black-hole/Wolf-Rayet or neutron list, or a Canonn POI body)
are counted and excluded, because they contain their target by construction. What
matters is **monotonicity** — a higher predicted probability giving a higher observed
hit rate, since ranking is all the overlay asks of the model. Three caveats belong in
any summary:

- **The resolved set is not random.** Commanders scan what already looks interesting.
- **Every "found" is a lower bound.** A system counts as scanned on its first reported
  body and no source says which bodies were surveyed.
- **Boxel-predicted rows barely resolve.** `is_catalog = FALSE` rows are in no dump;
  near-zero resolutions there mean "not yet testable", never "wrong".

## 5. The overlay's mirror

The overlay reads a copy of ten model tables in the app-state file, and it goes stale
silently. Back the app-state file up first — its `main` tables are this commander's
history and cannot be rebuilt — then stop the overlay, rebuild, and restart it:

```bash
cp elite_mapping_v2_current.duckdb <scratchpad>/elite_mapping_v2_current.backup.duckdb
python etl/refresh_current.py                  # ~1 min; prints every count beside "was N"
python -m app.main                             # restart with the same command line it had
```

Check that the app-state `main` table counts are unchanged from the backup, that
`system_known_probe` did not shrink (a collapse there means a key changed under it), and
that the overlay's startup lines resolve the current system.

## 6. Report

Say plainly: systems and bodies added, predictions deleted and added, how many resolved
and how the calibration came out (with the caveats), anything excluded or dangling, and
anything that needed a fix. Quote every number from this run's output, never from memory.
