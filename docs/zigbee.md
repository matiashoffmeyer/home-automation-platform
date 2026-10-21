# Zigbee — Nabu Casa ZBT-2 Coordinator

Authoritative reference for the Zigbee stack. Values extracted from the
running HA instance (ZHA config entry `01KN9E1XNA0E19B99YAQ33EE3X`).

## Coordinator hardware

| Field | Value |
|---|---|
| **Device** | Home Assistant Connect ZBT-2 (Nabu Casa ZBT-2) |
| **Manufacturer** | Nabu Casa |
| **Product** | ZBT-2 - Nabu Casa ZBT-2 |
| **Serial** | `911599ED786C` |
| **VID:PID** | `303A:831A` |
| **USB path (by-id)** | `/dev/serial/by-id/usb-Nabu_Casa_ZBT-2_911599ED786C-if00` |

The `by-id` path is stable across reboots and should always be used —
never reference `/dev/ttyUSB*` or `/dev/ttyACM*` directly.

## Radio configuration

| Field | Value |
|---|---|
| **Radio type** | `ezsp` |
| **Firmware** | `7.5.1.0 build 0 (20260224005837)` |
| **Baudrate** | `460800` |
| **Flow control** | `hardware` |
| **Integration** | ZHA (not Zigbee2MQTT) |
| **Config entry ID** | `01KN9E1XNA0E19B99YAQ33EE3X` |
| **Network EPID** | `0b:09:f1:e1:72:39:e0:26` |

## ZHA setup from scratch (disaster recovery)

If HA is rebuilt from a fresh HAOS image:

1. Plug the ZBT-2 into a USB port on the NUC.
2. In HA: **Settings → Devices & Services → Add Integration → ZHA**.
3. Select the device at `/dev/serial/by-id/usb-Nabu_Casa_ZBT-2_911599ED786C-if00`.
4. Radio type: **EZSP**. Baudrate: **460800**. Flow control: **Hardware**.
5. Restore the network from the most recent backup to preserve device
   pairings — ZHA stores its network key in `.storage/core.restore_state`
   and the Zigbee DB at `zigbee.db`. A full HAOS backup restore is the
   simplest path.

## Devices paired through this coordinator

As of the current running system:

| Device | Manufacturer | Model | Zigbee IEEE |
|---|---|---|---|
| Valhorn 1 | IKEA of Sweden | VALLHORN Wireless Motion Sensor | `fd:00:ad:46:6a:93:29:a8` |

All other devices in the apartment layout (other Vallhorns, Parasolls,
Somrigs, IKEA curtains, Hue Lily, etc.) are on the roadmap but have not
yet been paired — see `README.md` and `docs/apartment_layout.yaml` for
the full planned inventory.

## Notes

- **DUAL RADIO setup live siden 2026-05-05**: ZBT-2 (Zigbee) + Sonoff
  ZBDongle-E (Thread/Matter, OpenThread RCP firmware). Begge plugged in.
- **Thread network**: `ha-thread-4187`, channel 15, PAN 0xfd6c. Border
  Router via OpenThread Border Router addon. Matter Server addon (8.4.0)
  + Matter integration auto-discovered med bluetooth_adapter_id=0.
- **4 Matter devices commissioned via Thread**: 3× Myggbett door (1
  hoveddør, 2 standby) + 1× Myggspray motion (entré).
- **Commissioning playbook**: see [docs/matter_pairing_playbook.md](matter_pairing_playbook.md).
  Magic-trick procedure: mobile commission attempt joiner Thread mesh,
  NUC `commission_with_code network_only=True` finishe via Thread/UDP.
- **IKEA curtains** (planlagt post-flyt): vil joine Thread mesh direkte
  via Matter-over-Thread. Ingen DIRIGERA hub kræves.

## Mesh-fejl recovery decision tree (A3)

Hvis Zigbee mesh er ustabilt — efter flytning, post-strom-svigt, eller
random — så følg dette træ. Hvert trin tager 5-30 min. Eskaler kun hvis
forrige trin ikke løste det.

### Symptomer på mesh-fejl

- Flere devices viser `unavailable` i ZHA → Devices uden tydelig årsag
- `binary_sensor.depot_valhorn_occupancy` (eller andre battery-devices)
  reagerer langsomt eller slet ikke
- Lights tager 5-10 sek at reagere på Styrbar-tryk
- ZHA logs viser "device did not acknowledge" / "no response"

### Trin 1: Flyt ZBT-2 til central placering (5 min)

ZBT-2 er Zigbee-koordinator — alt går igennem den. Hvis den står i et hjørne
eller bag noget metal er mesh svag.

1. Træk ZBT-2 USB-stikket ud af NUC.
2. Sæt et **USB-extension-kabel** (1-2 meter) fra NUC til ZBT-2.
3. Placér ZBT-2 ud i åbent rum, gerne lidt højt (på en hylde i stuen).
4. Vent 5 min for at devices kan re-forhandle mesh-routes.
5. Tjek ZHA → Devices: stadig unavailable?

### Trin 2: Re-pair de 3 nærmeste mains-powered routere (15 min)

Mains-powered Innr/Tradfri pærer fungerer som Zigbee-routere — de hop
batteri-devices' beskeder videre. Hvis disse er ustabile dør hele mesh.

1. Identificer 3 mains-powered devices nærmest ZBT-2:
   - Sandsynligt: stue_loft, spisestue_pendel, koekken_loft
2. For hver: ZHA → Devices → vælg device → "Reconfigure". Vent på success.
3. Hvis Reconfigure fejler: unpair + repair (ZHA → Add Device → tænd/sluk
   device 6 gange hurtigt for at sætte i pairing-mode).
4. Vent 10 min. Re-tjek device-status.

### Trin 3: Power-cycle alle Zigbee-devices (10 min)

Tag stikket ud af alle mains-powered Zigbee devices i 30 sek, sæt i igen.
For battery devices: tag batteri ud, vent 30 sek, sæt i igen.

Devices vil rejoine mesh sekventielt. Vent 15 min efter sidste device.

### Trin 4: Factory-reset + restore fra backup (30 min — sidste udvej)

Hvis mesh stadig er broken efter trin 1-3:

1. Sluk alle Zigbee-devices.
2. **TAGE BACKUP FØRST** — sørg for HA-backup er current (Settings → System
   → Backups). Download til USB/laptop.
3. ZHA → Configure → Migrate Radio → eller "Reset Network" (irreversibelt).
4. Re-add ZHA integration: USB path
   `/dev/serial/by-id/usb-Nabu_Casa_ZBT-2_911599ED786C-if00`,
   radio type EZSP, baudrate 460800, flow control hardware.
5. Re-pair devices én ad gangen, start med mains-powered routere nærmest
   ZBT-2. Brug `entities/device_inventory.yaml` som checklist.
6. Verificer hver device's IEEE matcher hvad der er i automations/.
   Hvis IEEE ændrede sig (kan ske ved fuld reset): opdater automations/.
7. Forventet tid: 30 min for mains-devices + 30 min for batteries.

### Trin 5: Spare ZBT-2 + Thread-roadmap (post-flytte)

Hvis mesh fundamentalt fejler igen efter trin 4 — overvej hardware-issue:

- **Spare ZBT-2**: køb en ekstra (~700 kr) og hold som backup. Swap'ning
  tager 5 min hvis du har konfigurationen klar.
- **Thread/OpenThread Border Router** via Sonoff ZBDongle-E (ZBT-1):
  langsigtet roadmap. Thread er en alternativ protocol med bedre mesh-
  egenskaber. Devices der støtter både Zigbee og Thread (fx nyere IKEA)
  kan migreres. Se `docs/hardware.md` roadmap.
