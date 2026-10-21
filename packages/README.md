# packages/ — index

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

HA "packages" mekanisme tillader at gruppere relateret config (input_boolean + input_number + input_select + input_datetime + sensor + automation + script + ...) i én fil per concern.

Loaded af HA via `homeassistant: packages: !include_dir_named packages/` i [configuration.yaml](../configuration.yaml).

**Last reviewed: 2026-05-08** efter sprint sequence (kids_home v2 + putning auto-detect + global tuning sliders + morning sanity-check + kalde blink).

---

## Indhold

| Fil | Beskrivelse | Definerer |
|-----|-------------|-----------|
| **[house_modes.yaml](house_modes.yaml)** ⭐ | House lifestyle (Normal/AirBnB/Vacation) + state (Active/Dormant) + alle mood-flag input_booleans + person-tracking + arbejdsdag template + house_state_to_active/_dormant automations + **NEW (2026-05-08): kids_home_manual + auto_putning_enabled** | input_select × 2, input_boolean × 14, template-sensors × 4, automations × 8 |
| **[room_modes.yaml](room_modes.yaml)** ⭐ | Per-rum room_mode + last_press timestamps + Styrbar color/hue/grace/holding helpers | input_select × 7, input_datetime × 7, input_number × 17, input_boolean × 17 |
| **[activity_state.yaml](activity_state.yaml)** ⭐ | Aktivitets-klassifikation: sensor.activity_state, terrasse_active, presence_sensors_available, auto_color_temp_evening, **godnat_any_active union**. Plus guest_mode + bedroom_only_winddown. **NEW (2026-05-08): binary_sensor.kids_home + 2× history_stats sensorer (boern_occupancy_4h, boern_occupancy_today)**. Kids_home-signalerne er latch/overnight/today (06-18) + **ankomst (07-30, se boern_ankomst.yaml)** — den gamle "v2 S1-S4"-liste i header-kommentaren er historik. | template-sensors × 5, template-binary-sensors × 4, history_stats × 2, input_boolean × 2 |
| **[boern_ankomst.yaml](boern_ankomst.yaml)** ⭐ NEW (2026-07-30) | Ankomst-detektion = 4. auto-signal i `binary_sensor.kids_home`. Headeren bærer kalibrerings-tabellen (14 dages længste sammenhængende børneværelses-ophold pr. dag) + hvorfor flaget bevidst IKKE er `boern_sov_her_i_nat`. Automations i [automations/boern_ankomst_detekter.yaml](../automations/boern_ankomst_detekter.yaml). | input_boolean × 2, input_number × 2, input_datetime × 2, input_text × 1 |
| **[global_tuning.yaml](global_tuning.yaml)** ⭐ NEW (2026-05-07) | 4 user-tunable sliders (Light Aggressiveness, Sensor Sensitivity, Turn-Off Aggressiveness, LUX Sensitivity) + 4 computed factor template_sensors. Default 50 = factor 1.0 (= no change). | input_number × 4, template-sensors × 4 |
| **[room_absence_tuning.yaml](room_absence_tuning.yaml)** ⭐ NEW (2026-08-12) | Per-rum sluk-forsinkelse for sofa-stuen og spisestuen (minutter), ganget med `sensor.global_absence_wait_factor` og klampet til 30 s–6 t. `sensor.spisestue_sofa_off_sekunder` = ¼ af den fulde værdi (min 60 s) = hurtig-sluk når man flytter fra spisebord til sofa. Forbruges af templatede `for:` i [automations/presence_stue.yaml](../automations/presence_stue.yaml). | input_number × 2, template-sensors × 3 |
| **[constants.yaml](constants.yaml)** | Tunable constants — fade-tider + lr_grace milliseconds + godnat brightness/kelvin. Persistence: `initial:` removed, defaults via init_user_preferences. | input_number × 6 |
| **[light_groups.yaml](light_groups.yaml)** ⭐ | Light + switch + cover groups for dynamisk reference. Per-rum `_all` (7 stk: stue, sove, boern, bad, depot, entre, terrasse) + cross-room `alle_lys`/`alle_indvendige` + smart-plugs + gardiner. **⚠️ KRITISK:** Templated refs `light.{{ room }}_all` MISSES af validators — sletning kræver verifikation. Se [docs/cross_cutting_map.md](../docs/cross_cutting_map.md) #1. | light groups × 9, group × 2 |
| **[presence.yaml](presence.yaml)** | Home zone GPS-koordinater + person-tracking automations (parent_a/parent_b arrive/leave) | zone × 2, automations × 5 |
| **[roborock.yaml](roborock.yaml)** ⭐ NEW (2026-06-10) | Roborock S8 MaxV Ultra: dormant-start (1×/dag, full hver 3. dag / quick ellers, full dagligt ved kids_home), interrupt ved Dormant-exit (pause+dock), completion-stamping, manuel quick/full toggle på ledig Styrbar. | input_boolean × 1, input_select × 1, input_datetime × 2, scripts × 3, automations × 4 |
| **[roborock_rum_scripts.yaml](roborock_rum_scripts.yaml)** ⭐ NEW (2026-08-13) | Rengøring pr. rum: 2 widget-/knap-scripts × 8 rum (🧹 hurtig = balanced + mop af · 💧 grundig = max_plus + extreme mop + deep_plus, 2 gennemløb). Roborock har ingen server-side kø → flere tryk lægger sig i en HA-kø der først dispatcher når robotten er ledig; tryk i træk med samme grundighed samles til ÉN `app_segment_clean`. **Indeholder den data-udledte segment→rum-tabel — læs den før du rører et segment-nummer.** | input_text × 2, input_datetime × 1, input_number × 2, sensors × 2, scripts × 19, automations × 3 |
| **[ejerskab_koekken_lyskaede.yaml](ejerskab_koekken_lyskaede.yaml)** 🤖 GENERERET (2026-10-04) | Fra [ejerskab/koekken_lyskaede.yaml](../ejerskab/koekken_lyskaede.yaml) via `python3 scripts/ejerskab.py gen` — RET IKKE. Rangeret `sensor.koekken_lyskaede_ejer` (højeste aktive krav, ellers `hus`), `binary_sensor.koekken_lyskaede_laant` (= ejer ≠ hus) og genoptag-automationen. Kontrakt: [docs/auto/ejerskab/koekken_lyskaede.md](../docs/auto/ejerskab/koekken_lyskaede.md). | sensor × 1, binary_sensor × 1, automation × 1 |
| **[ejerskab_index.yaml](ejerskab_index.yaml)** 🤖 GENERERET (2026-10-04) | `sensor.lys_ejerskab` — hvilke lamper har et ejerskabs-register (rum-logikkens drift-back sætter ikke deres styrke). | sensor × 1 |
| **[roborock_smartplan.yaml](roborock_smartplan.yaml)** ⭐ NEW (2026-10-04, eksperiment) | Roborocks SmartPlan (robotten vælger selv sug/vand/rute pr. rum) som kø-grundighed `s` — Styrbarens "Valgte rum — SmartPlan". Sættes atomisk med `set_clean_motor_mode` (110/209/306) + read-back i logbogen; landede den ikke → hurtig + push. **Afleveringen** tager robotten ud af SmartPlan igen efter HA's tur, så husets hurtige veje (der ikke skriver mop-ruten) ikke arver den. | input_boolean × 1, binary_sensor × 1, script × 1, automation × 1 |
| **[entre_ned_dormant.yaml](entre_ned_dormant.yaml)** NEW (2026-07-09) | Entré-Styrbar kort-NED armerer ét Dormant-tjek N min senere (default 15): tomt hus + terrassedør lukket + wasp-guard OK → Dormant. One-shot (stempel ryddes uanset udfald), annulleres ved senere entré-tryk. AirBnB undtaget. | input_number × 1, input_datetime × 1, automations × 2 |
| **[anomali_vagt.yaml](anomali_vagt.yaml)** NEW (2026-07-15) | Dysfunktions-detektor (observerer kun, rører intet): push ved lys i tomt rum ≥ N min, rum mørkt trods vedvarende bevægelse (soveværelser undtaget under godnat/putning) og terrasse-plug der ikke slukker under regn/Dormant/vinter-kill. Killswitch + 5 sliders + 3 push_notify-nids (anomali_lys/anomali_moerke/anomali_plug). Tiles på 🔔-fanen. | input_boolean × 10, input_number × 5, input_datetime × 9, automations × 3 |
| **[system_varsler.yaml](system_varsler.yaml)** NEW (2026-07-15b) | System-varsler: nids `sikkerhed` (dør-push — selve dør-automations bor i [automations/security.yaml](../automations/security.yaml)) + `backup` (dagligt 10:00-tjek: seneste backup > N timer / sensor død → push) + Apollo ESP-temp-canary (> N °C i 15 min → push via `apollo`-nid, 6t dedupe). 6 sliders + 2 runtime-dedupe-stempler. Tiles på 🔔-fanen. | input_boolean × 6, input_number × 6, input_datetime × 6, automations × 2 |
| **[dark_mode.yaml](dark_mode.yaml)** NEW (2026-07-27) | 🎬 Dark Mode (projektor-mørklægning): lukker rummets gardiner (m. manuel-grace-stempel), slukker lyset + **HOLDER det slukket** (enforce-backstop + source-gates + cinema_active-suppression). **Scope = ÉT rum** (2026-08-02) via prioritets-stigen sove → boern → stue, hver gated på aktivitet indenfor `dark_mode_meget_nylig_sekunder`; rum kan komme til undervejs, og listen er sticky. **Kører projektoren IKKE ved ON, er scopet hårdt `sove`** (2026-09-02, `input_boolean.dark_mode_kun_sove`): cinema_active sættes ikke, room_joins må kun tilføje `sove`, og køkken-lyskæden gater på `binary_sensor.dark_mode_stue` — open plan følger sofastuen, ikke soveværelset. OFF genåbner kun gardiner der var åbne + kun i dagslys (+ rydder deres grace). Toggles: Dark Mode-RODRET (op=ON/ned=OFF, **to op-tryk = alle tre rum** + open plan med igen), script.dark_mode_toggle (tlf-widget), tile på Scener-siden. | input_boolean × 2, input_text × 3, input_datetime × 2, input_number × 2, template × 2, script × 4, automation × 5 |
| **[mad_planlaegning.yaml](mad_planlaegning.yaml)** NEW (2026-07-29) | 🍽️ Mad-planlægning: sliders for hvornår/hvor ofte der spørges om retter (dagens ret til BEGGE telefoner med JA!/NIX!/Måske) + indkøbsliste-kalender (ugedag, hver N. uge, anker-dato), min/max retter, andel børnevenlige, basisvare-filter. Ret-katalog + stemmer i Google Sheets (Gemini fylder på); kører `scripts/mad_planner.py`. Se [docs/mad_planlaegning.md](../docs/mad_planlaegning.md). | input_boolean × 3, input_number × 6, input_datetime × 3, input_select × 1, shell_command × 5 |

| **[apollo_led_lux_kompensation.yaml](apollo_led_lux_kompensation.yaml)** ⭐ NEW (2026-07-30) | Apollo MSR-2'ens onboard varsels-RGB blænder sin EGEN LTR390 (målt +403 lx sove / +486 lx køkken @ brightness 204) → `sensor.sovevaerelse_lux_reel` + `sensor.koekken_lux_reel` trækker `offset × brightness/255` fra. **ALL adfærds-logik skal læse `_lux_reel`, ikke de rå `*_apollo_lux`** (fejlklasse #2). Køkkenets indgår i `sensor.open_plan_lux`. | input_number × 2, template-sensors × 2 |
| **[sove_alarm_morgen.yaml](sove_alarm_morgen.yaml)** (2026-07-30, omskrevet 07-31) | Morgen-soveværelset bag privacy-gardinet. **Afgangs-sekvensen** måler "to personer oppe": rummet bliver tomt mens entréen var aktiv (= én gik ud) → rummet optaget igen ≥ 8 min senere UDEN entré-trafik (= anden krop lå der allerede). `binary_sensor.sove_alarm_morgen_lys` = rummet er bevidst mørkt (alarm-vindue ELLER 06-11 med gardin på/under privacy) **OG** to oppe bekræftet — hård gate på begge sove-auto-tænd-veje. Bekræftet to-oppe + dagens første bad-besøg ovre → `script.sove_gardin_op` ruller gardinet helt op → presence normaliseres til lux-styring. Nulstilles 04:00. **Døren (2026-08-30):** `binary_sensor.parasoll_sovedoer` er husets første DIREKTE morgen-vidne — åben ≥ `sove_morgen_doer_aaben_minutter` i 04-12 sætter to-oppe uden om radar-udledningen, og `binary_sensor.sove_doer_moerkhold` (lukket dør 04-12) er et VETO oven i både lys-ankeret og `script.sove_gardin_op`. | input_datetime × 3, input_boolean × 1, input_number × 5, template-binary-sensor × 5, automation × 5 |
| **[regn_rapport.yaml](regn_rapport.yaml)** NEW (2026-08-01) | 🌧️ Regn-**FACIT**: hentet fra DMI's metObs-OBSERVATIONER (station 06180, Københavns Lufthavn) — alt andet regn-data i huset er forecast og kan ikke svare på "endte det med at regne". `sensor.regn_faldet` summerer `precip_past1h` over et slider-vindue (24 t) med `this`-fallback ved API-fejl. Morgen-automation sender KUN når der faktisk faldt ≥ minimums-grænsen. NB: hosten er `opendataapi.dmi.dk`, og VERSIONEN hører til produktet — `/v2/metObs` for observationer, `/v1/forecastedr` for prognosen (`/v1/metObs` er 404). Legacy-hosten `dmigw.govcloud.dk` er DNS-nedlagt 9/9 2026 og må ikke genindføres. | rest_command × 1, input_boolean × 1, input_number × 2, input_datetime × 1, trigger-sensor × 1, automation × 1 |
| **[sleepover.yaml](sleepover.yaml)** NEW (2026-08-13g) | 🛋️ Sleep Over: en overnattende gæst sover i open-plan → INTET automatisk lys dér mens godnat er aktivt (og videre til `sleepover_morgen_slut`, default 07:30, fordi godnat-flagene ryddes 06:00 og alle tænd-veje har en 6-12-undtagelse). Ét delt anker, `binary_sensor.sleepover_openplan_moerkt`, gates de 8 tænd-veje (presence stue/køkken, lux-fald ×2, nattur, velkomstlys, børn-oppe-i-stuen, HA-start-resync). Vagten slukker automatik-tændt open-plan lys igen — manuel tænding (Manual-mode / friskt Styrbar-tryk / user-context) vinder altid. "I nat" rydder sig selv om morgenen + ved AirBnB entry/exit. | input_boolean × 2, input_datetime × 1, template-binary-sensor × 1, automations × 2 |

⭐ = "skal kende" — primære filer.

---

## Hvor finder jeg X?

| Søger efter | I fil | Sektion |
|-------------|-------|---------|
| godnat_active boolean | house_modes.yaml | input_boolean |
| godnat_any_active **union** ⭐ | activity_state.yaml | template.binary_sensor |
| guest_mode boolean | activity_state.yaml | input_boolean |
| **kids_home_manual** boolean ⭐ NEW | house_modes.yaml | input_boolean |
| **auto_putning_enabled** kill switch ⭐ NEW | house_modes.yaml | input_boolean |
| **binary_sensor.kids_home** v2 ⭐ NEW | activity_state.yaml | template.binary_sensor |
| **boern_occupancy_4h** + **_today** ⭐ NEW | activity_state.yaml | sensor: history_stats |
| **global_*_aggressiveness/sensitivity** sliders ⭐ NEW | global_tuning.yaml | input_number |
| **global_*_factor** computed factors ⭐ NEW | global_tuning.yaml | template.sensor |
| room_mode_<rum> input_select | room_modes.yaml | input_select |
| Styrbar grace boolean per rum | room_modes.yaml | input_boolean.styrbar_lr_grace_<rum> |
| activity_state template sensor | activity_state.yaml | template.sensor |
| terrasse_active binary_sensor | activity_state.yaml | template.binary_sensor |
| presence_sensors_available master gate | activity_state.yaml | template.binary_sensor |
| auto_color_temp_evening sun-baseret K | activity_state.yaml | template.sensor |
| open_plan_lux fallback chain ⭐ | activity_state.yaml | template.sensor |
| people_estimate v4 = people_familie (voksne + børn) + ekstra-gulv fra people_zones_now | people_estimate.yaml | template.sensor |
| arbejdsdag (workday) template | house_modes.yaml | template.binary_sensor |
| house_state_to_active automation | house_modes.yaml | automation: |
| Light groups per rum | light_groups.yaml | light: - platform: group |
| Smart plugs + gardin groups | light_groups.yaml | group: |
| fade_passage_seconds + fade_ophold_seconds tunables | constants.yaml | input_number |
| lr_grace_milliseconds tunable | constants.yaml | input_number |
| godnat_brightness_pct + godnat_kelvin tunables | constants.yaml | input_number |
| Hjemmezone GPS | presence.yaml | zone: |
| Parent A/Parent B arrive automations | presence.yaml | automation: |

---

## Mode flag-oversigt (fra house_modes + activity_state)

```
Per-rum mode (room_modes.yaml):
  input_select.room_mode_<rum> ∈ {Auto, Manual, Dim, Bright, Off}

House lifestyle (house_modes.yaml):
  input_select.house_mode  ∈ {Normal, AirBnB, Home Vacation}
  input_select.house_state ∈ {Active, Dormant}

Mood-flags (house_modes.yaml input_boolean):
  cinema_active            — Dark Mode's interne suppression-flag (blokerer presence_lights); cinema-scenen fjernet 2026-07-27
  cirkus_active            — set af scene_cirkus, blokerer presence_lights
  godnat_active            — full house bedtime
  godnat_voksne_active     — voksen-godnat (somrig_6 click op)
  godnat_boern_active      — børn-godnat (somrig_4 / kalde-knap somrig_7)
  godnat_pending           — afventer stue at clear efter voksen-godnat
  kalde_active             — kids ringer mor/far om natten
  winter_solar_active      — syd-gardin åbnet for passiv solar heating
  entre_somrig_undo_grace  — 10-min vindue til "undo exit" efter "vi gaar"

Activity-flags (activity_state.yaml input_boolean):
  guest_mode               — auto-set ved sustained social activity
  bedroom_only_winddown    — auto-set ved bedroom_only state efter 21:00

Person-tracking (house_modes.yaml input_boolean):
  parent_a_home, parent_b_home

Plus master gate (template binary_sensor):
  presence_sensors_available  — ON hvis 1+ presence-sensor online
```

---

## Naming convention for helpers

- `input_boolean.<purpose>_active` — flag for tilstand (cinema_active, godnat_active)
- `input_boolean.<purpose>_pending` — overgangs-tilstand (godnat_pending)
- `input_select.<concept>_<rum>` — per-rum dropdown (room_mode_stue)
- `input_number.<concept>_<rum>_<sub>` — per-rum tuner (styrbar_color_idx_stue)
- `input_datetime.<concept>_<rum>` — per-rum timestamp (styrbar_last_press_stue)
- `template.binary_sensor.<concept>` — beregnet boolean (terrasse_active)
- `template.sensor.<concept>` — beregnet værdi (activity_state, people_estimate)

---

## Tip: tjek state of any helper

HA UI → **Developer Tools → States** → søg efter `input_boolean.X` eller `sensor.X`. Viser current state + last_changed timestamp + attributes.

For helpers du kan tune: HA UI → **Settings → Devices & Services → Helpers** → klik for slider.
