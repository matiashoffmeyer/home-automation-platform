# Rum-dossier: sovevaerelse

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `sovevaerelse, sove`

## Indhold
- [Automations](sovevaerelse.md#automations) (37)
- [Entities](sovevaerelse.md#entities) (225)
- [Helpers](sovevaerelse.md#helpers) (83)

---

## Automations

### `automations/bedroom_night_guard.yaml`

- **Sikkerhed: Soveværelser ALDRIG auto-fuldt-lys om natten (refleks-lås)** (line 24, mode=parallel)
  - Snapper et soveværelse-lys tilbage til nat-tilstand hvis det auto-ramper OP
- **Sikkerhed: Stamp soveværelse-knap nød-intent (FØR lys-logik)** (line 165, mode=parallel)
  - Stempler input_datetime.bedroom_styrbar_intent_at øjeblikkeligt når en

### `automations/godmorgen_godnat.yaml`

- **Sove-knap: kort ned (godnat hele huset, 60s fade)** (line 81, mode=restart)
  - Somrig short release endpoint=2 (kort ned) i soveværelse.
- **Sove-knap: kort op (aften=toggle hygge / dag=godmorgen)** (line 163, mode=restart)
  - Somrig short release endpoint=1 (kort op) i soveværelse.
- **Sove: frigiv aften-hygge hold kl 04:00 (Manual→Auto)** (line 397, mode=single)
- **Sove-knap: lang op (sove 80% + gardin helt op)** (line 434, mode=restart)
  - Somrig long_press endpoint=1 (long op) i soveværelse. Sove til 80%
- **Godmorgen: Auto-off ved akkumuleret aktivitet + soveværelse tomt** (line 1010, mode=single)
  - Sustained fælles-rum-aktivitet over slider-threshold MENS voksen-
- **Godnat: Børn oppe i stuen (forældre sover stadig)** (line 1148, mode=single)
  - Weekend mornings: kids enter stue while godnat is still active.
- **Soveværelse: sengelys ved sengetid (dim, før godnat)** (line 1320, mode=single)
  - Tænder soveloftet svagt+varmt når en voksen går i seng om aftenen (før
- **Soveværelse: voksen-afgang sweep (retning)** (line 1461, mode=queued)
  - Skriver input_text.sove_voksen_afgang når sove-Apolloens moving_distance

### `automations/godnat_auto_declare.yaml`

- **Godnat: auto-declare efter 2t kun-soveværelse presence** (line 35, mode=single)
  - Auto-fallback hvis Somrig godnat-knap ikke trykkes. Kører script.godnat

### `automations/light_power_recovery.yaml`

- **Sovelys: post-strom -> sun-aware default** (line 203, mode=single)
  - Sove bulb wake fra wall-switch eller mesh-flicker → fader til sun-aware

### `automations/morning_curtains.yaml`

- **Gardiner: Åbn sove-gardin om morgenen når soveværelset er tomt** (line 103, mode=single)
  - 2026-07-28 (item 7 user-spec: "åbner sove-gardinet automatisk om morgenen?

### `automations/morning_lights_sanity_check.yaml`

- **Morgen: Sove lys auto-sluk (lyst eller tomt)** (line 179, mode=single)
  - Slukker sove_loft hvis (a) Apollo lux > 50 i 5 min ELLER (b) occupancy
- **Morgen: Sove lys fast-off ved LUX surge (gardin rolled)** (line 404, mode=single)
  - 5 sek above 80*factor → fade off. Reagerer hurtigt naar user manuelt

### `automations/presence_lights.yaml`

- **Lysnet: Soveværelse tænd ved LUX-fald** (line 462, mode=single)
- **Lysnet: Soveværelse sluk ved LUX-stigning** (line 943, mode=single)
  - Dagslys tilbage i soveværelset mens sove-pendlen står tændt — blid fade off.

### `automations/presence_sovevaerelse.yaml`

- **Lysnet: Soveværelse tænd** (line 11, mode=single)
- **Lysnet: Soveværelse gradvis sluk** (line 249, mode=restart)
  - 5-minute absence rule (private-rum standard). Hold-alive modes respected. Fade 30s.
- **Lysnet: Soveværelse no-motion watchdog (spøgelses-still)** (line 343, mode=single)
  - Ingen moving-target i slider-minutter mens lyset er tændt → sluk, uanset
- **Lysnet: Soveværelse hurtig sluk når tomt + dagslys** (line 424, mode=restart)
  - 60-sek empty + lux>40 + morning → fade off sove. Catches scenarie hvor
- **Lysnet: Soveværelse gang-early-detect pre-lys** (line 533, mode=single)
  - Bevægelse i entréen tænder sove-lyset svagt+varmt når mørkt + ikke godnat,
- **Lysnet: Soveværelse gang-early-detect hurtig-sluk** (line 665, mode=restart)
  - Entré i ro + sove stadig på pre-lys + rummet tomt (Apollo occupancy off) →
- **Lysnet: Soveværelse ryd approach-flag ved lys-sluk** (line 701, mode=single)
- **Lysnet: Soveværelse hygge-fade (ligger stille)** (line 744, mode=restart)
  - Still-target on + ingen bevægelse i settle_delay = man ligger i sengen →

### `automations/somrig_buttons.yaml`

- **Somrig Soveværelse: gardin op (tryk) / stop hvis på vej op** (line 80, mode=queued)
- **Somrig Soveværelse: gardin ned (tryk) / stop hvis på vej ned** (line 110, mode=queued)

### `automations/sove_apollo_morning_reporting.yaml`

- **Sove Apollo: DB reporting OFF (06:00 — morning responsiveness)** (line 24, mode=single)
  - 06:00 daglig — slå reduce_db_reporting OFF for sove Apollo så lux/temp/
- **Sove Apollo: DB reporting ON (07:30 — post wake-up)** (line 52, mode=single)
  - 07:30 daglig — slå reduce_db_reporting tilbage ON. Spare ESP/network

### `automations/sove_rodret_button.yaml`

- **Sove RODRET: kort-op → tænd lux-tilpasset** (line 27, mode=single)
  - Kort tryk på TOP af RODRET (56:25:d3:d2:0b:bd:62:42) → tænd sove-pendlen på
- **Sove RODRET: lang-op → 100 %** (line 71, mode=single)
  - Hold TOP af RODRET (move_with_on_off) → skru sove-pendlen op til 100 %.
- **Sove RODRET: ned (kort/lang) → sluk** (line 104, mode=single)
  - Kort-ned (off) ELLER lang-ned (move) på RODRET → sluk sove-pendlen. Sætter

### `automations/styrbar_rooms.yaml`

- **Styrbar Sove: L/R grace 2-sek efter release** (line 781, mode=restart)

### `automations/styrbar_sove_warmth.yaml`

- **Styrbar Sove: varme ét skridt (L/R klik)** (line 51, mode=queued)
- **Styrbar Sove: varme-loop (L/R hold)** (line 118, mode=parallel)
- **Styrbar Sove: stop varme-loop (L/R release)** (line 198, mode=single)

### `automations/wakeup_post_sluk.yaml`

- **Vækning: Sove sluk/dim 15 min efter wakeup (smart LUX)** (line 19, mode=single)
  - 15 min efter godnat_voksne_active flipper off (= wakeup completer eller

---

## Entities

### `automation.*`

- `automation.god_morgen_sovevaerelse_gardin_abner_kl_09_00_weekend` — 2 refs in 1 file(s)
- `automation.godnat_auto_declare_efter_2t_kun_sovevaerelse_presence` — 3 refs in 2 file(s)
- `automation.godnat_born_oppe_i_stuen_foraeldre_sover_stadig` — 2 refs in 1 file(s)
- `automation.lysnet_sovevaerelse_gang_early_detect_hurtig_sluk` — 1 refs in 1 file(s)
- `automation.lysnet_sovevaerelse_sluk_ved_lux_stigning` — 1 refs in 1 file(s)
- `automation.lysnet_sovevaerelse_taend` — 1 refs in 1 file(s)
- `automation.vaekning_sove_sluk_dim_15_min_efter_wakeup_smart_lux` — 2 refs in 1 file(s)

### `binary_sensor.*`

- `binary_sensor.dark_mode_sove` — 2 refs in 2 file(s)
- `binary_sensor.filmmoerke_sove` — 11 refs in 6 file(s)
- `binary_sensor.mood_pause_sovevaerelse` — 3 refs in 2 file(s)
- `binary_sensor.parasoll_sovedoer` — 13 refs in 3 file(s)
- `binary_sensor.sove_aften_laasevindue` — 2 refs in 2 file(s)
- `binary_sensor.sove_alarm_morgen_lys` — 14 refs in 4 file(s)
- `binary_sensor.sove_alarm_morgen_to_oppe` — 19 refs in 6 file(s)
- `binary_sensor.sove_alarm_morgen_vindue` — 8 refs in 4 file(s)
- `binary_sensor.sove_alle_voksne_i_seng` — 2 refs in 1 file(s)
- `binary_sensor.sove_doer_moerkhold` — 7 refs in 4 file(s)
- `binary_sensor.sove_gardin_aftenluk_vindue` — 5 refs in 3 file(s)
- `binary_sensor.sove_gardin_bad_klar` — 13 refs in 4 file(s)
- `binary_sensor.sove_moerke_godnat_kandidat` — 2 refs in 1 file(s)
- `binary_sensor.sove_morgen_moerklagt` — 7 refs in 5 file(s)
- `binary_sensor.sove_radar_frossen` — 3 refs in 3 file(s)
- `binary_sensor.sove_retur_til_seng` — 7 refs in 4 file(s)
- `binary_sensor.sovevaerelse_apollo_occupancy` — 90 refs in 45 file(s)
- `binary_sensor.sovevaerelse_apollo_online` — 1 refs in 1 file(s)
- `binary_sensor.sovevaerelse_apollo_radar_moving_target` — 18 refs in 10 file(s)
- `binary_sensor.sovevaerelse_apollo_radar_still_target` — 21 refs in 9 file(s)
- `binary_sensor.sovevaerelse_apollo_radar_zone_1_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.sovevaerelse_apollo_radar_zone_2_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.sovevaerelse_apollo_radar_zone_3_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.sovevaerelse_dvale_vidne` — 10 refs in 6 file(s)
- `binary_sensor.sovevaerelse_empty_effective` — 2 refs in 1 file(s)
- `binary_sensor.sovevaerelse_lys_on_effektiv` — 1 refs in 1 file(s)
- `binary_sensor.sovevaerelse_morgen_beskyttelse_aktiv` — 38 refs in 16 file(s)
- `binary_sensor.sovevaerelse_voksne_oppe` — 5 refs in 3 file(s)

### `button.*`

- `button.gardin_sovevaerelse_delete_all_limits` — 1 refs in 1 file(s)
- `button.gardin_sovevaerelse_set_lower_limit` — 1 refs in 1 file(s)
- `button.gardin_sovevaerelse_set_upper_limit` — 1 refs in 1 file(s)
- `button.sovevaerelse_apollo_restart_radar` — 2 refs in 2 file(s)

### `counter.*`

- `counter.ghost_sovevaerelse` — 4 refs in 1 file(s)

### `cover.*`

- `cover.gardin_sovevaerelse` — 98 refs in 25 file(s)

### `input_boolean.*`

- `input_boolean.airbnb_velkomst_move_sove` — 3 refs in 2 file(s)
- `input_boolean.boernevaerelse_gaest_sover` — 20 refs in 7 file(s)
- `input_boolean.dark_mode_kun_sove` — 6 refs in 2 file(s)
- `input_boolean.notif_sove_radar_airbnb` — 1 refs in 1 file(s)
- `input_boolean.notif_sove_radar_parent_b` — 1 refs in 1 file(s)
- `input_boolean.notif_sove_radar_enabled` — 1 refs in 1 file(s)
- `input_boolean.notif_sove_radar_hjemme` — 1 refs in 1 file(s)
- `input_boolean.notif_sove_radar_parent_a` — 1 refs in 1 file(s)
- `input_boolean.putning_sove_active` — 26 refs in 13 file(s)
- `input_boolean.roborock_styrbar_kort_op_sovevaerelse` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_sovevaerelse` — 1 refs in 1 file(s)
- `input_boolean.sove_approach_lit` — 14 refs in 3 file(s)
- `input_boolean.sove_evening_hold` — 7 refs in 3 file(s)
- `input_boolean.sove_gardin_aftenluk_enabled` — 6 refs in 5 file(s)
- `input_boolean.sove_gardin_bad_foerste_besoeg_ovre` — 13 refs in 4 file(s)
- `input_boolean.sove_gardin_op_afventer` — 8 refs in 2 file(s)
- `input_boolean.sove_lyskaede_enabled` — 6 refs in 4 file(s)
- `input_boolean.sove_lyskaede_manuel_slukket` — 7 refs in 2 file(s)
- `input_boolean.sove_morgen_anden_krop` — 5 refs in 2 file(s)
- `input_boolean.sove_radar_watchdog_enabled` — 2 refs in 2 file(s)
- `input_boolean.sove_retur_enabled` — 2 refs in 2 file(s)
- `input_boolean.sove_seng_taeller_enabled` — 4 refs in 2 file(s)
- `input_boolean.sovevaerelse_manual_off_lock` — 19 refs in 8 file(s)
- `input_boolean.sovevaerelse_morgen_beskyttelse_enabled` — 6 refs in 5 file(s)
- `input_boolean.styrbar_lr_grace_sovevaerelse` — 3 refs in 2 file(s)
- `input_boolean.styrbar_lr_holding_sovevaerelse` — 4 refs in 2 file(s)
- `input_boolean.styrbar_up_holding_sovevaerelse` — 1 refs in 1 file(s)

### `input_datetime.*`

- `input_datetime.gardin_manual_down_sove` — 9 refs in 6 file(s)
- `input_datetime.notif_sove_radar_slut` — 1 refs in 1 file(s)
- `input_datetime.notif_sove_radar_start` — 1 refs in 1 file(s)
- `input_datetime.sove_aften_graense` — 7 refs in 5 file(s)
- `input_datetime.sove_alarm_morgen_2p_at` — 9 refs in 3 file(s)
- `input_datetime.sove_apollo_occ_since` — 3 refs in 2 file(s)
- `input_datetime.sove_manual_off_lock_start` — 8 refs in 4 file(s)
- `input_datetime.sove_morgen_afgang_at` — 15 refs in 5 file(s)
- `input_datetime.sove_morgen_doer_aabnet_at` — 4 refs in 2 file(s)
- `input_datetime.sove_morgen_doer_lukket_at` — 2 refs in 1 file(s)
- `input_datetime.sove_radar_watchdog_last_probe` — 2 refs in 1 file(s)
- `input_datetime.sove_radar_watchdog_last_restart` — 2 refs in 1 file(s)
- `input_datetime.sove_seng_sidst_talt` — 6 refs in 1 file(s)
- `input_datetime.sove_snooze_until` — 10 refs in 3 file(s)
- `input_datetime.sove_winddown_at` — 12 refs in 3 file(s)
- `input_datetime.styrbar_last_press_sovevaerelse` — 11 refs in 7 file(s)

### `input_number.*`

- `input_number.airbnb_natmode_sove_accum_min` — 3 refs in 2 file(s)
- `input_number.apollo_led_lux_offset_sove` — 2 refs in 2 file(s)
- `input_number.godmorgen_sove_afgang_vindue_min` — 2 refs in 2 file(s)
- `input_number.hoejttaler_sovemusik_minutter` — 2 refs in 2 file(s)
- `input_number.radiator_trin_sove` — 2 refs in 2 file(s)
- `input_number.sove_alarm_morgen_vindue_minutter` — 3 refs in 3 file(s)
- `input_number.sove_dvale_vidne_sekunder` — 2 refs in 2 file(s)
- `input_number.sove_g0_move` — 2 refs in 2 file(s)
- `input_number.sove_g0_still` — 2 refs in 2 file(s)
- `input_number.sove_g1_move` — 2 refs in 2 file(s)
- `input_number.sove_g1_still` — 2 refs in 2 file(s)
- `input_number.sove_g2_move` — 2 refs in 2 file(s)
- `input_number.sove_g2_still` — 2 refs in 2 file(s)
- `input_number.sove_g3_move` — 2 refs in 2 file(s)
- `input_number.sove_g3_still` — 2 refs in 2 file(s)
- `input_number.sove_g4_move` — 2 refs in 2 file(s)
- `input_number.sove_g4_still` — 2 refs in 2 file(s)
- `input_number.sove_g5_move` — 2 refs in 2 file(s)
- `input_number.sove_g5_still` — 2 refs in 2 file(s)
- `input_number.sove_g6_move` — 1 refs in 1 file(s)
- `input_number.sove_g6_still` — 1 refs in 1 file(s)
- `input_number.sove_g7_move` — 1 refs in 1 file(s)
- `input_number.sove_g7_still` — 1 refs in 1 file(s)
- `input_number.sove_g8_move` — 1 refs in 1 file(s)
- `input_number.sove_g8_still` — 1 refs in 1 file(s)
- `input_number.sove_gardin_aftenluk_offset_min` — 6 refs in 4 file(s)
- `input_number.sove_gardin_bad_min_aktivitet_minutter` — 5 refs in 3 file(s)
- `input_number.sove_gardin_bad_tomt_minutter` — 5 refs in 3 file(s)
- `input_number.sove_gardin_privacy_min_sol_elevation` — 5 refs in 4 file(s)
- `input_number.sove_godmorgen_fade_sekunder` — 3 refs in 3 file(s)
- `input_number.sove_hygge_brightness` — 2 refs in 2 file(s)
- `input_number.sove_lyskaede_min_loft_pct` — 3 refs in 3 file(s)
- `input_number.sove_lyskaede_presence_minutter` — 3 refs in 3 file(s)
- `input_number.sove_moerke_godnat_minutter` — 5 refs in 3 file(s)
- `input_number.sove_morgen_2p_doerzone_cm` — 9 refs in 5 file(s)
- `input_number.sove_morgen_afgang_entre_sekunder` — 3 refs in 3 file(s)
- `input_number.sove_morgen_anden_krop_minutter` — 4 refs in 3 file(s)
- `input_number.sove_morgen_doer_aaben_minutter` — 5 refs in 3 file(s)
- `input_number.sove_radar_frozen_minutes` — 2 refs in 2 file(s)
- `input_number.sove_radar_probe_seconds` — 3 refs in 2 file(s)
- `input_number.sove_radar_reprobe_minutes` — 2 refs in 2 file(s)
- `input_number.sove_radar_watchdog_cooldown_minutes` — 2 refs in 2 file(s)
- `input_number.sove_retur_min_sekunder` — 3 refs in 3 file(s)
- `input_number.sove_retur_seng_cm` — 5 refs in 5 file(s)
- `input_number.sove_retur_vindue_sekunder` — 4 refs in 3 file(s)
- `input_number.sove_seng_bliv_sekunder` — 2 refs in 2 file(s)
- `input_number.sove_seng_personer` — 17 refs in 2 file(s)
- `input_number.sove_seng_still_sekunder` — 2 refs in 2 file(s)
- `input_number.sove_sengelys_brightness` — 2 refs in 2 file(s)
- `input_number.sove_snooze_knap_minutter` — 3 refs in 3 file(s)
- `input_number.sove_snooze_timer` — 4 refs in 3 file(s)
- `input_number.sove_sol_blast_lux` — 6 refs in 3 file(s)
- `input_number.sovevaerelse_alarm_morgen_lux` — 4 refs in 4 file(s)
- `input_number.sovevaerelse_cozy_brightness` — 4 refs in 2 file(s)
- `input_number.sovevaerelse_cozy_fade_minutes` — 3 refs in 2 file(s)
- `input_number.sovevaerelse_cozy_warmth_k` — 4 refs in 3 file(s)
- `input_number.sovevaerelse_dagslys_sluk_lux` — 3 refs in 2 file(s)
- `input_number.sovevaerelse_default_warmth_k` — 5 refs in 3 file(s)
- `input_number.sovevaerelse_early_brightness` — 2 refs in 2 file(s)
- `input_number.sovevaerelse_early_lux_threshold` — 3 refs in 3 file(s)
- `input_number.sovevaerelse_gardin_morgen_tom_minutter` — 4 refs in 3 file(s)
- `input_number.sovevaerelse_lux_threshold` — 3 refs in 3 file(s)
- `input_number.sovevaerelse_manual_on_hold_hours` — 2 refs in 2 file(s)
- `input_number.sovevaerelse_no_motion_off_minutes` — 6 refs in 2 file(s)
- `input_number.sovevaerelse_settle_delay_seconds` — 3 refs in 3 file(s)
- `input_number.sovevaerelse_start_brightness` — 3 refs in 3 file(s)
- `input_number.styrbar_ct_kelvin_sove` — 4 refs in 1 file(s)
- `input_number.styrbar_sove_ct_cool_k` — 2 refs in 1 file(s)
- `input_number.styrbar_sove_ct_step_k` — 2 refs in 1 file(s)
- `input_number.styrbar_sove_ct_warm_k` — 2 refs in 1 file(s)

### `input_select.*`

- `input_select.room_mode_sovevaerelse` — 39 refs in 20 file(s)

### `input_text.*`

- `input_text.sove_apollo_last_flap` — 1 refs in 1 file(s)
- `input_text.sove_gate_flapcount` — 1 refs in 1 file(s)
- `input_text.sove_gate_floors` — 1 refs in 1 file(s)
- `input_text.sove_voksen_afgang` — 7 refs in 1 file(s)

### `light.*`

- `light.sove_lyskaede` — 24 refs in 11 file(s)
- `light.sovevaerelse_all` — 17 refs in 9 file(s)
- `light.sovevaerelse_apollo_rgb_light` — 13 refs in 8 file(s)
- `light.sovevaerelse_loft` — 11 refs in 7 file(s)

### `number.*`

- `number.sovevaerelse_apollo_g0_move_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g0_still_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g1_move_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g1_still_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g2_move_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g2_still_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g3_move_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g3_still_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g4_move_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g4_still_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g5_move_threshold` — 1 refs in 1 file(s)
- `number.sovevaerelse_apollo_g5_still_threshold` — 1 refs in 1 file(s)

### `script.*`

- `script.gaest_sover_sluk` — 3 refs in 3 file(s)
- `script.roborock_grundig_sovevaerelse` — 1 refs in 1 file(s)
- `script.roborock_hurtig_sovevaerelse` — 1 refs in 1 file(s)
- `script.sove_apollo_apply_all_gates` — 1 refs in 1 file(s)
- `script.sove_gardin_op` — 18 refs in 9 file(s)
- `script.sove_gardin_privacy_morgen` — 2 refs in 1 file(s)
- `script.sove_godmorgen_fade` — 5 refs in 2 file(s)
- `script.sove_radar_hang_probe` — 1 refs in 1 file(s)
- `script.sove_seng_facit` — 4 refs in 1 file(s)
- `script.sove_snooze_clear` — 2 refs in 1 file(s)
- `script.sove_snooze_kort` — 1 refs in 1 file(s)
- `script.sove_snooze_start` — 1 refs in 1 file(s)

### `select.*`

- `select.gardin_sovevaerelse_motor_direction` — 1 refs in 1 file(s)

### `sensor.*`

- `sensor.gardin_sovevaerelse_battery` — 2 refs in 2 file(s)
- `sensor.parasoll_sovedoer_battery` — 1 refs in 1 file(s)
- `sensor.radiator_effekt_sove` — 2 refs in 2 file(s)
- `sensor.sove_doerzone_stempel` — 4 refs in 2 file(s)
- `sensor.sove_knap_battery` — 3 refs in 2 file(s)
- `sensor.sove_lux` — 2 refs in 2 file(s)
- `sensor.sove_lyskaede_current` — 1 refs in 1 file(s)
- `sensor.sove_lyskaede_power` — 3 refs in 3 file(s)
- `sensor.sove_lyskaede_presence_siden_loft` — 2 refs in 1 file(s)
- `sensor.sove_lyskaede_summation_delivered` — 1 refs in 1 file(s)
- `sensor.sove_lyskaede_voltage` — 1 refs in 1 file(s)
- `sensor.sove_plug_current` — 1 refs in 1 file(s)
- `sensor.sove_plug_current_summation_delivered` — 1 refs in 1 file(s)
- `sensor.sove_plug_current_voltage` — 1 refs in 1 file(s)
- `sensor.sove_plug_power` — 1 refs in 1 file(s)
- `sensor.sove_presence_60min` — 5 refs in 3 file(s)
- `sensor.sove_sidste_tryk` — 1 refs in 1 file(s)
- `sensor.sove_temperatur` — 3 refs in 2 file(s)
- `sensor.sovevaerelse_apollo_esp_temperature` — 4 refs in 3 file(s)
- `sensor.sovevaerelse_apollo_ghost_flaps_1h` — 3 refs in 2 file(s)
- `sensor.sovevaerelse_apollo_lux` — 10 refs in 6 file(s)
- `sensor.sovevaerelse_apollo_radar_move_energy` — 1 refs in 1 file(s)
- `sensor.sovevaerelse_apollo_radar_moving_distance` — 8 refs in 4 file(s)
- `sensor.sovevaerelse_apollo_radar_still_distance` — 2 refs in 2 file(s)
- `sensor.sovevaerelse_apollo_radar_still_energy` — 1 refs in 1 file(s)
- `sensor.sovevaerelse_apollo_temperature` — 3 refs in 2 file(s)
- `sensor.sovevaerelse_dagslys_sluk_effektiv` — 9 refs in 4 file(s)
- `sensor.sovevaerelse_lux_gate` — 8 refs in 5 file(s)
- `sensor.sovevaerelse_lux_reel` — 38 refs in 16 file(s)
- `sensor.sovevaerelse_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.sovevaerelse_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.sovevaerelse_styrbar_battery` — 9 refs in 5 file(s)

### `switch.*`

- `switch.sove_lyskaede` — 9 refs in 4 file(s)
- `switch.sove_plug` — 6 refs in 4 file(s)
- `switch.sovevaerelse_apollo_ld2410_bluetooth` — 1 refs in 1 file(s)
- `switch.sovevaerelse_apollo_radar_engineering_mode` — 3 refs in 2 file(s)
- `switch.sovevaerelse_apollo_reduce_db_reporting` — 4 refs in 1 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.airbnb_velkomst_move_sove` (defined in `packages/airbnb_velkomst.yaml`)
- `input_boolean.notif_sove_radar_parent_b` (defined in `packages/notifikationer.yaml`)
- `input_boolean.notif_sove_radar_enabled` (defined in `packages/notifikationer.yaml`)
- `input_boolean.notif_sove_radar_hjemme` (defined in `packages/notif_hjemme.yaml`)
- `input_boolean.notif_sove_radar_parent_a` (defined in `packages/notifikationer.yaml`)
- `input_boolean.putning_sove_active` (defined in `packages/putning_sove.yaml`)
- `input_boolean.roborock_styrbar_kort_op_sovevaerelse` (defined in `packages/roborock_styrbar.yaml`)
- `input_boolean.sove_approach_lit` (defined in `packages/sovevaerelse_smart_light.yaml`)
- `input_boolean.sove_gardin_aftenluk_enabled` (defined in `packages/sove_gardin_aftenluk.yaml`)
- `input_boolean.sove_gardin_op_afventer` (defined in `packages/sove_gardin_bad_gate.yaml`)
- `input_boolean.sove_lyskaede_enabled` (defined in `packages/sove_lyskaede.yaml`)
- `input_boolean.sove_lyskaede_manuel_slukket` (defined in `packages/sove_lyskaede.yaml`)
- `input_boolean.sove_morgen_anden_krop` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_boolean.sove_radar_watchdog_enabled` (defined in `packages/sove_apollo_radar_watchdog.yaml`)
- `input_boolean.sove_retur_enabled` (defined in `packages/nattur_retur.yaml`)
- `input_boolean.sove_seng_taeller_enabled` (defined in `packages/sove_seng_taeller.yaml`)
- `input_boolean.sovevaerelse_manual_off_lock` (defined in `packages/aften_manual_off_lock.yaml`)
- `input_boolean.sovevaerelse_morgen_beskyttelse_enabled` (defined in `packages/sovevaerelse_morgen_beskyttelse.yaml`)
- `input_boolean.styrbar_lr_grace_sovevaerelse` (defined in `packages/room_modes.yaml`)

### `input_datetime.*`

- `input_datetime.gardin_manual_down_sove` (defined in `packages/gardin_manual_grace.yaml`)
- `input_datetime.notif_sove_radar_slut` (defined in `packages/notifikationer.yaml`)
- `input_datetime.notif_sove_radar_start` (defined in `packages/notifikationer.yaml`)
- `input_datetime.sove_aften_graense` (defined in `packages/sovevaerelse_smart_light.yaml`)
- `input_datetime.sove_alarm_morgen_2p_at` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_datetime.sove_apollo_flap_last_bump` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.sove_apollo_occ_since` (defined in `packages/apollo_latch_detect.yaml`)
- `input_datetime.sove_flapcount_since` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.sove_manual_off_lock_start` (defined in `packages/aften_manual_off_lock.yaml`)
- `input_datetime.sove_morgen_afgang_at` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_datetime.sove_morgen_doer_aabnet_at` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_datetime.sove_morgen_doer_lukket_at` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_datetime.sove_radar_watchdog_last_probe` (defined in `packages/sove_apollo_radar_watchdog.yaml`)
- `input_datetime.sove_radar_watchdog_last_restart` (defined in `packages/sove_apollo_radar_watchdog.yaml`)
- `input_datetime.sove_seng_sidst_talt` (defined in `packages/sove_seng_taeller.yaml`)
- `input_datetime.sove_snooze_until` (defined in `packages/sovevaerelse_morgen_beskyttelse.yaml`)
- `input_datetime.styrbar_last_press_sovevaerelse` (defined in `packages/room_modes.yaml`)

### `input_number.*`

- `input_number.hoejttaler_sovemusik_minutter` (defined in `packages/hoejttaler.yaml`)
- `input_number.sove_alarm_morgen_vindue_minutter` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_number.sove_dvale_vidne_sekunder` (defined in `packages/sove_dvale_vidne.yaml`)
- `input_number.sove_g0_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g0_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g1_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g1_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g2_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g2_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g3_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g3_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g4_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g4_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g5_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g5_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g6_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g6_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g7_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g7_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g8_move` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_g8_still` (defined in `packages/sove_apollo_per_gate.yaml`)
- `input_number.sove_gardin_aftenluk_offset_min` (defined in `packages/sove_gardin_aftenluk.yaml`)
- `input_number.sove_gardin_bad_tomt_minutter` (defined in `packages/sove_gardin_bad_gate.yaml`)
- `input_number.sove_gardin_privacy_min_sol_elevation` (defined in `packages/sove_gardin_privacy_moerke.yaml`)
- `input_number.sove_godmorgen_fade_sekunder` (defined in `packages/sove_lyskaede.yaml`)
- `input_number.sove_lyskaede_min_loft_pct` (defined in `packages/sove_lyskaede.yaml`)
- `input_number.sove_lyskaede_presence_minutter` (defined in `packages/sove_lyskaede.yaml`)
- `input_number.sove_moerke_godnat_minutter` (defined in `packages/godnat_auto_declare.yaml`)
- `input_number.sove_morgen_2p_doerzone_cm` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_number.sove_morgen_afgang_entre_sekunder` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_number.sove_morgen_anden_krop_minutter` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_number.sove_morgen_doer_aaben_minutter` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_number.sove_radar_frozen_minutes` (defined in `packages/sove_apollo_radar_watchdog.yaml`)
- `input_number.sove_retur_seng_cm` (defined in `packages/nattur_retur.yaml`)
- `input_number.sove_seng_bliv_sekunder` (defined in `packages/sove_seng_taeller.yaml`)
- `input_number.sove_seng_personer` (defined in `packages/sove_seng_taeller.yaml`)
- `input_number.sove_seng_still_sekunder` (defined in `packages/sove_seng_taeller.yaml`)
- `input_number.sove_snooze_timer` (defined in `packages/sovevaerelse_morgen_beskyttelse.yaml`)
- `input_number.sovevaerelse_alarm_morgen_lux` (defined in `packages/sove_alarm_morgen.yaml`)
- `input_number.sovevaerelse_default_warmth_k` (defined in `packages/sovevaerelse_smart_light.yaml`)
- `input_number.sovevaerelse_gardin_morgen_tom_minutter` (defined in `packages/morning_curtains.yaml`)
- `input_number.sovevaerelse_lux_threshold` (defined in `packages/room_lux_tuning.yaml`)

### `input_select.*`

- `input_select.room_mode_sovevaerelse` (defined in `packages/room_modes.yaml`)

### `input_text.*`

- `input_text.sove_apollo_last_flap` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.sove_gate_flapcount` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.sove_gate_floors` (defined in `packages/apollo_gate_decay.yaml`)
- `input_text.sove_voksen_afgang` (defined in `packages/godnat_autooff.yaml`)
