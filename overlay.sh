#!/usr/bin/env bash
cd "$(dirname "$0")" && exec overlay/target/release/explorers-companion.exe --state elite_mapping_current.duckdb --log log/explorers-companion.log "$@"
