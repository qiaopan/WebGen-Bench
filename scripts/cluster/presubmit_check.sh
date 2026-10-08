#!/bin/bash
# Pre-submit check on the cluster LOGIN node: seconds, no GPU, no Slurm job, nothing started.
# Catches what has cost us queue time before (an incomplete model download, a script that does not
# parse, a wrong port, an Azure endpoint) before a job waits hours for a GPU and then fails.
#   bash scripts/cluster/presubmit_check.sh N|L|"N L" [WEBGEN_PORT_OFFSET]
# Prints PRESUBMIT_OK or PRESUBMIT_FAIL with every problem found. Model behaviour (what the GPU run
# itself does) cannot be checked here.
set -uo pipefail
source /data/qma258/env.sh
cd "$WG/webgen"
arms="${1:-N L}"; offset="${2:-0}"
py=env/webvoyager/bin/python3.10
problems=()
fail() { problems+=("$1"); echo "  FAIL $1"; }
ok() { echo "  ok   $1"; }

echo "== scripts"
for f in scripts/cluster/run_queue.sbatch scripts/cluster/start_services.sh; do
  bash -n "$f" && ok "$f parses" || fail "$f does not parse"
done
zsh -n scripts/start_bolt_provider.sh && ok "start_bolt_provider.sh parses" || fail "start_bolt_provider.sh does not parse"
"$py" -m py_compile scripts/run_continual_memory.py scripts/run_stage1.py scripts/preflight_reflective_models.py \
  scripts/cluster/check_task_health.py src/automatic_bolt_diy/automatic_web_gen.py \
  src/automatic_bolt_diy/generation_validator.py webvoyager/run.py \
  && ok "python sources compile" || fail "python sources do not compile"
(cd scripts && ../"$py" -c "import sys; sys.path[:0]=['../src','../src/automatic_bolt_diy','.']; import run_continual_memory" 2>/dev/null) \
  && ok "runner imports" || fail "runner does not import"

echo "== configuration"
if grep -v '^#' .env | grep -qi azure; then fail ".env references Azure"; else ok ".env has no Azure endpoint"; fi
config=config/long_memory_cluster.json
"$py" -c "import sys; sys.path.insert(0,'src'); from long_memory_settings import load_long_memory_settings as l; l(__import__('pathlib').Path('$config'))" \
  && ok "$config loads" || fail "$config does not load"
[[ -s bolt.diy-Fork/.env.local ]] && ok "Bolt .env.local present" || fail "Bolt .env.local missing (GitHub token for templates)"
[[ -d bolt.diy-Fork/node_modules ]] && ok "Bolt dependencies installed" || fail "Bolt node_modules missing"

echo "== models (config, tokenizer, weights complete against their index)"
models=(WebGen-LM-7B Qwen2.5-VL-32B-Instruct)
[[ " $arms " == *" L "* ]] && models+=(Qwen2.5-VL-72B-Instruct-AWQ bge-m3)
for m in "${models[@]}"; do
  "$WG/venvs/vllm/bin/python" - "$WG/models/$m" <<'EOF' && ok "$m" || fail "$m incomplete (see above)"
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
missing = [n for n in ("config.json",) if not (root / n).is_file()]
if not any((root / n).is_file() for n in ("tokenizer.json", "tokenizer.model", "vocab.txt", "sentencepiece.bpe.model")):
    missing.append("tokenizer file")
index = next(iter(root.glob("*.safetensors.index.json")), None)
weights = sorted(root.glob("*.safetensors")) + sorted(root.glob("pytorch_model*.bin"))
if index:
    needed = set(json.loads(index.read_text())["weight_map"].values())
    missing += sorted(n for n in needed if not (root / n).is_file())
elif not weights:
    missing.append("weights")
if missing:
    print("     missing:", ", ".join(missing)); sys.exit(1)
EOF
done

echo "== ports (shift $offset) free on this node"
set -a; source .env; set +a
urls=("$WEBGEN_GENERATOR_BASE_URL" "$WEBGEN_FUNCTIONAL_EVALUATOR_BASE_URL")
[[ " $arms " == *" L "* ]] && urls+=("$WEBGEN_MEMORY_BASE_URL" "$WEBGEN_EMBEDDING_BASE_URL")
ports=(); for u in "${urls[@]}"; do p="${u##*:}"; ports+=($(( ${p%%/*} + offset ))); done
ports+=($(( 28419 + offset )))
in_use=$(ss -ltnH | awk '{print $4}' | grep -o -E '[0-9]+$' | sort -u)
for p in "${ports[@]}"; do
  grep -qx "$p" <<< "$in_use" && fail "port $p already in use" || ok "port $p free"
done

echo "== health check on an earlier result (if any)"
sample=$(ls -d outputs/experiment/cluster_nomem_webgenlm7b_r1 2>/dev/null)
if [[ -n "$sample" ]]; then
  first=$("$py" -c "import json; print(json.loads(open('$sample/progress.jsonl').readline())['task_id'])" 2>/dev/null)
  [[ -n "$first" ]] && "$py" scripts/cluster/check_task_health.py "$sample" "$first" disabled >/dev/null \
    && ok "check_task_health runs on $first" || fail "check_task_health did not run"
fi

echo "== queue plan (dry run)"
"$py" -c "
import json
m = json.load(open('data/experiment_splits/continual_domain_blocks/manifest.json'))
ids = [t for b in m['batches'] for t in b['task_ids']]
start, count = int('${QUEUE_FROM:-0}'), int('${QUEUE_COUNT:-0}') or len(ids)
sel = ids[start:start + count]
print(f'  arms: $arms; {len(sel)} task(s): {sel[0]} .. {sel[-1]}')
"

if (( ${#problems[@]} )); then echo "PRESUBMIT_FAIL (${#problems[@]} problem(s))"; exit 1; fi
echo PRESUBMIT_OK
