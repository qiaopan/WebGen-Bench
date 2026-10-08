#!/bin/zsh
# Case-only A ablation: original task requirement + complete selected cases.
# The wrapper uses a fresh output directory so the earlier r1 run is preserved.
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h}"
export WEBGEN_RUN_OUTPUT="${WEBGEN_RUN_OUTPUT:-$project_root/outputs/experiment/case_only_contact_pilot_a_r1}"

exec zsh "$script_dir/run_case_only_contact_pilot.sh" "$@"
