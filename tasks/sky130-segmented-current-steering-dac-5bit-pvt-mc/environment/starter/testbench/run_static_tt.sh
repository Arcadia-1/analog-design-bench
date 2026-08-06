#!/usr/bin/env bash
set -euo pipefail

exec ngspice -b /app/testbench/tb_static_tt.spi
