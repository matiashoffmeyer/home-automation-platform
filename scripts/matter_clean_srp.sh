#!/usr/bin/env bash
# =============================================================================
# Matter SRP Cache Cleaner
# =============================================================================
# Restart OTBR addon for at clear stale SRP entries fra failed commissioning
# attempts. Devices on mesh re-registrerer automatic indenfor 30 sek.
#
# Brug efter flere failed commission attempts hvor SRP server har akkumuleret
# multiple entries med samme discriminator men forskellige host names.
#
# Usage: ./scripts/matter_clean_srp.sh
# =============================================================================

set -e
cd "$(dirname "$0")/.."
[ -f .env ] && . .env

if [ -z "$HA_TOKEN" ]; then echo "❌ HA_TOKEN ikke sat"; exit 1; fi

echo "=== Restart OTBR addon (clears SRP cache) ==="
ssh ha "zsh -lc 'curl -s -X POST -H \"Authorization: Bearer \$SUPERVISOR_TOKEN\" http://supervisor/addons/core_openthread_border_router/restart'" 2>&1 | tail -2

echo
echo "Wait OTBR leader..."
until ssh ha "docker exec app_core_openthread_border_router ot-ctl state 2>&1 | grep -q leader"; do sleep 3; done
echo "✅ OTBR leader"

echo
echo "Wait 15s for devices to re-register SRP..."
sleep 15

echo
echo "=== SRP entries post-restart ==="
ssh ha "docker exec app_core_openthread_border_router ot-ctl srp server service 2>&1"

echo
echo "✅ SRP cache cleared. Klar til ny commission attempt."
