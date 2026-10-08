#!/bin/zsh
# Copy the cluster runs back to the Mac (incremental; safe to re-run while jobs are running).
# Cluster storage is working storage with no backup (Cluster Policies), so pull regularly.
# Needs the shared SSH connection: run `ssh csml3` once (password:2FA) before this.
#   outputs/experiment/cluster_*  -> outputs/experiment/   (progress, memory.db, events, reflections,
#                                                          chats, zips, evaluator transcripts, screenshots)
#   /data/qma258/jobs, /data/qma258/logs -> outputs/cluster_logs/   (Slurm and model-server logs)
# Generated sites' node_modules are skipped (they can be rebuilt from the zip archives).
set -euo pipefail
cd "${0:A:h}/../.."
ssh -O check csml3 >/dev/null 2>&1 || { print -u2 "No shared SSH connection: run 'ssh csml3' first"; exit 1; }

rsync -a --exclude 'node_modules/' --exclude '.pm2*' \
  'csml3:/data/qma258/webgen/outputs/experiment/cluster_*' outputs/experiment/
mkdir -p outputs/cluster_logs
rsync -a csml3:/data/qma258/jobs csml3:/data/qma258/logs outputs/cluster_logs/
du -sh outputs/experiment/cluster_* outputs/cluster_logs 2>/dev/null
