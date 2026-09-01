import getpass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def main() -> None:
    api_key = getpass.getpass("请粘贴新的百炼 API Key（输入不会显示）：").strip()
    if not api_key.startswith("sk-") or len(api_key) <= 20:
        raise SystemExit("API Key 格式不正确，未写入任何文件。")

    content = "\n".join(
        [
            f"DASHSCOPE_API_KEY={api_key}",
            "WEBVOYAGER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1",
            "WEBVOYAGER_API_MODEL=qwen3-vl-32b-instruct",
            "WEBVOYAGER_NUM_WORKERS=1",
            "",
        ]
    )
    ENV_PATH.write_text(content, encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)
    print(f"配置已保存到：{ENV_PATH}")
    print("该文件已被 .gitignore 忽略，不会进入 Git。")


if __name__ == "__main__":
    main()
