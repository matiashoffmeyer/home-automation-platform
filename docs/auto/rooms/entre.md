# Rum-dossier: entre

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `entre`

## Indhold
- [Automations](entre.md#automations) (13)
- [Entities](entre.md#entities) (64)
- [Helpers](entre.md#helpers) (13)

---

## Automations

### `automations/airbnb_mode.yaml`

- **AirBnB: Dormant -> Active ved entré presence (comfort welcome)** (line 1094, mode=single)
  - Hvis huset er Dormant og guest entrer entré, tænd lys "behageligt"

### `automations/arrival.yaml`

- **Hjemkomst: Entré lys ved hoveddør** (line 31, mode=single)

### `automations/entre_motion.yaml`

- **Entré: Detekt manuel tænd (væg / Styrbar / app)** (line 42, mode=queued)
  - Stampler input_datetime.entre_loft_manual_on_at når et MENNESKE tændte
- **Entré: Lys tænd ved bevægelse** (line 103, mode=single)
  - Lights on in entré when motion detected during the day.
- **Entré: Lys sluk efter bevægelse** (line 280, mode=restart)
  - Entré is exempt from the global 5-minute fade rule — it is a
- **Entré: Svagt lys om natten** (line 400, mode=single)

### `automations/entre_somrig.yaml`

- **Entré Styrbar: TOP quick -> dim UP entré / undo / AirBnB welcome** (line 66, mode=queued)
  - 3 branches:
- **Entré Styrbar: TOP long -> nødlys** (line 268, mode=single)
  - 2026-10-15 (user-spec): "langt tryk op og 3 hurtige piletryk og 3 hurtige
- **Entré Styrbar: BUND quick -> sluk ALT lys (uden gardiner) + grace** (line 300, mode=single)
  - 2026-06-16 (user-spec) — REDESIGN: kort NED dæmper IKKE længere entré ned
- **Entré Styrbar: Auto-ryd undo grace efter 10 min** (line 397, mode=single)
  - Naar grace har staaet on i 10 min uden TOP-press, slukker vi den.
- **Entré Styrbar: Auto-ryd nedluknings-grace efter slider-min** (line 436, mode=restart)
  - Nedluknings-grace (set af NED kort/lang i Normal OG AirBnB) holder ALLE
- **Entré Styrbar: BUND long -> sluk alt (uden gardiner) + Roborock full** (line 473, mode=single)
  - 2026-06-16 (user-spec): "det samme som NED kort PLUS grundig rengøring".
- **Entré Styrbar: L/R mode cycle [auto, zen, all_bright, all_off]** (line 560, mode=restart)
  - L/R quick på entré Styrbar = cycle mellem 4 modes. Cursor wraps via

---

## Entities

### `automation.*`

- `automation.airbnb_dormant_active_ved_entre_presence_comfort_welcome` — 1 refs in 1 file(s)
- `automation.entre_lys_taend_ved_bevaegelse` — 3 refs in 3 file(s)

### `binary_sensor.*`

- `binary_sensor.entre_lys_on_effektiv` — 4 refs in 3 file(s)
- `binary_sensor.entre_lys_rent` — 3 refs in 1 file(s)
- `binary_sensor.entre_morgen_passager_nok` — 1 refs in 1 file(s)
- `binary_sensor.entre_roegalarm` — 2 refs in 2 file(s)
- `binary_sensor.entre_stedfortraeder_bevaegelse` — 6 refs in 2 file(s)
- `binary_sensor.entre_valhorn_occupancy` — 105 refs in 47 file(s)
- `binary_sensor.entre_vallhorn_haengt` — 6 refs in 3 file(s)

### `button.*`

- `button.entre_somrig_identify` — 1 refs in 1 file(s)

### `input_boolean.*`

- `input_boolean.airbnb_velkomst_move_entre` — 3 refs in 2 file(s)
- `input_boolean.dance_room_entre` — 5 refs in 5 file(s)
- `input_boolean.entre_shutdown_grace` — 25 refs in 9 file(s)
- `input_boolean.entre_somrig_undo_grace` — 8 refs in 3 file(s)
- `input_boolean.entre_valhorn_outage_alerted` — 4 refs in 2 file(s)
- `input_boolean.entre_valhorn_stuck_alerted` — 3 refs in 1 file(s)
- `input_boolean.openplan_entre_velkomst_enabled` — 3 refs in 3 file(s)
- `input_boolean.openplan_entre_velkomst_venter` — 11 refs in 2 file(s)
- `input_boolean.roborock_styrbar_kort_op_entre` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_entre` — 1 refs in 1 file(s)

### `input_datetime.*`

- `input_datetime.entre_loft_manual_on_at` — 4 refs in 2 file(s)
- `input_datetime.entre_ned_dormant_armed` — 5 refs in 1 file(s)
- `input_datetime.openplan_entre_velkomst_at` — 4 refs in 2 file(s)
- `input_datetime.styrbar_last_press_entre` — 16 refs in 6 file(s)

### `input_number.*`

- `input_number.entre_brightness_cursor` — 6 refs in 2 file(s)
- `input_number.entre_brightness_moerke` — 2 refs in 2 file(s)
- `input_number.entre_brightness_taerskel` — 2 refs in 2 file(s)
- `input_number.entre_fade_ud_sekunder` — 4 refs in 3 file(s)
- `input_number.entre_godnat_brightness` — 2 refs in 2 file(s)
- `input_number.entre_kelvin` — 4 refs in 4 file(s)
- `input_number.entre_lux_threshold` — 5 refs in 3 file(s)
- `input_number.entre_mode_idx` — 2 refs in 1 file(s)
- `input_number.entre_ned_dormant_minutter` — 7 refs in 3 file(s)
- `input_number.entre_ned_dormant_vindue_minutter` — 3 refs in 2 file(s)
- `input_number.entre_off_sekunder` — 4 refs in 3 file(s)
- `input_number.entre_shutdown_grace_minutes` — 5 refs in 2 file(s)
- `input_number.global_entre_manual_grace_minutes` — 3 refs in 2 file(s)
- `input_number.godmorgen_entre_passager_antal` — 2 refs in 2 file(s)
- `input_number.open_plan_entre_fallback_faktor` — 2 refs in 2 file(s)
- `input_number.openplan_entre_velkomst_tom_minutter` — 7 refs in 4 file(s)
- `input_number.sove_morgen_afgang_entre_sekunder` — 3 refs in 3 file(s)

### `input_select.*`

- `input_select.room_mode_entre` — 18 refs in 13 file(s)

### `light.*`

- `light.entre_all` — 11 refs in 6 file(s)
- `light.entre_loft` — 80 refs in 34 file(s)
- `light.entre_loft_tradfri_udgaaet` — 1 refs in 1 file(s)

### `scene.*`

- `scene.entre_somrig_undo_snapshot` — 2 refs in 2 file(s)

### `script.*`

- `script.entre_fade_ud` — 5 refs in 4 file(s)
- `script.entre_ned_sluk_alt` — 7 refs in 3 file(s)
- `script.roborock_grundig_entre` — 1 refs in 1 file(s)
- `script.roborock_hurtig_entre` — 1 refs in 1 file(s)

### `sensor.*`

- `sensor.entre_cykel_lader_effekt` — 14 refs in 6 file(s)
- `sensor.entre_cykel_lader_energi` — 4 refs in 2 file(s)
- `sensor.entre_dagslys_sample` — 6 refs in 1 file(s)
- `sensor.entre_lux_reel` — 6 refs in 3 file(s)
- `sensor.entre_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.entre_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.entre_passager_5min` — 2 refs in 2 file(s)
- `sensor.entre_somrig_battery` — 10 refs in 6 file(s)
- `sensor.entre_styrbar_battery` — 3 refs in 2 file(s)
- `sensor.entre_tom_sluk_sekunder` — 5 refs in 3 file(s)
- `sensor.entre_valhorn_battery` — 2 refs in 2 file(s)
- `sensor.entre_valhorn_illuminance` — 10 refs in 3 file(s)

### `switch.*`

- `switch.entre_cykel_lader_plug` — 17 refs in 5 file(s)

### `update.*`

- `update.entre_somrig_firmware` — 1 refs in 1 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.airbnb_velkomst_move_entre` (defined in `packages/airbnb_velkomst.yaml`)
- `input_boolean.entre_valhorn_outage_alerted` (defined in `packages/valhorn_watchdog.yaml`)
- `input_boolean.openplan_entre_velkomst_enabled` (defined in `packages/openplan_entre_velkomst.yaml`)
- `input_boolean.openplan_entre_velkomst_venter` (defined in `packages/openplan_entre_velkomst.yaml`)
- `input_boolean.roborock_styrbar_kort_op_entre` (defined in `packages/roborock_styrbar.yaml`)

### `input_datetime.*`

- `input_datetime.entre_ned_dormant_armed` (defined in `packages/entre_ned_dormant.yaml`)
- `input_datetime.openplan_entre_velkomst_at` (defined in `packages/openplan_entre_velkomst.yaml`)
- `input_datetime.styrbar_last_press_entre` (defined in `packages/room_modes.yaml`)

### `input_number.*`

- `input_number.entre_ned_dormant_minutter` (defined in `packages/entre_ned_dormant.yaml`)
- `input_number.open_plan_entre_fallback_faktor` (defined in `packages/room_lux_tuning.yaml`)
- `input_number.openplan_entre_velkomst_tom_minutter` (defined in `packages/openplan_entre_velkomst.yaml`)
- `input_number.sove_morgen_afgang_entre_sekunder` (defined in `packages/sove_alarm_morgen.yaml`)

### `input_select.*`

- `input_select.room_mode_entre` (defined in `packages/room_modes.yaml`)
