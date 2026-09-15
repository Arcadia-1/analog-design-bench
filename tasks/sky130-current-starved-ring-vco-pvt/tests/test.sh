#!/usr/bin/env sh

mkdir -p /logs/verifier
rm -f /logs/verifier/reward.json /logs/verifier/new-ctrf.json
test -e /app/circuit.spi || true
python3 /app/analog_arena_tests/verify.py
