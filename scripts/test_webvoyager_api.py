import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少环境变量：{name}")
    return value


def require_api_key() -> str:
    value = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    if not value:
        value = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not value:
        raise RuntimeError(
            "缺少环境变量：AZURE_OPENAI_API_KEY 或 DASHSCOPE_API_KEY"
        )
    return value


def main() -> None:
    api_key = require_api_key()
    base_url = require_env("WEBVOYAGER_BASE_URL")
    model = require_env("WEBVOYAGER_API_MODEL")

    if not base_url.startswith("https://") or any(char in base_url for char in "[]()"):
        raise RuntimeError(
            "WEBVOYAGER_BASE_URL 格式错误，必须是纯 https:// 地址，不能包含 []()。"
        )

    print(f"正在连接：{base_url}")
    print(f"正在测试模型：{model}")

    client = OpenAI(api_key=api_key, base_url=base_url)
    token_limit = (
        {"max_completion_tokens": 30}
        if "azure.com/openai/v1" in base_url
        else {"max_tokens": 30}
    )
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "只回答：模型 API 连接成功"}],
        stream=True,
        stream_options={"include_usage": True},
        **token_limit,
    )

    print("模型回复：", end="", flush=True)
    usage = None
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="", flush=True)
    print()
    if usage:
        print(
            "Token 用量："
            f"输入 {usage.prompt_tokens}，"
            f"输出 {usage.completion_tokens}，"
            f"合计 {usage.total_tokens}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"连接失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
