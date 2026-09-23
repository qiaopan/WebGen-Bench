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
    *) print -u2 "Usage: $0 --provider azure|dashscope --port PORT"; exit 2 ;;
  esac
done

[[ "$provider" == "azure" || "$provider" == "dashscope" ]] || {
  print -u2 "--provider must be azure or dashscope"; exit 2
}
[[ "$port" == <-> ]] || { print -u2 "--port must be an integer"; exit 2; }

set -a
source "$project_root/.env"
set +a

if [[ "$provider" == "azure" ]]; then
  : "${AZURE_OPENAI_API_KEY:?AZURE_OPENAI_API_KEY is required}"
  export OPENAI_LIKE_API_KEY="$AZURE_OPENAI_API_KEY"
  export OPENAI_LIKE_API_BASE_URL="${WEBGEN_GENERATOR_BASE_URL:?WEBGEN_GENERATOR_BASE_URL is required}"
else
  : "${DASHSCOPE_API_KEY:?DASHSCOPE_API_KEY is required}"
  export OPENAI_LIKE_API_KEY="$DASHSCOPE_API_KEY"
  export OPENAI_LIKE_API_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
fi

cd "$project_root/bolt.diy-Fork"
exec npm run dev -- --host 127.0.0.1 --port "$port"
