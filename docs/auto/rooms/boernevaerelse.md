# Rum-dossier: boernevaerelse

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `boernevaerelse, bornevaerelse, boern`

## Indhold
- [Automations](boernevaerelse.md#automations) (26)
- [Entities](boernevaerelse.md#entities) (173)
- [Helpers](boernevaerelse.md#helpers) (52)

---

## Automations

### `automations/airbnb_mode.yaml`

- **AirBnB: Bloker børneværelse-lys (slukkes straks)** (line 948, mode=queued)
  - Undtagelse 1 (user 2026-06-30; rev. 2026-07-08 #12): BØRNEVÆRELSE må aldrig

### `automations/boern_ankomst_detekter.yaml`

- **Børn: sammenhængende børneværelses-ophold → børn hjemme** (line 20, mode=single)
  - Ophold i børneværelset i boern_ankomst_ophold_minutter (12) sammenhængende
- **Børn: ro i børneværelset → ryd aktivitets-flaget** (line 138, mode=single)
  - Selv-rydning. boern_ankomst_ro_minutter (120) uden aktivitet → flaget off,
- **Børn: svar på ankomst-spørgsmål → log + evt. ryd** (line 187, mode=queued)
  - "❌ Nej" = falsk positiv → ryd flaget + undertryk detektionen i
- **Børn: people count ≥ 3 i periode uden børn → spørg** (line 326, mode=single)
- **Børn: rene skift forbi køkkenet uden kamera-bevægelse → spørg** (line 383, mode=single)
- **Børn: kids_home tændt af 4 t-signal (ingen periode) → spørg** (line 441, mode=single)
- **Børn: voksen kommer hjem → ophæv Nej-pausen (spørg igen)** (line 490, mode=single)

### `automations/boern_loft_manual_cycle.yaml`

- **Børn loft: stamp last-off timestamp (cycle tracker)** (line 27, mode=queued)
  - Stamps input_datetime.boern_loft_left_on_at hver gang lyset forlader
- **Børn loft: manuel cycle → kraftigt lys (100%/3000K)** (line 46, mode=single)
  - Når lyset går til on uden automation-context og last-off var 2-15 sek

### `automations/boern_sleep_latch.yaml`

- **Børn: latch 'sov her i nat' (06:30 ud fra sidste nats søvn)** (line 17, mode=single)
  - Sætter input_boolean.boern_sov_her_i_nat hvis et barn faktisk sov i

### `automations/boernevaerelse_hyggelys_mirror.yaml`

- **Børnehygge: plug-lampe følger hygge-strip (app + Styrbar)** (line 33, mode=queued)
  - Plug-lampen følger light.boernevaerelse_hygge_strip on/off, så den tænder
- **Børn: Styrbar OP tænder hyggelys direkte (dagstime)** (line 101, mode=single)
  - OP-klik ('on') + OP-langklik ('move_with_on_off') på børne-Styrbaren tænder

### `automations/godnat_night.yaml`

- **Putning: Auto-actions ved godnat_børn flip ON** (line 147, mode=single)
  - Triggers på enhver godnat_boern_active off→on transition. Slukker boern

### `automations/light_power_recovery.yaml`

- **Børneværelselys: post-strøm → lux-aware default** (line 351, mode=single)
  - Boern bulb waker fra wall-switch på NVRAM-default 5% (brightness=13).

### `automations/morning_lights_sanity_check.yaml`

- **Morgen: Børn lys auto-sluk (lyst eller tomt)** (line 39, mode=single)
  - Slukker børnelyset hvis (a) rummet er lyst nok i 5 min ELLER (b) occupancy
- **Morgen: Børn lys fast-off ved LUX surge (gardin rolled)** (line 302, mode=single)
  - 5 sek above 80*factor → fade off. Reagerer hurtigt naar user manuelt

### `automations/presence_boernevaerelse.yaml`

- **Lysnet: Børneværelse tænd** (line 27, mode=single)
  - Før sengetid (eller uden børn hjemme): lux-styret varm hvid. Efter sengetid
- **Lysnet: Børneværelse adult-vækning under godnat (moving target)** (line 211, mode=single)
  - Tænder boern-loft 60% warm når en adult går ind i kids rum efter 06:00
- **Lysnet: Børneværelse gradvis sluk** (line 300, mode=restart)
  - 5-minute absence rule (private-rum standard). Stamps input_datetime.boernevaerelse_last_off

### `automations/presence_lights.yaml`

- **Lysnet: Børneværelse tænd ved LUX-fald** (line 599, mode=single)
  - Daylight fades while børneværelse occupied — gentle light for kids.
- **Lysnet: Børneværelse sluk ved LUX-stigning** (line 1015, mode=single)
  - Dagslys tilbage i børneværelset mens loftet står tændt — blid fade off.

### `automations/putning_auto_detect.yaml`

- **Putning: Auto-detect via børn still_target (FALLBACK, pre-flyt)** (line 189, mode=single)
  - Trigger B: Boern still_target=on for 10 min mellem 19:30-23:30.

### `automations/somrig_buttons.yaml`

- **Dark Mode-RODRET: Dark Mode ON (klik/hold øverste)** (line 689, mode=single)
- **Dark Mode-RODRET: Dark Mode OFF (klik/hold nederste)** (line 733, mode=single)

### `automations/styrbar_rooms.yaml`

- **Styrbar Boern: L/R grace 2-sek efter release** (line 823, mode=restart)

---

## Entities

### `automation.*`

- `automation.airbnb_bloker_depot_bornevaerelse_lys_slukkes_straks` — 1 refs in 1 file(s)
- `automation.klima_bornevaerelse_for_koldt` — 2 refs in 1 file(s)
- `automation.lysnet_bornevaerelse_gradvis_sluk` — 2 refs in 1 file(s)
- `automation.lysnet_bornevaerelse_sluk_ved_lux_stigning` — 3 refs in 2 file(s)
- `automation.lysnet_bornevaerelse_taend` — 3 refs in 2 file(s)
- `automation.lysnet_bornevaerelse_taend_ved_lux_fald` — 2 refs in 1 file(s)

### `binary_sensor.*`

- `binary_sensor.boern_aften_laasevindue` — 3 refs in 2 file(s)
- `binary_sensor.boern_putte_zone_aktiv` — 4 refs in 3 file(s)
- `binary_sensor.boern_set_i_eftermiddag` — 6 refs in 2 file(s)
- `binary_sensor.boernevaerelse_any_lys` — 1 refs in 1 file(s)
- `binary_sensor.boernevaerelse_apollo_occupancy` — 121 refs in 46 file(s)
- `binary_sensor.boernevaerelse_apollo_online` — 1 refs in 1 file(s)
- `binary_sensor.boernevaerelse_apollo_radar_moving_target` — 12 refs in 10 file(s)
- `binary_sensor.boernevaerelse_apollo_radar_still_target` — 4 refs in 3 file(s)
- `binary_sensor.boernevaerelse_apollo_radar_zone_1_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.boernevaerelse_apollo_radar_zone_2_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.boernevaerelse_apollo_radar_zone_3_occupancy` — 1 refs in 1 file(s)
- `binary_sensor.boernevaerelse_bevaegelse_frisk` — 4 refs in 3 file(s)
- `binary_sensor.boernevaerelse_lys_on_effektiv` — 1 refs in 1 file(s)
- `binary_sensor.boernevaerelse_morgen_beskyttelse_aktiv` — 8 refs in 5 file(s)
- `binary_sensor.boernevaerelse_morgen_bevaegelse` — 1 refs in 1 file(s)
- `binary_sensor.boernevaerelse_morgen_vindue` — 3 refs in 1 file(s)
- `binary_sensor.boernevaerelse_solo_bevis` — 7 refs in 1 file(s)
- `binary_sensor.boernevaerelse_vaekning_bevaegelse` — 1 refs in 1 file(s)
- `binary_sensor.boernevaerelse_vaekning_hold` — 5 refs in 4 file(s)
- `binary_sensor.boernevaerelse_vaekning_koert_i_dag` — 2 refs in 1 file(s)
- `binary_sensor.dark_mode_boern` — 4 refs in 4 file(s)
- `binary_sensor.filmmoerke_boern` — 7 refs in 5 file(s)
- `binary_sensor.mood_pause_boernevaerelse` — 2 refs in 1 file(s)

### `button.*`

- `button.boernevaerelse_styrbar_identify` — 1 refs in 1 file(s)

### `counter.*`

- `counter.ghost_boernevaerelse` — 4 refs in 1 file(s)

### `input_boolean.*`

- `input_boolean.boern_aktivitet_detekteret` — 19 refs in 7 file(s)
- `input_boolean.boern_ankomst_detekt_enabled` — 4 refs in 2 file(s)
- `input_boolean.boern_eftermiddag_tjek_enabled` — 2 refs in 2 file(s)
- `input_boolean.boern_ikke_set_i_eftermiddag` — 7 refs in 4 file(s)
- `input_boolean.boern_morgen_beskyttelse_enabled` — 4 refs in 3 file(s)
- `input_boolean.boern_morgen_bevaeget` — 16 refs in 5 file(s)
- `input_boolean.boern_morgen_nedtoning_aktiv` — 22 refs in 5 file(s)
- `input_boolean.boern_sov_her_i_nat` — 24 refs in 9 file(s)
- `input_boolean.boernevaerelse_gaest_sover` — 20 refs in 7 file(s)
- `input_boolean.boernevaerelse_manual_off_lock` — 46 refs in 14 file(s)
- `input_boolean.dance_room_boern` — 15 refs in 7 file(s)
- `input_boolean.festlys_boern_styrbar` — 8 refs in 3 file(s)
- `input_boolean.godnat_boern_active` — 95 refs in 41 file(s)
- `input_boolean.koekken_lav_krop_boern_enabled` — 3 refs in 3 file(s)
- `input_boolean.people_boern_set_efter_doer` — 12 refs in 2 file(s)
- `input_boolean.roborock_styrbar_kort_op_boernevaerelse` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_boernevaerelse` — 1 refs in 1 file(s)
- `input_boolean.styrbar_lr_grace_boernevaerelse` — 3 refs in 2 file(s)
- `input_boolean.styrbar_lr_holding_boernevaerelse` — 1 refs in 1 file(s)
- `input_boolean.styrbar_up_holding_boernevaerelse` — 1 refs in 1 file(s)

### `input_datetime.*`

- `input_datetime.boern_ankomst_stille_until` — 5 refs in 5 file(s)
- `input_datetime.boern_ankomst_suppress_timer` — 6 refs in 3 file(s)
- `input_datetime.boern_ankomst_suppress_until` — 10 refs in 4 file(s)
- `input_datetime.boern_loft_left_on_at` — 4 refs in 1 file(s)
- `input_datetime.boern_manual_off_lock_start` — 6 refs in 4 file(s)
- `input_datetime.boern_morgen_beskyttelse_slut` — 8 refs in 4 file(s)
- `input_datetime.boernevaerelse_last_off` — 4 refs in 3 file(s)
- `input_datetime.styrbar_last_press_boernevaerelse` — 8 refs in 6 file(s)

### `input_number.*`

- `input_number.apollo_led_lux_offset_boern` — 1 refs in 1 file(s)
- `input_number.boern_ankomst_ophold_minutter` — 5 refs in 3 file(s)
- `input_number.boern_ankomst_ro_minutter` — 4 refs in 2 file(s)
- `input_number.boern_eftermiddag_bevis_min` — 2 refs in 2 file(s)
- `input_number.boern_eftermiddag_fra_time` — 5 refs in 2 file(s)
- `input_number.boern_eftermiddag_tjek_min_foer` — 2 refs in 2 file(s)
- `input_number.boern_morgen_bevaegelse_sekunder` — 7 refs in 4 file(s)
- `input_number.boern_morgen_nedtoning_minutter` — 4 refs in 3 file(s)
- `input_number.boern_morgen_nedtoning_stilhed_sek` — 6 refs in 3 file(s)
- `input_number.boern_morgen_nedtoning_vindue_min` — 2 refs in 2 file(s)
- `input_number.boern_ophold_bevis_sekunder` — 3 refs in 2 file(s)
- `input_number.boern_people_spoerg_minutter` — 3 refs in 2 file(s)
- `input_number.boernevaerelse_dagslys_sluk_lux` — 3 refs in 2 file(s)
- `input_number.boernevaerelse_g0_move` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g0_still` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g1_move` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g1_still` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g2_move` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g2_still` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g3_move` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g3_still` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g4_move` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g4_still` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g5_move` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g5_still` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_g6_move` — 1 refs in 1 file(s)
- `input_number.boernevaerelse_g6_still` — 1 refs in 1 file(s)
- `input_number.boernevaerelse_g7_move` — 1 refs in 1 file(s)
- `input_number.boernevaerelse_g7_still` — 1 refs in 1 file(s)
- `input_number.boernevaerelse_g8_move` — 1 refs in 1 file(s)
- `input_number.boernevaerelse_g8_still` — 1 refs in 1 file(s)
- `input_number.boernevaerelse_hyggelys_brightness` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_lux_andel_pct` — 6 refs in 3 file(s)
- `input_number.boernevaerelse_lux_threshold` — 6 refs in 4 file(s)
- `input_number.boernevaerelse_med_boern_sluk_sekunder` — 4 refs in 3 file(s)
- `input_number.boernevaerelse_morgen_lux_threshold` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_putte_reading_min_cm` — 2 refs in 2 file(s)
- `input_number.boernevaerelse_uden_boern_sluk_sekunder` — 4 refs in 3 file(s)
- `input_number.festlys_boern_tomt_minutter` — 5 refs in 3 file(s)
- `input_number.global_boern_bedtime_weekday` — 2 refs in 2 file(s)
- `input_number.global_boern_bedtime_weekend` — 2 refs in 2 file(s)
- `input_number.mad_boernevenlig_pct` — 2 refs in 2 file(s)
- `input_number.people_boern_antal` — 12 refs in 3 file(s)
- `input_number.people_boern_set_minutter` — 2 refs in 2 file(s)
- `input_number.people_boern_solo_sekunder` — 2 refs in 2 file(s)
- `input_number.people_boern_to_nat_timer` — 3 refs in 2 file(s)
- `input_number.radiator_trin_boernevaerelse` — 2 refs in 2 file(s)

### `input_select.*`

- `input_select.room_mode_boernevaerelse` — 24 refs in 18 file(s)

### `input_text.*`

- `input_text.boern_aften_niveau_hold` — 21 refs in 7 file(s)
- `input_text.boern_ankomst_pending` — 4 refs in 2 file(s)
- `input_text.boern_ankomst_pending_kilde` — 3 refs in 2 file(s)
- `input_text.boernevaerelse_apollo_last_flap` — 1 refs in 1 file(s)
- `input_text.boernevaerelse_gate_flapcount` — 1 refs in 1 file(s)
- `input_text.boernevaerelse_gate_floors` — 1 refs in 1 file(s)

### `light.*`

- `light.boernevaerelse_all` — 19 refs in 10 file(s)
- `light.boernevaerelse_apollo_rgb_light` — 5 refs in 5 file(s)
- `light.boernevaerelse_hygge_strip` — 89 refs in 31 file(s)
- `light.boernevaerelse_hyggelys` — 53 refs in 21 file(s)
- `light.boernevaerelse_lampe` — 44 refs in 20 file(s)
- `light.boernevaerelse_loft` — 95 refs in 37 file(s)

### `number.*`

- `number.boernevaerelse_apollo_g0_move_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g0_still_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g1_move_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g1_still_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g2_move_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g2_still_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g3_move_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g3_still_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g4_move_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g4_still_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g5_move_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_g5_still_threshold` — 1 refs in 1 file(s)
- `number.boernevaerelse_apollo_radar_timeout` — 4 refs in 2 file(s)

### `script.*`

- `script.boern_ankomst_spoerg` — 5 refs in 2 file(s)
- `script.boern_morgen_nedtoning_rampe` — 7 refs in 3 file(s)
- `script.boern_natlys_set` — 6 refs in 4 file(s)
- `script.boernevaerelse_apollo_apply_all_gates` — 1 refs in 1 file(s)
- `script.festlys_boern_slut` — 3 refs in 2 file(s)
- `script.roborock_grundig_boernevaerelse` — 1 refs in 1 file(s)
- `script.roborock_hurtig_boernevaerelse` — 1 refs in 1 file(s)

### `sensor.*`

- `sensor.boern_bedtime_hour` — 5 refs in 4 file(s)
- `sensor.boern_lux` — 2 refs in 2 file(s)
- `sensor.boern_occupancy_4h` — 5 refs in 4 file(s)
- `sensor.boern_occupancy_overnight` — 18 refs in 6 file(s)
- `sensor.boern_occupancy_today` — 6 refs in 4 file(s)
- `sensor.boern_sidste_tryk` — 1 refs in 1 file(s)
- `sensor.boern_solo_bevis_4h` — 2 refs in 1 file(s)
- `sensor.boern_temperatur` — 1 refs in 1 file(s)
- `sensor.boern_vaerelse_eftermiddag_timer` — 3 refs in 2 file(s)
- `sensor.boern_vaerelse_ophold_holdt` — 2 refs in 1 file(s)
- `sensor.boernevaerelse_apollo_esp_temperature` — 4 refs in 3 file(s)
- `sensor.boernevaerelse_apollo_ghost_flaps_1h` — 3 refs in 2 file(s)
- `sensor.boernevaerelse_apollo_lux` — 6 refs in 4 file(s)
- `sensor.boernevaerelse_apollo_radar_move_energy` — 1 refs in 1 file(s)
- `sensor.boernevaerelse_apollo_radar_moving_distance` — 4 refs in 3 file(s)
- `sensor.boernevaerelse_apollo_radar_still_distance` — 5 refs in 4 file(s)
- `sensor.boernevaerelse_apollo_radar_still_energy` — 1 refs in 1 file(s)
- `sensor.boernevaerelse_apollo_temperature` — 3 refs in 2 file(s)
- `sensor.boernevaerelse_auto_lys_pct` — 2 refs in 2 file(s)
- `sensor.boernevaerelse_dagslys_sluk_effektiv` — 10 refs in 4 file(s)
- `sensor.boernevaerelse_lux_reel` — 16 refs in 8 file(s)
- `sensor.boernevaerelse_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.boernevaerelse_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.boernevaerelse_morgen_bevaegelse_recent` — 3 refs in 1 file(s)
- `sensor.boernevaerelse_morgen_lux_gate` — 1 refs in 1 file(s)
- `sensor.boernevaerelse_styrbar_battery` — 10 refs in 6 file(s)
- `sensor.boernevaerelse_taend_lux_gate` — 6 refs in 4 file(s)
- `sensor.boernevaerelse_vaekning_bevaegelse_recent` — 2 refs in 1 file(s)
- `sensor.people_boern` — 6 refs in 2 file(s)
- `sensor.vaekning_boern_hold_alder` — 2 refs in 1 file(s)
- `sensor.vaekning_boern_hold_effektiv` — 4 refs in 3 file(s)

### `switch.*`

- `switch.boernevaerelse_apollo_ld2410_bluetooth` — 1 refs in 1 file(s)
- `switch.boernevaerelse_apollo_radar_engineering_mode` — 1 refs in 1 file(s)

### `update.*`

- `update.boernevaerelse_styrbar_firmware` — 1 refs in 1 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.boern_ankomst_detekt_enabled` (defined in `packages/boern_ankomst.yaml`)
- `input_boolean.boern_eftermiddag_tjek_enabled` (defined in `packages/boern_eftermiddag_tjek.yaml`)
- `input_boolean.boern_morgen_beskyttelse_enabled` (defined in `packages/boernevaerelse_morgen_beskyttelse.yaml`)
- `input_boolean.boern_morgen_bevaeget` (defined in `packages/boern_morgen_nedtoning.yaml`)
- `input_boolean.boern_morgen_nedtoning_aktiv` (defined in `packages/boern_morgen_nedtoning.yaml`)
- `input_boolean.boernevaerelse_manual_off_lock` (defined in `packages/boernevaerelse_manual_off_lock.yaml`)
- `input_boolean.festlys_boern_styrbar` (defined in `packages/festlys_boern_styrbar.yaml`)
- `input_boolean.roborock_styrbar_kort_op_boernevaerelse` (defined in `packages/roborock_styrbar.yaml`)
- `input_boolean.styrbar_lr_grace_boernevaerelse` (defined in `packages/room_modes.yaml`)

### `input_datetime.*`

- `input_datetime.boern_ankomst_suppress_until` (defined in `packages/boern_ankomst.yaml`)
- `input_datetime.boern_morgen_beskyttelse_slut` (defined in `packages/boernevaerelse_morgen_beskyttelse.yaml`)
- `input_datetime.boernevaerelse_apollo_flap_last_bump` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.boernevaerelse_apollo_occ_since` (defined in `packages/apollo_latch_detect.yaml`)
- `input_datetime.boernevaerelse_flapcount_since` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_datetime.boernevaerelse_last_off` (defined in `packages/house_modes.yaml`)
- `input_datetime.styrbar_last_press_boernevaerelse` (defined in `packages/room_modes.yaml`)

### `input_number.*`

- `input_number.boern_ankomst_ophold_minutter` (defined in `packages/boern_ankomst.yaml`)
- `input_number.boern_eftermiddag_fra_time` (defined in `packages/boern_eftermiddag_tjek.yaml`)
- `input_number.boern_morgen_bevaegelse_sekunder` (defined in `packages/boernevaerelse_morgen_beskyttelse.yaml`)
- `input_number.boern_morgen_nedtoning_minutter` (defined in `packages/boern_morgen_nedtoning.yaml`)
- `input_number.boern_morgen_nedtoning_stilhed_sek` (defined in `packages/boern_morgen_nedtoning.yaml`)
- `input_number.boern_morgen_nedtoning_vindue_min` (defined in `packages/boern_morgen_nedtoning.yaml`)
- `input_number.boernevaerelse_g0_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g0_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g1_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g1_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g2_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g2_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g3_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g3_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g4_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g4_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g5_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g5_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g6_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g6_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g7_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g7_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g8_move` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_g8_still` (defined in `packages/apollo_per_gate.yaml`)
- `input_number.boernevaerelse_lux_andel_pct` (defined in `packages/room_lux_tuning.yaml`)
- `input_number.boernevaerelse_med_boern_sluk_sekunder` (defined in `packages/boernevaerelse_uden_boern.yaml`)
- `input_number.boernevaerelse_morgen_lux_threshold` (defined in `packages/room_lux_tuning.yaml`)
- `input_number.festlys_boern_tomt_minutter` (defined in `packages/festlys_boern_styrbar.yaml`)
- `input_number.mad_boernevenlig_pct` (defined in `packages/mad_planlaegning.yaml`)

### `input_select.*`

- `input_select.room_mode_boernevaerelse` (defined in `packages/room_modes.yaml`)

### `input_text.*`

- `input_text.boern_aften_niveau_hold` (defined in `packages/boern_aften_niveau_hold.yaml`)
- `input_text.boern_ankomst_pending` (defined in `packages/boern_ankomst.yaml`)
- `input_text.boern_ankomst_pending_kilde` (defined in `packages/boern_ankomst.yaml`)
- `input_text.boernevaerelse_apollo_last_flap` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.boernevaerelse_gate_flapcount` (defined in `packages/apollo_flap_hunt.yaml`)
- `input_text.boernevaerelse_gate_floors` (defined in `packages/apollo_gate_decay.yaml`)
