#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h}"
ENV_FILE="$PROJECT_ROOT/.env"
BOLT_DIR="$PROJECT_ROOT/bolt.diy-Fork"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "未找到 $ENV_FILE，请先配置百炼 API Key。" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

API_KEY="${AZURE_OPENAI_API_KEY:-${DASHSCOPE_API_KEY:-}}"
if [[ -z "$API_KEY" ]]; then
  echo "AZURE_OPENAI_API_KEY 或 DASHSCOPE_API_KEY 未配置。" >&2
  exit 1
fi

export OPENAI_LIKE_API_KEY="$API_KEY"
export OPENAI_LIKE_API_BASE_URL="${WEBGEN_GENERATOR_BASE_URL:-${WEBVOYAGER_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}}"
export WEBGEN_GENERATOR_API_MODEL="${WEBGEN_GENERATOR_API_MODEL:-qwen3-coder-next}"

cd "$BOLT_DIR"
exec npm run dev
