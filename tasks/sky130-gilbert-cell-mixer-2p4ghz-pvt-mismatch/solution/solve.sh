#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/app}"
SOLUTION_DIR="${SOLUTION_DIR:-/solution}"

cd "$APP_DIR"
install -m 0644 "$SOLUTION_DIR/circuit.spi" circuit.spi
