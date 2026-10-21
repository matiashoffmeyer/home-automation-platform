#!/usr/bin/env bash
# =============================================================================
# Matter Commission Helper
# =============================================================================
# Wraps the full mobile-then-NUC pairing flow:
#   1. Verify pre-flight (run matter_preflight.sh)
#   2. Push Thread credentials to Matter Server (de wipes på restart)
#   3. Wait for user to start mobile commission attempt
#   4. Wait for "Can't reach device" failure
#   5. Catch device i CM=31 + commission via NUC network_only=True
#   6. Auto-rename device + entities
#
# Usage:
#   ./scripts/matter_commission.sh "MT:QDKT1-..." "parasoll_altandoer"
#
# Args:
#   $1  Matter QR code (MT:... format)
#   $2  Target entity prefix (e.g. parasoll_hoveddoer, entre_valhorn, parasoll_standby)
# =============================================================================

set -e
cd "$(dirname "$0")/.."
[ -f .env ] && . .env

CODE="$1"
PREFIX="$2"

if [ -z "$CODE" ] || [ -z "$PREFIX" ]; then
  echo "Usage: $0 <MT:QR-code> <entity_prefix>"
  echo "Example: $0 'MT:QDKT1E.N16G9VJ73A10' parasoll_altandoer"
  exit 1
fi

if [ -z "$HA_TOKEN" ]; then echo "❌ HA_TOKEN ikke sat"; exit 1; fi

echo "=== Step 1: Get Thread dataset TLV from HA ==="
TLV=$(ssh ha "HA_TOKEN='$HA_TOKEN' python3 -c \"
import asyncio,json,os,websockets
async def m():
  async with websockets.connect('ws://localhost:8123/api/websocket') as ws:
    await ws.recv()
    await ws.send(json.dumps({'type':'auth','access_token':os.environ['HA_TOKEN']}))
    await ws.recv()
    await ws.send(json.dumps({'id':1,'type':'thread/list_datasets'}))
    r=json.loads(await ws.recv())
    ds=[d for d in r.get('result',{}).get('datasets',[]) if d.get('preferred')]
    if not ds: print(''); return
    await ws.send(json.dumps({'id':2,'type':'thread/get_dataset_tlv','dataset_id':ds[0]['dataset_id']}))
    r=json.loads(await ws.recv())
    print(r.get('result',{}).get('tlv',''))
asyncio.run(m())
\"")

if [ -z "$TLV" ]; then
  echo "❌ Kunne ikke hente preferred Thread dataset TLV"
  exit 1
fi
echo "✅ TLV: ${TLV:0:40}... (${#TLV} chars)"

echo
echo "=== Step 2: Push Thread creds til Matter Server ==="
ssh ha "HA_TOKEN='$HA_TOKEN' python3 << PYEOF
import asyncio, json, websockets
async def main():
    async with websockets.connect('ws://172.30.32.1:5580/ws') as ws:
        await ws.recv()
        await ws.send(json.dumps({'message_id':'1','command':'set_thread_dataset','args':{'dataset':'$TLV'}}))
        await ws.recv()
        await ws.send(json.dumps({'message_id':'2','command':'server_info','args':{}}))
        r = await ws.recv()
        print('thread_creds_set:', '\"thread_credentials_set\": true' in r)
asyncio.run(main())
PYEOF"

echo
echo "=== Step 3: USER ACTION ==="
echo "1. Factory reset device: 4x kort klik → vent på pulserende LED"
echo "2. Læg device på Sonoff dongle (touching)"
echo "3. På telefon: HA Companion → Settings → Devices → Add → Matter → indtast/scan QR"
echo "4. Vent på mobile siger 'Can't reach device' (typisk ~60-90s)"
echo
read -p "Tryk ENTER når mobile har fejlet med 'Can't reach device' og device er på mesh i CM=31..."

echo
echo "=== Step 4: Verify device er commissionable i SRP ==="
ssh ha "docker exec app_core_openthread_border_router ot-ctl srp server service 2>&1" \
  | grep -B 1 -A 3 "_matterc" | grep "deleted: false" | head -1

echo
echo "=== Step 5: Fire NUC commission via Thread (network_only=True) ==="
RESULT=$(ssh ha "HA_TOKEN='$HA_TOKEN' python3 << PYEOF
import asyncio, json, websockets
async def main():
    async with websockets.connect('ws://172.30.32.1:5580/ws') as ws:
        await ws.recv()
        await ws.send(json.dumps({
            'message_id':'c',
            'command':'commission_with_code',
            'args':{'code':'$CODE','network_only':True}
        }))
        try:
            r = await asyncio.wait_for(ws.recv(), timeout=180)
            print(r[:500])
        except asyncio.TimeoutError:
            print('TIMEOUT')
asyncio.run(main())
PYEOF")

echo "$RESULT"

NODE_ID=$(echo "$RESULT" | grep -oE '"node_id":\s*[0-9]+' | head -1 | grep -oE '[0-9]+')
if [ -z "$NODE_ID" ]; then
  echo
  echo "❌ Commission failed. Tjek matter server logs:"
  echo "   ssh ha \"zsh -lc 'curl -s -H \\\"Authorization: Bearer \\\$SUPERVISOR_TOKEN\\\" http://supervisor/addons/core_matter_server/logs'\" | tail -30"
  echo
  echo "Hvis SRP entry er blevet stale: ./scripts/matter_clean_srp.sh"
  exit 1
fi

echo
echo "✅ Device commissioned: node_id=$NODE_ID"

echo
echo "=== Step 6: Rename device + entities ==="
ssh ha "HA_TOKEN='$HA_TOKEN' python3 << PYEOF
import asyncio, json, os, websockets
PREFIX = '$PREFIX'
async def main():
    async with websockets.connect('ws://localhost:8123/api/websocket') as ws:
        await ws.recv()
        await ws.send(json.dumps({'type':'auth','access_token':os.environ['HA_TOKEN']}))
        await ws.recv()
        await ws.send(json.dumps({'id':1,'type':'config/device_registry/list'}))
        r = json.loads(await ws.recv())
        # Find newest unrenamed Matter device
        dev = next((d for d in r.get('result',[]) if d.get('manufacturer') == 'IKEA of Sweden' and not d.get('name_by_user') and 'matter' in str(d.get('config_entries','')).lower() or any(c.startswith('matter') or len(c)==26 for c in d.get('config_entries',[]))), None)
        if not dev:
            # Fallback: find by model containing MYGGBETT/MYGGSPRAY
            dev = next((d for d in r.get('result',[]) if any(k in str(d.get('model','')).upper() for k in ['MYGGBETT','MYGGSPRAY','PRAKTLYSING']) and not d.get('name_by_user')), None)
        if not dev:
            print('❌ No new Matter device found'); return
        device_id = dev.get('id')
        print(f'Device: {dev.get(\"model\")} (id={device_id})')
        await ws.send(json.dumps({'id':2,'type':'config/device_registry/update','device_id':device_id,'name_by_user':PREFIX.replace('_',' ').title()}))
        await ws.recv()
        await ws.send(json.dumps({'id':3,'type':'config/entity_registry/list'}))
        r = json.loads(await ws.recv())
        ents = [e for e in r.get('result',[]) if e.get('device_id') == device_id]
        msg = 3
        for e in ents:
            old = e.get('entity_id')
            # Best-effort renaming
            for trigger in ['_door','_occupancy','_position','_current_position']:
                if old.startswith('binary_sensor.') and old.endswith(trigger):
                    new = f'binary_sensor.{PREFIX}'; break
                if old.startswith('cover.') and (old.endswith('_curtain') or '_position' in old):
                    new = f'cover.{PREFIX}'; break
            else:
                new = old
                for old_prefix in ['myggbett_door_window_sensor', 'myggspray_wrlss_mtn_sensor', 'praktlysing_curtain_motor']:
                    new = new.replace(old_prefix, PREFIX)
            if old == new: continue
            msg += 1
            await ws.send(json.dumps({'id':msg,'type':'config/entity_registry/update','entity_id':old,'new_entity_id':new}))
            r = json.loads(await ws.recv())
            ok = '✅' if r.get('success') else '❌'
            print(f'  {ok} {old} -> {new}')
asyncio.run(main())
PYEOF"

echo
echo "🎉 DONE. Verify: curl -s -H \"Authorization: Bearer \$HA_TOKEN\" \"http://homeassistant.local:8123/api/states/binary_sensor.$PREFIX\""
