# 1. Tunable values are snapshotted to git and seed a fresh install

- **Status:** accepted
- **Date:** 2026-06-17, revised 2026-10-04

## Context

Behaviour is tuned through several hundred helpers: `input_number` sliders
for timings, thresholds and brightness, plus booleans, selects and datetimes.
Home Assistant keeps their current values in `.storage`, which is not in git.
The YAML only declares them.

Neither of the two obvious options works:

- **`initial:` in YAML** looks like a default, but Home Assistant applies it on
  *every* start. A value tuned in the UI would be overwritten by the next
  restart.
- **No `initial:`** keeps the tuned value across restarts, but a lost or fresh
  `.storage` starts every slider at its `min:`. A hand-written first-boot
  automation then had to set 321 defaults, and those drifted from the tuned
  values. On 2026-10-04, booting a fresh install headless showed 283 of the
  644 sliders on a default that differed from the house, and 32 with no value
  at all.

## Decision

1. A feature lives in one package (`packages/<feature>.yaml`): its helpers,
   template sensors and automations together. Helpers are declared without
   `initial:`.
2. `scripts/helpers_export.py` writes the live values to
   `config_snapshots/helper_values.yaml` and derives
   `config_snapshots/fresh_install/input_number.yaml` from it. The derived file
   contains numbers only and is written atomically, because Home Assistant
   reads it on every start.
3. The first-boot automation (`automations/init_user_preferences.yaml`)
   applies the derived file when it detects a fresh install. The snapshot of
   the tuned values *is* the fresh-install default; a new slider needs no
   hand-written default.
4. The pre-commit hook rejects a staged snapshot whose derived file does not
   match (`helpers_export.py --check-derived --staged`).
   `scripts/helpers_restore.py` restores the values to a running instance.

## Consequences

- Git is the source of truth for tuned values, and a fresh install boots into
  the house as it is tuned. `ha_offline.py staging` proves it headless.
- A new slider has four steps in one session: set it live, add its settings
  tile, export, read the live value back. A slider that misses the export
  boots a fresh install at `min:`.
- The snapshot is only as current as the last export. Runtime counters are kept
  out of it (`RUNTIME_NUMBERS`), so it records preferences, not state.
- A malformed raw snapshot cannot stop Home Assistant from booting, because
  only the derived, numbers-only file is loaded.

## Further reading

The design notes are in Danish.

- [`docs/standing_instructions.md`](../standing_instructions.md), section "Tjek eksisterende slidere": reuse a slider before building one, and snapshot every value to git
- [`docs/fejlklasser.md`](../fejlklasser.md), failure class 5: the steps that used to be forgotten
