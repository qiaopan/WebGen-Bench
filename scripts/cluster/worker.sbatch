#!/bin/bash
# Long-lived worker on the CS ML cluster: loads the self-hosted models once (generator, Qwen-VL evaluator,
# memory model, embedder; no Azure) and then runs work items from a queue directory, so new experiment
# runs do not need a new job (and a new wait in the Slurm queue).
#   $WG/queue/pending/*.sh   items, run in file-name order with bash; each is moved to running/, then to
#                            done/ or failed/ (exit status), and its output goes to $WG/queue/logs/.
#   Items run with the current code on disk, so a code change takes effect from the next item (and, inside
#   an item, from the next task: every task is a new runner process).
# Cluster Policies: GPUs must not be held idle to keep a model loaded, so the worker exits when the queue
# has been empty for WORKER_IDLE_MINUTES (default 60). Add items with scripts/cluster/enqueue.sh.
# Helpers for items (run_longmem_tasks, ...) are in scripts/cluster/worker_lib.sh.
#SBATCH --job-name=qma-webgen-worker
#SBATCH --time=30-00:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --gres=gpu:h200:2
#SBATCH --output=/data/qma258/jobs/worker-%j.out
set -uo pipefail
source /data/qma258/env.sh
cd "$WG/webgen"

export WEBGEN_PORT_OFFSET="${WEBGEN_PORT_OFFSET:-40}"
export WEBGEN_OFFICIAL_PROTOCOL=1 WEBGEN_FORBID_AZURE=1 PYTHONUNBUFFERED=1
export WEBGEN_GENERATION_TIMEOUT_SECONDS=2700
export PM2_HOME="$WG/home/.pm2-${SLURM_JOB_ID:-manual}" WEBGEN_EVALUATION_LOCK="$WG/tmp/webgen-evaluation-${SLURM_JOB_ID:-manual}.lock"
export py="env/webvoyager/bin/python3.10" memory_config="config/long_memory_cluster.json"
queue="$WG/queue"; idle_limit=$(( ${WORKER_IDLE_MINUTES:-60} * 60 ))
mkdir -p "$queue"/{pending,running,done,failed,logs}

if grep -v '^#' .env | grep -qi 'azure'; then echo "WORKER_ABORT .env still references Azure"; exit 1; fi

cleanup() { pm2 kill >/dev/null 2>&1; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

until source scripts/cluster/start_services.sh && "$py" scripts/preflight_reflective_models.py --memory-config "$memory_config"; do
  echo "WORKER_STARTUP_RETRY in 10 minutes (see $SERVICE_LOG)"
  pm2 kill >/dev/null 2>&1; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null; sleep 600
done
export WEBGEN_BOLT_URL
echo "WORKER_READY $(date -Is) ports offset $WEBGEN_PORT_OFFSET; queue $queue"

services_up() {
  local url
  for url in "$WEBGEN_GENERATOR_BASE_URL" "$WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL" \
             "$WEBGEN_MEMORY_BASE_URL" "$WEBGEN_EMBEDDING_BASE_URL"; do
    curl -sf -o /dev/null "${url%/v1}/health" || { echo "SERVICE_DOWN $url"; return 1; }
  done
  curl -sf -o /dev/null "$WEBGEN_BOLT_URL" || { echo "SERVICE_DOWN $WEBGEN_BOLT_URL"; return 1; }
}
restart_services() {
  pm2 kill >/dev/null 2>&1; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null
  source scripts/cluster/start_services.sh && export WEBGEN_BOLT_URL
}

idle_since=$(date +%s)
while true; do
  item=$(ls "$queue/pending/"*.sh 2>/dev/null | sort | head -1)
  if [[ -z "$item" ]]; then
    if (( $(date +%s) - idle_since >= idle_limit )); then echo "WORKER_IDLE_EXIT $(date -Is)"; break; fi
    sleep 30; continue
  fi
  name=$(basename "$item"); mv "$item" "$queue/running/$name"
  until services_up; do
    echo "SERVICE_RESTART before $name"
    restart_services && services_up && break
    echo "SERVICE_RESTART_FAILED; retrying in 10 minutes"; sleep 600
  done
  echo "ITEM_START $name $(date -Is)"
  start=$(date +%s)
  bash "$queue/running/$name" > "$queue/logs/${name%.sh}.log" 2>&1
  status=$?
  if (( status == 0 )); then mv "$queue/running/$name" "$queue/done/"; else mv "$queue/running/$name" "$queue/failed/"; fi
  echo "ITEM_END $name exit $status after $(( $(date +%s) - start ))s"
  idle_since=$(date +%s)
done
