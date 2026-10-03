#!/bin/zsh
# Start one isolated Bolt service for a chosen generator provider.
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
provider=""
port=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) provider="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    *) print -u2 "Usage: $0 --provider azure|dashscope|local --port PORT"; exit 2 ;;
  esac
done

[[ "$provider" == "azure" || "$provider" == "dashscope" || "$provider" == "local" ]] || {
  print -u2 "--provider must be azure, dashscope, or local"; exit 2
}
[[ "$port" == <-> ]] || { print -u2 "--port must be an integer"; exit 2; }

set -a
source "$project_root/.env"
set +a

if [[ "$provider" == "azure" ]]; then
  : "${AZURE_OPENAI_API_KEY:?AZURE_OPENAI_API_KEY is required}"
  export OPENAI_LIKE_API_KEY="$AZURE_OPENAI_API_KEY"
  export OPENAI_LIKE_API_BASE_URL="${WEBGEN_GENERATOR_BASE_URL:?WEBGEN_GENERATOR_BASE_URL is required}"
elif [[ "$provider" == "dashscope" ]]; then
  : "${DASHSCOPE_API_KEY:?DASHSCOPE_API_KEY is required}"
  export OPENAI_LIKE_API_KEY="$DASHSCOPE_API_KEY"
  export OPENAI_LIKE_API_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
else
  : "${WEBGEN_GENERATOR_BASE_URL:?WEBGEN_GENERATOR_BASE_URL is required}"
  export OPENAI_LIKE_API_KEY="${WEBGEN_GENERATOR_API_KEY:-EMPTY}"
  export OPENAI_LIKE_API_BASE_URL="$WEBGEN_GENERATOR_BASE_URL"
fi

# Bolt's context-optimization summary is a non-streaming call; the local 7B can take over Node's
# default 300 s headers timeout, which silently dropped every build-repair reply (2026-10-02).
# Same setting for both arms. Source: tools/bolt-preload (run `npm install` there once; undici must match
# `node -p process.versions.undici`). Falls back to the copy outside the repo used during the experiments.
bolt_preload="${WEBGEN_BOLT_PRELOAD:-}"
if [[ -z "$bolt_preload" ]]; then
  if [[ -d "$project_root/tools/bolt-preload/node_modules/undici" ]]; then
    bolt_preload="$project_root/tools/bolt-preload/long-timeouts.mjs"
  else
    bolt_preload="$HOME/webgen-local-generator/bolt-preload/long-timeouts.mjs"
  fi
fi
if [[ -f "$bolt_preload" ]]; then
  export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--import $bolt_preload"
else
  echo "WARNING: $bolt_preload missing; Node's 300 s fetch timeout will cut slow repair calls" >&2
fi

cd "$project_root/bolt.diy-Fork"
exec npm run dev -- --host 127.0.0.1 --port "$port"
