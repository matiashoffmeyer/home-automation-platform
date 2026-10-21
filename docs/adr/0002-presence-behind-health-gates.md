# 2. Presence is read through health gates and sustained anchors

- **Status:** accepted
- **Date:** 2026-05-01, extended 2026-09-11

## Context

Presence comes from mmWave radars (ESPHome) and Zigbee motion sensors. Most of
the house's decisions depend on it: switching lights off in empty rooms,
returning a room to `Auto`, putting the house into `Dormant`. Three properties
of the raw signals made direct use unsafe:

- **A dead radio looks like an empty room.** A sensor that drops off Wi-Fi,
  Zigbee or Thread becomes `unavailable`. Checking `is_state(x, 'on')` quietly
  returns false, so "the sensor is gone" is read as "nobody is here", and
  lights go off around people.
- **Radar-derived binaries flicker.** A one-second blip resets `last_changed`,
  so "off for N minutes" can be erased by noise. A replay of past events can
  still look healthy, because it only contains the events that were recorded.
- **`last_changed` resets on restart.** It cannot tell how long a state has
  held.

## Decision

1. **Health gates before logic.** `binary_sensor.presence_sensors_available`
   is on when at least one presence channel reports. Presence-driven logic
   skips when it is off. In guest mode, the sweep that switches lights off
   when the house goes `Dormant` works per room and spares any room whose own
   channel is blind. A global block was tried first; replayed over 31
   transitions it prevented seven correct switch-offs to protect one lamp.
2. **Silence is measured on a sustained anchor.**
   `sensor.last_sustained_presence` is a timestamp moved only by presence that
   held. "Nobody for N minutes" compares against it, not against a radar
   binary's `last_changed`.
3. **Durations that matter are written down.** Occupancy start times are
   stored in `input_datetime` helpers (`input_datetime.<room>_apollo_occ_since`),
   which survive a restart. When a binary is off, its helper holds the epoch.
4. **A restart recovery does not prove its premise with the channel that was
   broken.** A sensor that boots stuck at `on` has `last_changed` equal to the
   boot time. Recovery requires a second channel and re-checks its gates after
   the settle delay.

## Consequences

- An outage degrades to "do nothing" rather than "switch off". The cost is a
  light that stays on longer while a radio is down.
- Thresholds on these signals are set from their measured distributions
  (`scripts/hq.py hist --stats`), not from datasheets. Radar fields do not
  follow walls, and ghost targets are part of the signal.
- Every new presence consumer has to choose its anchor. Failure classes #9,
  #14, #23 and #25 in `docs/fejlklasser.md` describe the variants that went
  wrong.

## Further reading

The design notes are in Danish.

- [`.claude/rules/presence_radar.md`](../../.claude/rules/presence_radar.md): radar zones, ghosts, blind channels and the gate layers
- [`docs/fejlklasser.md`](../fejlklasser.md), failure classes 9, 14, 25 and 28: the sensor traps behind this decision
