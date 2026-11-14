#!/usr/bin/env bash
# ssh_pakker.sh — install the SSH add-on's own `packages:` once the network is up.
#
# WHY THIS EXISTS
#   The Advanced SSH & Web Terminal add-on installs its `packages:` option ONCE
#   at start, and if `apk update` fails it skips them all ("Skipping installation
#   of custom packages so access stays available"). After a NUC boot DNS is often
#   not ready yet (12/11 07:51: "DNS: transient error"), so py3-websockets, nodejs
#   and npm were missing all day — live_godkend.py died on `import websockets`
#   and there was no node for Trail Buddy's tests.
#
# WHERE IT RUNS
#   Launched in the background from the add-on's init_commands. Reads the package
#   list from the add-on's own options (one list, no copy here), retries every
#   30 s for up to 30 min, then exits. Log: /tmp/ssh_pakker.log (container-local).
set -u
LOG=/tmp/ssh_pakker.log
exec >>"$LOG" 2>&1

pakker() {
  curl -fsS -H "Authorization: Bearer ${SUPERVISOR_TOKEN:-}" http://supervisor/addons/self/info \
    | jq -r '.data.options.packages[]?'
}

for i in $(seq 1 60); do
  mangler=()
  liste=$(pakker) || { echo "$(date '+%F %T') supervisor svarer ikke (forsøg $i)"; sleep 30; continue; }
  for p in $liste; do apk info -e "$p" >/dev/null || mangler+=("$p"); done
  if [ ${#mangler[@]} -eq 0 ]; then
    echo "$(date '+%F %T') alle pakker installeret (forsøg $i)"
    exit 0
  fi
  echo "$(date '+%F %T') mangler: ${mangler[*]} (forsøg $i)"
  apk update -q && apk add -q "${mangler[@]}" && continue
  sleep 30
done
echo "$(date '+%F %T') GAV OP efter 30 min — mangler stadig: ${mangler[*]}"
exit 1
