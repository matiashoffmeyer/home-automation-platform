#!/usr/bin/env bash
# =============================================================================
# HA Deploy with Smoke Gate + Auto-Revert (Blok B, sprint 2026-05-06)
# =============================================================================
# Deploy + verify pipeline der protecter mod broken commits:
#   1. Pre-deploy snapshot
#   2. Pull + restart
#   3. Wait for /api/ ready (timeout 120s)
#   4. Run smoke tests
#   5. Hvis fail → auto-revert til previous SHA + restart + notify Parent A
#   6. Hvis pass → success notification
#
# Usage:
#   bash scripts/ha_deploy.sh                # default: full pipeline
#   bash scripts/ha_deploy.sh --skip-smoke   # docs-only deploy
#   bash scripts/ha_deploy.sh --force        # deploy trods smoke fail
#
# Logs: /tmp/ha_deploy_<epoch>.log + symlink .cache/last_deploy.log
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Load HA_TOKEN
if [ -f .env ]; then
    set -a
    . .env
    set +a
fi
if [ -z "${HA_TOKEN:-}" ]; then
    echo "❌ HA_TOKEN ikke sat i .env" >&2
    exit 1
fi

# Logging
EPOCH=$(date +%s)
LOG=/tmp/ha_deploy_${EPOCH}.log
mkdir -p .cache
# Symlink doesn't work on Windows git-bash; just write last log path til text file
echo "$LOG" > .cache/last_deploy_log_path.txt

# Args
FORCE=false
SKIP_SMOKE=false
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        --skip-smoke) SKIP_SMOKE=true ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done

# Notification helper — sends to mobile + persistent
notify() {
    local title="${1:-HA Deploy}"
    local msg="${2:-no message}"
    # Persistent notification (always available)
    curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"message\":\"$msg\",\"title\":\"$title\"}" \
        "http://homeassistant.local:8123/api/services/notify/persistent_notification" >/dev/null 2>&1 || true
    # Mobile push (best-effort, may not exist)
    curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"message\":\"$msg\",\"title\":\"$title\"}" \
        "http://homeassistant.local:8123/api/services/notify/mobile_app_phone_a" >/dev/null 2>&1 || true
}

log() {
    local ts=$(date +"%H:%M:%S")
    echo "[$ts] $1" | tee -a "$LOG"
}

# Rollback function — revert til previous SHA + restart + notify
rollback() {
    local reason="${1:-unknown}"
    local prev_sha="${2:-unknown}"
    log "❌ ROLLBACK initiated: $reason"
    log "    Reverting til $prev_sha"
    ssh ha "cd /config && git reset --hard $prev_sha && zsh -lc 'bash /config/scripts/ha_restart.sh --force'" 2>&1 | tee -a "$LOG" || {
        log "❌ ROLLBACK FAILED — manual intervention required!"
        notify "HA ROLLBACK FAILED" "Reason: $reason. Manual SSH ind på NUC og fix asap."
        exit 99
    }
    notify "HA Deploy ROLLBACK" "Reason: $reason. Reverted til $prev_sha. Self-fix kicker ind."

    # Per user-request 2026-05-05: Claude skal automatisk begynde at fixe
    # efter rollback (ikke vente på user). Skriver structured log som næste
    # Claude-session kan læse + handle på.
    cat > .cache/last_rollback.json <<EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "reason": "$reason",
    "reverted_from_sha": "$NEW_SHA",
    "reverted_to_sha": "$prev_sha",
    "log_path": "$LOG",
    "next_action": "Claude session should: 1) read $LOG, 2) identify failing smoke test or HA error, 3) fix root cause, 4) test, 5) re-deploy via ha_deploy.sh"
}
EOF
    log "📝 Rollback context written til .cache/last_rollback.json"
    log "    Næste Claude-session vil pick up + self-fix"
    exit 1
}

# === MAIN PIPELINE ===

log "=== HA Deploy started (PID $$) ==="

# Step 1: Pre-deploy snapshot
log "Step 1: Pre-deploy snapshot"
bash scripts/ha_snapshot.sh > .cache/snapshot_pre_deploy.json 2>&1 || {
    log "⚠  Snapshot failed (HA unreachable?). Continuing without baseline."
}

# Step 2: Capture SHAs
PREV_SHA=$(ssh ha "cd /config && git rev-parse HEAD" 2>/dev/null || echo "unknown")
log "Step 2: Previous SHA på NUC = $PREV_SHA"

# Step 3: Pull
log "Step 3: Pull origin/main"
ssh ha "cd /config && git fetch origin && git reset --hard origin/main" 2>&1 | tee -a "$LOG"
NEW_SHA=$(ssh ha "cd /config && git rev-parse HEAD" 2>/dev/null || echo "unknown")
log "    New SHA = $NEW_SHA"

if [ "$PREV_SHA" = "$NEW_SHA" ]; then
    log "✓ No changes to deploy"
    exit 0
fi

# Step 4: Restart
log "Step 4: Restart HA"
ssh ha "zsh -lc 'bash /config/scripts/ha_restart.sh --force'" 2>&1 | tail -5 | tee -a "$LOG" || {
    rollback "ha core restart command failed" "$PREV_SHA"
}

# Step 5: Wait for /api/ ready (poll every 2s, timeout 120s)
log "Step 5: Waiting for HA /api/ ready (max 120s)"
for i in $(seq 1 60); do
    sleep 2
    code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $HA_TOKEN" \
        "http://homeassistant.local:8123/api/" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        log "    HA up after $((i*2))s"
        break
    fi
    if [ "$i" = "60" ]; then
        rollback "HA failed to return 200 within 120s" "$PREV_SHA"
    fi
done

# Step 6: Settle delay (let templates re-evaluate, sensors come online)
log "Step 6: 15s settle delay"
sleep 15

# Step 7: Smoke test
if [ "$SKIP_SMOKE" = true ]; then
    log "Step 7: Skipping smoke test (--skip-smoke)"
else
    # Run ALL tests for visibility, but only CRITICAL failures block deploy.
    # Hardware health failures (Apollo offline etc) er warn-only — kan ske af
    # årsager IKKE relateret til vores kode (bruger tager Apollo ud, WiFi blip).
    log "Step 7: Smoke test (--tier all, only critical failures block)"
    if ssh ha "HA_TOKEN='$HA_TOKEN' python3 /config/scripts/ha_smoketest.py --tier all" 2>&1 | tee -a "$LOG" | tail -8; then
        log "    ✅ Smoke tests passed (no critical failures)"
    else
        if [ "$FORCE" = true ]; then
            log "    ⚠  Critical smoke test failed, but --force given — continuing"
            notify "HA Deploy WARNING" "Critical smoke fail, men --force angivet. Verificer manuelt."
        else
            rollback "Critical smoke tests failed" "$PREV_SHA"
        fi
    fi
fi

# Step 8: Post-deploy snapshot
log "Step 8: Post-deploy snapshot"
bash scripts/ha_snapshot.sh > .cache/snapshot_post_deploy.json 2>&1 || true

# Step 9: Success notification
log "✅ Deploy successful: $PREV_SHA → $NEW_SHA"
notify "HA Deploy OK" "$PREV_SHA → $NEW_SHA. Smoke tests passed."

exit 0
