#!/usr/bin/env bash
# =============================================================================
# HA Remote Helpers — bash module til at styre HA fra terminal
# =============================================================================
# Source dette i din session: source scripts/ha.sh
# For permanent: tilfoej til ~/.bashrc:
#   source /c/Users/Matia/Documents/homeassistant-main/scripts/ha.sh
#
# Forudsaetninger:
# - SSH key paret med HA addon
# - Optional: $HA_TOKEN sat for REST API funktioner
# =============================================================================

HA_HOST="${HA_HOST:-homeassistant.local}"
HA_USER="${HA_USER:-root}"
HA_PORT="${HA_PORT:-22}"

# Core SSH helpers
# Wrap kommando i 'zsh -lc' saa SUPERVISOR_TOKEN er sat (ellers fejler ha CLI)
ha-cmd() {
    local cmd="$*"
    cmd="${cmd//\'/\'\\\'\'}"  # escape single quotes
    ssh -p "$HA_PORT" "${HA_USER}@${HA_HOST}" "zsh -lc '$cmd'"
}
ha-shell() { ssh -p "$HA_PORT" "${HA_USER}@${HA_HOST}"; }

# HA Core operations
# Genstart via ha_restart.sh: gemmer restore-state først (HA segfaulter ved nedlukning)
ha-restart() { echo "Restarting HA Core..."; ha-cmd "bash /config/scripts/ha_restart.sh"; }
ha-stop() { ha-cmd "ha core stop"; }  # NB gemmer IKKE restore-state først
ha-logs() { ha-cmd "ha core logs --tail ${1:-100}"; }
ha-info() { ha-cmd "ha core info && echo && ha supervisor info"; }

# Git deploy workflow
ha-pull() { ha-cmd "cd /config && git fetch origin && git reset --hard origin/main"; }
ha-deploy() {
    echo "Deploying latest from git..."
    ha-cmd "cd /config && git fetch origin && git reset --hard origin/main && bash scripts/ha_restart.sh"
}
ha-push-and-deploy() {
    git push origin main && ha-deploy
}

# File operations
ha-cat() { ha-cmd "cat /config/$1"; }
ha-edit() {
    echo "WARNING: direkte edit gaar ude af git sync."
    ssh -t -p "$HA_PORT" "${HA_USER}@${HA_HOST}" "vim /config/$1"
}
ha-ls() { ha-cmd "ls -la /config/${1:-}"; }

# REST API operations (kraever HA_TOKEN)
_ha-check-token() {
    [ -z "$HA_TOKEN" ] && { echo "HA_TOKEN env var ikke sat" >&2; return 1; }
    return 0
}

ha-state() {
    _ha-check-token || return 1
    curl -s -H "Authorization: Bearer $HA_TOKEN" \
        "http://${HA_HOST}:8123/api/states/$1" | jq .
}

ha-call() {
    # Usage: ha-call light.turn_on '{"entity_id":"light.x","brightness_pct":50}'
    _ha-check-token || return 1
    local domain="${1%.*}"
    local service="${1#*.}"
    local data="${2:-{\}}"
    curl -s -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$data" \
        "http://${HA_HOST}:8123/api/services/${domain}/${service}" | jq .
}

ha-help() {
    echo "HA Remote Helpers — available commands:"
    echo "  ha-cmd CMD              Run shell command on HA"
    echo "  ha-shell                Interactive SSH session"
    echo "  ha-restart              Restart HA Core"
    echo "  ha-stop                 Stop HA Core"
    echo "  ha-logs [N]             View logs (default 100 lines)"
    echo "  ha-info                 HA + Supervisor info"
    echo "  ha-pull                 Git pull on HA, no restart"
    echo "  ha-deploy               Git pull + restart (= deploy)"
    echo "  ha-push-and-deploy      Local push + remote deploy"
    echo "  ha-cat FILE             Print HA file"
    echo "  ha-edit FILE            Edit HA file via vim"
    echo "  ha-ls [PATH]            List HA /config or subdir"
    echo "  ha-state ENTITY         Get entity state (REST)"
    echo "  ha-call DOMAIN.SERVICE [DATA]  Call HA service (REST)"
}

echo "HA helpers loaded. Run 'ha-help' for command list."
