@echo off
cd /d "%~dp0"
start "" overlay\target\release\explorers-companion.exe --state elite_mapping_current.duckdb --log log\explorers-companion.log %*
