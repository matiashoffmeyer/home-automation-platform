# Rum-dossier: terrasse

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `terrasse`

## Indhold
- [Automations](terrasse.md#automations) (16)
- [Entities](terrasse.md#entities) (53)
- [Helpers](terrasse.md#helpers) (16)

---

## Automations

### `automations/activity_aware.yaml`

- **Activity: Terrasse-only winddown — slow dim af indendørs ceiling lys** (line 258, mode=single)
  - Efter 10 min terrasse_only fade ceiling-lights (stue/koekken/spisestue)
- **Activity: Clear terrasse-winddown notification ved skift væk** (line 320, mode=single)
  - A65 fix audit-3 2026-05-06 PM: tilfojet conditions for at undgå over-firing

### `automations/security.yaml`

- **Sikkerhed: Gulvvarmen brænder for spurvene (terrassedør åben)** (line 226, mode=single)
- **Sikkerhed: Terrassedør åben i regn** (line 340, mode=single)
  - Terrassedøren står åben ≥ slider min mens terrasse_regn_aktiv er on —

### `automations/styrbar_rooms.yaml`

- **Styrbar Terrasse: L/R grace 2-sek efter release** (line 842, mode=restart)

### `automations/terrace_plug_control.yaml`

- **Terrasse Plug: power controller (altid ON undtagen Dormant/regn)** (line 36, mode=restart)
  - Single source of truth for plug-tilstand. ON medmindre huset er Dormant,
- **Styrbar Terrasse: top/bund styrer pærelyskæde** (line 125, mode=queued)
- **Terrasse: auto-tænd pærelyskæde ved dusk (indtil godnat)** (line 288, mode=single)
  - Ved dusk (sol < -4°) tændes pærelyskæden automatisk på sol-tilpasset styrke
- **Terrasse Plug: manuel sluk → hold (til regn er forbi)** (line 420, mode=single)
- **Terrasse Plug: manuel tænd → ryd hold** (line 459, mode=single)
- **Terrasse Plug: regn-hold release-evaluator** (line 489, mode=single)
- **Terrasse: nat-auto-sluk af pærelyskæden (fra sluk-tid, open-plan-ro)** (line 585, mode=single)
  - Slukker pærelyskæden i nat-vinduet (sluk-tid-slider → 06:00) når open-plan
- **Terrasse: manuel nat-tænd sætter hold (auto-sluk viger)** (line 663, mode=single)
- **Terrasse: ryd nat-manuel-hold om morgenen** (line 697, mode=single)

### `automations/terrace_presence.yaml`

- **Terrasse: Dæmp indendørs lys (moderat)** (line 52, mode=restart)
- **Terrasse: Gendan indendørs lys** (line 201, mode=single)

---

## Entities

### `automation.*`

- `automation.activity_clear_terrasse_winddown_notification_ved_skift_vaek` — 2 refs in 1 file(s)
- `automation.activity_terrasse_only_winddown_slow_dim_af_indendors_ceiling_lys` — 2 refs in 1 file(s)

### `binary_sensor.*`

- `binary_sensor.likely_on_terrasse` — 8 refs in 6 file(s)
- `binary_sensor.mood_pause_terrasse` — 6 refs in 4 file(s)
- `binary_sensor.parasoll_terrassedoer` — 55 refs in 17 file(s)
- `binary_sensor.terrasse_active` — 14 refs in 10 file(s)
- `binary_sensor.terrasse_lights_on` — 5 refs in 5 file(s)
- `binary_sensor.terrasse_lys_on_effektiv` — 1 refs in 1 file(s)
- `binary_sensor.terrasse_nat_sluk_vindue` — 9 refs in 3 file(s)
- `binary_sensor.terrasse_regn_aktiv` — 15 refs in 6 file(s)

### `button.*`

- `button.terrasse_styrbar_identify` — 1 refs in 1 file(s)

### `input_boolean.*`

- `input_boolean.dance_room_terrasse` — 4 refs in 4 file(s)
- `input_boolean.fest_terrasse_fuld` — 3 refs in 2 file(s)
- `input_boolean.styrbar_lr_grace_terrasse` — 3 refs in 2 file(s)
- `input_boolean.styrbar_lr_holding_terrasse` — 1 refs in 1 file(s)
- `input_boolean.styrbar_up_holding_terrasse` — 1 refs in 1 file(s)
- `input_boolean.terrasse_dim_indoor_active` — 3 refs in 1 file(s)
- `input_boolean.terrasse_morgenlys_ejer` — 6 refs in 1 file(s)
- `input_boolean.terrasse_nat_manuel_hold` — 7 refs in 2 file(s)
- `input_boolean.terrasse_plug_manual_off_hold` — 14 refs in 5 file(s)

### `input_datetime.*`

- `input_datetime.styrbar_last_press_terrasse` — 6 refs in 4 file(s)
- `input_datetime.terrasse_force_on_until` — 3 refs in 2 file(s)
- `input_datetime.terrasse_lys_nat_sluk_tid` — 5 refs in 3 file(s)
- `input_datetime.terrasse_morgenlys_respekt` — 2 refs in 1 file(s)
- `input_datetime.terrasse_plug_manual_off_since` — 2 refs in 1 file(s)
- `input_datetime.terrasse_regn_dry_since` — 2 refs in 1 file(s)
- `input_datetime.terrasse_styrbar_last_cmd` — 3 refs in 2 file(s)

### `input_number.*`

- `input_number.people_terrassedoer_minutter` — 2 refs in 2 file(s)
- `input_number.terrasse_lux_threshold` — 2 refs in 2 file(s)
- `input_number.terrasse_lys_nat_ro_minutter` — 4 refs in 3 file(s)
- `input_number.terrasse_morgenlys_pct` — 4 refs in 3 file(s)
- `input_number.terrasse_morgenlys_sol_elevation` — 4 refs in 3 file(s)
- `input_number.terrasse_regn_dmi_threshold_mm` — 2 refs in 2 file(s)
- `input_number.terrasse_regn_dry_release_hours` — 3 refs in 2 file(s)
- `input_number.terrasse_regn_hold_max_hours` — 3 refs in 2 file(s)
- `input_number.terrasse_skumring_elevation` — 11 refs in 5 file(s)

### `input_select.*`

- `input_select.room_mode_terrasse` — 10 refs in 8 file(s)

### `light.*`

- `light.terrasse_all` — 2 refs in 1 file(s)
- `light.terrasse_paerelyskaede` — 99 refs in 29 file(s)

### `script.*`

- `script.terrasse_force_on` — 2 refs in 1 file(s)
- `script.terrasse_paerelys_til` — 2 refs in 2 file(s)

### `sensor.*`

- `sensor.parasoll_terrassedoer_battery` — 2 refs in 2 file(s)
- `sensor.terrasse_lux_gate` — 1 refs in 1 file(s)
- `sensor.terrasse_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.terrasse_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.terrasse_plug_current` — 1 refs in 1 file(s)
- `sensor.terrasse_plug_current_summation_delivered` — 1 refs in 1 file(s)
- `sensor.terrasse_plug_current_voltage` — 1 refs in 1 file(s)
- `sensor.terrasse_plug_power` — 1 refs in 1 file(s)
- `sensor.terrasse_sidste_tryk` — 1 refs in 1 file(s)
- `sensor.terrasse_styrbar_battery` — 10 refs in 6 file(s)

### `switch.*`

- `switch.terrasse_plug` — 18 refs in 11 file(s)

### `update.*`

- `update.terrasse_styrbar_firmware` — 1 refs in 1 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.styrbar_lr_grace_terrasse` (defined in `packages/room_modes.yaml`)
- `input_boolean.terrasse_morgenlys_ejer` (defined in `packages/terrasse_morgenlys.yaml`)
- `input_boolean.terrasse_plug_manual_off_hold` (defined in `packages/terrasse_plug.yaml`)

### `input_datetime.*`

- `input_datetime.styrbar_last_press_terrasse` (defined in `packages/room_modes.yaml`)
- `input_datetime.terrasse_force_on_until` (defined in `packages/terrasse_plug.yaml`)
- `input_datetime.terrasse_lys_nat_sluk_tid` (defined in `packages/terrasse_plug.yaml`)
- `input_datetime.terrasse_morgenlys_respekt` (defined in `packages/terrasse_morgenlys.yaml`)
- `input_datetime.terrasse_plug_manual_off_since` (defined in `packages/terrasse_plug.yaml`)
- `input_datetime.terrasse_regn_dry_since` (defined in `packages/terrasse_plug.yaml`)
- `input_datetime.terrasse_styrbar_last_cmd` (defined in `packages/terrasse_plug.yaml`)

### `input_number.*`

- `input_number.people_terrassedoer_minutter` (defined in `packages/people_estimate.yaml`)
- `input_number.terrasse_lux_threshold` (defined in `packages/room_lux_tuning.yaml`)
- `input_number.terrasse_morgenlys_pct` (defined in `packages/terrasse_morgenlys.yaml`)
- `input_number.terrasse_morgenlys_sol_elevation` (defined in `packages/terrasse_morgenlys.yaml`)
- `input_number.terrasse_skumring_elevation` (defined in `packages/terrasse_plug.yaml`)

### `input_select.*`

- `input_select.room_mode_terrasse` (defined in `packages/room_modes.yaml`)
