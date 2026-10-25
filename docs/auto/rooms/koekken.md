# Rum-dossier: koekken

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `koekken, kokken`

## Indhold
- [Automations](koekken.md#automations) (9)
- [Entities](koekken.md#entities) (242)
- [Helpers](koekken.md#helpers) (42)

---

## Automations

### `automations/boern_ankomst_detekter.yaml`

- **Børn: rene skift forbi køkkenet uden kamera-bevægelse → spørg** (line 383, mode=single)

### `automations/gestus_koekken.yaml`

- **Gestus: fingre i køkkenet → køkken-timer** (line 22, mode=single)
  - Oversætter MediaPipe-gestus til husets gestus-events, og kræver at den
- **Gestus: bevægelse i køkkenet → bed kameraet kigge efter fingre** (line 308, mode=single)
  - Den anden halvdel af kamera-indgangen. Add-on'et kigger kun når nogen beder

### `automations/presence_koekken.yaml`

- **Lysnet: Køkken tænd** (line 32, mode=single)
- **Lysnet: Køkken-spots ved madlavning (central zone + lux-gated)** (line 193, mode=single)
  - 2026-06-17 (item 1 user-spec, omlagt): tænd KUN køkken-spots
- **Lysnet: Køkken-spots sluk (køkken tomt)** (line 611, mode=restart)
  - 2026-06-17 rev.2 (user-spec "wider zone only"): spots slukker når man
- **Lysnet: Køkken-spots sluk ved dagslys** (line 764, mode=single)
  - Slukker switch.koekken_spots når køkkenets egen lux har ligget over
- **Lysnet: Køkken-lyskæde sluk (køkken tomt / lys stiger)** (line 828, mode=restart)
- **Lysnet: Køkken-session slut (tomt X min / godnat / væk)** (line 1065, mode=restart)
  - Afslut madlavnings-sessionen (input_boolean.koekken_session_active) når

---

## Entities

### `automation.*`

- `automation.activity_bedroom_only_winddown_soft_fade_af_stue_koekken` — 2 refs in 1 file(s)
- `automation.airbnb_kokken_vedvarende_bevaegelse_active_thread_uafhaengig` — 1 refs in 1 file(s)
- `automation.gestus_bevaegelse_i_kokkenet_bed_kameraet_kigge_efter_fingre` — 1 refs in 1 file(s)
- `automation.gestus_fingre_i_kokkenet_kokken_timer` — 1 refs in 1 file(s)
- `automation.kokken_gestus_start_timer_pa_n_minutter` — 1 refs in 1 file(s)
- `automation.kokken_lyskaede_farve_preview_nar_du_skruer_pa_farven` — 2 refs in 1 file(s)
- `automation.kokken_lyskaede_forste_lys_kulsort_open_plan_bevaegelse` — 2 refs in 2 file(s)
- `automation.kokken_radar_sa_en_krop_som_kameraet_ikke_kunne_se_tael_den` — 1 refs in 1 file(s)
- `automation.lysnet_kokken_spots_sluk_ved_dagslys` — 1 refs in 1 file(s)
- `automation.lysnet_kokken_taend` — 4 refs in 4 file(s)
- `automation.stemme_talt_kommando_fra_kokken_kameraet` — 1 refs in 1 file(s)

### `binary_sensor.*`

- `binary_sensor.filmmoerke_koekken` — 6 refs in 2 file(s)
- `binary_sensor.koekken_apollo_afstand_jitter` — 1 refs in 1 file(s)
- `binary_sensor.koekken_apollo_bevaegelse_frisk` — 3 refs in 2 file(s)
- `binary_sensor.koekken_apollo_central_zone` — 5 refs in 2 file(s)
- `binary_sensor.koekken_apollo_central_zone_filtered` — 4 refs in 1 file(s)
- `binary_sensor.koekken_apollo_frossen_ghost` — 6 refs in 4 file(s)
- `binary_sensor.koekken_apollo_naer_bekraeftet` — 2 refs in 1 file(s)
- `binary_sensor.koekken_apollo_naer_kandidat` — 4 refs in 1 file(s)
- `binary_sensor.koekken_apollo_occupancy` — 33 refs in 18 file(s)
- `binary_sensor.koekken_apollo_occupancy_filtered` — 110 refs in 43 file(s)
- `binary_sensor.koekken_apollo_online` — 2 refs in 1 file(s)
- `binary_sensor.koekken_apollo_radar_moving_target` — 19 refs in 12 file(s)
- `binary_sensor.koekken_apollo_radar_still_target` — 2 refs in 2 file(s)
- `binary_sensor.koekken_apollo_radar_zone_1_occupancy` — 2 refs in 2 file(s)
- `binary_sensor.koekken_apollo_radar_zone_2_occupancy` — 2 refs in 2 file(s)
- `binary_sensor.koekken_apollo_radar_zone_3_occupancy` — 2 refs in 2 file(s)
- `binary_sensor.koekken_apollo_still_bekraeftet` — 1 refs in 1 file(s)
- `binary_sensor.koekken_arbejdslys` — 8 refs in 3 file(s)
- `binary_sensor.koekken_bevaegelse_nylig` — 5 refs in 2 file(s)
- `binary_sensor.koekken_bevaegelse_raa` — 2 refs in 1 file(s)
- `binary_sensor.koekken_dvale_vidne` — 2 refs in 2 file(s)
- `binary_sensor.koekken_hjemkomstlys` — 1 refs in 1 file(s)
- `binary_sensor.koekken_kamera_krop` — 9 refs in 5 file(s)
- `binary_sensor.koekken_kamera_krop_gyldig` — 2 refs in 2 file(s)
- `binary_sensor.koekken_kamera_vaagen` — 6 refs in 3 file(s)
- `binary_sensor.koekken_lys_on_effektiv` — 2 refs in 2 file(s)
- `binary_sensor.koekken_lyskaede_laant` — 3 refs in 2 file(s)
- `binary_sensor.koekken_lyskaede_lux_ok` — 6 refs in 4 file(s)
- `binary_sensor.koekken_lyskaede_scene_laan` — 5 refs in 2 file(s)
- `binary_sensor.koekken_maaltidslys` — 7 refs in 3 file(s)
- `binary_sensor.koekken_madlavningslys` — 32 refs in 7 file(s)
- `binary_sensor.koekken_menneske_bevist` — 3 refs in 2 file(s)
- `binary_sensor.koekken_menneske_proof` — 3 refs in 2 file(s)
- `binary_sensor.koekken_menneske_proof_vedvarende` — 1 refs in 1 file(s)
- `binary_sensor.koekken_morgenlys` — 1 refs in 1 file(s)
- `binary_sensor.koekken_naer_menneske` — 4 refs in 1 file(s)
- `binary_sensor.koekken_openplan_kulsort` — 1 refs in 1 file(s)

### `counter.*`

- `counter.ghost_koekken` — 4 refs in 1 file(s)

### `input_boolean.*`

- `input_boolean.dance_room_koekken` — 8 refs in 5 file(s)
- `input_boolean.koekken_blik_arm_enabled` — 3 refs in 3 file(s)
- `input_boolean.koekken_cooking_ramp` — 4 refs in 3 file(s)
- `input_boolean.koekken_kamera_krop_enabled` — 7 refs in 5 file(s)
- `input_boolean.koekken_lav_krop_boern_enabled` — 3 refs in 3 file(s)
- `input_boolean.koekken_session_active` — 11 refs in 3 file(s)
- `input_boolean.koekken_stemme_arm_enabled` — 5 refs in 5 file(s)
- `input_boolean.roborock_styrbar_kort_op_koekken` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_koekken` — 1 refs in 1 file(s)

### `input_datetime.*`

- `input_datetime.koekken_lyskaede_cooking_taend_slut` — 5 refs in 3 file(s)
- `input_datetime.koekken_lyskaede_cooking_taend_start` — 5 refs in 3 file(s)
- `input_datetime.koekken_lyskaede_manual_off_at` — 5 refs in 3 file(s)

### `input_number.*`

- `input_number.airbnb_koekken_wake_sustain_sekunder` — 3 refs in 2 file(s)
- `input_number.apollo_led_lux_offset_koekken` — 2 refs in 2 file(s)
- `input_number.koekken_blik_ansigt_score` — 1 refs in 1 file(s)
- `input_number.koekken_blik_frames` — 1 refs in 1 file(s)
- `input_number.koekken_blik_frontal_max` — 1 refs in 1 file(s)
- `input_number.koekken_blik_taerskel_grader` — 2 refs in 2 file(s)
- `input_number.koekken_blik_tale_taerskel_grader` — 1 refs in 1 file(s)
- `input_number.koekken_cooking_aggressiveness` — 2 refs in 2 file(s)
- `input_number.koekken_dvale_vidne_sekunder` — 2 refs in 2 file(s)
- `input_number.koekken_g0_move` — 2 refs in 2 file(s)
- `input_number.koekken_g0_still` — 2 refs in 2 file(s)
- `input_number.koekken_g1_move` — 2 refs in 2 file(s)
- `input_number.koekken_g1_still` — 2 refs in 2 file(s)
- `input_number.koekken_g2_move` — 2 refs in 2 file(s)
- `input_number.koekken_g2_still` — 2 refs in 2 file(s)
- `input_number.koekken_g3_move` — 2 refs in 2 file(s)
- `input_number.koekken_g3_still` — 2 refs in 2 file(s)
- `input_number.koekken_g4_move` — 2 refs in 2 file(s)
- `input_number.koekken_g4_still` — 2 refs in 2 file(s)
- `input_number.koekken_g5_move` — 2 refs in 2 file(s)
- `input_number.koekken_g5_still` — 2 refs in 2 file(s)
- `input_number.koekken_g6_move` — 2 refs in 2 file(s)
- `input_number.koekken_g6_still` — 2 refs in 2 file(s)
- `input_number.koekken_g7_move` — 2 refs in 2 file(s)
- `input_number.koekken_g7_still` — 2 refs in 2 file(s)
- `input_number.koekken_g8_move` — 2 refs in 2 file(s)
- `input_number.koekken_g8_still` — 2 refs in 2 file(s)
- `input_number.koekken_gestus_alarm_sek` — 5 refs in 4 file(s)
- `input_number.koekken_gestus_burst_interval_s` — 5 refs in 4 file(s)
- `input_number.koekken_gestus_puls_pct` — 3 refs in 3 file(s)
- `input_number.koekken_hjemkomstlys_minutter` — 2 refs in 2 file(s)
- `input_number.koekken_kamera_min_lux` — 3 refs in 2 file(s)
- `input_number.koekken_kamera_session_sekunder` — 3 refs in 3 file(s)
- `input_number.koekken_klar_puls_pct` — 3 refs in 2 file(s)
- `input_number.koekken_lav_krop_antal` — 3 refs in 2 file(s)
- `input_number.koekken_lav_krop_vindue_min` — 2 refs in 2 file(s)
- `input_number.koekken_lyskaede_brightness` — 6 refs in 2 file(s)
- `input_number.koekken_lyskaede_cooking_brightness` — 3 refs in 2 file(s)
- `input_number.koekken_lyskaede_cooking_kelvin` — 2 refs in 2 file(s)
- `input_number.koekken_lyskaede_cooking_moerk_brightness` — 2 refs in 2 file(s)
- `input_number.koekken_lyskaede_cooking_morgen_kelvin` — 2 refs in 2 file(s)
- `input_number.koekken_lyskaede_dark_hold_sekunder` — 3 refs in 3 file(s)
- `input_number.koekken_lyskaede_dark_pct` — 4 refs in 3 file(s)
- `input_number.koekken_lyskaede_dark_session_pct` — 3 refs in 3 file(s)
- `input_number.koekken_lyskaede_doed_fade_sekunder` — 3 refs in 3 file(s)
- `input_number.koekken_lyskaede_doed_minutter` — 3 refs in 3 file(s)
- `input_number.koekken_lyskaede_efter_session_minutter` — 5 refs in 3 file(s)
- `input_number.koekken_lyskaede_eget_lys_lx` — 2 refs in 2 file(s)
- `input_number.koekken_lyskaede_fade_ind_hurtig` — 4 refs in 3 file(s)
- `input_number.koekken_lyskaede_fade_ind_langsom` — 6 refs in 3 file(s)
- `input_number.koekken_lyskaede_fade_ned` — 2 refs in 2 file(s)
- `input_number.koekken_lyskaede_foerste_lys_lux` — 3 refs in 3 file(s)
- `input_number.koekken_lyskaede_foerste_lys_pct` — 4 refs in 3 file(s)
- `input_number.koekken_lyskaede_hue` — 8 refs in 3 file(s)
- `input_number.koekken_lyskaede_lux_haard_off` — 7 refs in 4 file(s)
- `input_number.koekken_lyskaede_lux_haard_off_session` — 5 refs in 3 file(s)
- `input_number.koekken_lyskaede_lux_off_minutter` — 4 refs in 3 file(s)
- `input_number.koekken_lyskaede_lux_threshold` — 5 refs in 3 file(s)
- `input_number.koekken_lyskaede_maaltid_kelvin` — 4 refs in 3 file(s)
- `input_number.koekken_lyskaede_maaltid_pct` — 4 refs in 3 file(s)
- `input_number.koekken_lyskaede_moerk_fade_faktor` — 3 refs in 2 file(s)
- `input_number.koekken_lyskaede_preview_sekunder` — 3 refs in 3 file(s)
- `input_number.koekken_lyskaede_saturation` — 8 refs in 3 file(s)
- `input_number.koekken_manual_off_grace_minutes` — 5 refs in 4 file(s)
- `input_number.koekken_menneske_bevist_min_sekunder` — 2 refs in 2 file(s)
- `input_number.koekken_menneske_bevist_minutter` — 2 refs in 2 file(s)
- `input_number.koekken_naer_ghost_sekunder` — 3 refs in 2 file(s)
- `input_number.koekken_naer_pulser_min` — 2 refs in 2 file(s)
- `input_number.koekken_session_aktiv_minutter` — 4 refs in 3 file(s)
- `input_number.koekken_session_lux_bonus_pct` — 3 refs in 2 file(s)
- `input_number.koekken_session_relight_seconds` — 3 refs in 2 file(s)
- `input_number.koekken_session_timeout_minutes` — 5 refs in 3 file(s)
- `input_number.koekken_skift_min_afstand_sek` — 2 refs in 2 file(s)
- `input_number.koekken_skift_min_lux` — 2 refs in 2 file(s)
- `input_number.koekken_skift_min_segment_sek` — 2 refs in 2 file(s)
- `input_number.koekken_spots_dagslys_sluk_lux` — 6 refs in 4 file(s)
- `input_number.koekken_spots_hang_pct` — 2 refs in 2 file(s)
- `input_number.koekken_spots_lux_threshold` — 6 refs in 4 file(s)
- `input_number.koekken_spots_off_seconds` — 10 refs in 3 file(s)
- `input_number.koekken_spots_ramp_pct` — 2 refs in 2 file(s)
- `input_number.koekken_still_ghost_sekunder` — 4 refs in 2 file(s)
- `input_number.koekken_taend_bevaegelse_min_sekunder` — 3 refs in 2 file(s)
- `input_number.koekken_taend_bevaegelse_sekunder` — 4 refs in 3 file(s)
- `input_number.maaltid_stovsug_koekken_tomt_minutter` — 3 refs in 2 file(s)

### `input_select.*`

- `input_select.room_mode_koekken` — 36 refs in 22 file(s)

### `input_text.*`

- `input_text.koekken_apollo_last_flap` — 1 refs in 1 file(s)
- `input_text.koekken_gate_flapcount` — 1 refs in 1 file(s)
- `input_text.koekken_gate_floors` — 1 refs in 1 file(s)
- `input_text.koekken_gestus_alarm` — 19 refs in 7 file(s)
- `input_text.koekken_gestus_alarm_rum` — 5 refs in 1 file(s)
- `input_text.koekken_gestus_nedtael` — 17 refs in 4 file(s)
- `input_text.koekken_gestus_pending` — 7 refs in 3 file(s)
- `input_text.koekken_lav_krop_spor` — 6 refs in 2 file(s)
- `input_text.koekken_lyskaede_haand_ts` — 6 refs in 3 file(s)
- `input_text.koekken_lyskaede_preview` — 10 refs in 3 file(s)
- `input_text.koekken_stemme_arm_gestus` — 4 refs in 3 file(s)
- `input_text.koekken_stemme_arm_run` — 2 refs in 1 file(s)
- `input_text.koekken_stemme_armeret_at` — 4 refs in 2 file(s)

### `light.*`

- `light.koekken_apollo_rgb_light` — 13 refs in 5 file(s)
- `light.koekken_loft` — 2 refs in 2 file(s)
- `light.koekken_lyskaede` — 188 refs in 43 file(s)
- `light.koekken_room` — 11 refs in 8 file(s)

### `number.*`

- `number.koekken_apollo_g0_move_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g0_still_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g1_move_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g1_still_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g2_move_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g2_still_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g3_move_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g3_still_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g4_move_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g4_still_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g5_move_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_g5_still_threshold` — 1 refs in 1 file(s)
- `number.koekken_apollo_radar_timeout` — 3 refs in 2 file(s)

### `scene.*`

- `scene.koekken_gestus_alarm_foer` — 3 refs in 1 file(s)
- `scene.koekken_lyskaede_preview_foer` — 2 refs in 1 file(s)

### `script.*`

- `script.koekken_apollo_apply_all_gates` — 1 refs in 1 file(s)
- `script.koekken_gestus_alarm_burst` — 3 refs in 1 file(s)
- `script.koekken_gestus_alarm_stop` — 5 refs in 1 file(s)
- `script.koekken_gestus_burst_once` — 5 refs in 1 file(s)
- `script.koekken_gestus_kvittering` — 3 refs in 2 file(s)
- `script.koekken_gestus_saet` — 11 refs in 2 file(s)
- `script.koekken_gestus_set_signal` — 2 refs in 2 file(s)
- `script.koekken_gestus_telefon_alarm` — 2 refs in 1 file(s)
- `script.koekken_gestus_telefon_timer` — 2 refs in 1 file(s)
- `script.koekken_lyskaede_maal` — 12 refs in 6 file(s)
- `script.koekken_lyskaede_preview_slut` — 2 refs in 1 file(s)
- `script.koekken_lyskaede_signal` — 15 refs in 6 file(s)
- `script.koekken_skift_registrer` — 1 refs in 1 file(s)
- `script.koekken_stemme_kvittering` — 2 refs in 2 file(s)
- `script.koekken_timer_stemme` — 2 refs in 1 file(s)
- `script.roborock_grundig_koekken` — 1 refs in 1 file(s)
- `script.roborock_hurtig_koekken` — 1 refs in 1 file(s)

### `sensor.*`

- `sensor.koekken_aktiv_15m` — 5 refs in 2 file(s)
- `sensor.koekken_apollo_bevaegelse_5min` — 2 refs in 2 file(s)
- `sensor.koekken_apollo_esp_temperature` — 4 refs in 3 file(s)
- `sensor.koekken_apollo_ghost_flaps_1h` — 3 refs in 2 file(s)
- `sensor.koekken_apollo_lux` — 9 refs in 6 file(s)
- `sensor.koekken_apollo_radar_move_energy` — 1 refs in 1 file(s)
- `sensor.koekken_apollo_radar_moving_distance` — 6 refs in 3 file(s)
- `sensor.koekken_apollo_radar_still_distance` — 4 refs in 3 file(s)
- `sensor.koekken_apollo_radar_still_energy` — 1 refs in 1 file(s)
- `sensor.koekken_apollo_temperature` — 2 refs in 2 file(s)
- `sensor.koekken_bevaegelse_5min_sekunder` — 3 refs in 3 file(s)
- `sensor.koekken_bevaegelse_akkumuleret` — 1 refs in 1 file(s)
- `sensor.koekken_blik_sidst` — 1 refs in 1 file(s)
- `sensor.koekken_cooking_threshold_min` — 4 refs in 1 file(s)
- `sensor.koekken_dagslys_lx` — 24 refs in 7 file(s)
- `sensor.koekken_dagslys_sample` — 4 refs in 3 file(s)
- `sensor.koekken_felt_aktiv_30m` — 2 refs in 1 file(s)
- `sensor.koekken_kamera_blik` — 3 refs in 1 file(s)
- `sensor.koekken_kamera_vagt` — 2 refs in 2 file(s)
- `sensor.koekken_lux_effektiv` — 7 refs in 3 file(s)
- `sensor.koekken_lux_reel` — 9 refs in 4 file(s)
- `sensor.koekken_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.koekken_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.koekken_lyskaede_cooking_kelvin_effektiv` — 3 refs in 1 file(s)
- `sensor.koekken_lyskaede_ejer` — 17 refs in 7 file(s)
- `sensor.koekken_lyskaede_fade_hurtig_effektiv` — 9 refs in 4 file(s)
- `sensor.koekken_lyskaede_fade_langsom_effektiv` — 7 refs in 4 file(s)
- `sensor.koekken_lyskaede_kurve_slut` — 2 refs in 2 file(s)
- `sensor.koekken_lyskaede_sluk_fade` — 2 refs in 1 file(s)
- `sensor.koekken_lyskaede_target_brightness` — 8 refs in 4 file(s)
- `sensor.koekken_naer_pulser` — 1 refs in 1 file(s)
- `sensor.koekken_occupancy_recent` — 3 refs in 1 file(s)
- `sensor.koekken_skift_segment` — 9 refs in 2 file(s)
- `sensor.koekken_spots_dagslys_sluk_effektiv` — 6 refs in 3 file(s)
- `sensor.koekken_spots_lux_gate_effektiv` — 10 refs in 5 file(s)
- `sensor.koekken_stemme_kommando` — 6 refs in 1 file(s)
- `sensor.koekken_stemme_sidst` — 4 refs in 3 file(s)
- `sensor.koekken_trigger_log` — 4 refs in 2 file(s)
- `sensor.radiator_effekt_kokken` — 2 refs in 2 file(s)
- `sensor.thread_router_koekken_energy` — 1 refs in 1 file(s)
- `sensor.thread_router_koekken_power` — 1 refs in 1 file(s)
- `sensor.thread_router_koekken_voltage` — 1 refs in 1 file(s)

### `switch.*`

- `switch.koekken_apollo_ld2410_bluetooth` — 1 refs in 1 file(s)
- `switch.koekken_apollo_radar_engineering_mode` — 1 refs in 1 file(s)
- `switch.koekken_spots` — 46 refs in 19 file(s)
- `switch.thread_router_koekken` — 5 refs in 3 file(s)

### `timer.*`

- `timer.koekken_gestus` — 32 refs in 6 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.koekken_kamera_krop_enabled` (defined in `packages/koekken_kamera_krop.yaml`)
- `input_boolean.koekken_session_active` (defined in `packages/koekken_cooking.yaml`)
- `input_boolean.koekken_stemme_arm_enabled` (defined in `packages/koekken_stemme_arm.yaml`)
- `input_boolean.roborock_styrbar_kort_op_koekken` (defined in `packages/roborock_styrbar.yaml`)

### `input_datetime.*`

- `input_datetime.koekken_apollo_flap_last_bump` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.koekken_apollo_occ_since` (defined in `packages/apollo_latch_detect.yaml`)
- `input_datetime.koekken_flapcount_since` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.koekken_lyskaede_manual_off_at` (defined in `packages/koekken_lyskaede.yaml`)
- `input_datetime.styrbar_last_press_koekken` (defined in `packages/room_modes.yaml`)

### `input_number.*`

- `input_number.airbnb_koekken_wake_sustain_sekunder` (defined in `packages/airbnb_koekken_wake.yaml`)
- `input_number.koekken_cooking_aggressiveness` (defined in `packages/koekken_cooking.yaml`)
- `input_number.koekken_dvale_vidne_sekunder` (defined in `packages/koekken_dvale_vidne.yaml`)
- `input_number.koekken_g0_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g0_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g1_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g1_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g2_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g2_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g3_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g3_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g4_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g4_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g5_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g5_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g6_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g6_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g7_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g7_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g8_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_g8_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.koekken_kamera_session_sekunder` (defined in `packages/koekken_kamera_krop.yaml`)
- `input_number.koekken_klar_puls_pct` (defined in `packages/koekken_lyskaede.yaml`)

### `input_select.*`

- `input_select.room_mode_koekken` (defined in `packages/room_modes.yaml`)

### `input_text.*`

- `input_text.koekken_apollo_last_flap` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.koekken_gate_flapcount` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.koekken_gate_floors` (defined in `packages/apollo_gate_decay.yaml`)
- `input_text.koekken_gestus_pending` (defined in `packages/koekken_gestus_timer.yaml`)
- `input_text.koekken_lav_krop_spor` (defined in `packages/koekken_kamera_krop.yaml`)
- `input_text.koekken_lyskaede_haand_ts` (defined in `packages/koekken_lyskaede.yaml`)
- `input_text.koekken_lyskaede_preview` (defined in `packages/koekken_lyskaede.yaml`)
- `input_text.koekken_stemme_arm_gestus` (defined in `packages/koekken_stemme_arm.yaml`)

### `timer.*`

- `timer.koekken_gestus` (defined in `packages/koekken_gestus_timer.yaml`)
