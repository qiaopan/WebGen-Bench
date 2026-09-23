#!/bin/zsh
# Continue the same eight-task domain block after tasks 000014-000016.
set -euo pipefail
script_dir="${0:A:h}"
export WEBGEN_RUN_OUTPUT="${WEBGEN_RUN_OUTPUT:-${script_dir:h}/outputs/experiment/second_reflection_pilot_14_16_r1}"
export WEBGEN_TASK_IDS="000017,000018,000019,000020,000021"
exec zsh "$script_dir/run_case_only_contact_pilot.sh"
