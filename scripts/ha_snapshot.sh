#!/usr/bin/env bash
# =============================================================================
# HA State Snapshot — for refactor verification
# =============================================================================
# Phase 0 værktøj fra refactor-plan. Dump current HA state til JSON så vi kan
# verify "ingen ændring i adfærd" efter refactor commits.
#
# Workflow:
#   1. ./scripts/ha_snapshot.sh > before.json     # FØR refactor
#   2. <gør refactor + deploy>
#   3. ./scripts/ha_snapshot.sh > after.json      # EFTER refactor
#   4. ./scripts/ha_snapshot.sh diff before.json after.json
#
# Snapshot indeholder:
#   - Alle entity_id + state + last_changed
#   - Alle automation last_triggered + state
#   - Alle input_boolean/input_select/input_number values
#   - Activity_state + house_state + house_mode
#
# Usage:
#   ./scripts/ha_snapshot.sh                    # dump til stdout (JSON)
#   ./scripts/ha_snapshot.sh > before.json      # dump til fil
#   ./scripts/ha_snapshot.sh diff a.json b.json # compare two snapshots
# =============================================================================

set -e
cd "$(dirname "$0")/.."
[ -f .env ] && . .env

if [ -z "$HA_TOKEN" ]; then
  echo "❌ HA_TOKEN ikke sat. Tjek .env" >&2
  exit 1
fi

if [ "$1" = "diff" ]; then
  if [ -z "$2" ] || [ -z "$3" ]; then
    echo "Usage: $0 diff <before.json> <after.json>" >&2
    exit 1
  fi
  python3 - "$2" "$3" <<'PYEOF'
import json, sys
a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
ai = {s['entity_id']: s for s in a['states']}
bi = {s['entity_id']: s for s in b['states']}

added = set(bi) - set(ai)
removed = set(ai) - set(bi)
changed_state = []
changed_attrs = []

for eid in set(ai) & set(bi):
    if ai[eid]['state'] != bi[eid]['state']:
        changed_state.append((eid, ai[eid]['state'], bi[eid]['state']))
    if ai[eid].get('attributes') != bi[eid].get('attributes'):
        changed_attrs.append(eid)

print(f"=== Snapshot Diff ===")
print(f"Before: {a['timestamp']}  ({len(ai)} entities)")
print(f"After:  {b['timestamp']}  ({len(bi)} entities)")
print()
print(f"Added entities ({len(added)}):")
for e in sorted(added)[:20]: print(f"  + {e}")
if len(added) > 20: print(f"  ... and {len(added)-20} more")
print()
print(f"Removed entities ({len(removed)}):")
for e in sorted(removed)[:20]: print(f"  - {e}")
if len(removed) > 20: print(f"  ... and {len(removed)-20} more")
print()
print(f"State changed ({len(changed_state)}):")
# Filter out routinely-changing entities (sensors, etc.) for cleaner output
critical = [c for c in changed_state if not any(k in c[0] for k in ['_apollo_','_battery','_rssi','_uptime','_temperature','_lux','_pressure','_uv_index','_radar','_g0_','_g1_','_g2_','_g3_','_g4_','_g5_','_g6_','_g7_','_g8_'])]
for eid, s1, s2 in critical[:30]:
    print(f"  ~ {eid}: {s1} -> {s2}")
if len(critical) > 30: print(f"  ... and {len(critical)-30} more critical")
non_critical = len(changed_state) - len(critical)
if non_critical > 0:
    print(f"  (+ {non_critical} sensor/measurement changes filtered out — expected)")
print()
print(f"Attributes changed: {len(changed_attrs)}")
if any(c['state'] != c['state'] for c in []):  # placeholder for nontrivial
    pass
PYEOF
  exit 0
fi

# Generate fresh snapshot
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SNAPSHOT_OUTPUT=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://homeassistant.local:8123/api/states" \
  | python3 -c "
import json, sys, datetime
states = json.load(sys.stdin)
# Sort + canonicalize
states.sort(key=lambda s: s['entity_id'])
out = {
    'timestamp': '$TS',
    'count': len(states),
    'states': [{
        'entity_id': s['entity_id'],
        'state': s['state'],
        # Drop volatile attributes (timestamps, contexts) for clean diff
        'attributes': {k: v for k, v in s.get('attributes', {}).items()
                       if k not in ('last_triggered', 'last_changed', 'context', 'editable', 'friendly_name')},
    } for s in states],
}
print(json.dumps(out, indent=2, sort_keys=True))
")

# Side-effect: write to .cache/snapshot_latest.json (Blok A pre-push fallback).
# Pre-push hook reads denne hvis HA er unreachable (du arbejder offline).
mkdir -p .cache
echo "$SNAPSHOT_OUTPUT" > .cache/snapshot_latest.json

# Print snapshot to stdout (preserve original behavior for redirect)
echo "$SNAPSHOT_OUTPUT"
