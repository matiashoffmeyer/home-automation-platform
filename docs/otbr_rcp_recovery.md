# OTBR / Thread RCP hang — remote recovery (no physical re-plug)

**TL;DR:** When the Thread network dies because the Sonoff RCP firmware wedges,
run `python3 /config/scripts/otbr_rcp_reset.py --full` from the SSH add-on. It
resets the EFR32 over the CP210x DTR/RTS lines (= the nRESET pin) and the network
comes back on the same credentials — **no Matter re-pairing**. The Thread watchdog
now also does this automatically. First proven working **2026-06-29**.

## Symptom

- `binary_sensor.badevaerelse_matter_spots_ok` = `off`; bath spots 1–3 + door
  sensor go `unavailable` (they are Matter-over-Thread).
- OTBR add-on (`core_openthread_border_router`) state = `error`, crash-looping.
- A plain add-on restart does **not** fix it.

## Confirm the root cause (1 command)

```bash
curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  "http://supervisor/addons/core_openthread_border_router/logs" | tail -60
```

Look for, in `migrate_otbr_settings.py` → `get_adapter_hardware_addr` →
`spinel.send_frame`:

```
TimeoutError
WARNING: otbr-agent exited with code 1
s6-rc: warning: unable to start service otbr-agent: command exited 1
```

That is a **Spinel handshake timeout**: otbr-agent can't read the adapter
hardware address because the RCP firmware on the dongle isn't answering. The USB
device node (`/dev/ttyUSB0`) still exists — only the radio firmware is wedged.

## Why the common internet advice does NOT apply here

External AI / forum advice for "OTBR keeps crashing" usually says:

1. **"Roll back the OTBR add-on from 2.16.0 to 2.15.3 (mDNS regression)."**
   We run **3.0.1** (the latest; `version_latest` matches, no update available).
   There is no 2.16.0 to roll back from, and our failure is a Spinel serial
   timeout, not an mDNS/discovery problem.
2. **"Settings → Hardware → Configure → Switch between Zigbee/Thread firmware."**
   That multi-protocol firmware switch is for Nabu Casa SkyConnect / ZBT-1/ZBT-2
   dongles. **Our OTBR runs on a Sonoff ZBDongle (ttyUSB0, VID:PID 10c4:ea60).**
   Our ZBT-2 (ttyACM0) is the **Zigbee/ZHA coordinator** — applying a firmware
   switch to the wrong stick would **wipe the Zigbee network**. Do not use it.

Our hang is a wedged RCP. The real-world cure was always "unplug the stick."
This document is the remote substitute for that unplug.

## The fix: remote RCP reset

The Sonoff's CP210x USB-UART bridge has its **DTR/RTS lines wired to the EFR32's
reset/bootloader pins** (the same circuit `universal-silabs-flasher` uses to reset
the chip for flashing). Pulsing RTS asserts the EFR32 `nRESET` line, so the radio
cold-boots its firmware. We cannot cut USB VBUS from software: the NUC's root hub
has `wHubCharacteristics=0x000a` (no port power switching, measured 2026-10-09).
**The pin reset is NOT an equally good cure** (corrected 2026-10-09): on 08-09/10
the OTBR sat as a lone leader for 9 h, every pin reset and OTBR restart formed a
new lone partition, and only a physical replug (power-on reset) merged the mesh.
The HA ladder (`packages/thread_otbr_watchdog.yaml`) therefore rotates TX boost →
pin reset → USB re-enumeration (`scripts/otbr_usb_replug.py`, sysfs port
`disable`) forever while `binary_sensor.thread_border_router_nede` is on. On a
hub WITH per-port power switching the same `disable` write becomes a real VBUS
cut (the user declined buying one, 2026-10-09). A single Matter bulb that stays
in the router table but answers no ping (zombie router) is handled separately by
`scripts/thread_zombie_kick.py` (`ot-ctl releaserouterid`).

Proof it preserves the network: after the pulse the RCP logs
`Reset info: 0x301 (PIN)` and the role climbs `detached → child → router`. The RCP
holds **no** network credentials — the Thread dataset (PAN `0x4187`, network key)
lives in the OTBR add-on + `.storage/thread.datasets`, so the spots re-attach to
the same network. `matter_spots_ok` returning `on` is itself the proof the network
is intact (spots are provisioned to PAN 0x4187 and would not re-attach otherwise).

### Manual (Claude session, from the SSH add-on)

```bash
python3 /config/scripts/otbr_rcp_reset.py --full
```

`--full` = disable watchdog → stop add-on (free the port) → DTR/RTS reset pulse →
start add-on → poll `matter_spots_ok` (~90 s) → re-enable watchdog. It refuses to
touch anything that is not the Sonoff stick (VID:PID 10c4:ea60 / by-id
`Itead_Sonoff`); the ZBT-2 is never matched. Default (no flag) = pulse only.

### Automatic (Thread watchdog)

`packages/thread_otbr_watchdog.yaml` now escalates a hard hang automatically:
soft hang → one add-on restart; **hard hang → stop add-on → `shell_command.
otbr_rcp_reset` (pulse) → start add-on → re-check**; only if *that* fails does it
push "physical re-plug" (= genuine hardware/power fault, not just firmware). The
`shell_command` runs in HA core, which has serial access (ZHA uses ttyACM0).

## If even the RCP reset fails

Then it is not just a firmware wedge — suspect power/USB. Per CLAUDE.md the dongle
has shown PWR/HV resets; next step is a **physical re-plug** and moving it onto a
USB extension away from the NUC's USB3 port (USB3 RF interference). Re-flashing the
RCP firmware (`docs/zigbee.md`) is a separate, heavier step and does not help a
power problem.

## Manual diagnostic crib

```bash
# OTBR add-on version + state
curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  "http://supervisor/addons/core_openthread_border_router/info" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['version'],d['state'])"

# Is the dongle node present + which tty?
ls -l /dev/serial/by-id/        # Itead_Sonoff...-> ttyUSB0 ; Nabu_Casa_ZBT-2 -> ttyACM0

# Thread health proxy
curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  "http://supervisor/core/api/states/binary_sensor.badevaerelse_matter_spots_ok"
```

Note: `ssh ha` / `homeassistant.local` are for the **PC** session. Inside HAOS
(SSH add-on) use the local `http://supervisor/...` API with `$SUPERVISOR_TOKEN`.
