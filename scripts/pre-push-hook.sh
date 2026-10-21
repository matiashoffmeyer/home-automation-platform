#!/usr/bin/env bash
# =============================================================================
# Pre-push hook — Live entity validation gate (Blok A, sprint 2026-05-06)
# =============================================================================
# Tjekker at YAML entity refs eksisterer i den faktiske HA før push til main.
# Catcher den klasse af bugs hvor automation refererer light.X som ikke
# findes (silently failing). Boern-bulb-bug 2026-05-05 ville blevet catched
# her.
#
# Hvorfor pre-PUSH og ikke pre-COMMIT?
#   Live-fetch til HA tager 1-3 sek + kræver netværk. For lokale commits er
#   det for slow/flaky. Push er sjældnere event = acceptable cost.
#
# Override (sjælden):
#   git push --no-verify   # skipper hook helt
#   git push --no-verify   # eller --live=false hvis du arbejder offline
#
# Installation (engangs, sammen med pre-commit):
#   bash scripts/dev_setup.sh
#
# Snapshot fallback:
#   Hvis HA er unreachable (du er på flyet, etc), bruger validatoren
#   .cache/snapshot_latest.json som fallback. ha_snapshot.sh skriver til
#   den path som side-effect.
# =============================================================================

set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Python fra dev-venv'et (pinnet PyYAML) når det virker, ellers systemets: en
# clone uden globalt PyYAML kan så også køre tjekkene (scripts/dev_setup.sh).
if "$REPO_ROOT/.cache/dev-venv/bin/python" -c 'import yaml' 2>/dev/null; then
    PATH="$REPO_ROOT/.cache/dev-venv/bin:$PATH"
fi

# === Fresh-install-filen passer til snapshottet i det der pushes ===
# Pre-commit tjekker det stagede par, men rebase/cherry-pick --continue kører
# IKKE pre-commit, og merge=binary beholder den ene sides afledte fil — så et
# par der ikke passer kan nå HEAD uden en eneste advarsel (review 10-04).
if [ -f scripts/helpers_export.py ] && [ -f config_snapshots/helper_values.yaml ]; then
    if ! python3 scripts/helpers_export.py --check-derived --rev HEAD >&2; then
        echo "❌ PUSH BLOKERET: fresh-install-filen i HEAD passer ikke til snapshottet." >&2
        exit 1
    fi
fi

# === Offline: HA's EGEN validator (konsolidering 2026-10-04) ===
# Fanger fejlklasse #22 (validerings-fejlet = stum automation) og "én ugyldig
# sensor dræber hele template:-blokken" FØR deploy — uden HA, uden netværk.
# Replay af historikken: 5 af 7 kendte hændelser var blevet stoppet her.
# Kører kun når venv'et allerede findes (en hook må ikke bruge 2 min på at
# bygge det); byg det med `python3 scripts/ha_offline.py check` én gang.
HA_OFFLINE_VER="$(grep -v '^[[:space:]]*#' scripts/ha_offline_version.txt 2>/dev/null | head -1 | tr -d '[:space:]')"
if [ -n "$HA_OFFLINE_VER" ] && [ -e "${HA_OFFLINE_CACHE:-.cache/ha-offline}/venv-$HA_OFFLINE_VER" ]; then
    echo "🔍 Pre-push: HA $HA_OFFLINE_VER check_config (offline)..." >&2
    if ! python3 scripts/ha_offline.py check --quiet >&2; then
        echo "" >&2
        echo "❌ PUSH BLOKERET: HA's egen validator fandt fejl (se ovenfor)." >&2
        echo "   Det ville have gjort automations/templates stumme efter restart." >&2
        echo "   Skip (kun hvis du VED det er en falsk positiv):  git push --no-verify" >&2
        exit 1
    fi
elif [ -f scripts/ha_offline.py ]; then
    echo "ℹ  HA-offline-check sprunget over (intet venv): python3 scripts/ha_offline.py check" >&2
fi

# Skip kun hvis der slet ingen vej er til live-API'et.
# PC-checkouten har .env/$HA_TOKEN; kører vi PÅ HA-hosten findes .env ikke,
# men $SUPERVISOR_TOKEN gør — og ha_validate.py kender begge veje. Den gamle
# rene .env-gate gjorde hooken til en tavs no-op på præcis den maskine hvor
# commit == deploy.
if [ ! -f .env ] && [ -z "${HA_TOKEN:-}" ] && [ -z "${SUPERVISOR_TOKEN:-}" ]; then
    echo "ℹ  Hverken .env, \$HA_TOKEN eller \$SUPERVISOR_TOKEN — skipper live entity validation" >&2
    exit 0
fi

if [ ! -f scripts/ha_validate.py ]; then
    exit 0
fi

# Detect REAL python3 (Windows has Microsoft Store stub at python3 that errors).
# Test by running --version. If it fails, fall back to ssh-to-NUC.
USE_LOCAL_PYTHON=true
if ! python3 --version >/dev/null 2>&1; then
    USE_LOCAL_PYTHON=false
fi

# Run validator. Prefer local python3, else ssh to NUC.
echo "🔍 Pre-push: live entity ref check..." >&2

if [ "$USE_LOCAL_PYTHON" = true ]; then
    VALIDATE_CMD="python3 scripts/ha_validate.py --check refs --live --quiet"
    if ! $VALIDATE_CMD 2>&1; then
        echo "" >&2
        echo "❌ PUSH BLOKERET: live entity refs har errors" >&2
        echo "" >&2
        echo "Fix entities, eller skip check med:  git push --no-verify" >&2
        echo "Full report:  python3 scripts/ha_validate.py --check refs --live" >&2
        exit 1
    fi
    # Bonus: warn about stale whitelist entries (don't block)
    python3 scripts/ha_validate.py --check stale_whitelist --quiet 2>&1 || true
else
    # Windows fallback: ssh til NUC og kør validator der mod live HA.
    # Krav: ssh ha alias virker, /config/scripts/ha_validate.py er deployed.
    if ! command -v ssh >/dev/null 2>&1; then
        echo "⚠  Hverken local python3 eller ssh tilgængelig, skipper validation" >&2
        exit 0
    fi
    HA_TOKEN_FROM_ENV=$(grep '^HA_TOKEN=' .env | cut -d= -f2)
    if ! ssh ha "HA_TOKEN='$HA_TOKEN_FROM_ENV' python3 /config/scripts/ha_validate.py --check refs --live --quiet" 2>&1; then
        echo "" >&2
        echo "❌ PUSH BLOKERET: live entity refs har errors (kørt på NUC)" >&2
        echo "" >&2
        echo "Fix entities, eller skip check med:  git push --no-verify" >&2
        echo "Full report:  ssh ha 'cd /config && python3 scripts/ha_validate.py --check refs --live'" >&2
        exit 1
    fi
fi

exit 0
