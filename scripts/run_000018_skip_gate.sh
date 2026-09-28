#!/usr/bin/env bash
set -euo pipefail

# Diagnostic: 000018 with the relevance gate skipped (recalled top candidate per aspect = selected).
# Memory DB is a snapshot of the 000014-000017 state; 000018/000019 rows are removed from the COPY only.
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
source_db="outputs/experiment/continual_14_to_16_fresh/memory.db"
output="${WEBGEN_RUN_OUTPUT:-outputs/experiment/skip_gate_000018_r1}"
[ -e "$output" ] && { echo "Output $output already exists; set WEBGEN_RUN_OUTPUT to a new path" >&2; exit 1; }
mkdir -p "$output"
cp "$source_db" "$output/memory.db"

python3 - "$output/memory.db" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
triggers = con.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'").fetchall()
for name, _ in triggers:
    con.execute(f'DROP TRIGGER "{name}"')
con.execute("DELETE FROM memory_sources WHERE experience_record_id IN ('f59b41d73ba04affb940fa1536b7c5b6','589504b0c0514dde87ed5c907d19f134')")
con.execute("DELETE FROM experiences WHERE record_id IN ('f59b41d73ba04affb940fa1536b7c5b6','589504b0c0514dde87ed5c907d19f134')")
con.execute("DELETE FROM reflection_cases WHERE trajectory_id IN (SELECT trajectory_id FROM trajectories WHERE task_id IN ('000018','000019'))")
con.execute("DELETE FROM trajectories WHERE task_id IN ('000018','000019')")
for _, sql in triggers:
    con.execute(sql)
con.commit()
print("triggers restored:", len(triggers))
PY
echo "Snapshot trajectories:"; sqlite3 "$output/memory.db" "select task_id from trajectories order by started_at;"

WEBGEN_MAX_REPAIR_ATTEMPTS="${WEBGEN_MAX_REPAIR_ATTEMPTS:-2}" \
  env/webvoyager/bin/python3.10 scripts/run_continual_memory.py \
  --output "$output" \
  --database "$output/memory.db" \
  --task-ids 000018 \
  --modes continual \
  --memory-representation case_only \
  --memory-config config/long_memory_skip_gate.json \
  --post-task-reflection \
  --url "${WEBGEN_BOLT_URL:-http://localhost:5186/}" \
  --generator-model "${WEBGEN_GENERATOR_API_MODEL:-webgen-generator-gpt41-mini}"
