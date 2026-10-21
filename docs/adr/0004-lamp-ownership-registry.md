# 4. Contested lamps have an ownership registry and a generated owner sensor

- **Status:** accepted
- **Date:** 2026-10-04

## Context

Some lamps are written by many automations. The kitchen light chain is the
clearest case. On top of the house's own cooking, meal and film modes, the
smoke alarm, a timer and its countdown, confirmations, weather warnings,
games, colour previews, hand gestures, a welcome sequence, the morning ramp
and the night-walk light all have a reason to change it. Each automation
looked correct in its own file. Together they produced three recurring
defects:

- **Two writers at once.** `mode: single` only stops a script from running
  twice. Two different scripts can run together, and the one that starts in
  the middle of the other reads its intermediate state as normal and writes it
  back. In history this shows up as several state rows for one lamp within a
  second.
- **Stale hand-backs.** A temporary owner (a flash, a warning) snapshots the
  lamp and restores the snapshot when it finishes. If the house decided
  something else in the meantime, the restore wins, because it is the last
  call. The lamp switches off, or on again about 40 seconds after it was
  switched off.
- **Unknown writers.** Nobody could say which automations write a lamp
  without a repository-wide search, and searches missed templated targets.

## Decision

1. **The registry is the order of precedence.** `ejerskab/<lamp>.yaml` lists
   the lamp's claims, highest first. Each claim has a condition, a hand-back
   policy (paint the house's target, or keep the current look) and an optional
   resume action. The kitchen chain has sixteen claims, from the smoke alarm
   down to the night-walk light. When no claim is active, the house's own
   target applies, painted by one enforcer.
2. **Everything else is generated from it.** `scripts/ejerskab.py gen` writes
   `sensor.<lamp>_ejer` (the current owner), a "borrowed" binary sensor, the
   resume automation, and a contract page in `docs/auto/ejerskab/`.
3. **Every write site is registered.** `ejerskab.py lint` scans automations
   and scripts for calls that write the lamp, directly, through a light group
   that contains it, or through a scene whose snapshot contains it. The
   pre-commit hook fails on a writer that is not in the registry and on a
   registry entry that no longer writes. Templated targets the scanner cannot
   see are registered by hand as `dynamisk: true`.
4. **Hand-backs ask the house again.** A claim whose hand-back policy is to
   paint the target ends by handing over to the enforcer, which computes the
   target as it is now, instead of restoring a snapshot taken before the
   claim.
5. **Known deviations are listed.** A `huller` section records the gaps that
   remain. The list is only allowed to shrink.

## Consequences

- One file answers "who may write this lamp, and who wins", and the owner is
  visible as a sensor in history.
- Before an edit that touches a registered lamp, the agent is shown the
  contract by a hook (`scripts/ejerskab_hook.py`), and after the edit the same
  lint runs again. The pre-commit check is the enforcement; the hook only
  reports early.
- Adding a writer costs a registry entry and a regeneration. That cost is
  intended.
- A lamp is added to the scheme when it has competing writers, not room by
  room. `ejerskab.py steder <entity>` lists a lamp's write sites to decide.

## Further reading

The design notes are in Danish.

- [`ejerskab/koekken_lyskaede.yaml`](../../ejerskab/koekken_lyskaede.yaml): the first registry
- [`docs/fejlklasser.md`](../fejlklasser.md), failure classes 2 and 27: two writers on one lamp, and a borrower's hand-back
