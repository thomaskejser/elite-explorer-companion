---
name: start-overlay
description: Start (or restart) the in-game HUD overlay, the Rust overlay/target/release/explorers-companion.exe, in the background and confirm it came up from its log. Use when asked to start, launch, run, open or restart the overlay/HUD, or to bring it back after an ETL step that needed it closed.
---

# Start the overlay

The overlay is the Rust binary in `overlay/`, built as `explorers-companion.exe`.

## 1. Is one already running?

Two overlays fight over the app-state file (one writer per DuckDB file), so check for one:

```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'explorers-companion.exe' } | Select-Object ProcessId, Name, CommandLine"
```

- If one is listed and the user asked to *start* it, say it is already running and stop.
- If they asked to *restart*, close it cleanly, as closing its main window does, so any write in progress finishes; never `Stop-Process`, which kills it mid-write and shows as an error:

  ```bash
  powershell -NoProfile -Command "$p=Get-Process explorers-companion; $p.CloseMainWindow() | Out-Null; $p.WaitForExit(15000)"
  ```

## 2. Launch it in the background

From the repo root, with the Bash tool's `run_in_background: true` (the process lives as long as the HUD does):

```bash
./explorers-companion.sh
```

- It runs `overlay/target/release/explorers-companion.exe --state elite_mapping_current.duckdb --log log/explorers-companion.log`.
- `--state` keeps the commander's state in the one file the ETL also uses, and a file named this way is never replaced by a seed install.
- Pass through whatever the user asked for: `--sector "<name>"`, `--trace`, `--slow-ms <ms>`.
  `explorers-companion.exe --help` lists the rest.
- Sounds, throttle lights, navigation keys, always-visible, the title bar, dragging, HUD size and opacity, and keeping FSS screenshots are not flags: they are on the Settings tab, saved in the state file.
- If the binary is missing, build it: `(cd overlay && cargo build --release)`.

## 3. Confirm it came up

Every run is appended to `log/explorers-companion.log` under a `=== <UTC timestamp>  ...explorers-companion.exe` header.
Read what follows the newest header:

```bash
sed -n "$(grep -n '^=== ' log/explorers-companion.log | tail -1 | cut -d: -f1),\$p" log/explorers-companion.log
```

- A healthy start prints `state:`, `hud: <height> px high, scale <s>`, the `hotkeys:` bindings, a `ship: jump ... ly` line, then the first `[db]` reads.
  Report the ship line to the user.
- An error dialog, a `PANIC` line, or the background task exiting on its own means it did not start: show the error rather than retrying.
- A `SLOW db` line at startup is normal; `hand-named -- no procedural sector` means the commander is in a crafted system.

## Stale data

The overlay reads the model mirror in `elite_mapping_current.duckdb`, so it is as old as the last `python etl/refresh_current.py`.

- If an ETL load ran since then, say so: close the overlay, run `python etl/refresh_current.py`, and start it again.
- `python etl/build_seed.py` builds the release seed from the model and needs neither the overlay closed nor a rebuild.
