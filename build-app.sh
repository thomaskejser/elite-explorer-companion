#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/overlay"

cargo build --release

if [ "${1:-}" = "--installer" ]; then
    dotnet build -c Release installer
fi
