#!/usr/bin/env python3
"""Reconstruct a Bolt project ZIP from an exported chat JSON file."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import PurePosixPath


FILE_ACTION_RE = re.compile(
    r'<boltAction\b(?=[^>]*\btype="file")(?=[^>]*\bfilePath="([^"]+)")[^>]*>'
    r'(.*?)</boltAction>',
    re.DOTALL,
)


def text_content(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return ""


def safe_path(raw_path: str) -> str:
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe file path in chat export: {raw_path!r}")
    return str(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("chat_json", help="Bolt chat JSON exported from the UI")
    parser.add_argument("output_zip", help="Destination project ZIP")
    args = parser.parse_args()

    with open(args.chat_json, encoding="utf-8") as source:
        chat = json.load(source)

    files: dict[str, str] = {}
    writes = 0
    for message in chat.get("messages", []):
        if message.get("role") != "assistant":
            continue
        for raw_path, content in FILE_ACTION_RE.findall(text_content(message)):
            files[safe_path(raw_path)] = content
            writes += 1

    if not files:
        raise SystemExit("No Bolt file actions were found in the chat JSON")

    with zipfile.ZipFile(args.output_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            archive.writestr(path, content)

    print(f"Exported {len(files)} files ({writes} file actions) to {args.output_zip}")


if __name__ == "__main__":
    main()
