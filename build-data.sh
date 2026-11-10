#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

step() {
    echo "=== $(date -u +%H:%M:%S) $*"
    python "$@"
}

step scripts/create_current_db.py

step etl/sector/refresh.py
step etl/system_known/refresh.py
step etl/body/refresh.py
step etl/system_body/refresh.py
step etl/prediction_outcome/refresh.py
step etl/system_predicted/refresh.py --refresh-value
step etl/region/refresh.py
step etl/exobio_species/refresh.py
step etl/exobio_odds/refresh.py
step etl/exobio_genus_odds/refresh.py
step etl/system_exobio/refresh.py
step etl/system_green_giant/refresh.py
step etl/region_map/refresh.py

step etl/poi/refresh.py
step etl/system_known/poi.py
step etl/system_body/poi.py
step etl/poi/load.py
step etl/system_poi/refresh.py
step etl/body_poi/refresh.py

step etl/carrier/refresh.py
step etl/carrier_position/refresh.py
step etl/station_service/refresh.py
step etl/station/refresh.py
step etl/system_phenomenon/refresh.py
step etl/codex_sighting/refresh.py

step etl/system_catalog_alias/refresh.py
step scripts/export_commander_aliases.py || echo "=== commander aliases skipped: a first build has no system_catalog yet, and a later one needs explorers-companion.exe closed"
step etl/system_catalog/refresh.py
step etl/system_unfound/refresh.py || echo "=== system_unfound skipped: it needs staging.catalog_parallax, which no script creates (ETL.md)"
step scripts/apply_schema.py system_all
step scripts/apply_schema.py body_type_census

step etl/refresh_current.py
step etl/build_seed.py
