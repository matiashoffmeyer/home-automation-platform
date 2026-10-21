#!/usr/bin/env bash
# =============================================================================
# Matter Pre-Flight Check
# =============================================================================
# Verificer at Thread/Matter stack er healthy FØR commissioning af nyt device.
# Catcher de problemer der spiste en hel dag 2026-05-05.
#
# Usage: ./scripts/matter_preflight.sh
# =============================================================================

set -e
cd "$(dirname "$0")/.."

# Load HA_TOKEN from .env
[ -f .env ] && . .env

if [ -z "$HA_TOKEN" ]; then
  echo "❌ HA_TOKEN ikke sat. Tjek .env"
  exit 1
fi

echo "=== Thread/Matter Pre-Flight Check ==="
echo

PASS=0
FAIL=0
check() {
  local label="$1"
  local cmd="$2"
  local expect="$3"
  local actual=$(eval "$cmd" 2>/dev/null)
  if echo "$actual" | grep -qE "$expect"; then
    echo "✅ $label"
    PASS=$((PASS+1))
  else
    echo "❌ $label"
    echo "   Expected: $expect"
    echo "   Got: $actual"
    FAIL=$((FAIL+1))
  fi
}

# 1. NUC reachable
check "NUC reachable via SSH" \
  "ssh -o ConnectTimeout=5 ha 'echo ok' 2>/dev/null" \
  "ok"

# 2. Both network interfaces UP (kritisk for mDNS)
check "Ethernet (enp0s25) UP med IP" \
  "ssh ha 'ip -4 addr show enp0s25 2>/dev/null'" \
  "inet 192"

check "Wi-Fi (wlp2s0) UP med IP (fallback)" \
  "ssh ha 'ip -4 addr show wlp2s0 2>/dev/null'" \
  "inet 192"

# 3. Docker IPv6 enabled
check "Docker IPv6 enabled" \
  "ssh ha \"zsh -lc 'curl -s -H \\\"Authorization: Bearer \\\$SUPERVISOR_TOKEN\\\" http://supervisor/docker/info'\"" \
  '"enable_ipv6":true'

# 4. OTBR addon kørende + Thread leader
check "OTBR addon Thread state = leader" \
  "ssh ha 'docker exec app_core_openthread_border_router ot-ctl state 2>&1'" \
  "leader"

# 5. Sonoff dongle på rette path
check "Sonoff dongle på /dev/serial/by-id" \
  "ssh ha 'ls /dev/serial/by-id/ | grep Itead'" \
  "Itead_Sonoff_Zigbee"

# 6. Thread dataset source=otbr (kritisk for mobile sync)
check "Thread dataset source=otbr (preferred)" \
  "ssh ha \"HA_TOKEN='$HA_TOKEN' python3 -c \\\"
import asyncio,json,os,websockets
async def m():
  async with websockets.connect('ws://localhost:8123/api/websocket') as ws:
    await ws.recv()
    await ws.send(json.dumps({'type':'auth','access_token':os.environ['HA_TOKEN']}))
    await ws.recv()
    await ws.send(json.dumps({'id':1,'type':'thread/list_datasets'}))
    r=json.loads(await ws.recv())
    for d in r.get('result',{}).get('datasets',[]):
      if d.get('preferred'):print('source=' + d.get('source','?'))
asyncio.run(m())
\\\"\"" \
  "source=otbr"

# 7. Matter Server running
check "Matter Server addon kørende" \
  "ssh ha 'docker ps --filter name=matter_server --format {{.Status}}'" \
  "Up"

# 8. Matter Server reachable via WS
check "Matter Server WS endpoint reachable" \
  "ssh ha 'curl -s --max-time 3 http://172.30.32.1:5580/ 2>&1'" \
  "Python Matter Server"

# 9. mDNS broadcasts visible på LAN (kritisk for mobile commissioning)
check "OTBR mDNS _meshcop visible" \
  "ssh ha \"python3 -c 'import socket,struct;sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,4);sock.settimeout(3);q=struct.pack(\\\"!HHHHHH\\\",0,0,1,0,0,0)+b\\\"\\x08_meshcop\\x04_udp\\x05local\\x00\\x00\\x0c\\x00\\x01\\\";sock.sendto(q,(\\\"224.0.0.251\\\",5353));d,_=sock.recvfrom(4096);print(b\\\"Home Assistant\\\" in d)'\"" \
  "True"

# 10. SRP cache fri for stale entries (info only)
echo
echo "--- SRP Server entries (info, ikke pass/fail) ---"
ssh ha "docker exec app_core_openthread_border_router ot-ctl srp server service 2>&1" \
  | grep -E "^[A-F0-9]+\..*matter|deleted: false|host:|D=|CM=" | head -20

echo
echo "=== Result: $PASS passed, $FAIL failed ==="
if [ $FAIL -gt 0 ]; then
  echo "🚫 STOP — fix issues før commissioning. Se docs/matter_pairing_playbook.md."
  exit 1
fi
echo "✅ Stack ready for commissioning. Brug ./scripts/matter_commission.sh"
