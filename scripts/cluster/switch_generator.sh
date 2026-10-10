#!/bin/bash
# Swap the generator inside the running worker job without releasing its GPUs (a new job would wait in the
# Slurm queue). Run as a filler "X" line: X scripts/cluster/switch_generator.sh MARKER, with the target in
# $WG/queue/generator.env.next (WEBGEN_GENERATOR_WEIGHTS, WEBGEN_GENERATOR_API_MODEL,
# WEBGEN_GENERATOR_QUANTIZATION, WEBGEN_GENERATOR_GPU_UTIL). Steps: stop the old generator and Bolt (Bolt caches
# the model list), start the new generator on the same GPU and port, check it serves the new name, restart Bolt,
# then install generator.env (so later service restarts keep it) and write MARKER. If MARKER.env exists it is
# the target instead of generator.env.next (so a second X line can switch back). On failure, the old
# generator and Bolt are started again and the script exits 1.
set -uo pipefail
marker="$1"
source /data/qma258/env.sh
cd "$WG/webgen"
next="$WG/queue/generator.env.next"
[[ -f "$marker.env" ]] && next="$marker.env"
[[ -f "$next" ]] || { echo "SWITCH_ABORT no $next"; exit 1; }
old_env="$WG/queue/generator.env"
SERVICE_LOG="$WG/logs/services-${SLURM_JOB_ID:-manual}"
set -a; source .env; [[ -f "$old_env" ]] && source "$old_env"; set +a
old_weights="${WEBGEN_GENERATOR_WEIGHTS:-WebGen-LM-7B}"
offset="${WEBGEN_PORT_OFFSET:-0}"
gen_port=$(( $(u="${WEBGEN_GENERATOR_BASE_URL%/v1}"; echo "${u##*:}") ))
[[ "$WEBGEN_GENERATOR_BASE_URL" == *":$gen_port/v1" ]] || { echo "SWITCH_ABORT cannot read generator port"; exit 1; }
bolt_port=$(( ${BOLT_PORT_BASE:-28419} + offset ))
gpu="${CUDA_VISIBLE_DEVICES%%,*}"
VLLM="$WG/venvs/vllm/bin/vllm"

kill_tree() { local p; for p in $(pgrep -u "$USER" -P "$1"); do kill_tree "$p"; done; kill "$1" 2>/dev/null; }
stop_generator() { local p; for p in $(pgrep -u "$USER" -f "vllm serve $WG/models/$1 "); do kill_tree "$p"; done
                   for _ in $(seq 60); do pgrep -u "$USER" -f "vllm serve $WG/models/$1 " >/dev/null || return 0; sleep 5; done; return 1; }
stop_bolt() { local p; for p in $(pgrep -u "$USER" -f "start_bolt_provider.sh --provider local --port $bolt_port") \
                                 $(pgrep -u "$USER" -f "vite:dev --host 127.0.0.1 --port $bolt_port"); do kill_tree "$p"; done; sleep 5; }
start_generator() {  # weights served_name util quantization
  setsid env CUDA_VISIBLE_DEVICES="$gpu" "$VLLM" serve "$WG/models/$1" --served-model-name "$2" --host 127.0.0.1 \
    --port "$gen_port" --api-key "$WEBGEN_GENERATOR_API_KEY" --dtype bfloat16 --max-model-len 32768 \
    --gpu-memory-utilization "$3" --generation-config vllm ${4:+--quantization "$4"} \
    > "$SERVICE_LOG/vllm-webgen-lm-$2.log" 2>&1 < /dev/null &
  for _ in $(seq 180); do curl -sf -o /dev/null "http://127.0.0.1:$gen_port/health" && return 0; sleep 10; done; return 1
}
serves() { curl -sf -H "Authorization: Bearer $WEBGEN_GENERATOR_API_KEY" "http://127.0.0.1:$gen_port/v1/models" | grep -q "\"id\":\"$1\""; }
start_bolt() {
  (setsid zsh scripts/start_bolt_provider.sh --provider local --port "$bolt_port" > "$SERVICE_LOG/bolt-switch.log" 2>&1 < /dev/null &)
  for _ in $(seq 60); do curl -sf -o /dev/null "http://127.0.0.1:$bolt_port/" && return 0; sleep 10; done; return 1
}
rollback() {
  echo "SWITCH_FAILED: $1; restoring $old_weights"
  stop_generator "$new_weights"; stop_bolt
  start_generator "$old_weights" "$WEBGEN_GENERATOR_API_MODEL" "${WEBGEN_GENERATOR_GPU_UTIL:-0.28}" "${WEBGEN_GENERATOR_QUANTIZATION:-}" \
    && start_bolt && echo "SWITCH_ROLLED_BACK" || echo "SWITCH_ROLLBACK_FAILED (the worker restarts services on its next check)"
  exit 1
}

new_weights=$(set -a; source "$next"; echo "$WEBGEN_GENERATOR_WEIGHTS")
new_name=$(set -a; source "$next"; echo "$WEBGEN_GENERATOR_API_MODEL")
new_util=$(set -a; source "$next"; echo "${WEBGEN_GENERATOR_GPU_UTIL:-0.28}")
new_quant=$(set -a; source "$next"; echo "${WEBGEN_GENERATOR_QUANTIZATION:-}")
[[ -f "$WG/models/$new_weights/config.json" ]] || { echo "SWITCH_ABORT weights $WG/models/$new_weights missing"; exit 1; }
echo "SWITCH $old_weights -> $new_weights ($new_name, util $new_util, quantization ${new_quant:-none}) GPU $gpu port $gen_port $(date -Is)"

stop_generator "$old_weights" || rollback "old generator did not stop"
stop_bolt
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv
start_generator "$new_weights" "$new_name" "$new_util" "$new_quant" || rollback "new generator did not become healthy"
serves "$new_name" || rollback "generator does not serve $new_name"
start_bolt || rollback "Bolt did not start"
cp "$next" "$old_env"
date -Is > "$marker"
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv
echo "SWITCH_DONE $(date -Is)"
