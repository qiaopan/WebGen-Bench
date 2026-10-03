#!/bin/zsh
# Finish the 11-task catch-up set one task at a time; both arms of a task run back to back.
# After each task, prints a PAIR comparison for that task (paper convention) when both arms exist.
# Stops immediately when any task uses up every repair attempt, so it can be reviewed first.
set -uo pipefail

script_dir="${0:A:h}"
cd "${script_dir:h}"

nomem="outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o_r2"
longmem="outputs/experiment/longmem_mac_q8_19_21_then_remaining_r1"
bolt_url="${WEBGEN_BOLT_URL:-http://127.0.0.1:5186/}"
export WEBGEN_GENERATION_TIMEOUT_SECONDS="${WEBGEN_GENERATION_TIMEOUT_SECONDS:-2700}"
export WEBGEN_MAX_REPAIR_ATTEMPTS="${WEBGEN_MAX_REPAIR_ATTEMPTS:-5}"
export PYTHONUNBUFFERED=1

# arm:task pairs, in order. Tasks already complete in progress.jsonl are skipped by the runner.
queue=(${=QUEUE:-L:000016 L:000017 N:000018 L:000018 N:000019 N:000020 L:000020 N:000021 N:000026 N:000027 L:000027 N:000028})

env/webvoyager/bin/python3.10 scripts/preflight_reflective_models.py || exit 1

stop_if_exhausted() {
  local report="$1/tasks/$2/$3/000001.generation.json"
  env/webvoyager/bin/python3.10 - "$report" <<'EOF' || { echo "REPAIR_EXHAUSTED $2 $3 ($report)"; exit 2; }
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
if not path.is_file():
    sys.exit(0)
report = json.loads(path.read_text())
attempts = report.get("attempts", [])
exhausted = len(attempts) >= report.get("max_repair_attempts", 0) + 1 and not any(a.get("ok") for a in attempts)
sys.exit(1 if exhausted else 0)
EOF
}

for item in $queue; do
  arm=${item%%:*}; id=${item#*:}
  if [[ $arm == N ]]; then
    echo "=== No Memory $id ==="
    env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
      --modes disabled --url "$bolt_url" --generator-model WebGen-LM-7B \
      --output "$nomem" --database "$nomem/memory.db" --task-ids "$id"
    echo "No Memory $id exit code: $?"
    stop_if_exhausted "$nomem" "$id" disabled
  else
    echo "=== Long Memory $id ==="
    env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
      --modes continual --post-task-reflection --memory-representation case_only --memory-config config/long_memory_condensed.json \
      --url "$bolt_url" --generator-model WebGen-LM-7B \
      --output "$longmem" --database "$longmem/memory.db" --task-ids "$id"
    echo "Long Memory $id exit code: $?"
    stop_if_exhausted "$longmem" "$id" continual
  fi
  env/webvoyager/bin/python3.10 scripts/generate_scorecard.py \
    --nomem-progress "$nomem/progress.jsonl" --longmem-progress "$longmem/progress.jsonl" \
    --task-ids "$id" | grep "^| $id" | sed "s/^/PAIR /"
done

echo "CATCHUP_REMAINING_DONE"
