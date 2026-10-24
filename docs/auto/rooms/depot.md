# Rum-dossier: depot

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `depot`

## Indhold
- [Automations](depot.md#automations) (4)
- [Entities](depot.md#entities) (49)
- [Helpers](depot.md#helpers) (11)

---

## Automations

### `automations/airbnb_mode.yaml`

- **AirBnB: Bloker børneværelse-lys (slukkes straks)** (line 937, mode=queued)
  - Undtagelse 1 (user 2026-06-30; rev. 2026-07-08 #12): BØRNEVÆRELSE må aldrig

### `automations/depot_harry_potter.yaml`

- **Harry Potter rum: Tænd hyggelig lys** (line 21, mode=single)
- **Harry Potter rum: approach-lys hurtig-sluk** (line 129, mode=restart)
  - Pre-tændt depot-strip uden reel indgang (depot_approach_lit on, valhorn off)
- **Harry Potter rum: approach-flag clear (strip slukket)** (line 168, mode=single)

---

## Entities

### `automation.*`

- `automation.airbnb_bloker_depot_bornevaerelse_lys_slukkes_straks` — 1 refs in 1 file(s)

### `binary_sensor.*`

- `binary_sensor.depot_fortryd_vindue` — 1 refs in 1 file(s)
- `binary_sensor.depot_lys_on_effektiv` — 1 refs in 1 file(s)
- `binary_sensor.depot_valhorn_occupancy` — 69 refs in 30 file(s)
- `binary_sensor.depot_vallhorn_haengt` — 4 refs in 3 file(s)

### `button.*`

- `button.depot_valhorn_identify` — 1 refs in 1 file(s)

### `input_boolean.*`

- `input_boolean.dance_room_depot` — 4 refs in 3 file(s)
- `input_boolean.depot_approach_lit` — 8 refs in 3 file(s)
- `input_boolean.depot_valhorn_stuck_alerted` — 3 refs in 1 file(s)
- `input_boolean.roborock_styrbar_kort_op_depot` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_depot` — 1 refs in 1 file(s)
- `input_boolean.styrbar_lr_grace_depot` — 1 refs in 1 file(s)
- `input_boolean.styrbar_lr_holding_depot` — 1 refs in 1 file(s)
- `input_boolean.styrbar_up_holding_depot` — 1 refs in 1 file(s)

### `input_datetime.*`

- `input_datetime.depot_auto_off_at` — 3 refs in 1 file(s)
- `input_datetime.styrbar_last_press_depot` — 5 refs in 4 file(s)

### `input_number.*`

- `input_number.depot_approach_brightness` — 2 refs in 2 file(s)
- `input_number.depot_long_off_seconds` — 3 refs in 2 file(s)
- `input_number.depot_medium_off_seconds` — 2 refs in 2 file(s)
- `input_number.depot_quick_off_seconds` — 2 refs in 2 file(s)

### `input_select.*`

- `input_select.depot_visit_stage` — 19 refs in 4 file(s)
- `input_select.room_mode_depot` — 15 refs in 12 file(s)

### `input_text.*`

- `input_text.depot_foh_dance_rooms_saved` — 4 refs in 1 file(s)
- `input_text.depot_stadie_ved_auto_off` — 3 refs in 1 file(s)

### `light.*`

- `light.depot_all` — 27 refs in 11 file(s)
- `light.depot_loft` — 20 refs in 13 file(s)
- `light.depot_loft_hue_1` — 11 refs in 9 file(s)
- `light.depot_loft_hue_2` — 11 refs in 9 file(s)
- `light.depot_loft_ikea` — 12 refs in 10 file(s)
- `light.depot_strip` — 54 refs in 21 file(s)

### `number.*`

- `number.depot_valhorn_occupied_to_unoccupied_delay` — 1 refs in 1 file(s)
- `number.depot_valhorn_on_time` — 1 refs in 1 file(s)
- `number.depot_valhorn_unoccupied_to_occupied_delay` — 1 refs in 1 file(s)

### `script.*`

- `script.depot_foh_dance_restore` — 1 refs in 1 file(s)
- `script.depot_foh_dance_solo` — 2 refs in 1 file(s)
- `script.roborock_grundig_depot` — 1 refs in 1 file(s)
- `script.roborock_hurtig_depot` — 1 refs in 1 file(s)

### `sensor.*`

- `sensor.depot_absolut_fugt` — 1 refs in 1 file(s)
- `sensor.depot_absolut_fugt_30_min` — 2 refs in 1 file(s)
- `sensor.depot_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.depot_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.depot_sidste_tryk` — 1 refs in 1 file(s)
- `sensor.depot_styrbar_battery` — 3 refs in 2 file(s)
- `sensor.depot_valhorn_battery` — 6 refs in 5 file(s)
- `sensor.depot_valhorn_illuminance` — 2 refs in 2 file(s)

### `switch.*`

- `switch.depot_valhorn_on_only_when_dark` — 1 refs in 1 file(s)

### `timer.*`

- `timer.depot_light_lock` — 8 refs in 2 file(s)
- `timer.depot_sensor_grace` — 3 refs in 3 file(s)

### `update.*`

- `update.depot_valhorn_firmware` — 1 refs in 1 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.depot_approach_lit` (defined in `packages/depot_foh_switch.yaml`)
- `input_boolean.roborock_styrbar_kort_op_depot` (defined in `packages/roborock_styrbar.yaml`)
- `input_boolean.styrbar_lr_grace_depot` (defined in `packages/room_modes.yaml`)

### `input_datetime.*`

- `input_datetime.depot_auto_off_at` (defined in `packages/besoeg_fortryd.yaml`)
- `input_datetime.styrbar_last_press_depot` (defined in `packages/room_modes.yaml`)

### `input_select.*`

- `input_select.depot_visit_stage` (defined in `packages/depot_visit_quality.yaml`)
- `input_select.room_mode_depot` (defined in `packages/room_modes.yaml`)

### `input_text.*`

- `input_text.depot_foh_dance_rooms_saved` (defined in `packages/depot_foh_switch.yaml`)
- `input_text.depot_stadie_ved_auto_off` (defined in `packages/besoeg_fortryd.yaml`)

### `timer.*`

- `timer.depot_light_lock` (defined in `packages/depot_foh_switch.yaml`)
- `timer.depot_sensor_grace` (defined in `packages/depot_foh_switch.yaml`)
