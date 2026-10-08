#!/bin/bash
# Download a Hugging Face model into /data/qma258/models/<NAME> (CPU and network only, no GPU).
#   MODEL_REPO=luzimu/WebGen-LM-14B MODEL_REVISION=<sha> MODEL_NAME=WebGen-LM-14B sbatch scripts/cluster/download_model.sbatch
#SBATCH --job-name=qma-model-download
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --output=/data/qma258/jobs/download-%j.out
set -euo pipefail
source /data/qma258/env.sh
: "${MODEL_REPO:?}" "${MODEL_NAME:?}"
dest="/data/qma258/models/$MODEL_NAME"
echo "download $MODEL_REPO@${MODEL_REVISION:-main} -> $dest  $(date)"
/data/qma258/venvs/vllm/bin/hf download "$MODEL_REPO" --revision "${MODEL_REVISION:-main}" --local-dir "$dest"
du -sh "$dest"; ls "$dest"
echo "done $(date)"
