#!/bin/bash
# Worker item, DIAGNOSTIC ONLY (user 10-11): replay the seed-11 code-pool updates under v8 and v9 rules with the real
# memory model; no generation, no evaluation, fresh databases only.
set -uo pipefail
source scripts/cluster/worker_lib.sh
out=outputs/experiment/diag_replay_code_pool_seed11; mkdir -p "$out"
memkey=$(key_file WEBGEN_MEMORY_API_KEY); trap 'rm -f "$memkey"' EXIT
for v in v8 v9; do
  echo "== $v"
  "$py" scripts/cluster/replay_code_pool.py outputs/experiment/cluster_order_blocks11_longmem_v7 \
    config/long_memory_cluster_$v.json --key-file "$memkey" --out "$out/$v.db" 2>&1 | tee "$out/$v.log" | grep -E "ADD|VERSION|ROW"
done
