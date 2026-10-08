#!/bin/bash
# Add a work item for the worker job (scripts/cluster/worker.sbatch). Run on the cluster login node.
#   bash scripts/cluster/enqueue.sh NAME ITEM_SCRIPT     (copied to $WG/queue/pending/<time>-NAME.sh)
# The item is checked with `bash -n` first. List the queue with: ls $WG/queue/*
set -euo pipefail
source /data/qma258/env.sh
name="$1"; script="$2"
bash -n "$script"
mkdir -p "$WG/queue/pending"
dest="$WG/queue/pending/$(date +%Y%m%d-%H%M%S)-$name.sh"
cp "$script" "$dest"
echo "queued $dest"
ls "$WG/queue/pending"
