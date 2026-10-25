# Rum-dossier: badevaerelse

Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.

Search keywords: `badevaerelse, bad`

## Indhold
- [Automations](badevaerelse.md#automations) (22)
- [Entities](badevaerelse.md#entities) (166)
- [Helpers](badevaerelse.md#helpers) (40)

---

## Automations

### `automations/light_power_recovery.yaml`

- **Badelys: post-strom -> sun-aware default** (line 69, mode=single)
  - Bath bulb wake fra wall-switch eller mesh-flicker → fader til sun-aware
- **AirBnB: Alle lys post-strøm → lux-aware (bad=fuld)** (line 449, mode=parallel)
  - AirBnB undtagelse 2: vægkontakt-genstart tænder lys på passende niveau for

### `automations/presence_badevaerelse.yaml`

- **Lysnet: Badeværelse tænd** (line 24, mode=single)
  - Mindre skarpt aften-lys — undgaa at blaende moerketilpasset syn.
- **Lysnet: Badeværelse 60→100% langsom optrapning (kun ved ophold)** (line 376, mode=restart)
  - User-spec 2026-06-18: bad-spots hopper ALDRIG direkte til 100%. Efter 60%-
- **Lysnet: Badeværelse besøg bekræftet → løft probe til memory** (line 481, mode=single)
  - visit_serious flippede on (Quick → Medium/Fuld) → løft det tentative probe-
- **Lysnet: Badeværelse gradvis sluk** (line 540, mode=restart)
  - Sprint 2026-05-20: Reclassified fra passage → ophold-tier (private 5 min).
- **Lysnet: Badeværelse godnat nat-toilet hurtig-sluk** (line 770, mode=restart)
  - Mens badets natlys er aktivt: sluk hurtigt (badevaerelse_godnat_off_seconds)
- **Lysnet: Badeværelse natlys-slut opgradering** (line 920, mode=single)
  - Solopgang (eller godnat-slut) mens nogen er i badet og lyset stadig hænger
- **Lysnet: Badeværelse approach-lys hurtig-sluk** (line 1004, mode=restart)
  - Approach tændte badet men ingen gik ind (approach_lit stadig on, inde off,
- **Lysnet: Badeværelse probe quick-off (ubekræftet = sok)** (line 1112, mode=restart)
  - Ubekræftet besøg (kun dør-PIR, ingen deep/sustain → visit_serious off) og
- **Lysnet: Badeværelse Medium-besøg sluk (kortere hold)** (line 1245, mode=restart)
  - Stadie Medium + ingen indre-bevægelse i badevaerelse_medium_off_minutes →
- **Lysnet: Badeværelse leave-off (Fuld + dør åben + ro)** (line 1385, mode=restart)
  - Fuld-besøg (du lukkede døren = committet) hvor døren NU er åben og der ikke
- **Lysnet: Badeværelse spots resync efter reconnect** (line 1557, mode=queued)
  - KAJPLATS (Matter) + Innr (Zigbee) skal være 100% i sync. Spot der
- **Lysnet: Badeværelse spots sync-healer (blandet on/off)** (line 1674, mode=single)
  - Heler blandet on/off-tilstand på de 5 bad-spots NÅR alle er available
- **Lysnet: Badeværelse spots confirm-off (Matter missed-command)** (line 1844, mode=restart)
  - Re-sender turn_off til de 5 bad-spots efter gruppen er gået off + fade
- **Lysnet: Badeværelse restart-recovery (nogen står derinde når HA kommer op)** (line 1935, mode=single)
  - 30 s efter HA-start: er inde-PIR'en on og lyset stadig off i et Auto-rum,
- **Lysnet: Badeværelse sluk → Auto mode** (line 2006, mode=single)
  - Når bad-lyset bliver helt off (manuelt eller auto) — eller sættes i Manual
- **Lysnet: Badeværelse max-on watchdog** (line 2062, mode=single)
  - Sikkerhedsnet 2026-06-15 (user-spec): Når bad-presence-sensorerne (VALLHORN/
- **Lysnet: Badeværelse wasp-probe (dæmp→sluk ved stilhed bag lukket dør)** (line 2166, mode=restart)
  - Lukket dør + Fuld + ingen inde-motion i badevaerelse_wasp_probe_minutes →
- **Lysnet: Badeværelse wasp-probe re-arm (flanke tabt over restart)** (line 2371, mode=single)
  - Lys tændt + Fuld + lukket dør + stilhed langt ud over probe-vinduet =

### `automations/styrbar_rooms.yaml`

- **Styrbar Bad: L/R grace 2-sek efter release** (line 861, mode=restart)

### `automations/water_leak_alarm.yaml`

- **Sikkerhed: VANDLÆK alarm i badeværelse** (line 15, mode=single)
  - Badring detekterer vand -> rodt blinkende lys + persistent notification

---

## Entities

### `automation.*`

- `automation.airbnb_alle_lys_post_strom_lux_aware_bad_fuld` — 1 refs in 1 file(s)
- `automation.lysnet_badevaerelse_60_100_langsom_optrapning_kun_ved_ophold` — 1 refs in 1 file(s)
- `automation.lysnet_badevaerelse_taend` — 1 refs in 1 file(s)
- `automation.lysnet_badevaerelse_wasp_probe_daemp_sluk_ved_stilhed_bag_lukket_dor` — 1 refs in 1 file(s)

### `binary_sensor.*`

- `binary_sensor.bad_pavirker_lejligheden` — 1 refs in 1 file(s)
- `binary_sensor.badevaerelse_afventer_klimabevis` — 4 refs in 3 file(s)
- `binary_sensor.badevaerelse_alle_hjemme_i_bad` — 4 refs in 2 file(s)
- `binary_sensor.badevaerelse_bad_strom_ok` — 7 refs in 4 file(s)
- `binary_sensor.badevaerelse_badring` — 5 refs in 2 file(s)
- `binary_sensor.badevaerelse_badring_water_leak` — 1 refs in 1 file(s)
- `binary_sensor.badevaerelse_brusebad_hold` — 25 refs in 5 file(s)
- `binary_sensor.badevaerelse_brusebad_signatur` — 3 refs in 3 file(s)
- `binary_sensor.badevaerelse_bruser_vagt_vindue` — 1 refs in 1 file(s)
- `binary_sensor.badevaerelse_fortryd_vindue` — 1 refs in 1 file(s)
- `binary_sensor.badevaerelse_fugt_bevis` — 3 refs in 1 file(s)
- `binary_sensor.badevaerelse_fugt_frisk` — 9 refs in 2 file(s)
- `binary_sensor.badevaerelse_inde_1_occupancy` — 24 refs in 9 file(s)
- `binary_sensor.badevaerelse_inde_2_occupancy` — 23 refs in 8 file(s)
- `binary_sensor.badevaerelse_inde_occupancy` — 132 refs in 38 file(s)
- `binary_sensor.badevaerelse_lys_on_effektiv` — 1 refs in 1 file(s)
- `binary_sensor.badevaerelse_matter_spots_ok` — 12 refs in 5 file(s)
- `binary_sensor.badevaerelse_natlys_aktiv` — 10 refs in 3 file(s)
- `binary_sensor.badevaerelse_optaget_lukket_doer` — 2 refs in 1 file(s)
- `binary_sensor.badevaerelse_thread_lys_nede` — 8 refs in 2 file(s)
- `binary_sensor.badevaerelse_tumbler_mistanke` — 2 refs in 2 file(s)
- `binary_sensor.badevaerelse_visit_serious` — 15 refs in 6 file(s)
- `binary_sensor.parasoll_badevaerelse` — 30 refs in 6 file(s)
- `binary_sensor.sove_gardin_bad_klar` — 13 refs in 4 file(s)

### `button.*`

- `button.badevaerelse_badring_identify` — 1 refs in 1 file(s)

### `input_boolean.*`

- `input_boolean.airbnb_velkomst_move_bad` — 3 refs in 2 file(s)
- `input_boolean.bad_zigbee_nodlys_aktiv` — 14 refs in 3 file(s)
- `input_boolean.badevaerelse_approach_lit` — 13 refs in 3 file(s)
- `input_boolean.badevaerelse_brusebad_lys_genrejst` — 7 refs in 2 file(s)
- `input_boolean.badevaerelse_brusebad_session` — 18 refs in 6 file(s)
- `input_boolean.badevaerelse_bruser_vagt` — 11 refs in 4 file(s)
- `input_boolean.badevaerelse_bruser_vagt_enabled` — 8 refs in 4 file(s)
- `input_boolean.badevaerelse_first_deep_today` — 4 refs in 1 file(s)
- `input_boolean.badevaerelse_fugt_venteslukket` — 9 refs in 3 file(s)
- `input_boolean.badevaerelse_fuld_spot_1` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_fuld_spot_2` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_fuld_spot_3` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_fuld_spot_4` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_fuld_spot_5` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_medium_spot_1` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_medium_spot_2` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_medium_spot_3` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_medium_spot_4` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_medium_spot_5` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_quick_spot_1` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_quick_spot_2` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_quick_spot_3` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_quick_spot_4` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_quick_spot_5` — 2 refs in 2 file(s)
- `input_boolean.badevaerelse_wasp_active` — 34 refs in 8 file(s)
- `input_boolean.dance_room_bad` — 7 refs in 6 file(s)
- `input_boolean.notif_bad_lys_airbnb` — 1 refs in 1 file(s)
- `input_boolean.notif_bad_lys_parent_b` — 1 refs in 1 file(s)
- `input_boolean.notif_bad_lys_enabled` — 1 refs in 1 file(s)
- `input_boolean.notif_bad_lys_hjemme` — 1 refs in 1 file(s)
- `input_boolean.notif_bad_lys_parent_a` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_kort_op_badevaerelse` — 1 refs in 1 file(s)
- `input_boolean.roborock_styrbar_lang_op_badevaerelse` — 1 refs in 1 file(s)
- `input_boolean.sove_gardin_bad_foerste_besoeg_ovre` — 13 refs in 4 file(s)
- `input_boolean.styrbar_lr_grace_badevaerelse` — 3 refs in 2 file(s)
- `input_boolean.styrbar_lr_holding_badevaerelse` — 1 refs in 1 file(s)
- `input_boolean.styrbar_up_holding_badevaerelse` — 1 refs in 1 file(s)

### `input_datetime.*`

- `input_datetime.badevaerelse_auto_off_at` — 3 refs in 1 file(s)
- `input_datetime.badevaerelse_besoeg_start` — 3 refs in 1 file(s)
- `input_datetime.badevaerelse_brusebad_stempel` — 6 refs in 2 file(s)
- `input_datetime.badevaerelse_bruser_vagt_slut` — 6 refs in 4 file(s)
- `input_datetime.badevaerelse_bruser_vagt_start` — 6 refs in 4 file(s)
- `input_datetime.badevaerelse_bruser_vagt_stempel` — 7 refs in 3 file(s)
- `input_datetime.badevaerelse_dagmode_senest` — 4 refs in 3 file(s)
- `input_datetime.badevaerelse_sidste_indre_pir` — 5 refs in 2 file(s)
- `input_datetime.badevaerelse_sluk_alt_udskudt` — 5 refs in 2 file(s)
- `input_datetime.notif_bad_lys_slut` — 1 refs in 1 file(s)
- `input_datetime.notif_bad_lys_start` — 1 refs in 1 file(s)
- `input_datetime.styrbar_last_press_badevaerelse` — 5 refs in 4 file(s)

### `input_number.*`

- `input_number.badevaerelse_airbnb_off_forsigtighed` — 2 refs in 2 file(s)
- `input_number.badevaerelse_approach_brightness` — 6 refs in 4 file(s)
- `input_number.badevaerelse_brusebad_blank_minutter` — 3 refs in 3 file(s)
- `input_number.badevaerelse_brusebad_fald_point` — 3 refs in 3 file(s)
- `input_number.badevaerelse_brusebad_fugt_burst_point` — 4 refs in 3 file(s)
- `input_number.badevaerelse_brusebad_fugt_stigning_point` — 4 refs in 3 file(s)
- `input_number.badevaerelse_brusebad_indgang_vindue_minutter` — 2 refs in 2 file(s)
- `input_number.badevaerelse_brusebad_maks_minutter` — 5 refs in 3 file(s)
- `input_number.badevaerelse_bruser_off_faktor` — 5 refs in 4 file(s)
- `input_number.badevaerelse_bruser_vagt_bekraeft_sekunder` — 3 refs in 2 file(s)
- `input_number.badevaerelse_bruser_vagt_maks_minutter` — 4 refs in 3 file(s)
- `input_number.badevaerelse_dagmode_lux` — 4 refs in 3 file(s)
- `input_number.badevaerelse_fugt_frisk_sekunder` — 3 refs in 3 file(s)
- `input_number.badevaerelse_fuld_brightness` — 5 refs in 3 file(s)
- `input_number.badevaerelse_full_sustain_seconds` — 4 refs in 3 file(s)
- `input_number.badevaerelse_godnat_brightness` — 6 refs in 5 file(s)
- `input_number.badevaerelse_godnat_off_seconds` — 4 refs in 3 file(s)
- `input_number.badevaerelse_klimabevis_maks_minutter` — 2 refs in 2 file(s)
- `input_number.badevaerelse_leave_off_seconds` — 5 refs in 3 file(s)
- `input_number.badevaerelse_manual_til_auto_minutes` — 3 refs in 2 file(s)
- `input_number.badevaerelse_max_on_minutes` — 11 refs in 5 file(s)
- `input_number.badevaerelse_medium_brightness` — 6 refs in 3 file(s)
- `input_number.badevaerelse_medium_off_minutes` — 7 refs in 3 file(s)
- `input_number.badevaerelse_min_kelvin` — 6 refs in 3 file(s)
- `input_number.badevaerelse_min_on_minutes` — 2 refs in 2 file(s)
- `input_number.badevaerelse_off_minutter` — 5 refs in 3 file(s)
- `input_number.badevaerelse_probe_brightness` — 4 refs in 3 file(s)
- `input_number.badevaerelse_probe_grace_seconds` — 4 refs in 2 file(s)
- `input_number.badevaerelse_ramp_minutes` — 2 refs in 2 file(s)
- `input_number.badevaerelse_serious_sustain_seconds` — 3 refs in 2 file(s)
- `input_number.badevaerelse_sluk_alt_efterslaeb_minutter` — 3 refs in 3 file(s)
- `input_number.badevaerelse_wasp_probe_brightness` — 5 refs in 3 file(s)
- `input_number.badevaerelse_wasp_probe_minutes` — 5 refs in 3 file(s)
- `input_number.badevaerelse_wasp_probe_off_minutes` — 5 refs in 3 file(s)
- `input_number.radiator_trin_bad` — 2 refs in 2 file(s)
- `input_number.sove_gardin_bad_min_aktivitet_minutter` — 5 refs in 3 file(s)
- `input_number.sove_gardin_bad_tomt_minutter` — 5 refs in 3 file(s)

### `input_select.*`

- `input_select.badevaerelse_visit_stage` — 40 refs in 8 file(s)
- `input_select.room_mode_badevaerelse` — 50 refs in 16 file(s)

### `light.*`

- `light.badevaerelse_all` — 130 refs in 23 file(s)
- `light.badevaerelse_spot_1` — 37 refs in 23 file(s)
- `light.badevaerelse_spot_2` — 43 refs in 23 file(s)
- `light.badevaerelse_spot_3` — 34 refs in 20 file(s)
- `light.badevaerelse_spot_4` — 32 refs in 18 file(s)
- `light.badevaerelse_spot_5` — 32 refs in 18 file(s)

### `script.*`

- `script.badevaerelse_fugt_ventesluk` — 9 refs in 2 file(s)
- `script.badevaerelse_sluk_alt_udskyd` — 4 refs in 2 file(s)
- `script.roborock_grundig_badevaerelse` — 1 refs in 1 file(s)
- `script.roborock_hurtig_badevaerelse` — 1 refs in 1 file(s)

### `sensor.*`

- `sensor.bad_fugt_overskud` — 4 refs in 3 file(s)
- `sensor.bad_lux` — 2 refs in 2 file(s)
- `sensor.bad_sidste_tryk` — 1 refs in 1 file(s)
- `sensor.bad_torretid` — 5 refs in 2 file(s)
- `sensor.badevaerelse_airbnb_off_factor` — 8 refs in 1 file(s)
- `sensor.badevaerelse_aktiv_fase` — 5 refs in 2 file(s)
- `sensor.badevaerelse_aktivitet_30min` — 5 refs in 2 file(s)
- `sensor.badevaerelse_badring_battery` — 6 refs in 5 file(s)
- `sensor.badevaerelse_brusebad_alder` — 5 refs in 2 file(s)
- `sensor.badevaerelse_bruser_off_factor` — 7 refs in 1 file(s)
- `sensor.badevaerelse_fase_brightness` — 6 refs in 2 file(s)
- `sensor.badevaerelse_fase_spots` — 11 refs in 2 file(s)
- `sensor.badevaerelse_fugt_burst` — 4 refs in 3 file(s)
- `sensor.badevaerelse_fugt_burst_maks_15m` — 2 refs in 1 file(s)
- `sensor.badevaerelse_fugt_fald` — 2 refs in 1 file(s)
- `sensor.badevaerelse_fugt_forrige` — 3 refs in 1 file(s)
- `sensor.badevaerelse_fugt_maks_10m` — 1 refs in 1 file(s)
- `sensor.badevaerelse_fugt_min_10m` — 1 refs in 1 file(s)
- `sensor.badevaerelse_fugt_min_5m` — 1 refs in 1 file(s)
- `sensor.badevaerelse_fugt_stigning` — 7 refs in 4 file(s)
- `sensor.badevaerelse_fugt_stigning_maks_15m` — 2 refs in 1 file(s)
- `sensor.badevaerelse_inde_2_battery` — 1 refs in 1 file(s)
- `sensor.badevaerelse_inde_battery` — 1 refs in 1 file(s)
- `sensor.badevaerelse_inde_illuminance` — 3 refs in 2 file(s)
- `sensor.badevaerelse_lys_on_24h` — 1 refs in 1 file(s)
- `sensor.badevaerelse_lys_on_idag` — 8 refs in 2 file(s)
- `sensor.badevaerelse_lys_timer_dag` — 1 refs in 1 file(s)
- `sensor.badevaerelse_sluk_alt_undtagelse` — 11 refs in 5 file(s)
- `sensor.badevaerelse_styrbar_battery` — 9 refs in 5 file(s)
- `sensor.badevaerelse_temp_min_20m` — 1 refs in 1 file(s)
- `sensor.badevaerelse_temp_stigning` — 5 refs in 3 file(s)
- `sensor.badevaerelse_temp_stigning_maks_15m` — 1 refs in 1 file(s)
- `sensor.badevaerelse_timmerflotte_battery` — 1 refs in 1 file(s)
- `sensor.badevaerelse_timmerflotte_humidity` — 20 refs in 5 file(s)
- `sensor.badevaerelse_timmerflotte_temperature` — 10 refs in 5 file(s)
- `sensor.badevaerelse_tom_sluk_sekunder` — 3 refs in 1 file(s)
- `sensor.parasoll_badevaerelse_battery` — 2 refs in 2 file(s)
- `sensor.radiator_effekt_bad` — 2 refs in 2 file(s)

### `update.*`

- `update.badevaerelse_badring_firmware` — 1 refs in 1 file(s)

---

## Helpers

### `input_boolean.*`

- `input_boolean.airbnb_velkomst_move_bad` (defined in `packages/airbnb_velkomst.yaml`)
- `input_boolean.badevaerelse_brusebad_session` (defined in `packages/badevaerelse_brusebad.yaml`)
- `input_boolean.badevaerelse_bruser_vagt_enabled` (defined in `packages/badevaerelse_bruser_vagt.yaml`)
- `input_boolean.badevaerelse_first_deep_today` (defined in `packages/badevaerelse_visit_quality.yaml`)
- `input_boolean.badevaerelse_fuld_spot_1` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_fuld_spot_2` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_fuld_spot_3` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_fuld_spot_4` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_fuld_spot_5` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_medium_spot_1` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_medium_spot_2` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_medium_spot_3` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_medium_spot_4` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_medium_spot_5` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_quick_spot_1` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_quick_spot_2` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_quick_spot_3` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_quick_spot_4` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_quick_spot_5` (defined in `packages/badevaerelse_faser.yaml`)
- `input_boolean.badevaerelse_wasp_active` (defined in `packages/badevaerelse_wasp.yaml`)
- `input_boolean.notif_bad_lys_parent_b` (defined in `packages/notifikationer.yaml`)
- `input_boolean.notif_bad_lys_enabled` (defined in `packages/notifikationer.yaml`)
- `input_boolean.notif_bad_lys_hjemme` (defined in `packages/notif_hjemme.yaml`)
- `input_boolean.notif_bad_lys_parent_a` (defined in `packages/notifikationer.yaml`)
- `input_boolean.roborock_styrbar_kort_op_badevaerelse` (defined in `packages/roborock_styrbar.yaml`)
- `input_boolean.styrbar_lr_grace_badevaerelse` (defined in `packages/room_modes.yaml`)

### `input_datetime.*`

- `input_datetime.badevaerelse_auto_off_at` (defined in `packages/besoeg_fortryd.yaml`)
- `input_datetime.badevaerelse_brusebad_stempel` (defined in `packages/badevaerelse_brusebad.yaml`)
- `input_datetime.badevaerelse_bruser_vagt_slut` (defined in `packages/badevaerelse_bruser_vagt.yaml`)
- `input_datetime.badevaerelse_bruser_vagt_start` (defined in `packages/badevaerelse_bruser_vagt.yaml`)
- `input_datetime.badevaerelse_dagmode_senest` (defined in `packages/badevaerelse_faser.yaml`)
- `input_datetime.notif_bad_lys_slut` (defined in `packages/notifikationer.yaml`)
- `input_datetime.notif_bad_lys_start` (defined in `packages/notifikationer.yaml`)
- `input_datetime.styrbar_last_press_badevaerelse` (defined in `packages/room_modes.yaml`)

### `input_number.*`

- `input_number.badevaerelse_bruser_off_faktor` (defined in `packages/badevaerelse_bruser_vagt.yaml`)
- `input_number.badevaerelse_medium_brightness` (defined in `packages/badevaerelse_faser.yaml`)
- `input_number.badevaerelse_min_on_minutes` (defined in `packages/constants.yaml`)
- `input_number.sove_gardin_bad_tomt_minutter` (defined in `packages/sove_gardin_bad_gate.yaml`)

### `input_select.*`

- `input_select.badevaerelse_visit_stage` (defined in `packages/badevaerelse_visit_quality.yaml`)
- `input_select.room_mode_badevaerelse` (defined in `packages/room_modes.yaml`)
