import hashlib
import json
import os
import subprocess
from argparse import ArgumentParser
from pathlib import Path

# Import the function from remove_node_modules.py
from automatic_web_gen import automatic_web_gen
from remove_invalid_through_extract import process_directory

def main():
    parser = ArgumentParser(description="Process JSONL file and generate web content.")
    parser.add_argument("--provider", default="OpenAILike", help="Provider name")
    parser.add_argument("--desired_model", default="Qwen2.5-Coder-32B-Instruct", help="Desired model path")
    parser.add_argument("--jsonl_path", default="data/test.jsonl", help="Path to the JSONL file")
    parser.add_argument("--url", default="http://localhost:5173/", help="bolt.diy url")
    parser.add_argument(
        "--download_dir",
        help="Explicit output directory; recommended to keep experimental conditions separate",
    )
    parser.add_argument(
        "--record_id",
        help="Run only this record ID while preserving its position in the group file",
    )
    args = parser.parse_args()
    # Adjust these if you want different defaults
    provider = args.provider
    desired_model = args.desired_model
    url = args.url

    download_dir = args.download_dir or f"downloads/{provider}/{os.path.basename(desired_model)}_{os.path.basename(args.jsonl_path).split('.')[0]}".replace(":", "_")

    # Replace with the actual path to the jsonl file
    jsonl_path = args.jsonl_path

    # Ensure the download_dir exists (optional)
    os.makedirs(download_dir, exist_ok=True)
    input_path = Path(jsonl_path)
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    project_root = Path(__file__).resolve().parents[2]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    run_metadata = {
        "git_commit": commit,
        "input_file": str(input_path),
        "input_sha256": digest,
        "provider": provider,
        "model": desired_model,
        "bolt_url": url,
    }
    metadata_path = Path(download_dir) / "generation_run.json"
    if metadata_path.exists():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        if existing != run_metadata:
            raise RuntimeError(
                f"Output directory already belongs to a different run: {metadata_path}"
            )
    else:
        metadata_path.write_text(
            json.dumps(run_metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    process_directory(download_dir)  # Clean up the download directory first

    # Read the JSONL file line by line
    with open(jsonl_path, "r", encoding="utf-8") as f:
        found_record = False
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue  # Skip empty lines if any

            record = json.loads(line)
            if args.record_id and str(record.get("id")) != args.record_id:
                continue
            found_record = True
            instruction = record.get("instruction", "")

            # Call automatic_web_gen for each record
            automatic_web_gen(
                idx=idx,
                instruction=instruction,
                download_dir=download_dir,
                url=url,
                desired_model=desired_model,
                provider=provider
            )
        if args.record_id and not found_record:
            raise ValueError(f"Record ID {args.record_id!r} was not found in {jsonl_path}")

if __name__ == "__main__":
    main()
