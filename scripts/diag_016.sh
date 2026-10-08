#!/bin/zsh
# Diagnostic only: Long Memory 000016 on copies of the Long Memory DB. (a) condensed guidance, (b) unchanged.
set -uo pipefail
cd "${0:A:h:h}"
export WEBGEN_GENERATION_TIMEOUT_SECONDS=2700 WEBGEN_MAX_REPAIR_ATTEMPTS=5 PYTHONUNBUFFERED=1
run() {
  env/webvoyager/bin/python3.10 scripts/run_continual_memory.py --modes continual --post-task-reflection \
    --memory-representation case_only --url http://127.0.0.1:5186/ --generator-model WebGen-LM-7B \
    --memory-config "$2" --output "outputs/experiment/$1" --database "outputs/experiment/$1/memory.db" --task-ids 000016
  echo "$1 exit code: $?"
}
env/webvoyager/bin/python3.10 scripts/preflight_reflective_models.py || exit 1
echo "=== Long Memory 000016 (diag a: condensed) ==="; run diag_016_condensed config/long_memory_condensed.json
echo "=== Long Memory 000016 (diag b: unchanged rerun) ==="; run diag_016_baseline config/long_memory.json
echo DIAG016_DONE
