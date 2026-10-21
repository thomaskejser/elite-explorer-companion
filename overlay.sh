#!/usr/bin/env bash
cd "$(dirname "$0")" && exec overlay-rs/target/release/ed-overlay.exe --state elite_mapping_v2_current.duckdb --log log/ed-overlay.log "$@"
