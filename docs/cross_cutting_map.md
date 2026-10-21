# Cross-Cutting Concerns Map

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Formål:** Når du vil ændre noget i én YAML-fil, så viser dette dokument hvilke
ANDRE filer der også bliver påvirket. Forhindrer du brydende ændringer på
tværs af koden.

**Brug:** Find dit "concept" i tabellen. Læs CONSUMERS-listen før du editor.
Hvis ⚠️-flag: ekstra forsigtig (validators kan ikke fange fejl).

**Sidst opdateret:** 2026-05-08 efter sprint sequence (kids_home v2, putning
auto-detect, morning sanity-check, kalde blink, global tuning sliders).

---

## 🎯 Top 15 cross-cutting concerns

### 1. ⚠️ `light.{room}_all` light groups

**Defineret i:** [packages/light_groups.yaml](../packages/light_groups.yaml)
**Type:** Light groups (7 per-rum + 2 cross-room)

**CONSUMERS** (alle bruger templated refs `light.{{ room }}_all`):
| Fil | Linje | Bruger |
|---|---|---|
| [script_pkg/styrbar_helpers.yaml](../script_pkg/styrbar_helpers.yaml) | 49, 127, 201, 222, 246 | styrbar_color_cycle, brightness_step, snap_full, snap_off, reset_warm_white |
| [script_pkg/room_logic.yaml](../script_pkg/room_logic.yaml) | — | room_mode_apply, room_drift_back |
| [automations/styrbar_rooms.yaml](../automations/styrbar_rooms.yaml) | 273 | styrbar_universal_lr_hold |

**⚠️ KRITISK:** `ha_validate.py` kan **ikke** fange broken refs til templated
entity_ids. Hvis du sletter en gruppe → ALLE 5 Styrbars går silent broken.
Smoke test `test_room_light_groups_exist` i `scripts/ha_smoketest.py` catcher
det post-deploy. **Sletning af en gruppe kræver verifikation alle 11 refs er
fjernet først.**

**Historie:** Phase 3.D 2026-05-07 slettede grupperne med begrundelse "0 refs"
— det var FORKERT pga templated refs. Resultat: ALLE 5 Styrbars broken i 6 timer.

---

### 1b. ⚠️ Open-plan room_modes (3 stk.) + `binary_sensor.open_plan_manual`

**Defineret i:** [packages/room_modes.yaml](../packages/room_modes.yaml)
**Type:** 3 × `input_select` + 1 aggregat-`binary_sensor` (siden **2026-09-03d**)

Open-plan var ÉT anker (`room_mode_stue`) fordi det fysisk er ét rum. User-spec
2026-09-03d: *"hvis jeg via app justerer lys i spisestuen, så skal kun
spisestuen gå på manuel, ikke hele open plan"*. Nu:
`room_mode_stue` = **kun sofa-zonen**, plus `room_mode_spisestue` og
`room_mode_koekken`.

**BESLUTNINGSREGEL når du rører en gate:**
| Automationen handler på… | Skal læse |
|---|---|
| ÉT rums lamper (spiseloftet, køkkenkæden, sofa-lamperne) | dét rums eget `input_select.room_mode_<rum>` |
| hele open-plan-sættet på én gang | `binary_sensor.open_plan_manual` |

**CONSUMERS af aggregatet:**
| Fil | Bruger |
|---|---|
| [automations/presence_lights.yaml](../automations/presence_lights.yaml) | Stue sluk ved LUX-stigning (rører både spiseloft og sofa) |
| [packages/morgen_opstigning_rampe.yaml](../packages/morgen_opstigning_rampe.yaml) | 3 gates — rampen tænder `stue_laesehygge` + `koekken_lyskaede` |
| [automations/arrival.yaml](../automations/arrival.yaml) | Velkomstlys stue+køkken |
| [packages/sleepover.yaml](../packages/sleepover.yaml) | mørke-vagten slukker hele open-plan-rosteret |

**⚠️ WRITE-LISTER (glemmer du én, hænger et rum på Manual for evigt):**
`packages/all_rooms_mode.yaml` · `script_pkg/room_logic.yaml` (scene-exit) ·
`automations/entre_somrig.yaml` (NED-hold) · `packages/dance_mode.yaml`
(fest-release + room-map) · `packages/sleepover.yaml` (Styrbar OP) ·
`automations/room_drift_back.yaml` (per-rum drift-back — kræver at rummets
occupancy-sensor står i `presence_map`).

**⚠️ Fail-open:** gatesne skrives `not is_state(..., 'on')` / `not
is_state(..., 'Manual')` — mangler entity'en, skal lyset stadig virke.

**⚠️ Nye stempler:** `input_datetime.styrbar_last_press_spisestue` / `_koekken`
skrives af `script.styrbar_stamp_press` via `manual_override.yaml`s rum-map.
Læsere der brugte `_stue` som open-plan-vidne (nattur-blokken i
`godnat_night.yaml`, sleepover-vagten) tager nu det NYESTE af de tre.

---

### 2. `godnat_*_active` flags + `binary_sensor.godnat_any_active`

**Defineret i:** [packages/house_modes.yaml](../packages/house_modes.yaml)
**Union sensor i:** [packages/activity_state.yaml](../packages/activity_state.yaml) (`binary_sensor.godnat_any_active`)

**Flag-hierarki:**
```
godnat_active           = master (BÅDE voksne+boern aktive + pending=off)
godnat_voksne_active    = voksen i seng (sove Somrig kort-ned)
godnat_boern_active     = kid i seng (kalde-knap kort-ned ELLER putning auto-detect ELLER dashboard tile)
godnat_pending          = voksen-godnat afventer commit
kalde_active            = kid trykked kalde-knap (auto-clear ved 5-min absence)

binary_sensor.godnat_any_active = ON hvis NOGEN af ovenstående er ON
```

**SINGLE SOURCE OF TRUTH for actions:**
[automations/godnat_night.yaml](../automations/godnat_night.yaml):
- `automation.godnat_boern_active_on_actions` triggers på flag flip off→on
  → slukker boern_loft + boern_lampe (intet gardin i børneværelset, 2026-07-28)
- ALLE entry-points (kalde-knap, putning auto-detect, dashboard tile, script.godnat)
  bare sætter `godnat_boern_active=on` → cascading actions sker via on_actions automation

**CONSUMERS** (~30 automations):
- Per-rum presence_lights (gates: `godnat_any_active=off`)
- wakeup_kids_weekday/weekend (gates: `godnat_boern_active=off`)
- arrival.yaml (different brightness if godnat_any=on)
- airbnb_mode.yaml lockdown/resume
- script.godnat / script.godmorgen (sets/clears flags)

**Hvis du ændrer flag-logik:** check union sensor først (line 214 i activity_state.yaml).

---

### 3. `binary_sensor.kids_home` (v2 2026-05-08 → omskrevet 06-18 → ankomst 07-30)

**Defineret i:** [packages/activity_state.yaml](../packages/activity_state.yaml) (~line 413+)
**Manual override:** `input_boolean.kids_home_manual` / `_manual_off` ([packages/house_modes.yaml](../packages/house_modes.yaml))

⚠️ Den gamle **S1-S4-model er HISTORIK** — 2026-06-18 slettede den, fordi S1/S2/S3
var KUMULATIVE (15 min / 30-60 min pr. 4 t) og tændte børne-natlys fire dage i
træk uden børn i huset.

**4 signaler (any-of-4 → kids_home=true):**
- `slept_latch`: `input_boolean.boern_sov_her_i_nat` (sat/ryddet 06:30 ud fra
  sidste nat). **Fire skrivere** — jf. fejlklasse #1, ryk aldrig ét sted alene:
  06:30-jobbet ([boern_sleep_latch.yaml](../automations/boern_sleep_latch.yaml)),
  putningen ([godnat_night.yaml](../automations/godnat_night.yaml)),
  putte-trigger D ([putning_auto_detect.yaml](../automations/putning_auto_detect.yaml))
  og ⭐ 2026-07-30 et bekræftet "✅ Ja" EFTER `putning_vindue_start`
  ([boern_ankomst_detekter.yaml](../automations/boern_ankomst_detekter.yaml)).
  Fælles præmis: alle fire kræver et menneske-signal eller nattens facit —
  automatikken sætter den aldrig selv, fordi latch'en driver 06:05-vækningen.
  ([airbnb_mode.yaml](../automations/airbnb_mode.yaml) rydder den ved
  mode-skift, men sætter den aldrig.)
- `overnight_now`: `sensor.boern_occupancy_overnight` ≥ **4,0 t**
- `today_high`: `sensor.boern_occupancy_today` ≥ **4,0 t**
- `ankomst` ⭐ 2026-07-30: `input_boolean.boern_aktivitet_detekteret` —
  **sammenhængende** ophold ≥ `boern_ankomst_ophold_minutter` (12).
  De tre øvrige forudsætter alle at børnene har været her i TIMEVIS → uden dette
  var kids_home off hele ankomst-dagen indtil putning.
  Se [packages/boern_ankomst.yaml](../packages/boern_ankomst.yaml).

**Diagnostic attributes** (hover på tile): `signal_latch_slept`,
`signal_overnight_hours` + `_now_4t`, `signal_today_hours` + `_high_4t`,
`signal_ankomst_aktivitet`, `override_*`, `adults_home`.

**Override hierarchy:**
1. AirBnB house_mode → false (lockdown)
2. `input_boolean.kids_home_manual_off=on` → false (overruler ALT)
3. `input_boolean.kids_home_manual=on` → true (force)
4. Ingen voksen hjemme → false (4- og 1-årige kan ikke være hjemme alene)
5. Else → 4 signal any-of

**CONSUMERS:**
| Fil | Brug |
|---|---|
| [automations/wakeup_kids.yaml](../automations/wakeup_kids.yaml) | Skip wakeup hvis kids_home=off (line ~37) |
| [automations/putning_auto_detect.yaml](../automations/putning_auto_detect.yaml) | Skip auto-detect hvis kids_home=off (begge triggers) |
| [automations/boern_ankomst_detekter.yaml](../automations/boern_ankomst_detekter.yaml) | Sætter/rydder ankomst-signalet + spørger user (facit → ai_feedback) |
| [dashboards/status.yaml](../dashboards/status.yaml) | Tile + ankomst-flag |
| [dashboards/settings.yaml](../dashboards/settings.yaml) | Ankomst-slidere + kill-switch |

**Backlog B16:** Apollo MSR-2 radar height detection (post-flyt) — definitivt
højde-signal der kan skelne barn fra voksen direkte.

---

### 4. Global tuning sliders (4 input_numbers)

**Defineret i:** [packages/global_tuning.yaml](../packages/global_tuning.yaml)
**Computed factors via template_sensors** (samme fil):

| Slider | Default | Range | Factor | Effect |
|---|---|---|---|---|
| `global_light_aggressiveness` | 50 | 0-100 | 0.5 → 1.5 | Multiplier på alle brightness_pct |
| `global_sensor_sensitivity` | 50 | 0-100 | 2.0 → 0.5 INVERSE | Multiplier på Apollo radar gate thresholds |
| `global_turn_off_aggressiveness` | 50 | 0-100 | 2.0 → 0.2 INVERSE | Multiplier på `for:` durations i absence triggers |
| `global_lux_sensitivity` | 50 | 0-100 | 0.5 → 2.0 | Multiplier på lux thresholds |

**⚠️ CONSUMERS** (mange):
- `global_brightness_factor`: ~30 brightness_pct templates (alle presence_*, wakeup_*, arrival, godmorgen)
- `global_radar_threshold_factor`: [automations/apollo_radar_global_tuning.yaml](../automations/apollo_radar_global_tuning.yaml) → NVRAM writes
- `global_absence_wait_factor`: ~6 templated `for:` durations + `sensor.open_plan_empty_for_20m`
- `global_lux_threshold_factor`: ~14 day-aware lux templates

**Persistence:** `initial:` field FJERNET fra alle helpers (audit-fix 2026-05-07).
På en FRISK install gendanner `automation.init_user_preferences_first_boot`
alle input_numbers fra `config_snapshots/helper_values.yaml` (P1 2026-10-04).

**Hvis du ændrer en slider's range/default:** sæt den live + `helpers_export.py` — snapshottet ER defaulten.

---

### 5. Apollo radar tuning chain

**Trigger:** Slider change → 2s debounce → action chain

```
input_number.global_sensor_sensitivity (slider drag)
  ↓ (state change + for: 2s debounce)
automation.apollo_radar_global_tuner (automations/apollo_radar_global_tuning.yaml)
  ↓ (per-room dispatch)
script.apollo_radar_tune_room (script_pkg/apollo_helpers.yaml)
  ↓ (multiplies baseline gates × factor, max(1, …))
number.set_value på Apollo entities (NVRAM write)
  - number.{room}_apollo_g{0-8}_still_threshold
  - number.{room}_apollo_g{0-8}_move_threshold
```

**Per-rum baselines:** definert i `apollo_radar_global_tuning.yaml` variables
(`default_gates`, `sove_gates`).

**Sove er tunet anderledes** end default (g2/g3/g5 still threshold lower) per
audit-runde 19 + 2026-05-05 issue 4.

**Triggers:** slider change + Apollo back online (from unavailable→on/off) + HA start (60s delay).

---

### 6. Putning detection chain (sprint 2026-05-07/08, opdateret 2026-08-07)

Alle fire triggers ligger i `automations/putning_auto_detect.yaml`.

```
TRIGGER A (primary) — 2026-06-12 ROLLESKIFT: START-signal, IKKE flag:
  binary_sensor.badevaerelse_inde_occupancy → on for 3 min
  + time putning_vindue_start (18:30) → putning_vindue_slut (22:00)
    ⚠️ 2026-08-07: bagkanten var natlys_start (20:30) = NATLYSETS bagkant,
       ikke putningens. Nu egen slider (user: "putte lidt sent").
  + kids_home=on + godnat_boern=off + phase1_fired=off + descent=off
  + manual_off_lock=off + putning_sove_active=off
  ↓
- id: putning_auto_detect_via_bath_visit
  ↓ (TÆNDER FASE 1: script.puttelys_phase1_when_present → _phase1_apply —
     sætter IKKE godnat-flaget! phase1_fired forhindrer dobbelt-apply;
     cleares 09:00 af godnat_subflag_safety.)

TRIGGER B (fallback, still_target):
  binary_sensor.boernevaerelse_apollo_radar_still_target → on for 10 min
  + time 19:30–23:30 (EGEN faste bagkant — påvirkes IKKE af vindue_slut)
  + kids_home=on + boern motion seen recently + manual_off_lock=off
  ↓
- id: putning_auto_detect_via_boern_still
  ↓ (sætter godnat_boern_active DIREKTE)

TRIGGER C (user-signal): manuel natlys-dim af hygge-strippen
  ↓
- id: putning_auto_detect_via_natlys_dim
  ↓ (sætter godnat_boern_active direkte)

TRIGGER D (ankomst-aften / GENSTART efter afbrydelse) — 2026-06-12, udvidet 08-07:
  zha_event Styrbar børn OP (device_ieee 66:19:44:cc:2c:41:57:fe, cmd 'on')
  + time 18:45 → putning_vindue_slut  + auto_putning_enabled + Normal + Active
  + descent=off
    ⚠️ 2026-08-07: godnat_boern_active er IKKE længere en spærring på
       forkanten — efter en færdig nedtrapning stod den on, så et OP-tryk
       kunne ikke starte en NY session (user-spec efter tv-pause).
  ↓ wait_for_trigger: N min sammenhængende presence i lægge-zonen
    (binary_sensor.boern_putte_zone_aktiv; template-trigger fanger
     "zonen var allerede on" — fejlklasse #4-variant)
  ↓ EFTER presence-bekræftelsen: godnat_boern_active ryddes → fase 1
- id: puttelys_styrbar_start

MANUAL TRIGGER (UI):
  Dashboard tile "Boern i seng" toggle → sætter flaget direkte

ALLE PATHS → SAME CASCADE:
  input_boolean.godnat_boern_active = on
  ↓ (state flip off→on)
automation.godnat_boern_active_on_actions (automations/godnat_night.yaml)
  ↓
  - light.turn_off boern_loft + boern_lampe (transition 5s)
  ↓ (samme flip trigger også puttelys_natlys_strip = FASE 2 natlys,
     med 20:30 time-backstop; gated på binary_sensor.dark_mode_boern == off)
  ↓
binary_sensor.godnat_any_active = on (template recompute)
  ↓
  presence_light_boernevaerelse_on GATED (= boern lys forbliver dark)
```

**Kill switches:**
- `input_boolean.auto_putning_enabled` (default on) — slukker auto-detect
- `input_boolean.kids_home_manual` (manual override af kids_home)

**Recovery hvis false-positive:**
- Toggle "Boern i seng" tile → off
- Styrbar OP i boern (Trigger D): genåbner putningen — clearer godnat_boern_active
  + dræber kørende descent + tænder fase 1 (gardin forbliver lukket)
- Vent på morgen wakeup_kids auto-clear
- 09:00 godnat_subflag_safety_clear

**Med-ejere der kan SLUKKE puttelyset (grep før du ændrer noget her):**
- `luksus_lys_elpris_suppress_boern_strip` (packages/luksus_lys.yaml) — slukker
  hygge-strippen ved høj el-pris. **Undtaget siden 2026-08-07** når
  phase1_fired / descent_active / godnat_boern_active er on; uden undtagelsen
  slukkede den natlyset 1 s efter både fase 1 og fase 2 (målt 08-07).
- `boernevaerelse_manual_off_lock_arm_tv` (ARM 2 i
  packages/boernevaerelse_manual_off_lock.yaml) — tv tændt i børneværelset
  afbryder bevidst en igangværende putning, slukker rummet og armerer låsen.
  **Rum-lokalt** (user-valg 08-07 "frigiv stuen"): den tænder IKKE dark_mode /
  cinema_active, så resten af huset kører videre med normalt auto-lys.
  Udgangen er Styrbar børn OP = låsens CLEAR 1 → Trigger D.
- `presence_lux_boernevaerelse_off` — dagslys-sluk; ejer IKKE loftet i
  putte-vinduet (gated på phase1_fired / descent_active siden 08-06d).

---

### 7. Morning auto-off chain (sprint 2026-05-08)

**Filer:** [automations/morning_lights_sanity_check.yaml](../automations/morning_lights_sanity_check.yaml)

```
Trigger A: sensor.{room}_apollo_lux > 50 for: 5 min
Trigger B: binary_sensor.{room}_apollo_occupancy → off for: 10 min

Conditions: time 06-12 (07-12 for sove) + light on + no mood + godnat_any=off
  ↓
light.turn_off {room}_loft (4s smooth fade)
```

**Per-rum scope (pre-flyt):**
- `morning_boern_auto_off_when_bright_or_empty`
- `morning_sove_auto_off_when_bright_or_empty`
- entre: handled af eksisterende entre_motion off-rule

---

### 8. Notification routing (Parent A + Parent B)

**Phone services:**
- `notify.mobile_app_phone_a` — Parent A (Sony Xperia Android)
- `notify.mobile_app_phone_b` — Parent B (iPhone)

**Persistent notifications:** `persistent_notification.create` viser i HA UI for ALLE.

**Inkonsistent brug** (audit needed):
| Hvad | Hvem | Filer |
|---|---|---|
| Kalde-knap kid press | BEGGE | godnat_night.yaml `godnat_kalde_on` |
| Putning auto-detected | KUN Parent A | putning_auto_detect.yaml (begge triggers) |
| Water leak | KUN Parent A | water_leak_alarm.yaml |
| Battery alerts | KUN Parent A | battery_alerts.yaml |
| Device health | KUN Parent A | device_health_check.yaml |

**🟠 Backlog F2:** Audit + bulk replace til `notify.alle_voksne` group (kræver gruppe-definition).

---

### 9. Wakeup chain (cascade)

```
05:30-06:30 (variable): wakeup_alarm_driven_adults
  ↓ (if Parent A's phone alarm sat + 30 min før)
  Sove fade 5% → 40% → 80% over 30 min
  Phase 3 clearer ALLE godnat flags

06:00 (workday): godnat_auto_clear (= "Godnat: Deaktivér om morgenen")
  Conditions: workday + house presence + 06-12 window
  Action: clear godnat flags + open curtains

Voksenalarm + N min (workday, default 15): wakeup_kids_weekday
  2026-08-05: IKKE længere fast 06:05. Målet er ÉT anker, sensor.wakeup_kids_maal
  (packages/global_tuning.yaml), som både trigger og condition læser:
    1. input_datetime.wakeup_alarm_gaaet_af_at (stemplet i alarm-minuttet) + slider
    2. sensor.wakeup_alarm_next (forventet alarm i dag) + slider
    3. ingen alarm → fast 06:05 (den gamle adfærd)
  Loft 04:00-09:00 + last_triggered-guard = max én rampe pr. dag.
  Gates: presence_avail + workday + Active + kids_home + boern overnight motion + godnat_active=off + godnat_boern_active=off + lux<80
  Phase 1 (5%) → Phase 2 (30%) → Phase 3 (60%) → Phase 4 (curtain) over 15 min
  Ramper ALLE tre dæmpbare børne-lys + tænder hyggelys-pluggen (loftet er tit
  slukket på vægkontakten).

07:30 (weekend): wakeup_kids_weekend
  Same gates som weekday (sprint 2026-05-08)
  Phase 1-3 + curtain (50% peak, softere)

15-20 min efter adult wakeup: wakeup_post_sluk
  Smart LUX-aware fade off ELLER dim-down

08:00: wakeup_alarm_driven_restart_recovery
  Backup hvis HA restartede mid-wakeup → force Phase 3

08:00 daglig + state-trigger: morning_lights_sanity_check (NEW sprint 2026-05-08)
  Auto-off boern/sove hvis bright eller empty
```

**Vigtigt:** wakeup_kids gates blev STRENGT 2026-05-08 — kræver `kids_home=on` +
overnight boern motion + `godnat_boern_active=off`. Forhindrer fyring uden behov.

---

### 10. Lux abstractions

> ⚠️ **Adfærds-logik læser ALDRIG `sensor.<rum>_apollo_lux` direkte.** Apolloens
> onboard varsels-LED lyser ind i sin egen LTR390 (op til ~+490 lx), så den rå
> sensor melder dagslys i et bælgmørkt rum. Brug altid
> `sensor.<rum>_lux_reel` fra
> [packages/apollo_led_lux_kompensation.yaml](../packages/apollo_led_lux_kompensation.yaml)
> — findes for alle fem rum, og er identisk med rå-værdien når LED'en er slukket.
> Rå-sensorerne er kun til diagnostik/device-health-tiles. (2026-07-30)

**`sensor.open_plan_lux`** (template, fallback chain):
- Defineret i [packages/activity_state.yaml](../packages/activity_state.yaml)
- Snit af `spisestue_lux_reel` + `koekken_lux_reel`; fallback-kæde
  sove → stue → entré-valhorn
- Bruges af cross-room automations (cooking, dining, social_dining, presence_stue/koekken/spisestue)

**Per-rum lux:**
- `sensor.boernevaerelse_lux_reel` — boern only
- `sensor.sovevaerelse_lux_reel` — sove only
- `sensor.koekken_lux_reel` / `sensor.spisestue_lux_reel` — driver open_plan_lux
- `sensor.stue_lux_reel` — `unavailable`: chippen døde 2026-05-05

**Day-aware threshold pattern (14 sites):**
```jinja
{% set lux = states('sensor.X_lux') | float(50) %}
{% set day = is_state('sensor.sun_bracket', 'day') %}
{% set f = states('sensor.global_lux_threshold_factor') | float(1.0) %}
{{ lux < ((day_threshold if day else night_threshold) * f) }}
```

Hvor `day_threshold < night_threshold` (= stricter mid-day).

---

### 11. `sensor.auto_color_temp_evening` (sun-aware Kelvin)

**Defineret i:** [packages/activity_state.yaml](../packages/activity_state.yaml)

**4 brackets baseret på sun.elevation:**
- High day (>10°): 4000K (cool white)
- Mid (0-10°): 3000K (neutral)
- Twilight (-6 to 0°): 2500K (warm)
- Night (<-6°): 2326K (very warm)

**CONSUMERS:** ~10 places — entre_motion, light_power_recovery (bath/sove),
arrival.yaml welcome lights, presence_lights bath, etc.

**Hvis du ændrer brackets:** verificer alle CONSUMERS forventer same K-range
(ingen hardcoded checks).

---

### 12. `sensor.activity_state` (intelligent classifier)

**Defineret i:** [packages/activity_state.yaml](../packages/activity_state.yaml)

**Mulige tilstande:**
`idle`, `bedroom_only`, `sofa_relax`, `dining`, `cooking`, `social_dining`,
`social_party`, `nightwalk`, `bath_visit`, `transit`, `terrasse_only`,
`terrasse_with_indoor`, `godnat`, `active`.

**CONSUMERS:**
- `automation.activity_guest_mode_auto_set` (in activity_aware.yaml) — sustained social → guest_mode; `terrasse_with_indoor` kun med `input_number.people_ekstra_gulv` ≥ 1 (B183). Auto-clear har 5-min restart-backstop.
- `automation.bedroom_winddown_auto_set` — bedroom_only after 21:00 → winddown flag
- `automation.terrasse_winddown_set` — terrasse_only

**F5 fix audit Phase 1 2026-05-07:** activity_state nu bruger `godnat_any_active`
(union) i stedet for kun master flag.

---

### 13. Recorder filter (DB-størrelse)

**Defineret i:** [configuration.yaml](../configuration.yaml) `recorder.exclude` block

**Filtrer ud:**
- Alle `_lqi`, `_rssi`, `_link_quality`, `_last_seen`, `_battery_voltage` (Zigbee diagnostic)
- Apollo radar gate energy (`_apollo_g*_*_energy`, `_apollo_radar_*_energy`, `_distance`)
- Apollo zone occupancy (`*_apollo_radar_zone_*_occupancy`, `_moving_target`, `_still_target`)

**A57 fix audit-3 2026-05-06:** Apollo zone binary_sensors fyrer 596+/2h — added
til exclude. Restore I1's "30-50% reduction" target.

**Hvis du tilføjer noisy entity:** check om den skal i recorder exclude (DB grow).

---

### 14. Init user preferences (fresh-install protection)

**Fil:** [automations/init_user_preferences.yaml](../automations/init_user_preferences.yaml)

**Trigger:** `homeassistant: start` event (efter 30s delay).

**Logik (P1 2026-10-04):** kun på en FRISK install (`prefs_fresh_install`):
ét loop gendanner hver input_number der står på sin min fra
`config_snapshots/helper_values.yaml` (`!include`). Derefter: kill-switches,
datetimes, selects/texts og Apollo-NVRAM-push (`*_apollo_apply_all_gates`
skubber nu de TUNEDE gates). Staging-bevis: 644/644 sliders = tunet værdi.

**⚠️ Hvis du tilføjer en ny tunable input_number:**
1. Drop `initial:` field i input_number definition (kvæler restart-persistence)
2. Sæt den live + `python3 scripts/helpers_export.py` + commit (= fresh-install-default)
3. Tilføj til `critical_helpers` list i `scripts/ha_smoketest.py`

---

### 15. Smoke test critical_helpers list

**Fil:** [scripts/ha_smoketest.py](../scripts/ha_smoketest.py) line ~370 `test_critical_helpers_exist()`

**Hvis test fejler:** auto-deploy ROLLBACKS via `scripts/ha_deploy.sh`.

**Liste vedligeholdt manuelt** — hvis du tilføjer en kritisk helper, opdater
denne liste. Hvis du fjerner en helper men efterlader i listen, deploy fejler.

**Nuværende liste (19 entries):**
- `input_boolean.godnat_active`, `cinema_active`, `cirkus_active`, `guest_mode`
- `input_select.house_state`, `house_mode`
- `input_number.fade_living_seconds`, `fade_hallway_seconds`, `fade_extended_seconds`,
  `lr_grace_milliseconds`, `godnat_brightness_pct`, `godnat_kelvin`,
  `global_light_aggressiveness`, `global_sensor_sensitivity`,
  `global_turn_off_aggressiveness`, `global_lux_sensitivity`,
  `room_manual_on_hold_hours`

---

## 🚦 Trafik-lys: hvor sikkert er det at edit X?

| Hvis du editor… | Sikkert | Forsigtig | ⚠️ Farligt |
|---|---|---|---|
| Per-rum presence_X.yaml (en fil) | ✅ Local change, tested via per-room |  |  |
| Brightness pct i én automation | ✅ Local effect |  |  |
| Tilføj en ny scene_X script |  | ⚠️ Husk dashboard tile + scene_idx_map (4 steder) |  |
| Slette en helper |  |  | ❌ Tjek consumers først via grep |
| Slette en light_group |  |  | ❌ Templated refs — validators MISSER |
| Ændre godnat_*_active flag-logik |  |  | ❌ ~30 consumers i automations |
| Ændre kids_home signaler | ✅ Self-contained i activity_state.yaml |  |  |
| Ændre house_state Dormant-paths |  |  | ❌ `binary_sensor.physical_presence_recent` er central (2026-06-02): (1) VETOER de 3 phone-paths (to_dormant/gps_fast/flag_fast), (2) TRIGGER den primære `house_state_to_dormant_physical` (3t ingen aktivitet → Dormant, uafhængig af telefon, godnat-gated). Sensoren = "occupancy ON nu (ikke stuck 24h) ELLER transition/knap <3t". Fysisk aktivitet = suverænt HJEMME. Rør ikke uden at forstå current-occupancy + transition stuck-proofing |
| Tilføje ny global slider |  | ⚠️ Init defaults + smoke test list |  |
| Ændre Apollo gate baseline | ✅ Self-contained i apollo_radar_global_tuning.yaml |  |  |
| Tilføje notification | ✅ Test via persistent first |  |  |
| Ændre recorder filter | ✅ Doc-only impact |  |  |
| Ny skriver/låner til en lampe med ejerskabs-register (`ejerskab/`) |  | ⚠️ Registret + `python3 scripts/ejerskab.py gen` — pre-commit blokerer ellers |  |
| Bulk-replace numerics |  |  | ❌ `transition: 60` matcher prefix af 600! |

---

## 🔍 Verifications efter ændringer

```bash
# 1. Validate YAML + entity refs (skipper templated refs!)
python3 scripts/ha_validate.py

# 2. Live entity refs (tjekker mod HA running state)
python3 scripts/ha_validate.py --check refs --live

# 3. Smoke test (after deploy)
python3 scripts/ha_smoketest.py

# 4. Doc-regen if entities/files changed
python3 scripts/gen_docs.py

# 5. Auto-deploy with auto-revert
bash scripts/ha_deploy.sh
```

**Auto-deploy gate:** `scripts/ha_deploy.sh` (sprint 2026-05-06):
- Pre-deploy snapshot
- Restart HA
- 15s settle
- Smoke test (critical-tier blocks deploy)
- Auto-rollback hvis fail (logs til `.cache/last_rollback.json`)

---

## 📚 Se også

- [CLAUDE.md](../CLAUDE.md) — backlog + standing instructions
- [AGENTS.md](../AGENTS.md) — fast-path navigation for AI sessions
- [docs/architecture.md](architecture.md) — system design overblik
- [docs/state_machine.md](state_machine.md) — state transitions
- [system_design.md](../system_design.md) — verificeret Holy Grail-spec (knapper, drift-back, sluk-tider, hus-tilstande)
- [packages/README.md](../packages/README.md) — index over helpers + template_sensors
- [automations/README.md](../automations/README.md) — index over automation-filer
