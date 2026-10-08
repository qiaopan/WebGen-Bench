#!/bin/zsh
# A ablation after channel-isolated relevance gates; only tasks 000014 and 000015.
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
export WEBGEN_RUN_OUTPUT="${WEBGEN_RUN_OUTPUT:-$project_root/outputs/experiment/case_only_contact_pilot_a_14_15_r1}"
export WEBGEN_TASK_IDS="000014,000015"

exec zsh "$script_dir/run_case_only_contact_pilot.sh" "$@"
