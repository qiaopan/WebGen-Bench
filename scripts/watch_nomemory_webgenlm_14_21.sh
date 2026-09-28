#!/usr/bin/env bash
set -euo pipefail

# Read-only progress view for scripts/run_nomemory_webgenlm_14_21.sh.
# It deliberately does not contact a model or modify experiment outputs.

project_root="$(cd "$(dirname "$0")/.." && pwd)"
output="${WEBGEN_RUN_OUTPUT:-$project_root/outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o}"
interval="${WEBGEN_WATCH_INTERVAL_SECONDS:-30}"

while true; do
  clear 2>/dev/null || true
  date '+%Y-%m-%d %H:%M:%S'
  echo "Output: $output"
  echo

  if pgrep -f 'scripts/run_continual_memory.py.*nomem_14_21_webgenlm_qwenvl_gpt4o' >/dev/null; then
    echo 'Runner: running'
  else
    echo 'Runner: not found (completed or stopped)'
  fi

  for task_id in 000014 000015 000016 000017 000018 000019 000020 000021; do
    directory="$output/tasks/$task_id/disabled"
    if [ -f "$directory/000001.zip" ]; then
      echo "$task_id  generated; awaiting/completing evaluation"
    elif [ -f "$directory/000001.prompt.txt" ]; then
      echo "$task_id  generation in progress"
    else
      echo "$task_id  queued"
    fi
  done

  if [ -f "$output/progress.jsonl" ]; then
    echo
    echo 'Latest completed task:'
    tail -1 "$output/progress.jsonl"
  fi
  sleep "$interval"
done
