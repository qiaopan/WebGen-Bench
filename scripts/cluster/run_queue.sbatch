#!/bin/bash
# WebGen-Bench No Memory vs Long Memory on the CS ML cluster, self-hosted models only (no Azure).
# Tasks run in manifest order; per task both arms run back to back and the arm that goes first alternates
# (even manifest position: No Memory first). Completed (task, arm) pairs are skipped on resubmission.
# The queue never stops on its own (user decision 2026-10-05; a stopped job also loses its GPU):
# check_task_health.py logs suspicious tasks to health-warnings.jsonl for analysis or a re-run later, and
# if a model server dies the services are restarted (retried every 10 minutes) before the next task.
#   WEBGEN_PORT_OFFSET: shift all local ports so a No Memory and a Long Memory job can share the node.
#   QUEUE_FROM / QUEUE_COUNT: manifest positions to run (0-based start, count); default = all 101.
#   ARMS: "N L" (default, alternating), "N" (No Memory only: one GPU is enough, submit with
#         --gres=gpu:h200:1) or "L" (Long Memory only).
#SBATCH --job-name=qma-webgen-queue
#SBATCH --time=72:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --gres=gpu:h200:2
#SBATCH --output=/data/qma258/jobs/queue-%j.out
set -uo pipefail
source /data/qma258/env.sh
cd "$WG/webgen"

nomem="outputs/experiment/cluster_nomem_webgenlm7b_r1"
longmem="outputs/experiment/cluster_longmem_webgenlm7b_r1"
memory_config="config/long_memory_cluster.json"
manifest="data/experiment_splits/continual_domain_blocks/manifest.json"
py="env/webvoyager/bin/python3.10"

export WEBGEN_OFFICIAL_PROTOCOL=1 WEBGEN_FORBID_AZURE=1 PYTHONUNBUFFERED=1
export WEBGEN_GENERATION_TIMEOUT_SECONDS=2700
# Per-job PM2 daemon and evaluation lock: the evaluators run `pm2 delete all`, which must not reach
# the sites of another queue job on the same node.
export PM2_HOME="$WG/home/.pm2-${SLURM_JOB_ID:-manual}" WEBGEN_EVALUATION_LOCK="$WG/tmp/webgen-evaluation-${SLURM_JOB_ID:-manual}.lock"

if grep -v '^#' .env | grep -qi 'azure'; then echo "QUEUE_ABORT .env still references Azure"; exit 1; fi

cleanup() { pm2 kill >/dev/null 2>&1; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

read -r -a arms <<< "${ARMS:-N L}"
preflight_args=(--memory-config "$memory_config")
if [[ " ${arms[*]} " != *" L "* ]]; then  # No Memory never calls the memory model or the embedder
  export START_MEMORY_SERVICES=0; preflight_args+=(--skip-memory)
fi
echo "QUEUE_ARMS ${arms[*]}"

# Start-up never gives up either: retry the services and the model check every 10 minutes.
until source scripts/cluster/start_services.sh && "$py" scripts/preflight_reflective_models.py "${preflight_args[@]}"; do
  echo "QUEUE_STARTUP_RETRY in 10 minutes (see $SERVICE_LOG)"
  pm2 kill >/dev/null 2>&1; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null; sleep 600
done

mapfile -t ids < <("$py" -c "
import json, sys
m = json.load(open('$manifest'))
ids = [t for b in m['batches'] for t in b['task_ids']]
start, count = int('${QUEUE_FROM:-0}'), int('${QUEUE_COUNT:-0}') or len(ids)
for position in range(start, min(start + count, len(ids))):
    print(position, ids[position])
")

run_arm() {  # arm task_id
  local arm="$1" id="$2" start=$(date +%s)
  if [[ $arm == N ]]; then
    echo "=== No Memory $id"
    "$py" scripts/run_continual_memory.py --modes disabled --memory-config "$memory_config" \
      --url "$WEBGEN_BOLT_URL" --generator-model WebGen-LM-7B \
      --output "$nomem" --database "$nomem/memory.db" --task-ids "$id"
    echo "No Memory $id exit $? after $(( $(date +%s) - start ))s"
    "$py" scripts/cluster/check_task_health.py "$nomem" "$id" disabled
  else
    echo "=== Long Memory $id"
    "$py" scripts/run_continual_memory.py --modes continual --post-task-reflection \
      --memory-representation case_only --memory-config "$memory_config" \
      --url "$WEBGEN_BOLT_URL" --generator-model WebGen-LM-7B \
      --output "$longmem" --database "$longmem/memory.db" --task-ids "$id"
    echo "Long Memory $id exit $? after $(( $(date +%s) - start ))s"
    "$py" scripts/cluster/check_task_health.py "$longmem" "$id" continual
  fi
}

services_up() {  # every server this queue needs still answers
  local url
  for url in "$WEBGEN_GENERATOR_BASE_URL" "$WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL" \
             $([[ " ${arms[*]} " == *" L "* ]] && echo "$WEBGEN_MEMORY_BASE_URL $WEBGEN_EMBEDDING_BASE_URL"); do
    curl -sf -o /dev/null "${url%/v1}/health" || { echo "SERVICE_DOWN $url"; return 1; }
  done
  curl -sf -o /dev/null "$WEBGEN_BOLT_URL" || { echo "SERVICE_DOWN $WEBGEN_BOLT_URL"; return 1; }
}

restart_services() {
  pm2 kill >/dev/null 2>&1
  kill $(jobs -p) 2>/dev/null; wait 2>/dev/null
  source scripts/cluster/start_services.sh
}

for line in "${ids[@]}"; do
  position=${line%% *}; id=${line#* }
  if (( ${#arms[@]} == 1 )); then order=("${arms[@]}")
  elif (( position % 2 == 0 )); then order=(N L); else order=(L N); fi
  for arm in "${order[@]}"; do
    until services_up; do
      echo "SERVICE_RESTART before $arm:$id"
      restart_services && services_up && break
      echo "SERVICE_RESTART_FAILED; retrying in 10 minutes"; sleep 600
    done
    run_arm "$arm" "$id" || echo "HEALTH_BLOCK logged for $arm:$id; continuing (queue never stops)"
  done
done
echo QUEUE_DONE
