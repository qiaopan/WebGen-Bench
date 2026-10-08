#!/bin/bash
# Worker item: Long Memory, current code (A+B+C reflection/condense changes), fresh chain over all 101
# tasks in manifest order. Formal run 1 of the new version; compare with cluster_nomem_webgenlm7b_r1.
set -uo pipefail
source scripts/cluster/worker_lib.sh
run_longmem_tasks outputs/experiment/cluster_longmem_v2_webgenlm7b_r1 $(manifest_ids)
echo LONGMEM_V2_R1_DONE
