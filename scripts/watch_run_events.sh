#!/bin/zsh
# Read-only watcher: prints one line per notable event so a human can intervene early.
# Events: each failed build attempt (with its first error), saved failed-repair chats,
# task completions, retries, infrastructure failures, crashes, and repair exhaustion.
cd "${0:A:h:h}"
roots=(outputs/experiment/nomem_14_21_webgenlm_qwenvl_gpt4o_r2 outputs/experiment/longmem_mac_q8_19_21_then_remaining_r1 outputs/experiment/diag_016_condensed outputs/experiment/diag_016_baseline)
logs=(outputs/experiment/pilot_2tasks.log outputs/experiment/rerun_000017.log outputs/experiment/catchup_remaining.log outputs/experiment/diag_016.log)
seen=/tmp/webgen_watch_seen.txt
touch "$seen"

for f in ${^roots}/tasks/<->/*/000001.attempt-*.failed.zip(N) ${^roots}/tasks/<->/*/000001.failed-chat.json(N); do
  k="$f $(stat -f %m "$f")"; grep -qxF "$k" "$seen" || echo "$k" >> "$seen"
done
typeset -A offsets
for l in $logs; do [[ -f $l ]] && offsets[$l]=$(wc -l < $l) || offsets[$l]=0; done

while true; do
  for f in ${^roots}/tasks/<->/*/000001.attempt-*.failed.zip(N) ${^roots}/tasks/<->/*/000001.failed-chat.json(N); do
    k="$f $(stat -f %m "$f")"
    grep -qxF "$k" "$seen" && continue
    echo "$k" >> "$seen"
    task=${f:h:h:t}; mode=${f:h:t}
    if [[ $f == *failed-chat.json ]]; then
      echo "FAILED-REPAIR CHAT SAVED: $task/$mode -> $f"
    else
      n=${${f:t}#000001.attempt-}; n=${n%%.*}
      err=$(python3 -c "
import json,sys
d=json.load(open('${f:h}/000001.generation.json'))
a=[x for x in d['attempts'] if x.get('attempt')==$n]
e=(a[0].get('error','') if a else '')
lines=[x for x in e.splitlines() if 'error' in x.lower()]
print((lines[0] if lines else e.strip()[:160])[:200])
" 2>/dev/null)
      echo "BUILD FAILED attempt $n: $task/$mode | $err"
    fi
  done
  for l in $logs; do
    [[ -f $l ]] || continue
    total=$(wc -l < $l)
    if (( total > ${offsets[$l]:-0} )); then
      tail -n +$(( ${offsets[$l]:-0} + 1 )) $l | head -n $(( total - ${offsets[$l]:-0} )) | \
        grep -E "retrying|infrastructure failure|failed validation|Traceback|Error:|REPAIR_EXHAUSTED|DIAG016_DONE|diag a|diag b|PAIR |=== (No|Long) Memory|completed [0-9]+/[0-9]+|_DONE|exit code|Killed|prompt_delivered.*false|WARNING" | cut -c1-240
      offsets[$l]=$total
    fi
  done
  sleep 10
done
