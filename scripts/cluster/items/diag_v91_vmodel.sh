#!/bin/bash
# Worker item, DIAGNOSTIC ONLY (user 10-12): v9.1 v-model fix on the three v9 tasks that failed on v-model.
set -uo pipefail
source scripts/cluster/worker_lib.sh
out=outputs/experiment/diag_v91_vmodel_seed11; mkdir -p "$out"
"$py" scripts/cluster/diag_v91_vmodel.py --out "$out" 000001 000002 000031 2>&1 | tee "$out/log.txt" | grep -E "RESULT|error|Traceback"
