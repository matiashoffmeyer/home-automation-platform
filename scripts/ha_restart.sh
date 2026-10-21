#!/usr/bin/env bash
# =============================================================================
# ha_restart.sh: a Home Assistant Core restart that keeps restore-state
# =============================================================================
# Home Assistant segfaults during shutdown on this host (a pychromecast thread
# under Python 3.14), so its final restore-state write never happens and only
# the 15-minute periodic dump survives. Slider and toggle changes from the last
# 15 minutes before a restart used to vanish without a trace. This script
# saves first.
#
# Usage (on the host, in the SSH add-on):
#   bash scripts/ha_restart.sh           # save restore-state, then restart
#   bash scripts/ha_restart.sh --force   # restart even if the save fails
#                                        # (for example in recovery mode)
# The remote variants (scripts/ha.sh, scripts/ha_deploy.sh) call it over ssh.
# scripts/restart_guard.py rejects a plain `ha core restart` in agent sessions.
# =============================================================================
set -u
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

if [ -z "${SUPERVISOR_TOKEN:-}" ]; then
    echo "ha_restart: SUPERVISOR_TOKEN mangler — kører du uden for SSH-add-on'et?" >&2
    [ "$FORCE" = 1 ] || exit 1
elif curl -sf -m 20 -X POST \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H "Content-Type: application/json" -d '{}' \
        http://supervisor/core/api/services/homeassistant/save_persistent_states >/dev/null; then
    echo "ha_restart: restore-state gemt"
    sleep 2
else
    echo "ha_restart: save_persistent_states FEJLEDE — genstarter ikke (--force for at gøre det alligevel)" >&2
    [ "$FORCE" = 1 ] || exit 1
fi

exec ha core restart
