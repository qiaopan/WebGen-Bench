#!/bin/zsh
# Keep the 8001 SSH forward to the evaluator server alive; logs each reconnect.
# The server login (user@host) comes from WEBGEN_EVAL_SSH_HOST in .env; it is not kept in the repo.
root="${0:A:h:h}"
[[ -z "$WEBGEN_EVAL_SSH_HOST" && -f "$root/.env" ]] && source "$root/.env"
: "${WEBGEN_EVAL_SSH_HOST:?set WEBGEN_EVAL_SSH_HOST=user@host in .env}"
log="$root/outputs/experiment/tunnel_keeper.log"
while true; do
  if ! curl -s -m10 -o /dev/null 127.0.0.1:8001/v1/models; then
    pkill -f "ssh -f -N .*-L 8001:127.0.0.1:8001" 2>/dev/null
    ssh -f -N -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=6 -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=15 -L 8001:127.0.0.1:8001 "$WEBGEN_EVAL_SSH_HOST" 2>/dev/null
    echo "$(date '+%F %T') reconnect: $(curl -s -m10 -o /dev/null -w '%{http_code}' 127.0.0.1:8001/v1/models)" >> "$log"
  fi
  sleep 30
done
