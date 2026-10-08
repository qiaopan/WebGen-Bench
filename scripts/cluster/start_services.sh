#!/bin/bash
# Start the cluster profile's self-hosted services inside a Slurm job on foscsmlprd03 (H200s).
# No Azure: every role runs here. Source this from a job script after `source /data/qma258/env.sh`.
#   GPU A: WebGen-LM-7B BF16 (generator) + Qwen2.5-VL-32B-Instruct BF16 (functional + appearance evaluator)
#   GPU B (only when WEBGEN_MEMORY_BASE_URL is set and START_MEMORY_SERVICES is not 0, i.e. Long Memory):
#          Qwen2.5-VL-72B-Instruct-AWQ
#          (memory + reflection; sees screenshots) + bge-m3 (embedding)
# Then Bolt with the local provider. All servers bind 127.0.0.1 with API keys: the node is shared.

WEBGEN_ROOT="${WEBGEN_ROOT:-$WG/webgen}"
SERVICE_LOG="${SERVICE_LOG:-$WG/logs/services-${SLURM_JOB_ID:-manual}}"
mkdir -p "$SERVICE_LOG"

set -a; source "$WEBGEN_ROOT/.env"; set +a
IFS=',' read -r -a SERVICE_GPUS <<< "${CUDA_VISIBLE_DEVICES:-0}"

# Two queue jobs may share the node (No Memory and Long Memory): WEBGEN_PORT_OFFSET shifts every local
# port so each job talks only to its own servers. The shifted URLs are exported, and the runner's
# load_dotenv() does not override variables that are already set.
offset="${WEBGEN_PORT_OFFSET:-0}"
shift_url() { local u="$1" port="${1##*:}"; port="${port%%/*}"; echo "${u%:*}:$((port + offset))/v1"; }
for var in WEBGEN_GENERATOR_BASE_URL WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL WEBGEN_APPEARANCE_EVALUATOR_BASE_URL \
           WEBGEN_MEMORY_BASE_URL WEBGEN_EMBEDDING_BASE_URL; do
  [[ -n "${!var:-}" ]] && export "$var=$(shift_url "${!var}")"
done
BOLT_PORT=$(( ${BOLT_PORT_BASE:-28419} + offset ))

wait_http() {  # url, seconds, label; fails at once if the last background server has already exited
  local url="$1" limit="$2" label="$3" waited=0 pid=$!
  until curl -sf -o /dev/null "$url"; do
    if ! kill -0 "$pid" 2>/dev/null; then echo "SERVICE_DIED $label (see $SERVICE_LOG)"; return 1; fi
    sleep 10; waited=$((waited + 10))
    if (( waited >= limit )); then echo "SERVICE_TIMEOUT $label after ${limit}s ($url)"; return 1; fi
  done
  echo "SERVICE_UP $label after ${waited}s"
}

url_port() { local u="${1%/v1}"; echo "${u##*:}"; }
VLLM="$WG/venvs/vllm/bin/vllm"

# Functional + appearance evaluator, as in upstream src-remote/deploy/deploy_qwenvl_32b.sh (bfloat16,
# image=5, model's default generation config); context capped at 32k to fit beside the generator.
# The 32B model starts first: each vLLM instance checks free GPU memory against its own share.
CUDA_VISIBLE_DEVICES="${SERVICE_GPUS[0]}" "$VLLM" serve "$WG/models/Qwen2.5-VL-32B-Instruct" \
  --served-model-name "$WEBGEN_FUNCTIONAL_EVALUATOR_MODEL" --host 127.0.0.1 \
  --port "$(url_port "$WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL")" \
  --api-key "$WEBGEN_FUNCTIONAL_EVALUATOR_API_KEY" --dtype bfloat16 --max-model-len 32768 \
  --limit-mm-per-prompt '{"image": 5, "video": 5}' --gpu-memory-utilization 0.62 \
  > "$SERVICE_LOG/vllm-qwen-vl.log" 2>&1 &
wait_http "http://127.0.0.1:$(url_port "$WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL")/health" 1200 qwen-vl || return 1

# --generation-config vllm: by default vLLM silently applies the repo's generation_config.json
# (repetition_penalty 1.1), which Bolt never sends and llama.cpp on the Mac never applied. With it, Bolt's
# file-selection step produced no usable answer on every build repair (pipetest 23342: 5 repairs, no
# reply, code unchanged); the penalty also discourages copying file paths and repeated code tokens.
# Bolt (AI SDK 4) sends temperature 0, so generation stays greedy as before.
# Generator weights: WebGen-LM-7B by default; WEBGEN_GENERATOR_WEIGHTS=WebGen-LM-14B for the second-generator
# experiment (set it, and WEBGEN_GENERATOR_API_MODEL, before the worker job starts).
CUDA_VISIBLE_DEVICES="${SERVICE_GPUS[0]}" "$VLLM" serve "$WG/models/${WEBGEN_GENERATOR_WEIGHTS:-WebGen-LM-7B}" \
  --served-model-name "$WEBGEN_GENERATOR_API_MODEL" --host 127.0.0.1 \
  --port "$(url_port "$WEBGEN_GENERATOR_BASE_URL")" \
  --api-key "$WEBGEN_GENERATOR_API_KEY" --dtype bfloat16 --max-model-len 32768 \
  --gpu-memory-utilization 0.28 --generation-config vllm \
  > "$SERVICE_LOG/vllm-webgen-lm.log" 2>&1 &
wait_http "http://127.0.0.1:$(url_port "$WEBGEN_GENERATOR_BASE_URL")/health" 900 webgen-lm || return 1

if [[ -n "${WEBGEN_MEMORY_BASE_URL:-}" && "${START_MEMORY_SERVICES:-1}" == 1 ]]; then
  [[ ${#SERVICE_GPUS[@]} -ge 2 ]] || { echo "SERVICE_CONFIG memory models need a second GPU"; return 1; }
  # Memory/reflection: requests send temperature 0; no repo generation config, so verbatim quotes
  # (code/requirement grounding) are not penalised as repetitions.
  CUDA_VISIBLE_DEVICES="${SERVICE_GPUS[1]}" "$VLLM" serve "$WG/models/Qwen2.5-VL-72B-Instruct-AWQ" \
    --served-model-name qwen2.5-vl-72b-instruct-awq --host 127.0.0.1 \
    --port "$(url_port "$WEBGEN_MEMORY_BASE_URL")" \
    --api-key "$WEBGEN_MEMORY_API_KEY" --max-model-len 32768 \
    --limit-mm-per-prompt '{"image": 8}' --gpu-memory-utilization 0.80 --generation-config vllm \
    > "$SERVICE_LOG/vllm-memory-72b.log" 2>&1 &
  wait_http "http://127.0.0.1:$(url_port "$WEBGEN_MEMORY_BASE_URL")/health" 1800 memory-72b || return 1

  CUDA_VISIBLE_DEVICES="${SERVICE_GPUS[1]}" "$VLLM" serve "$WG/models/bge-m3" \
    --served-model-name bge-m3 --host 127.0.0.1 --port "$(url_port "$WEBGEN_EMBEDDING_BASE_URL")" \
    --api-key "$WEBGEN_EMBEDDING_API_KEY" --runner pooling --convert embed \
    --gpu-memory-utilization 0.08 \
    > "$SERVICE_LOG/vllm-bge-m3.log" 2>&1 &
  wait_http "http://127.0.0.1:$(url_port "$WEBGEN_EMBEDDING_BASE_URL")/health" 900 bge-m3 || return 1
fi

(cd "$WEBGEN_ROOT" && exec zsh scripts/start_bolt_provider.sh --provider local --port "$BOLT_PORT") \
  > "$SERVICE_LOG/bolt.log" 2>&1 &
wait_http "http://127.0.0.1:$BOLT_PORT/" 600 bolt || return 1

export WEBGEN_BOLT_URL="http://127.0.0.1:$BOLT_PORT/"
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv
