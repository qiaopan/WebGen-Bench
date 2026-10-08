#!/bin/bash
# Worker item: does the reflection change (code facts on undeclared imports + "fix within reach") and the
# condense change (keep names, no cross-problem merge) stop the white-screen failures?  DIAGNOSTIC ONLY.
# Starts from the stopped Long Memory chain's final memory; never writes to that chain.
#  1. re-run the reflection of the 20 white-screen tasks (undeclared vue-router / prismjs) with the new code;
#  2. seed DB = copy of the chain's memory.db with those tasks' cases replaced (old ones archived);
#  3. preview the guidance two later white-screen tasks would get;
#  4. run Long Memory on 3 white-screen tasks and 2 tasks that were fine (did the new guidance break them?).
set -uo pipefail
source scripts/cluster/worker_lib.sh
src=outputs/experiment/cluster_longmem_webgenlm7b_r1
diag=outputs/experiment/cluster_diag_whitescreen_r1
mkdir -p "$diag"
memkey=$(key_file WEBGEN_MEMORY_API_KEY); embkey=$(key_file WEBGEN_EMBEDDING_API_KEY)
trap 'rm -f "$memkey" "$embkey"' EXIT
white=(000030 000032 000034 000035 000038 000056 000059 000060 000012 000005 000065 000075 000096 000098
       000099 000100 000101 000051 000054 000081)

echo "== 1. re-reflect ${#white[@]} white-screen tasks"
"$py" scripts/cluster/rereflect_local.py "$src" "${white[@]}" --base-url "$WEBGEN_MEMORY_BASE_URL" \
  --key-file "$memkey" --out "$diag/rereflections.jsonl"

echo "== 2. seed memory"
"$py" -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d)" \
  "$src/memory.db" "$diag/memory_seed.db"
"$py" scripts/cluster/store_reflections_copy.py "$diag/rereflections.jsonl" "$diag/memory_seed.db" \
  --memory-url "$WEBGEN_MEMORY_BASE_URL" --memory-key-file "$memkey" \
  --embedding-url "$WEBGEN_EMBEDDING_BASE_URL" --embedding-key-file "$embkey" || exit 1
mv "$diag/memory_seed.db" "$diag/memory.db"

echo "== 3. guidance preview"
view=$(mktemp -d "$WG/tmp/preview.XXXXXX"); ln -s "$PWD/$diag/memory.db" "$view/memory.db"; ln -s "$PWD/$src/tasks" "$view/tasks"
for t in 000056 000065; do
  "$py" scripts/preview_guidance.py --output "$view" --task-id "$t" --memory-config "$memory_config" \
    --log "$diag/preview-$t.events.jsonl" --memory-url "$WEBGEN_MEMORY_BASE_URL" --memory-key-file "$memkey" \
    --embedding-url "$WEBGEN_EMBEDDING_BASE_URL" --embedding-key-file "$embkey" > "$diag/preview-$t.txt" 2>&1
  grep -E '^- |^CONDENSE|^COMMON POOL' "$diag/preview-$t.txt"
done
rm -rf "$view"

echo "== 4. generate and evaluate"
run_longmem_tasks "$diag" 000056 000065 000096 000016 000045
echo DIAG_DONE
