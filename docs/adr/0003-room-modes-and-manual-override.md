# 3. Each room is Auto, Manual or Off, and a person's action wins

- **Status:** accepted
- **Date:** 2026-04-11, extended 2026-06-10

## Context

Automations and people change the same lights. If an automation re-asserts its
own idea of the right light after someone dimmed it by hand, the house fights
its occupants. If a manual change disables automation forever, the house
gradually stops being automatic. The system needed a rule for who is in
charge of a room and for how long, and a reliable way to tell a person's action
from an automation's.

Two signals that look usable are not:

- `context.parent_id is none` is also true for a call made by a time trigger
  or a backstop, so it does not identify a person.
- A physical remote press carries no user id at all.

## Decision

1. **One anchor per room.** `input_select.room_mode_<room>` exists for nine
   zones, with options `Auto`, `Manual` and `Off`. In normal operation only
   `Auto` and `Manual` are written. `Off` is used while sleeping, as a
   presence block.
2. **A person's action switches the room to `Manual`.**
   `automations/manual_override.yaml` listens to `light.turn_on` and
   `light.turn_off` service calls and acts only on calls whose context has a
   `user_id`. Remote presses are stamped as manual by their handler
   (`script.styrbar_stamp_press`). Only the touched room changes, not the
   whole open-plan area.
3. **Rooms drift back to `Auto`.** `automations/room_drift_back.yaml` returns a
   room when it has been empty for `global_drift_back_empty_minutes`, when the
   manual hold has expired while the room stays occupied, or after 24 hours
   in any mode other than `Auto`. Lights that are on fade to the automatic
   target over ten minutes.
4. **Automatic light paths read the anchor.** The paths that adjust a room's
   lights on their own check its mode before they write. Signals that must
   reach a lamp regardless, such as the smoke alarm, are ranked in an
   ownership registry instead ([ADR 4](0004-lamp-ownership-registry.md)).

## Consequences

- Manual changes are respected without a separate "pause automation" switch,
  and the house returns to automatic behaviour without being told to.
- Tests have to clean up after themselves. An API call carries a user id and
  is therefore recorded as a person's action, which flips the room to
  `Manual` and stamps manual-off trackers.
- Restoring a scene sends internal `light.turn_on` calls with the scene's
  context, which would look like several manual changes at once. Restore
  scenes are allowlisted in `manual_override.yaml`.
- Lamps that several automations compete for need more than a room mode; see
  [ADR 4](0004-lamp-ownership-registry.md).

## Further reading

The design notes are in Danish.

- [`docs/architecture.md`](../architecture.md), section "Room-mode state machine"
- [`system_design.md`](../../system_design.md): buttons, drift-back and switch-off times, with the slider that owns each number
- [`docs/fejlklasser.md`](../fejlklasser.md), failure class 3: what counts as a manual action
