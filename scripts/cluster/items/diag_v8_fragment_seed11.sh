#!/bin/bash
# Worker item, DIAGNOSTIC ONLY (user 10-10): regenerate the 8 seed-11 tasks where v7 returned the scaffold,
# with the whole-file "Missing package" example replaced by the v8 fragment; code checks only, no evaluation.
set -uo pipefail
source scripts/cluster/worker_lib.sh
load_generator_env
out=outputs/experiment/diag_v8_fragment_seed11
mkdir -p "$out"
memkey=$(key_file WEBGEN_MEMORY_API_KEY); trap 'rm -f "$memkey"' EXIT
"$py" scripts/cluster/diag_v8_fragment.py --key-file "$memkey" --out "$out" \
  000029 000026 000050 000049 000080 000025 000023 000076 2>&1 | tee "$out/run.log" | grep -E "^RESULT|^FRAGMENT|skipped|error"
