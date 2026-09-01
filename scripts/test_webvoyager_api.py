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


def main() -> None:
    api_key = require_env("DASHSCOPE_API_KEY")
    base_url = require_env("WEBVOYAGER_BASE_URL")
    model = require_env("WEBVOYAGER_API_MODEL")

    if not base_url.startswith("https://") or any(char in base_url for char in "[]()"):
        raise RuntimeError(
            "WEBVOYAGER_BASE_URL 格式错误，必须是纯 https:// 地址，不能包含 []()。"
        )

    print(f"正在连接：{base_url}")
    print(f"正在测试模型：{model}")

    client = OpenAI(api_key=api_key, base_url=base_url)
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "只回答：百炼 API 连接成功"}],
        max_tokens=30,
        stream=True,
        stream_options={"include_usage": True},
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
