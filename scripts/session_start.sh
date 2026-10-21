#!/usr/bin/env bash
# =============================================================================
# session_start.sh: SessionStart hook for the coding agent (.claude/settings.json)
# =============================================================================
# Performs the rituals CLAUDE.md asks of every session, so that they cost no
# tool calls and cannot be forgotten (docs/konsolidering.md):
#   1. Git hooks do not follow a clone, so a fresh checkout (cloud,
#      workstation) used to commit without the pre-commit lint. Install or
#      sync them.
#   2. "Check status before you code": how far behind origin/main are we?
#   3. In the cloud: build the Home Assistant venv for scripts/ha_offline.py
#      in the background, so `check` and `staging` are ready when needed.
# Output is at most 2 lines, because everything here is paid for in tokens in
# every session. Never fails the session: everything is best-effort, exit 0.
# =============================================================================
set -u
ROOT="${CLAUDE_PROJECT_DIR:-}"
[ -n "$ROOT" ] || ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

notes=()

# 1) git-hooks = kopier af scripts/*-hook.sh (synkes også når scriptet ændres)
HOOKDIR="$(git rev-parse --git-path hooks 2>/dev/null)"
if [ -n "$HOOKDIR" ] && mkdir -p "$HOOKDIR" 2>/dev/null; then
    for h in pre-commit pre-push; do
        src="scripts/${h}-hook.sh"
        dst="$HOOKDIR/$h"
        if [ -f "$src" ] && ! cmp -s "$src" "$dst" 2>/dev/null; then
            cp "$src" "$dst" 2>/dev/null && chmod +x "$dst" && notes+=("$h-hook synket")
        fi
    done
fi

# 2) bagud origin/main? (timeout: et offline net må ikke hænge sessionen)
if command -v timeout >/dev/null 2>&1; then
    timeout 10 git fetch -q origin main 2>/dev/null
else
    git fetch -q origin main 2>/dev/null
fi
behind="$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")"

# 3) cloud: HA-venv i baggrunden (NUC'en bygger det kun når nogen beder om det)
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && [ -f scripts/ha_offline.py ]; then
    ver="$(grep -v '^\s*#' scripts/ha_offline_version.txt 2>/dev/null | head -1 | tr -d '[:space:]')"
    if [ -n "$ver" ] && [ ! -e "${HA_OFFLINE_CACHE:-.cache/ha-offline}/venv-$ver" ]; then
        mkdir -p .cache/ha-offline
        nohup python3 scripts/ha_offline.py check > .cache/ha-offline/bootstrap.log 2>&1 &
        notes+=("ha_offline-venv bygges i baggrunden")
    fi
fi

if [ "$behind" = "0" ]; then
    status="git: ajour med origin/main"
elif [ "$behind" = "?" ]; then
    status="git: kunne ikke sammenligne med origin/main (offline?) — kør status-tjekket selv"
else
    status="⚠️ git: $behind commits BAGUD origin/main — \`git merge --ff-only origin/main\` før du rører noget"
fi
if [ ${#notes[@]} -gt 0 ]; then
    joined="$(printf '%s, ' "${notes[@]}")"
    status="$status · ${joined%, }"
fi
echo "[session_start] $status"
exit 0
