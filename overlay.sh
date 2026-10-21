#!/usr/bin/env bash
cd "$(dirname "$0")" && exec overlay/target/release/ed-overlay.exe --state elite_mapping_current.duckdb --log log/ed-overlay.log "$@"
