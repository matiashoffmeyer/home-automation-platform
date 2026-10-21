#!/usr/bin/env bash
# otbr_selfheal.sh — auto-recover a wedged OpenThread Border Router (Thread) RCP.
#
# WHY THIS EXISTS
#   The Sonoff ZBDongle-E's OpenThread RCP firmware can hard-hang. When it does,
#   the OTBR add-on crash-loops on a spinel TimeoutError and the ENTIRE Thread
#   network goes dark (bath spots, door sensors, Timmerflotte, ...). Supervisor's
#   own add-on watchdog only *restarts* the add-on — which is not enough, because
#   the add-on's startup does a *soft* spinel reset, and a wedged chip can't even
#   receive that. Only a *physical* RTS/DTR reset-pin pulse followed by a
#   bootloader "launch application" (done by universal-silabs-flasher) revives it.
#   This watchdog performs exactly that, gated so it never hammers the chip.
#
# WHERE IT RUNS
#   As a daemon inside the Advanced SSH & Web Terminal add-on (the only place with
#   BOTH /dev/ttyUSB0 access AND a fresh SUPERVISOR_TOKEN). Launched from the
#   add-on's init_commands so it survives reboots/add-on restarts. Cron is NOT
#   usable here: cron jobs don't inherit SUPERVISOR_TOKEN (rotated per container).
#
# CONTROL / VISIBILITY
#   input_boolean.thread_watchdog_enabled   shared killswitch with the HA-side
#     Thread watchdog (packages/thread_otbr_watchdog.yaml) — ONE switch kills
#     all automatic Thread healing (default on if missing).
#   input_boolean.otbr_selfheal_request     delegation flag: the HA watchdog's
#     recovery script sets it on hard-hang; we consume it (turn off + recover).
#     This makes THIS daemon the single owner of the physical chip reset —
#     the HA side never touches the serial port anymore (its old pure pin-pulse
#     was proven insufficient 2026-07-24: leaves chip without guaranteed app
#     relaunch; the flasher's bootloader+launch sequence is the real cure).
#   input_boolean.otbr_selfheal_txboost     (2026-10-09) request flag: raise the
#     RCP's TX power to $TXBOOST_DBM via `ot-ctl txpower` while the OTBR is cut
#     off from the mesh (the add-on forces 6 dBm at every start, so the boost
#     lasts until the next add-on start). Consumed like the reset flag.
#   txhold (2026-10-14, B234): TX power is re-asserted to $TXBOOST_DBM every
#     poll — permanent now, not only while the OTBR is cut off.
#   sensor.otbr_rcp_resets_1t (scripts/otbr_rcp_stats.py, every poll): RCP
#     resets in the last hour + partition-split attributes.
#   input_text.otbr_selfheal_heartbeat      epoch heartbeat (hourly) →
#     binary_sensor.otbr_selfheal_daemon_ok gives HA-side liveness visibility.
#   Pushes go through script.push_notify (nid `thread`) so the user's central
#   toggles (per-type, per-phone, AirBnB opt-in, hjemkomst-kø) all apply.
#   Log + state under /data/otbr_selfheal/ (add-on persistent storage, not git).
set -uo pipefail

ADDON="core_openthread_border_router"
DEVICE="/dev/serial/by-id/usb-Itead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_V2_1ce022a8cbf3ef11a8f8c51b6d9880ab-if00-port0"
STATE_DIR="/data/otbr_selfheal"
VENV="$STATE_DIR/venv"
FLASHER="$VENV/bin/universal-silabs-flasher"
LOG="$STATE_DIR/selfheal.log"
LAST_RECOVERY="$STATE_DIR/last_recovery_epoch"
FAIL_MARKER="$STATE_DIR/failing"
PIDFILE="$STATE_DIR/daemon.pid"
COOLDOWN=600          # min seconds between recovery attempts (chip-wear guard)
FAIL_COOLDOWN=3600    # backoff while FAIL_MARKER set — a dead/unplugged chip
                      # must not get 3 reset pulses every 10 min forever
POLL=120              # daemon poll interval (seconds)
HB_INTERVAL=3600      # heartbeat to HA (input_text) — daemon-liveness proxy
TXBOOST_DBM=17        # EFR32MG21A020 can do +20; 17 dBm conducted keeps EIRP
                      # under the EU 20 dBm limit with the dongle's ~2-3 dBi antenna.
                      # Add-on default is 6 (→ 5 dBm): 10-08/09 the mesh could
                      # hear the OTBR too weakly to merge (LinkMarginLow, NoAck).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUP="http://supervisor"
AUTH="Authorization: Bearer ${SUPERVISOR_TOKEN:-}"

mkdir -p "$STATE_DIR"
log(){ echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
api(){ curl -s -H "$AUTH" "$@"; }

addon_state(){
  api "$SUP/addons/$ADDON/info" \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('data',{}).get('state','unknown'))" 2>/dev/null \
    || echo unknown
}

state_of(){  # $1 = entity_id -> state string (or 'unknown')
  api "$SUP/core/api/states/$1" \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('state','unknown'))" 2>/dev/null \
    || echo unknown
}

enabled(){ [ "$(state_of input_boolean.thread_watchdog_enabled)" != "off" ]; }  # default on if missing

push(){  # $1 title  $2 message — via central push_notify (nid thread): master/
         # per-type/per-phone/AirBnB-opt-in/hjemkomst-kø gates all live THERE.
  local body
  body=$(python3 -c 'import json,sys;print(json.dumps({"notif_id":"thread","title":sys.argv[1],"message":sys.argv[2]}))' "$1" "$2")
  api -X POST -H "Content-Type: application/json" -d "$body" \
    "$SUP/core/api/services/script/push_notify" >/dev/null 2>&1
  log "push handed to push_notify: $1"
}

heartbeat(){  # epoch → input_text.otbr_selfheal_heartbeat (HA-side liveness)
  api -X POST -H "Content-Type: application/json" \
    -d "{\"entity_id\":\"input_text.otbr_selfheal_heartbeat\",\"value\":\"$(date +%s)\"}" \
    "$SUP/core/api/services/input_text/set_value" >/dev/null 2>&1
}

ensure_venv(){
  if "$FLASHER" --help >/dev/null 2>&1; then return 0; fi
  log "flasher missing/broken — (re)building venv"
  rm -rf "$VENV"
  python3 -m venv "$VENV" >/dev/null 2>&1 \
    && "$VENV/bin/pip" install --quiet universal-silabs-flasher >/dev/null 2>&1 \
    && "$FLASHER" --help >/dev/null 2>&1 \
    || { log "venv build FAILED"; return 1; }
}

reset_chip(){  # physical RTS/DTR reset + launch app; returns 0 if chip speaks spinel
  local try
  for try in 1 2 3; do
    log "flasher rts_dtr reset (attempt $try)"
    if timeout 100 "$FLASHER" --device "$DEVICE" --bootloader-reset rts_dtr \
         --probe-methods spinel:460800 probe 2>&1 \
         | grep -q "Detected ApplicationType.SPINEL"; then
      return 0
    fi
    sleep 3
  done
  return 1
}

otbr_container(){ docker ps --format '{{.Names}}' 2>/dev/null | grep -m1 "core_openthread_border_router"; }

txboost(){  # raise RCP TX power inside the running OTBR container
  local c out
  c=$(otbr_container)
  if [ -z "$c" ]; then log "txboost: OTBR container not running — skipped"; return 1; fi
  docker exec "$c" sh -c "ot-ctl txpower $TXBOOST_DBM" >/dev/null 2>&1
  out=$(docker exec "$c" sh -c "ot-ctl txpower" 2>/dev/null | head -1 | tr -d '\r')
  log "txboost: requested ${TXBOOST_DBM} dBm, RCP reports '${out}'"
}

txhold(){  # 2026-10-14 (B234): hold TX power at $TXBOOST_DBM PERMANENTLY.
  # The add-on forces 6 dBm at every start, and the 10-09 boost only lasted
  # until then — 13/10 evening the stue spots + entré dropped off again while
  # the OTBR was back at 6. One ot-ctl read per poll; a write only on mismatch.
  local c cur
  c=$(otbr_container) || return 0
  [ -n "$c" ] || return 0
  cur=$(docker exec "$c" sh -c "ot-ctl txpower" 2>/dev/null | head -1 | tr -dc '0-9-')
  [ -n "$cur" ] || return 0
  if [ "$cur" -lt "$TXBOOST_DBM" ]; then
    docker exec "$c" sh -c "ot-ctl txpower $TXBOOST_DBM" >/dev/null 2>&1
    log "txhold: RCP was at ${cur} dBm → ${TXBOOST_DBM} dBm"
  fi
}

recover(){  # $1 = "delegated" → the HA watchdog owns all user pushes
  local mode="${1:-}"
  local now last cd
  now=$(date +%s)
  last=$(cat "$LAST_RECOVERY" 2>/dev/null || echo 0)
  cd=$COOLDOWN
  # backoff while persistently failing — but NOT for HA-delegated requests: the
  # HA ladder (thread_otbr_watchdog.yaml) paces its own retries and never gives
  # up; a 60-min daemon backoff silently swallowed its attempts.
  [ -f "$FAIL_MARKER" ] && [ "$mode" != "delegated" ] && cd=$FAIL_COOLDOWN
  if [ $((now - last)) -lt "$cd" ]; then
    log "recovery skipped — cooldown ($((now-last))s < ${cd}s$([ -f "$FAIL_MARKER" ] && echo ', fail-backoff'))"
    return 0
  fi
  echo "$now" > "$LAST_RECOVERY"
  log "RECOVERY start (addon state=$(addon_state))"

  if ! ensure_venv; then
    log "no flasher — cannot recover"
    if [ ! -f "$FAIL_MARKER" ]; then
      touch "$FAIL_MARKER"
      push "⚠️ Thread self-heal fejlede" "Flasher-værktøjet mangler og kan ikke bygges. RCP kan ikke resettes automatisk — genplug Sonoff-donglen manuelt."
    fi
    return 1
  fi

  api -X POST "$SUP/addons/$ADDON/stop" >/dev/null 2>&1
  sleep 4

  if ! reset_chip; then
    api -X POST "$SUP/addons/$ADDON/start" >/dev/null 2>&1
    log "RECOVERY FAILED — chip did not return to spinel after 3 resets"
    if [ ! -f "$FAIL_MARKER" ]; then
      touch "$FAIL_MARKER"
      push "⚠️ Thread self-heal fejlede" "RCP svarer ikke efter RTS/DTR-reset. Thread (bad-lys m.m.) er nede — prøv fysisk at genplugge Sonoff-donglen."
    fi
    return 1
  fi

  api -X POST "$SUP/addons/$ADDON/start" >/dev/null 2>&1
  local i
  for i in $(seq 1 12); do
    sleep 5
    [ "$(addon_state)" = "started" ] && break
  done

  if [ "$(addon_state)" = "started" ]; then
    rm -f "$FAIL_MARKER"
    log "RECOVERY OK — chip on spinel, OTBR started ($mode)"
    # 2026-10-09: "chip on spinel" proves the CHIP, not the MESH — 10-08 21:35
    # this push said "hele Thread-nettet er oppe" while the OTBR stayed cut off
    # for 9 more hours. Delegated runs: the HA ladder verifies routerCount and
    # pushes. Own (addon-error) runs: honest wording.
    [ "$mode" = "delegated" ] || push "🧵 Thread-chippen genstartet" "OpenThread Border Router var crashet (RCP hang) og er genstartet med RTS/DTR-reset. HA-vagten tjekker om mesh'et samler sig og fortsætter selv hvis ikke."
  else
    log "RECOVERY PARTIAL — chip ok but OTBR not 'started'"
    push "⚠️ Thread self-heal delvist" "RCP blev resat, men OTBR-addon startede ikke rent. Tjek add-on-loggen."
  fi
}

check(){
  enabled || { return 0; }  # killswitch off
  # Delegation from the HA-side watchdog (soft-hang path: addon 'started' but
  # Thread down — invisible to our addon-state detector). Consume flag FIRST
  # so a hung recovery can't leave it stuck on and re-fire forever.
  if [ "$(state_of input_boolean.otbr_selfheal_request)" = "on" ]; then
    api -X POST -H "Content-Type: application/json" \
      -d '{"entity_id":"input_boolean.otbr_selfheal_request"}' \
      "$SUP/core/api/services/input_boolean/turn_off" >/dev/null 2>&1
    log "recovery requested by HA watchdog (delegation flag) → recovery"
    recover delegated
    return
  fi
  if [ "$(state_of input_boolean.otbr_selfheal_txboost)" = "on" ]; then
    api -X POST -H "Content-Type: application/json" \
      -d '{"entity_id":"input_boolean.otbr_selfheal_txboost"}' \
      "$SUP/core/api/services/input_boolean/turn_off" >/dev/null 2>&1
    log "txboost requested by HA watchdog"
    txboost
  fi
  # Zombie-routere (2026-10-09): en Thread-pære der sender MLE men er døv for
  # unicast → releaserouterid på lederen. Gates og cooldown bor i scriptet.
  timeout 120 python3 "$SCRIPT_DIR/thread_zombie_kick.py" >/dev/null 2>&1 || true
  txhold
  # RCP-resets/time + partition-split → sensor.otbr_rcp_resets_1t (B234):
  # ilden pauser på den, og split-varslet læser den.
  timeout 60 python3 "$SCRIPT_DIR/otbr_rcp_stats.py" >/dev/null 2>&1 || true
  local st; st=$(addon_state)
  if [ "$st" = "error" ]; then
    log "OTBR add-on state=error → recovery"
    recover
  fi
}

daemon(){
  # singleton guard. The pidfile lives in persistent /data, so after a container
  # restart it holds a stale PID that a *different* process may have reused —
  # hence verify the live process is really us (cmdline mentions this script),
  # not just that *some* process has that PID.
  local oldpid
  oldpid=$(cat "$PIDFILE" 2>/dev/null || echo "")
  if [ -n "$oldpid" ] && [ "$oldpid" != "$$" ] && kill -0 "$oldpid" 2>/dev/null \
     && tr '\0' ' ' < "/proc/$oldpid/cmdline" 2>/dev/null | grep -q "otbr_selfheal.sh"; then
    log "daemon already running (pid $oldpid) — exiting"
    exit 0
  fi
  echo $$ > "$PIDFILE"
  # trim log so a weeks-long failure episode can't grow it unboundedly
  if [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt 5000 ]; then
    tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
  log "daemon started (pid $$, poll ${POLL}s)"
  ensure_venv || log "warning: flasher venv not ready at daemon start"
  local hb_last=0 now
  while true; do
    check
    now=$(date +%s)
    if [ $((now - hb_last)) -ge "$HB_INTERVAL" ]; then
      heartbeat && hb_last=$now   # on API failure: retry next tick
    fi
    sleep "$POLL"
  done
}

case "${1:-check}" in
  check)   check ;;
  recover) recover ;;               # force one recovery (ignores enabled flag)
  txboost) txboost; tail -1 "$LOG" ;;
  daemon)  daemon ;;
  install) ensure_venv && echo "venv ok"; echo "run 'daemon' from add-on init_commands" ;;
  status)
    echo "OTBR add-on : $(addon_state)"
    echo "killswitch  : $(state_of input_boolean.thread_watchdog_enabled) (delt m. HA-watchdog)"
    echo "request-flag: $(state_of input_boolean.otbr_selfheal_request)"
    echo "txboost-flag: $(state_of input_boolean.otbr_selfheal_txboost)"
    echo "last recover: $(cat "$LAST_RECOVERY" 2>/dev/null || echo none)"
    echo "failing     : $([ -f "$FAIL_MARKER" ] && echo yes || echo no)"
    echo "daemon pid  : $(cat "$PIDFILE" 2>/dev/null || echo none) ($(kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null && echo alive || echo dead))"
    echo "--- last log ---"; tail -8 "$LOG" 2>/dev/null ;;
  *) echo "usage: $0 {check|recover|txboost|daemon|install|status}"; exit 1 ;;
esac
