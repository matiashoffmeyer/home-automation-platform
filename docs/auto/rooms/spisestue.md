# Rum-dossier: spisestue

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `spisestue`

## Indhold
- [Automations](spisestue.md#automations) (5)
- [Entities](spisestue.md#entities) (105)
- [Helpers](spisestue.md#helpers) (32)

---

## Automations

### `automations/presence_lights.yaml`

- **Lysnet: Spisestue tænd ved LUX-fald** (line 78, mode=single)
  - Daylight fades while spisebordet er besat — spisestue-loftet kommer blidt på.
- **Lysnet: Spisestue tænd på mørk indedag** (line 252, mode=single)
- **Lysnet: Stue/spisestue re-arm efter dagslys-sluk** (line 845, mode=single)
  - Lux-præmissen bag dagslys-sluk faldt bort mens rummet stadig er optaget →

### `automations/presence_stue.yaml`

- **Lysnet: Spisestue tænd** (line 17, mode=single)
- **Lysnet: Spisestue gradvis sluk** (line 376, mode=restart)
  - 2026-06-19 (user-spec): spisestue-loftet slukker når spisebords-Apolloen

---

## Entities

### `automation.*`

- `automation.lysnet_spisestue_taend_pa_mork_indedag` — 1 refs in 1 file(s)

### `binary_sensor.*`

- `binary_sensor.godnat_spisestue_sol_under_graense` — 1 refs in 1 file(s)
- `binary_sensor.scene_spisestue_middag_active` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_apollo_afstand_jitter` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_apollo_frossen_ghost` — 2 refs in 2 file(s)
- `binary_sensor.spisestue_apollo_occupancy` — 29 refs in 19 file(s)
- `binary_sensor.spisestue_apollo_occupancy_filtered` — 112 refs in 40 file(s)
- `binary_sensor.spisestue_apollo_online` — 2 refs in 1 file(s)
- `binary_sensor.spisestue_apollo_radar_moving_target` — 12 refs in 11 file(s)
- `binary_sensor.spisestue_apollo_radar_still_target` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_apollo_radar_zone_1_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_apollo_radar_zone_2_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_apollo_radar_zone_3_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_gardin_ghost` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_gardin_ghost_kandidat` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_lys_on_effektiv` — 4 refs in 3 file(s)
- `binary_sensor.spisestue_nabo_varm` — 3 refs in 3 file(s)
- `binary_sensor.spisestue_ophold_bevis` — 1 refs in 1 file(s)

### `counter.*`

- `counter.ghost_spisestue` — 4 refs in 1 file(s)

### `cover.*`

- `cover.gardin_spisestue_vest` — 77 refs in 22 file(s)

### `input_boolean.*`

- `input_boolean.dance_room_spisestue` — 3 refs in 3 file(s)
- `input_boolean.putte_glare_spisestue_vest_ned` — 9 refs in 4 file(s)
- `input_boolean.roborock_styrbar_kort_op_spisestue` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_spisestue` — 1 refs in 1 file(s)

### `input_datetime.*`

- `input_datetime.gardin_manual_down_spisestue_vest` — 6 refs in 4 file(s)
- `input_datetime.gardin_spisestue_antaget_at` — 5 refs in 1 file(s)

### `input_number.*`

- `input_number.apollo_led_lux_offset_spisestue` — 2 refs in 2 file(s)
- `input_number.apollo_natkalib_spisestue_stille_min` — 2 refs in 2 file(s)
- `input_number.gardin_spisestue_antaget_pos` — 4 refs in 1 file(s)
- `input_number.gardin_spisestue_fuld_sekunder` — 2 refs in 2 file(s)
- `input_number.godnat_spisestue_sol_elevation` — 2 refs in 2 file(s)
- `input_number.maaltid_registrer_min_spisestue_min` — 3 refs in 2 file(s)
- `input_number.morgenrampe_spisestue_sekunder` — 4 refs in 3 file(s)
- `input_number.radiator_trin_spisestue` — 2 refs in 2 file(s)
- `input_number.spisestue_auto_brightness` — 4 refs in 3 file(s)
- `input_number.spisestue_auto_kelvin` — 4 refs in 3 file(s)
- `input_number.spisestue_debounce_varm_sekunder` — 3 refs in 3 file(s)
- `input_number.spisestue_g0_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g0_still` — 2 refs in 2 file(s)
- `input_number.spisestue_g1_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g1_still` — 2 refs in 2 file(s)
- `input_number.spisestue_g2_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g2_still` — 2 refs in 2 file(s)
- `input_number.spisestue_g3_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g3_still` — 2 refs in 2 file(s)
- `input_number.spisestue_g4_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g4_still` — 2 refs in 2 file(s)
- `input_number.spisestue_g5_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g5_still` — 2 refs in 2 file(s)
- `input_number.spisestue_g6_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g6_still` — 2 refs in 2 file(s)
- `input_number.spisestue_g7_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g7_still` — 2 refs in 2 file(s)
- `input_number.spisestue_g8_move` — 2 refs in 2 file(s)
- `input_number.spisestue_g8_still` — 2 refs in 2 file(s)
- `input_number.spisestue_ghost_reject_minutes` — 2 refs in 2 file(s)
- `input_number.spisestue_lux_threshold` — 8 refs in 5 file(s)
- `input_number.spisestue_nabo_varm_minutter` — 3 refs in 3 file(s)
- `input_number.spisestue_natlys_brightness` — 3 refs in 3 file(s)
- `input_number.spisestue_occupancy_debounce_seconds` — 3 refs in 3 file(s)
- `input_number.spisestue_off_minutter` — 6 refs in 3 file(s)

### `input_select.*`

- `input_select.room_mode_spisestue` — 27 refs in 20 file(s)

### `input_text.*`

- `input_text.spisestue_apollo_last_flap` — 1 refs in 1 file(s)
- `input_text.spisestue_gate_flapcount` — 1 refs in 1 file(s)
- `input_text.spisestue_gate_floors` — 1 refs in 1 file(s)

### `light.*`

- `light.spisestue_apollo_rgb_light` — 2 refs in 2 file(s)
- `light.spisestue_loft` — 121 refs in 47 file(s)
- `light.spisestue_pendel` — 136 refs in 39 file(s)

### `number.*`

- `number.spisestue_apollo_g0_move_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g0_still_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g1_move_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g1_still_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g2_move_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g2_still_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g3_move_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g3_still_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g4_move_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g4_still_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g5_move_threshold` — 1 refs in 1 file(s)
- `number.spisestue_apollo_g5_still_threshold` — 1 refs in 1 file(s)

### `script.*`

- `script.gardin_spisestue_position` — 1 refs in 1 file(s)
- `script.roborock_grundig_spisestue` — 1 refs in 1 file(s)
- `script.roborock_hurtig_spisestue` — 1 refs in 1 file(s)
- `script.spisestue_apollo_apply_all_gates` — 1 refs in 1 file(s)

### `sensor.*`

- `sensor.hjemmearbejde_spisestue_ophold_vindue` — 1 refs in 1 file(s)
- `sensor.maaltid_spisestue_bekraeft_min_i_vindue` — 2 refs in 2 file(s)
- `sensor.maaltid_spisestue_bekraeft_vindue` — 1 refs in 1 file(s)
- `sensor.spisestue_apollo_esp_temperature` — 4 refs in 3 file(s)
- `sensor.spisestue_apollo_ghost_flaps_1h` — 3 refs in 2 file(s)
- `sensor.spisestue_apollo_lux` — 11 refs in 7 file(s)
- `sensor.spisestue_apollo_radar_move_energy` — 1 refs in 1 file(s)
- `sensor.spisestue_apollo_radar_moving_distance` — 2 refs in 2 file(s)
- `sensor.spisestue_apollo_radar_still_distance` — 3 refs in 3 file(s)
- `sensor.spisestue_apollo_radar_still_energy` — 1 refs in 1 file(s)
- `sensor.spisestue_apollo_temperature` — 1 refs in 1 file(s)
- `sensor.spisestue_dagslys_lx` — 15 refs in 9 file(s)
- `sensor.spisestue_dagslys_sample` — 7 refs in 2 file(s)
- `sensor.spisestue_lux` — 2 refs in 2 file(s)
- `sensor.spisestue_lux_reel` — 32 refs in 11 file(s)
- `sensor.spisestue_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.spisestue_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.spisestue_off_sekunder` — 5 refs in 2 file(s)
- `sensor.spisestue_sofa_off_sekunder` — 2 refs in 1 file(s)

### `switch.*`

- `switch.spisestue_apollo_ld2410_bluetooth` — 1 refs in 1 file(s)
- `switch.spisestue_apollo_radar_engineering_mode` — 1 refs in 1 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.putte_glare_spisestue_vest_ned` (defined in `packages/putte_vest_glare.yaml`)
- `input_boolean.roborock_styrbar_kort_op_spisestue` (defined in `packages/roborock_styrbar.yaml`)

### `input_datetime.*`

- `input_datetime.gardin_manual_down_spisestue_vest` (defined in `packages/gardin_manual_grace.yaml`)
- `input_datetime.gardin_spisestue_antaget_at` (defined in `packages/broadlink_gardiner.yaml`)
- `input_datetime.spisestue_apollo_flap_last_bump` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.spisestue_apollo_occ_since` (defined in `packages/apollo_latch_detect.yaml`)
- `input_datetime.spisestue_flapcount_since` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.styrbar_last_press_spisestue` (defined in `packages/room_modes.yaml`)

### `input_number.*`

- `input_number.gardin_spisestue_antaget_pos` (defined in `packages/broadlink_gardiner.yaml`)
- `input_number.spisestue_g0_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g0_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g1_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g1_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g2_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g2_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g3_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g3_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g4_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g4_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g5_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g5_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g6_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g6_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g7_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g7_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g8_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_g8_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.spisestue_ghost_reject_minutes` (defined in `packages/spisestue_curtain_ghost.yaml`)

### `input_select.*`

- `input_select.room_mode_spisestue` (defined in `packages/room_modes.yaml`)

### `input_text.*`

- `input_text.spisestue_apollo_last_flap` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.spisestue_gate_flapcount` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.spisestue_gate_floors` (defined in `packages/apollo_gate_decay.yaml`)
