@echo off
cd /d "%~dp0"
start "" overlay\target\release\ed-overlay.exe --state elite_mapping_v2_current.duckdb --log log\ed-overlay.log %*
