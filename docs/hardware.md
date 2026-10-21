# Home Assistant Hardware & Host

Reference document describing the physical hardware and system-level
integrations that run Home Assistant for this home (its name and
address live only in `secrets.yaml` as `home_name`).

Generated from the running HA instance (HAOS 2026.4.0) — this is the
authoritative record of the host stack. If HA ever has to be reinstalled
from scratch, this document plus `docs/zigbee.md` should be enough to
rebuild the base system.

## Host

- **Platform:** Intel NUC running Home Assistant OS (HAOS)
- **HA version:** 2026.4.0
- **Onboard Bluetooth adapter:** Intel Corporate 0a2a (`8087:0a2a`) — `hci0`
- **Bluetooth MAC:** `52:AF:C5:8A:62:27`

The NUC runs HAOS natively, managed by the `hassio` Supervisor. All
integrations listed below are paired via the HA UI and persisted in
`.storage/core.config_entries`.

## Location

- **Name + coordinates:** `home_name` / `home_latitude` / `home_longitude` in
  `secrets.yaml` (never in git; `configuration.yaml` and the Home zone read them via `!secret`)
- **Timezone:** Europe/Copenhagen
- **Currency:** DKK
- **Country:** DK
- **Elevation:** 10 m

## System-level integrations

These are the built-in / host-managed integrations that form the base
stack. They are NOT hardware peripherals but they are essential for the
host to function normally.

| Integration | Purpose |
|---|---|
| `hassio` | Supervisor — manages HAOS, add-ons, backups |
| `backup` | Scheduled local backups |
| `bluetooth` | Onboard Intel BT adapter (hci0) used for BLE sensors |
| `go2rtc` | RTC video relay (used by camera integrations) |
| `sun` | Astronomical sun position (sunrise/sunset triggers) |
| `met` | Met.no weather forecast |
| `radio_browser` | Internet radio browser |
| `google_translate` | Google Translate TTS (da/en) |
| `shopping_list` | Built-in shopping list |
| `cast` | Google Cast — Epson projector (built-in) + external Chromecast (see Media devices below) |

## Zigbee coordinator (USB)

- **Device:** Nabu Casa ZBT-2 (Home Assistant Connect ZBT-2)
- **Serial number:** `911599ED786C`
- **USB path:** `/dev/serial/by-id/usb-Nabu_Casa_ZBT-2_911599ED786C-if00`
- **VID:PID:** `303A:831A`
- **Radio firmware:** `ezsp 7.5.1.0 build 0 (20260224005837)`
- **Integration:** ZHA (see `docs/zigbee.md` for full configuration)

## Thread / 802.15.4 (LIVE since 2026-05-05)

Sonoff ZBDongle-E flashed with OpenThread RCP firmware
(`zbdonglee_openthread_rcp_2.5.3.0`) via HA's Silicon Labs Flasher addon.
Plugged in USB 2.0 via 0.6m forlænger.

- **Thread network:** `ha-thread-4187`, channel 15, PAN 0xfd6c
- **Border Router:** OpenThread Border Router addon (Home Assistant Supervisor)
  - **watchdog: ON** (sat 2026-06-03). 2026-06-03: donglen havde et `PWR`-reset
    (USB-reenumerering) → otbr-agent døde → addon sad fast i `error` UDEN auto-
    recovery (watchdog var off) → alle Matter-over-Thread offline. Genstart +
    watchdog ON løste det (Thread → leader). Watchdog self-healer fremover.
    Bemærk: donglen virker glitch-tilbøjelig — hold øje med OTBR-state.
- **Matter integration:** auto-discovered via Matter Server addon (8.4.0)
- **bluetooth_adapter_id:** 0 (Intel BT)
- **Docker IPv6:** enabled via `ha docker options --enable-ipv6=true` (kritisk
  for mDNS routing mellem Thread mesh og LAN)

**Live Matter devices (4):**
- 3× IKEA Myggbett door sensors (1 hoveddør, 2 standby)
- 1× IKEA Myggspray motion sensor (entré, replacing Vallhorn role pre-flyt)

**Commissioning playbook:** [docs/matter_pairing_playbook.md](matter_pairing_playbook.md).
Includes magic-trick (mobile commission joiner Thread mesh, NUC's `commission_with_code
network_only=True` finishe via Thread/UDP without BLE).

**Planned post-flyt:** 5× IKEA blackout curtains (Matter-over-Thread direct).
Verify product is direct-Matter (NOT Zigbee-via-DIRIGERA-bridge).

## Media / Cast devices (updated 2026-06-01)

Auto-discovered by the `cast` integration over WiFi **ExampleHome** (same
`192.168.0.0/24` subnet as HA). Set up post-move; old test devices removed.

| Entity | Device | IP | MAC | Cast UDN |
|---|---|---|---|---|
| `media_player.projector` | Epson projector w/ built-in Chromecast (EpiqVision-type) | 192.0.2.97 | `77:B1:A6:6F:BD:93` | `842b7bbf-19be-d725-26c1-c7059cd3bd90` |
| `media_player.chromecast5234` | External Chromecast (cast name "Bedroom TV") | 192.0.2.1 | `A7:F8:74:51:04:32` | `53421f24-6a26-f217-26f9-edf452d1b2ca` |

**Projector power control — IMPORTANT LIMITATION (verified live 2026-06-01):**
- The projector **lamp cannot be turned off from HA via cast.**
  `media_player.turn_off` only quits the running cast app → projector returns to
  its own home screen, lamp stays ON.
- `media_player.turn_on` DOES wake the device / launch the Default Media Receiver
  (display physically reacts), but only while the projector is network-reachable.
- **No Epson network power control:** ESC/VP.net (tcp/3629) and PJLink (tcp/4352)
  are both CLOSED — this is a consumer cast model, not a business projector. The
  only on-device toggles are HDMI CEC / Device Auto Power / HDMI ARC (no
  network-standby setting).
- **For reliable lamp on/off → Broadlink RM4 Pro+ (IR, learn the remote's power
  button).** Use cast (`media_player`) for wake + media control only.

**Removed 2026-06-01** (old tests / dead devices, not expected to return):
- `media_player.lg_stue_frb` — LG webOS TV SM8600PLA (`webostv` config entry deleted)
- `media_player.googletv7139`, `media_player.hyggestue` — two dead Google TVs
- `media_player.bathroom_tv` — phantom cast endpoint

Note: `media_player.hyggestue` is a Cast ghost the integration may re-create; a
recorder-exclude in `configuration.yaml` suppresses its DB writes regardless.

## What is intentionally NOT in this document

The following integrations exist in the running HA instance but are
documented elsewhere / excluded from the base hardware stack on purpose:

- **Media / Cast devices** (Epson projector, external Chromecast) — see the
  "Media / Cast devices" section above; not host hardware
  (LG webOS TV `webostv` removed 2026-06-01 — was an old test device)
- **SwitchBot Indoor/Outdoor Meter** (`switchbot`, hygrometer `65:D8:07:13:F5:C0`) — user-space sensor, not host hardware
