#!/bin/bash
# Worker item, DIAGNOSTIC ONLY (user 10-11): v9 code pool on seed-11 v7 failures + high scorers; generation and
# code check only, no evaluation. v9 full run stays held in filler.conf until this passes.
set -uo pipefail
source scripts/cluster/worker_lib.sh
out=outputs/experiment/diag_v9_codepool_seed11; mkdir -p "$out"
memkey=$(key_file WEBGEN_MEMORY_API_KEY); trap 'rm -f "$memkey"' EXIT
"$py" scripts/cluster/diag_v9_codepool.py --key-file "$memkey" --out "$out" \
  000029 000026 000050 000049 000080 000025 000023 000076 000101 000054 000052 000051 000053 000041 000066 000070 000042 000087 000086 \
  000056 000032 000081 000077 \
  000072 000082 000085 000067 000065 000064 000075 000062 2>&1 | tee "$out/log.txt" | grep -E "RESULT|error|Traceback"
