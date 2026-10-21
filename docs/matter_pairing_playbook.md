# Matter-over-Thread Pairing Playbook

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

> **⭐ START HER I STEDET: [thread_pairing_drejebog.md](thread_pairing_drejebog.md)**
> — den skudsikre drejebog (2026-06-10) med engangs-forberedelse, URL-bug-
> workaround (#6367), 3 veje (telefon/NUC-BLE/Google-link) og fejltabel.
> Denne fil er nu reference for scripts + felt-rapporter.

Step-by-step procedure for adding new Matter devices (IKEA Myggbett, Myggspray, etc.)
to Home Assistant via Thread Border Router.

**Established 2026-05-05** efter long debugging session — denne playbook er den
proven recipe der virker reliable.

---

## Setup forudsætninger (one-time, allerede klar)

- ✅ **Sonoff ZBDongle-E** flashed med **OpenThread RCP firmware**
  (`zbdonglee_openthread_rcp_2.5.3.0_GitHub-1fceb225b_gsdk_2024.6.3_no_flow_460800.gbl`)
  via Silicon Labs Flasher addon. Plugget i NUC (USB 2.0 port + 0.6m forlænger).
- ✅ **OpenThread Border Router addon** kørende. Konfigureret med:
  - device: `/dev/serial/by-id/usb-Itead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_V2_*`
  - baudrate: 460800
  - flow_control: false
  - backbone_interface: wlp2s0 (Wi-Fi for fallback)
- ✅ **Matter Server addon** kørende (port 5580 internal).
- ✅ **HA OTBR integration** loaded med `source=otbr` dataset (border_agent_id linked).
- ✅ **HA Matter integration** loaded.
- ✅ **HA Thread integration** loaded med preferred dataset (`ha-thread-4187`).
- ✅ **Docker IPv6 enabled** (`ha docker options --enable-ipv6=true` + reboot).
- ✅ **HA Bluetooth integration** loaded (Intel-adapteren `hci1` — se advarslen
  nedenfor; den duer til passiv scanning, ikke til BLE-commissioning).
- ⚠️ **Matter-addon'ets `bluetooth_adapter_id` SKAL være `0`** — se
  "To BLE-adaptere" nedenfor. Verificér i addon-loggen:
  `docker logs app_core_matter_server 2>&1 | grep -a "Bluetooth commissioning enabled"`
- ✅ **Ethernet plugget i NUC** (kritisk for mDNS routing — Wi-Fi alone er ikke nok).

---

## Helper scripts

3 bash-scripts i `scripts/` automatiserer hele flow'et:

```bash
# 1. Verify stack health før commissioning (catcher dagens problemer på 30 sek)
./scripts/matter_preflight.sh

# 2. Full commission flow med auto-rename
./scripts/matter_commission.sh "MT:QDKT1E.N16G9VJ73A10" "parasoll_altandoer"

# 3. Hvis SRP cache har stale entries fra failed attempts
./scripts/matter_clean_srp.sh
```

`matter_preflight.sh` checker:
- NUC reachable + begge interfaces UP
- Docker IPv6 enabled
- OTBR Thread state = leader
- Sonoff dongle på rette path
- Thread dataset source=`otbr` (kritisk)
- Matter Server kørende + reachable
- mDNS broadcasts visible på LAN

Hvis nogen check fejler → STOP, fix issue. Det er præcis de problemer der spiste en hel dag 2026-05-05.

`matter_commission.sh` gør:
1. Henter Thread TLV fra HA's preferred dataset
2. Pusher creds til Matter Server (de wipes på restart!)
3. Venter på user starter mobile commission attempt
4. Venter på "Can't reach device" failure (forventet)
5. Fyrer NUC `commission_with_code network_only=True` (magic trick)
6. Auto-renamer device + entities til target prefix

`matter_clean_srp.sh` restarter OTBR addon → SRP cache cleared → devices re-registrerer fresh. Brug efter multiple failed attempts har akkumuleret stale entries.

---

## Per-pairing playbook (~3-4 min per device, manual variant)

Hvis du vil køre flow'et manuelt i stedet for via helper script (debug-purpose), følg disse 7 steps:

### Step 1 — Device prep (USER)

1. **Factory reset device:**
   - IKEA Myggbett/Myggspray: **4x kort klik** på reset-knap
   - Vent på pulse-LED (gul for Myggbett, hvid for Myggspray)
2. **Læg device på Sonoff Thread donglen** (touching = best RSSI under commissioning)
3. **Forbered QR-kode/setup code** — `MT:...` format eller `XXXX-XXX-XXXX` digits

### Step 2 — Mobile commission attempt (USER)

Mobile commissioning bruges til at få device på Thread mesh — ikke fordi det
færdiggør, men fordi mobilens BLE er mere reliable end NUC's interne BT.

1. Åbn **HA Companion app**
2. Settings → Devices & Services → "+ Add Integration" → **Matter (Beta)**
3. Scan QR-kode (eller indtast `MT:...` manuelt)
4. Forvent: efter ~60-90s vil mobile sige **"Can't reach device"** ELLER
   "Setting up..." der hænger
5. **Det er forventet og OK** — device er nu på Thread mesh men ikke commissioned
   til HA's fabric (heller ikke til Google's fabric typisk, hvis mobile failer).

> **Hvis mobile lykkedes** (uventet): device er i Google's fabric. Se "Recovery
> from Google fabric" sektionen nederst.

### Step 3 — Verificer device er på Thread mesh + commissionable (CLAUDE)

```bash
docker exec app_core_openthread_border_router ot-ctl srp server service 2>&1 \
  | grep -B 1 -A 6 "_matterc\|CM=31"
```

> **Container-navnene er `app_core_*`, ikke `addon_core_*`** (verificeret
> 2026-08-21 med `docker ps --format '{{.Names}}'`). Kører du PÅ HA-hosten —
> hvilket vi gør, `/homeassistant` == `/config` — skal der ikke `ssh ha` foran.

Forvent at se:
```
{HASH}._matterc._udp.default.service.arpa.
    deleted: false
    subtypes: _V4476,_S{X},_L{DISCRIMINATOR},_CM
    TXT: ... CM=31, D={DISCRIMINATOR_DEC} ...
    host: {DEVICE_EXT_MAC}.default.service.arpa.
    addresses: [fd6d:ac87:0485:1:....]
```

`CM=31` (= "1" hex) betyder **commissionable mode** = klar til commission.

**Hvis stale entries fra tidligere forsøg** (multiple `_matterc` for samme
discriminator):
```bash
# Restart OTBR for at clear SRP cache
ssh ha "zsh -lc 'curl -s -X POST -H \"Authorization: Bearer \$SUPERVISOR_TOKEN\" \
  http://supervisor/addons/core_openthread_border_router/restart'"
# Vent ~30 sek på OTBR leader + device re-registrerer
```

### Step 4 — Push Thread credentials til Matter Server (CLAUDE)

⚠️ **KRITISK**: Matter Server's Thread credentials er **IKKE persistent** —
de wipes hver gang Matter Server addon restartes. Push altid før commission.

```bash
ssh ha "HA_TOKEN='dummy' python3 << 'PYEOF'
import asyncio, json, websockets
TLV = '0e08...{TLV_HEX}...f7f8'  # fra `thread/get_dataset_tlv` for ha-thread-4187
async def main():
    async with websockets.connect('ws://172.30.32.1:5580/ws') as ws:
        await ws.recv()
        await ws.send(json.dumps({'message_id':'1','command':'set_thread_dataset','args':{'dataset':TLV}}))
        await ws.recv()
        await ws.send(json.dumps({'message_id':'2','command':'server_info','args':{}}))
        r = await ws.recv()
        print('thread_creds_set:', '\"thread_credentials_set\": true' in r)
asyncio.run(main())
PYEOF"
```

For at få current TLV:
```bash
. .env && curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://homeassistant.local:8123/api/services/websocket_api/list_datasets"
```
(eller via WS API `thread/get_dataset_tlv`)

### Step 5 — Fire NUC commission via Thread (CLAUDE)

Det er **det magiske trick** der reliable fuldfører commissioning. `network_only=True`
betyder "skip BLE, brug kun mDNS/Thread/IPv6".

```bash
ssh ha "HA_TOKEN='dummy' python3 << 'PYEOF'
import asyncio, json, websockets
async def main():
    async with websockets.connect('ws://172.30.32.1:5580/ws') as ws:
        await ws.recv()
        await ws.send(json.dumps({
            'message_id':'c',
            'command':'commission_with_code',
            'args':{'code':'MT:QDKT...','network_only':True}
        }))
        r = await asyncio.wait_for(ws.recv(), timeout=120)
        print(r[:1500])
asyncio.run(main())
PYEOF"
```

**Forventes:** `result: {node_id: {N}, available: true, attributes: {...}}` inden 30-90 sek.

### Step 6 — Find + rename entities (CLAUDE)

Default entity names er ulæselige (fx `binary_sensor.myggbett_door_window_sensor_door`).
Rename til konventionen i `entities/sensors/valhorn.yaml`:

```bash
. .env && ssh ha "HA_TOKEN='$HA_TOKEN' python3 << 'PYEOF'
import asyncio, json, os, websockets
TARGET_PREFIX = 'parasoll_hoveddoer'  # eller _altandoer, _badevaerelse, _standby
async def main():
    async with websockets.connect('ws://localhost:8123/api/websocket') as ws:
        await ws.recv()
        await ws.send(json.dumps({'type':'auth','access_token':os.environ['HA_TOKEN']}))
        await ws.recv()
        # Find newest unrenamed Myggbett device
        await ws.send(json.dumps({'id':1,'type':'config/device_registry/list'}))
        r = json.loads(await ws.recv())
        dev = next((d for d in r.get('result',[]) if 'myggbett' in str(d.get('model','')).lower() and not d.get('name_by_user')), None)
        if not dev:
            print('No new device found')
            return
        device_id = dev.get('id')
        # Rename device
        await ws.send(json.dumps({
            'id':2,'type':'config/device_registry/update',
            'device_id':device_id,'name_by_user':f'Myggbett {TARGET_PREFIX}'
        }))
        await ws.recv()
        # Rename entities
        await ws.send(json.dumps({'id':3,'type':'config/entity_registry/list'}))
        r = json.loads(await ws.recv())
        ents = [e for e in r.get('result',[]) if e.get('device_id') == device_id]
        msg = 3
        for e in ents:
            old = e.get('entity_id')
            if old.startswith('binary_sensor.') and old.endswith('_door'):
                new = f'binary_sensor.{TARGET_PREFIX}'
            else:
                new = old.replace('myggbett_door_window_sensor', TARGET_PREFIX)
            if old == new:
                continue
            msg += 1
            await ws.send(json.dumps({'id':msg,'type':'config/entity_registry/update','entity_id':old,'new_entity_id':new}))
            await ws.recv()
            print(f'  {old} -> {new}')
asyncio.run(main())
PYEOF"
```

### Step 7 — Verificer device i HA

```bash
. .env && curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://homeassistant.local:8123/api/states/binary_sensor.{TARGET_PREFIX}"
```

Forvent state on/off + device_class door/opening.

---

## 🔥 Felt-rapport 2026-06-10: KAJPLATS bad-spots (1 succes, ~90 fejl)

Hård dag: spot 1 (KAJPLATS GU10, node 75) paret efter 3 forsøg; spot 2+3
opgivet efter ~90 forsøg. Komplet obduktion — læs FØR næste pairing-session.

### ✅ Hvad der VIRKEDE (spot 1's succesopskrift)

1. **Ren NUC-BLE commissioning** — `commission_with_code` UDEN `network_only`
   (Matter-serveren bruger NUC'ens hci0 direkte). Ingen telefon involveret.
2. **Timing:** succes kom ~40 min efter frisk NUC-boot (BT-chip endnu rask)
   og indenfor pærens ~15-min annoncerings-vindue efter 6× reset.
3. **Auto-retry-loop** via Matter-server WS (3-12 forsøg, 240s timeout per
   forsøg, 5-10s pause) — succes på 3. forsøg. Enkeltskud er spild.
4. **Sekvensen:** Matter-server restart → re-push Thread-creds (de wipes!) →
   armér loop → DEREFTER 6× reset af pæren → hænderne væk.
5. **Telefon-BT slukket** (eller telefon helt væk) under hele forløbet.

### ❌ Hvad der IKKE virkede (og hvorfor)

| Symptom | Årsag | Bevis |
|---|---|---|
| HA-app "Can't reach device" ×5+ | Google-stack commissioner først til Google-fabric; HA-handover fejler (Tailscale-app-URL pre-fix + NUC-BLE) → pære fanget på fremmed fabric, annoncerer ikke | `A360F32F...`-records i SRP (fremmed fabric), `_matterc deleted: true` |
| "Discovery timed out" trods annoncerende pære | `bluetoothctl scan`-diagnostik lagde pæren i BlueZ-cache → CHIP-scanner ser kun NYE enheder | Host så adv (FFF6, disc 0x303); Matter-server: 0 discoveries |
| "Method Connect doesn't exist" (GDBus) | BlueZ DBus-objekter rådner efter mange scan-cyklusser | Kom igen efter hver ~10 forsøg; matter-server-restart kurerer midlertidigt |
| "ATT error 0x0e" / "Remote closed BLE" | Telefonens Google-stack prikkede til pæren parallelt (1 BLE-slot) + flaky Intel-chip | Google Home-prompt på tlf samtidig |
| PASE crypto-fejl (CHIPCryptoPAL) | BEGGE KAJPLATS-koder har short discriminator 3 → scanner rammer forkert pære når begge er strømsat | Decoded: 0647→disc 3, 0622→disc 3, pære-adv 0x303 |
| Kernel: "Unexpected start frame" | NUC'ens Intel-BT-chip korrumperer HCI-frames over tid | dmesg; 0 fejl efter host-reboot |

### 📜 Regler udledt (følg dem slavisk næste gang)

1. **ÉN uparret Matter-pære med strøm ad gangen** (discriminator-kollision).
2. **Telefon-BT SLUKKET** — Google-prompten er en aktiv saboteur.
3. **ALDRIG bluetoothctl-scans under commissioning** (cache-forgiftning).
   Skal du diagnosticere: `bluetoothctl remove <mac>` bagefter.
4. **Re-push Thread-creds efter HVER matter-server-restart.**
5. **Frisk host-reboot = 40-min gyldent vindue** for NUC-BLE. Udnyt det.
6. **6× reset-kvittering (fade) er obligatorisk** — ingen fade = intet reset
   = pæren annoncerer ikke (især hvis den sidder fanget på Google-fabric).
7. Fejler NUC-BLE alligevel: **Google Home multi-admin link** (telefonens BLE
   + Thread-handover, nul NUC-BLE) eller **USB-BT-dongle** til NUC'en.
8. Innr/Zigbee-pærer fader OGSÅ ved 6× reset — forveksl dem ikke med KAJPLATS
   (kostede ~30 forsøg mod en pære der slet ikke var Matter).

## Common gotchas + recovery

### "Commission with code failed" på første attempt

**Sandsynlig årsag:** Mobile har commissioned device til Google's fabric.

**Fix:**
1. **Factory reset device** (4x kort klik) — clears Google fabric
2. **Ny mobile commission attempt** — bør fejle ved "Can't reach device" denne gang
3. **NUC `network_only=True`** — fanger device i CM=31 vinduet

### "TIMEOUT" eller stale SRP entries

**Sandsynlig årsag:** Multiple commissioning attempts har efterladt stale SRP
entries. Matter Server vælger gammel IPv6 → unreachable.

**Fix:**
```bash
# Restart OTBR — clears SRP cache, devices re-registrerer fresh
ssh ha "zsh -lc 'curl -s -X POST -H \"Authorization: Bearer \$SUPERVISOR_TOKEN\" \
  http://supervisor/addons/core_openthread_border_router/restart'"
```

### "Required network information not provided" + "thread (no)"

**Sandsynlig årsag:** Matter Server's `thread_credentials_set` er false.

**Signatur:** commissioning når HELE vejen gennem attestation og dør først på
`SendNOC` med `AutoCommissioner.cpp:305: CHIP Error 0x0000002F: Invalid
argument`. Beviset står to linjer nede i addon-loggen og er utvetydigt:

```
Parameters supplied: wifi (no) thread (no)
Device supports:     wifi (no) thread(yes)
```

**Fix:** Push Thread dataset via `set_thread_dataset` (Step 4 ovenfor). Husk
Matter Server wipes credentials på restart — push igen efter hver restart.
Det gælder OGSÅ en restart du selv lige har lavet for at nulstille BLE-stakken;
kommandoen hedder `set_thread_dataset` (ikke `set_thread_operational_dataset`,
som er python-metodens navn). TLV'en hentes uden om HA med:

```bash
docker exec app_core_openthread_border_router ot-ctl dataset active -x
```

### "BLE ack recv timeout" eller "le-connection-abort-by-local"

**Signatur (målt 2026-08-21):** BLE-scanningen FINDER enheden, PASE lykkes, og
stage-maskinen dør så konsekvent på `ConfigureTCAcknowledgments ->
SendPAICertificateRequest` med `CHIP Error 0x00000032: Timeout` — ~30 s pr.
forsøg, identisk hver gang. Det er ikke pæren: PASE er små pakker, mens
PAI-certifikatet skal fragmenteres over BTP, og en dårlig radio taber
fragmenterne. **Skift ALDRIG pæren i fabriksreset (6×) på det her mønster** —
at PASE lykkes beviser at den står i parringstilstand med den rigtige kode.

**To BLE-adaptere, og de er ikke lige gode:**

| | MAC | Duer til commissioning |
|---|---|---|
| `hci0` | `FB:69:F4:31:2E:61` | ✅ USB-dongle — **brug denne** |
| `hci1` | `52:AF:C5:8A:62:27` | ❌ Intel i NUC'en, og HA's egen bluetooth-integration deler den |

Indekserne er IKKE i den rækkefølge man gætter (donglen er `hci0`), og
`bluetoothctl list` viser kun MAC + alias, ikke hci-nummeret. Slå det op:

```bash
dbus-send --system --print-reply --dest=org.bluez / \
  org.freedesktop.DBus.ObjectManager.GetManagedObjects \
  | grep -aE 'object path "/org/bluez/hci[0-9]+"|string "Address"' -A3
```

**Fix:** sæt addon-optionen og genstart:

```bash
curl -s -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" -H "Content-Type: application/json" \
  -d '{"options":{"log_level":"debug","log_level_sdk":"detail","beta":false,"enable_test_net_dcl":false,"bluetooth_adapter_id":0}}' \
  http://supervisor/addons/core_matter_server/options
curl -s -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  http://supervisor/addons/core_matter_server/restart
```

Med donglen kører hele attestation-kæden igennem på ~4 s. Virker det stadig
ikke, er afstand næste mistanke — BLE bruges KUN under parringen, så pæren kan
skrues i en lampe tæt på NUC'en, pares dér og flyttes tilbage bagefter
(credentials ligger i pærens NVRAM).

### IKEA GRILLPLATS: håndtryk OK, derefter tavshed (2026-09-23)

**Signatur:** `Received Matter handshake response: 656c04f10005` → 15 s →
`Acknowledgement for the sent sequence number was not received ... disconnect`
(matter.js) / `PASESession timed out ... Expected message type was 33`
(CHIP-SDK). Pluggen svarer aldrig på PBKDFParamRequest. Afprøvet uden held:
CSR + Intel, matter.js + CHIP-SDK (midlertidig `python-matter-server`-container
på port 5581, `--network host -v /run/dbus:/run/dbus:ro`, Matter-addon'et
genstartet UDEN `bluetooth_adapter_id` så donglen frigives), < 1 m, factory
reset, HA-BT-integration slået fra. **Stop efter 2 forsøg** — se
permanente_fakta og B159. **Løsning (2026-09-23): telefon-flowet, efter
OTBR-backbone-fixet øverst i [thread_pairing_drejebog.md](thread_pairing_drejebog.md).** matter.js cacher desuden den gamle BLE-adresse efter
en strømcyklus (`Timeout while connecting to peripheral <gammel MAC>`) →
genstart addon'et før et nyt forsøg.

**NB om `stop`:** HA's Matter-integration STARTER addon'et igen inden for ~20 s.
Skal donglen frigives, så fjern `bluetooth_adapter_id` fra options og genstart.

### "Cannot assign requested address" (mDNS errors)

**Sandsynlig årsag:** Matter Server prøver at broadcast mDNS på en interface
der er nede (fx Ethernet pulled while Matter Server running).

**Fix:**
1. Sæt Ethernet kablet i (begge interfaces UP)
2. Restart Matter Server addon
3. Push Thread creds igen (de wipes på restart)
4. Retry commission

### Mobile siger "Your device requires a Thread border router"

**Sandsynlig årsag:** Thread dataset i HA har source=`manual` i stedet for
`otbr`. Android Matter stack nægter at sync credentials uden source=`otbr`.

**Fix:** Verify `source=otbr` på preferred dataset:
```bash
ssh ha "HA_TOKEN='$HA_TOKEN' python3 -c \"
import urllib.request, json, os
url = 'http://localhost:8123/api/services/websocket_api/...'  # via WS thread/list_datasets
\""
```

Hvis source=manual: gå til Settings → Devices & Services → OpenThread Border
Router → "Create network" via UI (HA opretter dataset med source=otbr).

### Recovery from Google fabric

Hvis device endte i Google's fabric (mobile lykkedes uventet) og du vil have
det i HA:

**Option A — Factory reset + retry** (enklest):
1. Factory reset device (4x kort klik)
2. Følg standard playbook fra Step 1

**Option B — Multi-fabric add via Google Home** (device i BÅDE Google + HA):
1. Åbn Google Home app
2. Find device → settings → "Linked services" / "Use with another platform"
3. Generer 21-cifret pairing code (15 min gyldig)
4. I HA Companion: Settings → Devices & Services → Matter → Add device →
   indtast 21-cifret kode
5. HA tilføjer device til SIN fabric (multi-fabric)

---

## Bekræftet pattern — hvad virkede 2026-05-05

| Device | Path | Result |
|---|---|---|
| Myggbett 1 (hoveddor) | NUC BLE retry → mesh-join → network_only=True | ✅ |
| Myggspray (entré) | Mobile fail → SRP CM=31 → NUC network_only=True | ✅ |
| Myggbett 2 (standby) | Mobile fail → factory reset → mobile fail → SRP CM=31 → NUC network_only=True | ✅ |
| Myggbett 3 (standby_2) | Mobile fail → factory reset → mobile fail → SRP CM=31 → NUC network_only=True | ✅ |

**Konklusionen:** mobile-then-NUC er den proven recipe. Plus factory-reset hvis
mobile lykkedes uventet (dummy commissioned to Google).

---

## Naming convention (per `entities/sensors/valhorn.yaml`)

| Placering | Entity prefix |
|---|---|
| Hoveddør | `parasoll_hoveddoer` |
| Altandør | `parasoll_altandoer` |
| Badeværelse-dør | `parasoll_badevaerelse` |
| Standby (uplaceret) | `parasoll_standby` / `parasoll_standby_2` etc. |
| Entré motion | `entre_valhorn_*` (Myggspray) |
| Terrasse motion | `terrasse_valhorn_*` (planned) |

For Myggspray (motion + lux):
- `binary_sensor.{rum}_valhorn_occupancy` (motion)
- `sensor.{rum}_valhorn_illuminance` (lux)
- `sensor.{rum}_valhorn_battery` (%)
- `sensor.{rum}_valhorn_battery_voltage`

For Myggbett (door):
- `binary_sensor.{prefix}` (door open/close — main sensor)
- `sensor.{prefix}_battery` (%)

---

## Reference data

- **Thread network**: `ha-thread-4187`, channel 15, PAN ID 0xfd6c
- **HA fabric ID**: `0x2`, compressed `BB335B2CA03048E7`
- **OTBR REST API**: `http://172.30.32.1:8081`
- **Matter Server WS**: `ws://172.30.32.1:5580/ws`
- **Matter Server UI** (browser via SSH tunnel): `http://localhost:5580`
