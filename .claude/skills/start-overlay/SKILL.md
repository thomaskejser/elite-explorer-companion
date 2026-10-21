---
name: start-overlay
description: Start (or restart) the in-game HUD overlay, the Rust overlay/target/release/ed-overlay.exe, in the background and confirm it came up from its log. Use when asked to start, launch, run, open or restart the overlay/HUD, or to bring it back after an ETL step that needed it closed.
---

# Start the overlay

The overlay is the Rust binary in `overlay/`.

## 1. Is one already running?

Two overlays fight over the app-state file (one writer per DuckDB file), so check for one:

```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'ed-overlay.exe' } | Select-Object ProcessId, Name, CommandLine"
```

- If one is listed and the user asked to *start* it, say it is already running and stop.
- If they asked to *restart*, stop it first, but only while it does not hold the database, so no write is cut off.
  The overlay releases the file after 30 s without a query; this waits for that and then stops it:

  ```bash
  for i in $(seq 1 60); do python -c "import duckdb; duckdb.connect('elite_mapping_current.duckdb', read_only=True).close()" 2>/dev/null && { powershell -NoProfile -Command "Stop-Process -Id <pid> -Confirm:\$false"; break; }; sleep 2; done
  ```

## 2. Launch it in the background

From the repo root, with the Bash tool's `run_in_background: true` (the process lives as long as the HUD does):

```bash
overlay/target/release/ed-overlay.exe --state elite_mapping_current.duckdb --log log/ed-overlay.log
```

- `--state` keeps the commander's state in the one file the ETL also uses; without it the binary keeps its own copy in `%LOCALAPPDATA%\ed-overlay\`.
- Pass through whatever the user asked for: `--chrome`, `--sector "<name>"`, `--no-hotkeys`, `--no-lights`, `--no-sound`, `--trace`.
  `ed-overlay.exe --help` lists the rest.
- `overlay.cmd` / `overlay.sh` are the same command for a person double-clicking.
- If the binary is missing, build it: `python overlay/bundle.py && (cd overlay && cargo build --release)`.

## 3. Confirm it came up

Every run is appended to `log/ed-overlay.log` under a `=== <UTC timestamp>  ...ed-overlay.exe` header.
Read what follows the newest header:

```bash
sed -n "$(grep -n '^=== ' log/ed-overlay.log | tail -1 | cut -d: -f1),\$p" log/ed-overlay.log
```

- A healthy start prints `model:` and `state:`, the `hotkeys:` bindings, a `ship: jump ... ly` line, then the first `[db]` reads.
  Report the ship line to the user.
- An error dialog, a `PANIC` line, or the background task exiting on its own means it did not start: show the error rather than retrying.
- A `SLOW db` line at startup is normal; `hand-named -- no procedural sector` means the commander is in a crafted system.

## Stale data

The galaxy is compiled into the binary, so it is as old as the last `bundle.py`.
If an ETL load ran since then, say so: run `python etl/refresh_current.py`, then `python overlay/bundle.py` and `cargo build --release`, and restart the overlay.
`bundle.py` and the refresh both read or write the app-state file, so the overlay must be closed for them.
