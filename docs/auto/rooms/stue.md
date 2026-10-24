# Rum-dossier: stue

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `stue, open_plan`

## Indhold
- [Automations](stue.md#automations) (22)
- [Entities](stue.md#entities) (303)
- [Helpers](stue.md#helpers) (92)

---

## Automations

### `automations/activity_aware.yaml`

- **Activity: Bedroom-only winddown — soft fade af stue/køkken** (line 132, mode=single)
  - Hvis kun sove/boern har presence efter 21:00 i 10+ min, og stue+koekken

### `automations/arrival.yaml`

- **Hjemkomst: Velkomstlys stue+køkken** (line 137, mode=single)

### `automations/godmorgen_godnat.yaml`

- **Godnat: Børn oppe i stuen (forældre sover stadig)** (line 1148, mode=single)
  - Weekend mornings: kids enter stue while godnat is still active.
- **Godnat: Gendan stuelys ved godnat-slut (stue allerede beboet)** (line 1229, mode=single)
  - When godnat_active clears (parents got up, godnat_auto_clear fired, or

### `automations/godnat_night.yaml`

- **Godnat: Voksen nattur (dim stue+køkken)** (line 547, mode=restart)

### `automations/mood_flag_safety.yaml`

- **Mood: Auto-clear cinema_active hvis stuck >4h og stue tom** (line 15, mode=single)
  - Cinema_active on i 4h+ + stue tom 30+ min = sandsynligvis stuck flag
- **Mood: Auto-clear cirkus_active hvis stuck >4h og stue tom** (line 103, mode=single)
  - Samme safety som cinema men for cirkus_active.

### `automations/presence_lights.yaml`

- **Lysnet: Spisestue tænd ved LUX-fald** (line 78, mode=single)
  - Daylight fades while spisebordet er besat — spisestue-loftet kommer blidt på.
- **Lysnet: Spisestue tænd på mørk indedag** (line 252, mode=single)
- **Lysnet: Sofa-stue tænd ved LUX-fald** (line 320, mode=single)
- **Lysnet: Stue sluk ved LUX-stigning** (line 740, mode=single)
  - Dagslys tilbage i open-plan mens lys står tændt — blid fade off af
- **Lysnet: Stue/spisestue re-arm efter dagslys-sluk** (line 845, mode=single)
  - Lux-præmissen bag dagslys-sluk faldt bort mens rummet stadig er optaget →

### `automations/presence_resync_on_start.yaml`

- **Lysnet: open-plan re-sync ved HA-start (stuck-occupancy fix)** (line 29, mode=single)

### `automations/presence_stue.yaml`

- **Lysnet: Spisestue tænd** (line 17, mode=single)
- **Lysnet: Sofa-stue tænd** (line 181, mode=single)
- **Lysnet: Spisestue gradvis sluk** (line 376, mode=restart)
  - 2026-06-19 (user-spec): spisestue-loftet slukker når spisebords-Apolloen
- **Lysnet: Sofa-stue gradvis sluk** (line 505, mode=restart)
  - 2026-06-19: sofa-lamperne slukker når sofa-Apolloen (stue_apollo) har været

### `automations/somrig_buttons.yaml`

- **Stue Gardin RODRET: smart klik (syd/vest-sekvens + stop)** (line 172, mode=parallel)
- **Stue Gardin: track sidst nedrullede (syd/vest)** (line 389, mode=queued)
- **Stue Gardin RODRET: begge gardiner helt op (hold øverste)** (line 455, mode=single)
- **Stue Gardin RODRET: begge gardiner helt ned (hold nederste)** (line 488, mode=single)

### `automations/styrbar_rooms.yaml`

- **Styrbar Stue: L/R grace 2-sek efter release** (line 800, mode=restart)

---

## Entities

### `automation.*`

- `automation.activity_bedroom_only_winddown_soft_fade_af_stue_koekken` — 2 refs in 1 file(s)
- `automation.godnat_born_oppe_i_stuen_foraeldre_sover_stadig` — 2 refs in 1 file(s)
- `automation.godnat_gendan_stuelys_ved_godnat_slut_stue_allerede_beboet` — 2 refs in 1 file(s)
- `automation.kokken_lyskaede_forste_lys_kulsort_open_plan_bevaegelse` — 2 refs in 2 file(s)
- `automation.lysnet_sofa_stue_taend` — 5 refs in 5 file(s)
- `automation.lysnet_spisestue_taend_pa_mork_indedag` — 1 refs in 1 file(s)
- `automation.lysnet_stue_sluk_ved_lux_stigning` — 1 refs in 1 file(s)
- `automation.lysnet_stue_taend` — 6 refs in 6 file(s)
- `automation.open_plan_dagslys_probe_naar_samplet_er_laast_ude` — 3 refs in 2 file(s)

### `binary_sensor.*`

- `binary_sensor.dark_mode_stue` — 19 refs in 7 file(s)
- `binary_sensor.filmmoerke_stue` — 15 refs in 9 file(s)
- `binary_sensor.godnat_spisestue_sol_under_graense` — 1 refs in 1 file(s)
- `binary_sensor.mood_pause_stue` — 15 refs in 7 file(s)
- `binary_sensor.open_plan_empty_for_20m` — 4 refs in 3 file(s)
- `binary_sensor.open_plan_gardin_op_tilladt` — 8 refs in 4 file(s)
- `binary_sensor.open_plan_lys_rent` — 5 refs in 2 file(s)
- `binary_sensor.open_plan_manual` — 8 refs in 6 file(s)
- `binary_sensor.open_plan_mork_indedag` — 5 refs in 2 file(s)
- `binary_sensor.open_plan_mork_morgen` — 5 refs in 3 file(s)
- `binary_sensor.open_plan_occupied` — 11 refs in 6 file(s)
- `binary_sensor.open_plan_occupied_frisk` — 6 refs in 3 file(s)
- `binary_sensor.open_plan_varsel_publikum` — 5 refs in 3 file(s)
- `binary_sensor.scene_spisestue_middag_active` — 1 refs in 1 file(s)
- `binary_sensor.sofa_hygge_stue_nylig` — 2 refs in 1 file(s)
- `binary_sensor.solo_uden_for_open_plan` — 7 refs in 3 file(s)
- `binary_sensor.spisestue_apollo_afstand_jitter` — 1 refs in 1 file(s)
- `binary_sensor.spisestue_apollo_frossen_ghost` — 2 refs in 2 file(s)
- `binary_sensor.spisestue_apollo_occupancy` — 29 refs in 19 file(s)
- `binary_sensor.spisestue_apollo_occupancy_filtered` — 111 refs in 39 file(s)
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
- `binary_sensor.stue_apollo_afstand_jitter` — 1 refs in 1 file(s)
- `binary_sensor.stue_apollo_bevaegelse_frisk` — 2 refs in 2 file(s)
- `binary_sensor.stue_apollo_frossen_ghost` — 4 refs in 3 file(s)
- `binary_sensor.stue_apollo_occupancy` — 24 refs in 16 file(s)
- `binary_sensor.stue_apollo_occupancy_filtered` — 118 refs in 47 file(s)
- `binary_sensor.stue_apollo_online` — 2 refs in 1 file(s)
- `binary_sensor.stue_apollo_radar_moving_target` — 10 refs in 9 file(s)
- `binary_sensor.stue_apollo_radar_still_target` — 1 refs in 1 file(s)
- `binary_sensor.stue_apollo_radar_zone_1_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.stue_apollo_radar_zone_2_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.stue_apollo_radar_zone_3_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.stue_apollo_still_bekraeftet` — 1 refs in 1 file(s)
- `binary_sensor.stue_ild_morgen_mulig` — 6 refs in 3 file(s)
- `binary_sensor.stue_lys_on_effektiv` — 4 refs in 3 file(s)
- `binary_sensor.stue_manuel_lys_hold` — 4 refs in 2 file(s)
- `binary_sensor.stue_mork_morgen` — 5 refs in 5 file(s)
- `binary_sensor.stue_spots_ild_aktiv` — 8 refs in 2 file(s)
- `binary_sensor.stue_spots_ild_mulig` — 2 refs in 2 file(s)
- `binary_sensor.stue_spots_ild_thread_pause` — 2 refs in 2 file(s)
- `binary_sensor.stue_spots_spotify_aktiv` — 8 refs in 3 file(s)
- `binary_sensor.styrbar_stue_radio` — 7 refs in 5 file(s)
- `binary_sensor.styrbar_stue_spotify` — 3 refs in 1 file(s)

### `button.*`

- `button.stue_styrbar_identify` — 1 refs in 1 file(s)

### `counter.*`

- `counter.ghost_spisestue` — 4 refs in 1 file(s)
- `counter.ghost_stue` — 4 refs in 1 file(s)

### `cover.*`

- `cover.gardin_spisestue_vest` — 77 refs in 22 file(s)
- `cover.gardin_stue_syd` — 69 refs in 22 file(s)
- `cover.gardin_stue_vest_1` — 66 refs in 22 file(s)

### `input_boolean.*`

- `input_boolean.dance_room_spisestue` — 3 refs in 3 file(s)
- `input_boolean.dance_room_stue` — 4 refs in 3 file(s)
- `input_boolean.open_plan_fuldt_lys` — 18 refs in 7 file(s)
- `input_boolean.putte_glare_spisestue_vest_ned` — 9 refs in 4 file(s)
- `input_boolean.roborock_let_stue_enabled` — 4 refs in 3 file(s)
- `input_boolean.roborock_styrbar_kort_op_spisestue` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_kort_op_stue` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_spisestue` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_stue` — 1 refs in 1 file(s)
- `input_boolean.stue_hyggelampe_fravalgt` — 12 refs in 8 file(s)
- `input_boolean.stue_ild_morgen_aktiv` — 13 refs in 3 file(s)
- `input_boolean.stue_ild_morgen_enabled` — 3 refs in 3 file(s)
- `input_boolean.stue_spots_ild` — 4 refs in 4 file(s)
- `input_boolean.stue_spots_spotify` — 6 refs in 3 file(s)
- `input_boolean.styrbar_lr_grace_stue` — 3 refs in 2 file(s)
- `input_boolean.styrbar_lr_holding_stue` — 9 refs in 4 file(s)
- `input_boolean.styrbar_up_holding_stue` — 1 refs in 1 file(s)

### `input_datetime.*`

- `input_datetime.gardin_manual_down_spisestue_vest` — 6 refs in 4 file(s)
- `input_datetime.gardin_spisestue_antaget_at` — 5 refs in 1 file(s)
- `input_datetime.open_plan_fuldt_lys_sluppet` — 3 refs in 2 file(s)
- `input_datetime.open_plan_fuldt_lys_start` — 2 refs in 1 file(s)
- `input_datetime.stue_rodret_seq_at` — 4 refs in 1 file(s)
- `input_datetime.stue_spots_ild_rcp_byge_til` — 2 refs in 1 file(s)
- `input_datetime.styrbar_last_press_stue` — 7 refs in 5 file(s)

### `input_number.*`

- `input_number.apollo_led_lux_offset_spisestue` — 2 refs in 2 file(s)
- `input_number.apollo_led_lux_offset_stue` — 1 refs in 1 file(s)
- `input_number.apollo_natkalib_spisestue_stille_min` — 2 refs in 2 file(s)
- `input_number.gardin_spisestue_antaget_pos` — 4 refs in 1 file(s)
- `input_number.gardin_spisestue_fuld_sekunder` — 2 refs in 2 file(s)
- `input_number.godnat_spisestue_sol_elevation` — 2 refs in 2 file(s)
- `input_number.maaltid_registrer_min_spisestue_min` — 3 refs in 2 file(s)
- `input_number.morgenrampe_spisestue_sekunder` — 4 refs in 3 file(s)
- `input_number.morgenrampe_stue_kelvin` — 3 refs in 3 file(s)
- `input_number.morgenrampe_stue_minutter` — 4 refs in 3 file(s)
- `input_number.morgenrampe_stue_pct` — 7 refs in 6 file(s)
- `input_number.open_plan_dagslys_hold_minutter` — 9 refs in 3 file(s)
- `input_number.open_plan_drift_back_empty_minutes` — 7 refs in 3 file(s)
- `input_number.open_plan_entre_fallback_faktor` — 2 refs in 2 file(s)
- `input_number.open_plan_fuldt_lys_min_minutter` — 4 refs in 3 file(s)
- `input_number.open_plan_fuldt_lys_tomt_minutter` — 5 refs in 3 file(s)
- `input_number.radiator_trin_spisestue` — 2 refs in 2 file(s)
- `input_number.radiator_trin_stue` — 2 refs in 2 file(s)
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
- `input_number.stue_dagslys_sluk_lux` — 4 refs in 3 file(s)
- `input_number.stue_dagslys_sluk_minutter` — 4 refs in 3 file(s)
- `input_number.stue_g0_move` — 2 refs in 2 file(s)
- `input_number.stue_g0_still` — 2 refs in 2 file(s)
- `input_number.stue_g1_move` — 2 refs in 2 file(s)
- `input_number.stue_g1_still` — 2 refs in 2 file(s)
- `input_number.stue_g2_move` — 2 refs in 2 file(s)
- `input_number.stue_g2_still` — 2 refs in 2 file(s)
- `input_number.stue_g3_move` — 2 refs in 2 file(s)
- `input_number.stue_g3_still` — 2 refs in 2 file(s)
- `input_number.stue_g4_move` — 2 refs in 2 file(s)
- `input_number.stue_g4_still` — 2 refs in 2 file(s)
- `input_number.stue_g5_move` — 2 refs in 2 file(s)
- `input_number.stue_g5_still` — 2 refs in 2 file(s)
- `input_number.stue_g6_move` — 2 refs in 2 file(s)
- `input_number.stue_g6_still` — 2 refs in 2 file(s)
- `input_number.stue_g7_move` — 2 refs in 2 file(s)
- `input_number.stue_g7_still` — 2 refs in 2 file(s)
- `input_number.stue_g8_move` — 2 refs in 2 file(s)
- `input_number.stue_g8_still` — 2 refs in 2 file(s)
- `input_number.stue_ild_morgen_fade_minutter` — 3 refs in 3 file(s)
- `input_number.stue_ild_morgen_hurtigere` — 3 refs in 3 file(s)
- `input_number.stue_ild_morgen_naer_cm` — 3 refs in 3 file(s)
- `input_number.stue_laeselampe_auto_max_pct` — 6 refs in 6 file(s)
- `input_number.stue_lux_threshold` — 2 refs in 2 file(s)
- `input_number.stue_rodret_seq_minutes` — 2 refs in 2 file(s)
- `input_number.stue_sofa_off_minutter` — 5 refs in 3 file(s)
- `input_number.stue_spot_1_brugerstyrke` — 3 refs in 3 file(s)
- `input_number.stue_spot_2_brugerstyrke` — 3 refs in 3 file(s)
- `input_number.stue_spots_auto_brightness_pct` — 5 refs in 4 file(s)
- `input_number.stue_spots_auto_kelvin_offset` — 2 refs in 2 file(s)
- `input_number.stue_spots_ild_lysstyrke` — 3 refs in 3 file(s)
- `input_number.stue_spots_ild_rcp_byge` — 3 refs in 3 file(s)
- `input_number.stue_spots_ild_rcp_byge_minutter` — 3 refs in 2 file(s)
- `input_number.stue_spots_ild_rcp_loft` — 4 refs in 3 file(s)
- `input_number.stue_spots_ild_sekunder` — 4 refs in 3 file(s)
- `input_number.stue_spots_ild_styrke` — 3 refs in 3 file(s)
- `input_number.stue_spots_morgen_forhold` — 3 refs in 3 file(s)
- `input_number.stue_spots_spotify_boelge_dybde` — 3 refs in 3 file(s)
- `input_number.stue_spots_spotify_overgang` — 2 refs in 2 file(s)
- `input_number.stue_spots_spotify_spredning` — 4 refs in 3 file(s)
- `input_number.stue_still_ghost_sekunder` — 3 refs in 2 file(s)

### `input_select.*`

- `input_select.room_mode_spisestue` — 27 refs in 20 file(s)
- `input_select.room_mode_stue` — 38 refs in 25 file(s)

### `input_text.*`

- `input_text.spisestue_apollo_last_flap` — 1 refs in 1 file(s)
- `input_text.spisestue_gate_flapcount` — 1 refs in 1 file(s)
- `input_text.spisestue_gate_floors` — 1 refs in 1 file(s)
- `input_text.stue_apollo_last_flap` — 1 refs in 1 file(s)
- `input_text.stue_gate_flapcount` — 1 refs in 1 file(s)
- `input_text.stue_gate_floors` — 1 refs in 1 file(s)
- `input_text.stue_hyggelampe_stedfortraeder_context` — 4 refs in 2 file(s)
- `input_text.stue_rodret_koerer` — 3 refs in 2 file(s)
- `input_text.stue_rodret_last_curtain` — 7 refs in 1 file(s)
- `input_text.stue_rodret_last_lowered` — 6 refs in 1 file(s)
- `input_text.stue_rodret_seq` — 8 refs in 1 file(s)
- `input_text.stue_spot_1_brugerfarve` — 1 refs in 1 file(s)
- `input_text.stue_spot_2_brugerfarve` — 1 refs in 1 file(s)

### `light.*`

- `light.spisestue_apollo_rgb_light` — 2 refs in 2 file(s)
- `light.spisestue_loft` — 120 refs in 46 file(s)
- `light.spisestue_pendel` — 135 refs in 38 file(s)
- `light.stue_all` — 24 refs in 13 file(s)
- `light.stue_apollo_rgb_light` — 5 refs in 3 file(s)
- `light.stue_hjoernelampe` — 53 refs in 26 file(s)
- `light.stue_laesehygge` — 78 refs in 36 file(s)
- `light.stue_loft` — 2 refs in 2 file(s)
- `light.stue_plug` — 73 refs in 27 file(s)
- `light.stue_room` — 20 refs in 13 file(s)
- `light.stue_sofa_lampe` — 51 refs in 25 file(s)
- `light.stue_sofa_lampe_2` — 50 refs in 25 file(s)
- `light.stue_spot_1` — 41 refs in 17 file(s)
- `light.stue_spot_2` — 41 refs in 17 file(s)

### `media_player.*`

- `media_player.hyggestue` — 1 refs in 1 file(s)

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
- `number.stue_apollo_g0_move_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g0_still_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g1_move_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g1_still_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g2_move_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g2_still_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g3_move_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g3_still_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g4_move_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g4_still_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g5_move_threshold` — 1 refs in 1 file(s)
- `number.stue_apollo_g5_still_threshold` — 1 refs in 1 file(s)

### `script.*`

- `script.gardin_spisestue_position` — 1 refs in 1 file(s)
- `script.roborock_grundig_spisestue` — 1 refs in 1 file(s)
- `script.roborock_grundig_stue` — 1 refs in 1 file(s)
- `script.roborock_hurtig_spisestue` — 1 refs in 1 file(s)
- `script.roborock_hurtig_stue` — 1 refs in 1 file(s)
- `script.roborock_start_let_stue` — 4 refs in 1 file(s)
- `script.spisestue_apollo_apply_all_gates` — 1 refs in 1 file(s)
- `script.stue_apollo_apply_all_gates` — 1 refs in 1 file(s)
- `script.stue_ild_morgen` — 5 refs in 3 file(s)
- `script.stue_rodret_koerer_saet` — 7 refs in 1 file(s)
- `script.stue_spots_ild` — 3 refs in 2 file(s)

### `sensor.*`

- `sensor.hjemmearbejde_spisestue_ophold_vindue` — 1 refs in 1 file(s)
- `sensor.maaltid_spisestue_bekraeft_min_i_vindue` — 2 refs in 2 file(s)
- `sensor.maaltid_spisestue_bekraeft_vindue` — 1 refs in 1 file(s)
- `sensor.open_plan_active_recent` — 10 refs in 4 file(s)
- `sensor.open_plan_fade_ind_effektiv` — 10 refs in 5 file(s)
- `sensor.open_plan_haendelse_lux_gate` — 4 refs in 3 file(s)
- `sensor.open_plan_lampe_tilstand` — 1 refs in 1 file(s)
- `sensor.open_plan_lux` — 103 refs in 35 file(s)
- `sensor.open_plan_lux_snapshot` — 1 refs in 1 file(s)
- `sensor.open_plan_mork_indedag_lux_gate` — 3 refs in 2 file(s)
- `sensor.radiator_effekt_stue` — 2 refs in 2 file(s)
- `sensor.sleepover_stue_efter_langt_ned` — 2 refs in 1 file(s)
- `sensor.sleepover_stue_nat_minutter` — 3 refs in 1 file(s)
- `sensor.sleepover_stue_siden_0030` — 3 refs in 1 file(s)
- `sensor.sofa_stue_off_sekunder` — 4 refs in 1 file(s)
- `sensor.spisestue_apollo_esp_temperature` — 4 refs in 3 file(s)
- `sensor.spisestue_apollo_ghost_flaps_1h` — 3 refs in 2 file(s)
- `sensor.spisestue_apollo_lux` — 11 refs in 7 file(s)
- `sensor.spisestue_apollo_radar_move_energy` — 1 refs in 1 file(s)
- `sensor.spisestue_apollo_radar_moving_distance` — 2 refs in 2 file(s)
- `sensor.spisestue_apollo_radar_still_distance` — 3 refs in 3 file(s)
- `sensor.spisestue_apollo_radar_still_energy` — 1 refs in 1 file(s)
- `sensor.spisestue_apollo_temperature` — 1 refs in 1 file(s)
- `sensor.spisestue_dagslys_lx` — 13 refs in 9 file(s)
- `sensor.spisestue_dagslys_sample` — 7 refs in 2 file(s)
- `sensor.spisestue_lux` — 2 refs in 2 file(s)
- `sensor.spisestue_lux_reel` — 32 refs in 11 file(s)
- `sensor.spisestue_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.spisestue_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.spisestue_off_sekunder` — 5 refs in 2 file(s)
- `sensor.spisestue_sofa_off_sekunder` — 2 refs in 1 file(s)
- `sensor.stue_apollo_esp_temperature` — 4 refs in 3 file(s)
- `sensor.stue_apollo_ghost_flaps_1h` — 3 refs in 2 file(s)
- `sensor.stue_apollo_lux` — 6 refs in 4 file(s)
- `sensor.stue_apollo_radar_move_energy` — 1 refs in 1 file(s)
- `sensor.stue_apollo_radar_moving_distance` — 3 refs in 3 file(s)
- `sensor.stue_apollo_radar_still_distance` — 2 refs in 2 file(s)
- `sensor.stue_apollo_radar_still_energy` — 1 refs in 1 file(s)
- `sensor.stue_apollo_temperature` — 3 refs in 2 file(s)
- `sensor.stue_dagslys_sluk_effektiv` — 10 refs in 5 file(s)
- `sensor.stue_lux` — 1 refs in 1 file(s)
- `sensor.stue_lux_gate` — 15 refs in 6 file(s)
- `sensor.stue_lux_reel` — 6 refs in 3 file(s)
- `sensor.stue_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.stue_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.stue_plug_current` — 1 refs in 1 file(s)
- `sensor.stue_plug_energy` — 1 refs in 1 file(s)
- `sensor.stue_plug_power` — 4 refs in 4 file(s)
- `sensor.stue_plug_voltage` — 1 refs in 1 file(s)
- `sensor.stue_sidste_tryk` — 1 refs in 1 file(s)
- `sensor.stue_spotify_stemning` — 11 refs in 4 file(s)
- `sensor.stue_styrbar_battery` — 10 refs in 6 file(s)
- `sensor.stue_temperatur` — 4 refs in 3 file(s)

### `switch.*`

- `switch.spisestue_apollo_ld2410_bluetooth` — 1 refs in 1 file(s)
- `switch.spisestue_apollo_radar_engineering_mode` — 1 refs in 1 file(s)
- `switch.stue_apollo_ld2410_bluetooth` — 1 refs in 1 file(s)
- `switch.stue_apollo_radar_engineering_mode` — 1 refs in 1 file(s)
- `switch.stue_plug` — 12 refs in 6 file(s)

### `update.*`

- `update.stue_styrbar_firmware` — 1 refs in 1 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.open_plan_fuldt_lys` (defined in `packages/open_plan_fuldt_lys.yaml`)
- `input_boolean.putte_glare_spisestue_vest_ned` (defined in `packages/putte_vest_glare.yaml`)
- `input_boolean.roborock_styrbar_kort_op_spisestue` (defined in `packages/roborock_styrbar.yaml`)
- `input_boolean.roborock_styrbar_kort_op_stue` (defined in `packages/roborock_styrbar.yaml`)
- `input_boolean.stue_hyggelampe_fravalgt` (defined in `packages/stue_plug.yaml`)
- `input_boolean.stue_ild_morgen_aktiv` (defined in `packages/stue_ild_morgen.yaml`)
- `input_boolean.stue_ild_morgen_enabled` (defined in `packages/stue_ild_morgen.yaml`)
- `input_boolean.stue_spots_ild` (defined in `packages/stue_spots_ild.yaml`)
- `input_boolean.stue_spots_spotify` (defined in `packages/stue_spots_spotify.yaml`)
- `input_boolean.styrbar_lr_grace_stue` (defined in `packages/room_modes.yaml`)

### `input_datetime.*`

- `input_datetime.gardin_manual_down_spisestue_vest` (defined in `packages/gardin_manual_grace.yaml`)
- `input_datetime.gardin_spisestue_antaget_at` (defined in `packages/broadlink_gardiner.yaml`)
- `input_datetime.open_plan_fuldt_lys_sluppet` (defined in `packages/open_plan_fuldt_lys.yaml`)
- `input_datetime.open_plan_fuldt_lys_start` (defined in `packages/open_plan_fuldt_lys.yaml`)
- `input_datetime.spisestue_apollo_flap_last_bump` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.spisestue_apollo_occ_since` (defined in `packages/apollo_latch_detect.yaml`)
- `input_datetime.spisestue_flapcount_since` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.stue_apollo_flap_last_bump` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.stue_apollo_occ_since` (defined in `packages/apollo_latch_detect.yaml`)
- `input_datetime.stue_flapcount_since` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.stue_rodret_seq_at` (defined in `packages/broadlink_gardiner.yaml`)
- `input_datetime.stue_spots_ild_rcp_byge_til` (defined in `packages/stue_spots_ild.yaml`)
- `input_datetime.styrbar_last_press_spisestue` (defined in `packages/room_modes.yaml`)
- `input_datetime.styrbar_last_press_stue` (defined in `packages/room_modes.yaml`)

### `input_number.*`

- `input_number.gardin_spisestue_antaget_pos` (defined in `packages/broadlink_gardiner.yaml`)
- `input_number.morgenrampe_stue_minutter` (defined in `packages/morgen_opstigning_rampe.yaml`)
- `input_number.open_plan_dagslys_hold_minutter` (defined in `packages/room_lux_tuning.yaml`)
- `input_number.open_plan_drift_back_empty_minutes` (defined in `packages/room_modes.yaml`)
- `input_number.open_plan_entre_fallback_faktor` (defined in `packages/room_lux_tuning.yaml`)
- `input_number.open_plan_fuldt_lys_min_minutter` (defined in `packages/open_plan_fuldt_lys.yaml`)
- `input_number.open_plan_fuldt_lys_tomt_minutter` (defined in `packages/open_plan_fuldt_lys.yaml`)
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
- `input_number.stue_g0_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g0_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g1_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g1_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g2_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g2_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g3_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g3_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g4_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g4_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g5_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g5_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g6_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g6_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g7_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g7_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g8_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_g8_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.stue_ild_morgen_fade_minutter` (defined in `packages/stue_ild_morgen.yaml`)
- `input_number.stue_ild_morgen_hurtigere` (defined in `packages/stue_ild_morgen.yaml`)
- `input_number.stue_ild_morgen_naer_cm` (defined in `packages/stue_ild_morgen.yaml`)
- `input_number.stue_lux_threshold` (defined in `packages/room_lux_tuning.yaml`)
- `input_number.stue_sofa_off_minutter` (defined in `packages/room_absence_tuning.yaml`)
- `input_number.stue_spots_auto_kelvin_offset` (defined in `packages/stue_spots.yaml`)
- `input_number.stue_spots_ild_sekunder` (defined in `packages/stue_spots_ild.yaml`)
- `input_number.stue_spots_spotify_spredning` (defined in `packages/stue_spots_spotify.yaml`)
- `input_number.stue_still_ghost_sekunder` (defined in `packages/stue_apollo_ghost.yaml`)

### `input_select.*`

- `input_select.room_mode_spisestue` (defined in `packages/room_modes.yaml`)
- `input_select.room_mode_stue` (defined in `packages/room_modes.yaml`)

### `input_text.*`

- `input_text.spisestue_apollo_last_flap` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.spisestue_gate_flapcount` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.spisestue_gate_floors` (defined in `packages/apollo_gate_decay.yaml`)
- `input_text.stue_apollo_last_flap` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.stue_gate_flapcount` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.stue_gate_floors` (defined in `packages/apollo_gate_decay.yaml`)
- `input_text.stue_hyggelampe_stedfortraeder_context` (defined in `packages/thread_stedfortraedere.yaml`)
- `input_text.stue_rodret_koerer` (defined in `packages/broadlink_gardiner.yaml`)
- `input_text.stue_rodret_last_curtain` (defined in `packages/broadlink_gardiner.yaml`)
- `input_text.stue_rodret_last_lowered` (defined in `packages/broadlink_gardiner.yaml`)
- `input_text.stue_rodret_seq` (defined in `packages/broadlink_gardiner.yaml`)
- `input_text.stue_spot_1_brugerfarve` (defined in `packages/stue_spots.yaml`)
- `input_text.stue_spot_2_brugerfarve` (defined in `packages/stue_spots.yaml`)
