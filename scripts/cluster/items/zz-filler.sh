#!/bin/bash
# Worker item that keeps the GPUs busy: while no other item is pending, run the next unfinished task of
# the runs listed in $WG/queue/filler.conf, one task at a time. When another item appears (or a task's
# runner fails, so the worker checks the services first), it puts itself back at the end of the queue
# and exits; when every listed run is complete it exits for good (the worker then idles out).
set -uo pipefail
source scripts/cluster/worker_lib.sh
default_memory_config="$memory_config"
requeue() { cp "$0" "$WG/queue/pending/zz-filler.sh"; exit 0; }
while true; do
  others=$(ls "$WG/queue/pending/"*.sh 2>/dev/null | grep -v '/zz-filler.sh$' | head -1)
  [[ -n "$others" ]] && { echo "FILLER_YIELD to $(basename "$others")"; requeue; }
  next=$(filler_next) || { echo FILLER_ALL_DONE; exit 0; }
  read -r arm out id cfg <<< "$next"
  if [[ $arm == HALT ]]; then echo "FILLER_HALT: $out failed three times; fix it, then remove its lines from $WG/queue/filler-failures.txt"; exit 0; fi
  if [[ $arm == X ]]; then
    echo "=== FILLER_SWITCH $out"; bash "$out" "$id"
    [[ -e "$id" ]] || { echo "$out $id" >> "$WG/queue/filler-failures.txt"; echo "FILLER_SWITCH_FAILED $out"; requeue; }
    continue
  fi
  memory_config="$default_memory_config"
  [[ -n "${cfg:-}" && "$cfg" != "-" ]] && memory_config="$cfg"
  if [[ $arm == L ]]; then run_longmem_tasks "$out" "$id"; status=$?; else run_nomem_tasks "$out" "$id"; status=$?; fi
  if ! grep -q "\"task_id\": \"$id\"" "$out/progress.jsonl" 2>/dev/null; then
    echo "$out $id" >> "$WG/queue/filler-failures.txt"; echo "FILLER_TASK_FAILED $arm $out $id"; requeue
  fi
done
