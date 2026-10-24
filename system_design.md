# Home Assistant: System Design (The Holy Grail)

> *Written in Danish. English overview: [README](README.md) ·
> [ARCHITECTURE](ARCHITECTURE.md).*

Husets globale adfærd **som den er**, ikke som den var tænkt. Hvert punkt er
verificeret mod koden (sidst 2026-10-07, efter fem måneders drift fra
april-specen). **Tal står ikke her:** hver tærskel peger på den helper der ejer
den. Læs live-værdien med `python3 scripts/hq.py state <entity>`. Ændrer du
adfærden, så ret dette dokument i SAMME commit (fejlklasse #2/#3).

Konceptuel arkitektur (activity-tree, mode-flag-prioritet, nyt rum/ny pære):
[docs/architecture.md](docs/architecture.md). Hvad rører rum X:
`docs/auto/rooms/<rum>.md`.

## 0. Principper

1. **Lyset ændrer sig aldrig brat.** Sluk fader, og drift tilbage til Auto
   glider over 10 min.
2. **Manuel kontrol respekteres.** Et tryk eller en app-justering sætter
   rummet i Manual og holder automatikken væk, indtil rummet har været tomt
   eller fallback-tiden er gået.
3. **Auto kun når brugeren ikke modsiger.** Aktivitet (`sensor.activity_state`,
   `mood_pause_<rum>`, dance) pauser auto-ændringer.

## 1. Zoner

Der er **9 room_mode-ankre** (`input_select.room_mode_<rum>`, `packages/room_modes.yaml`):
`sovevaerelse`, `stue` (kun sofa-zonen), `spisestue`, `koekken`,
`boernevaerelse`, `terrasse`, `depot`, `badevaerelse` og `entre`.

- **Open plan** (stue + spisestue + køkken) er fysisk ét rum med tre
  Apollo-felter, men har haft tre ankre siden 2026-09-03d.
  - En handling på ÉT rums lamper læser dét rums `room_mode`.
  - En handling på hele open plan (morgenrampe, dagslys-sluk, velkomst) læser
    `binary_sensor.open_plan_manual`, som er sand hvis mindst ét af dem står
    Manual.
- **Vinduesløse rum:** bad og depot.
- **Gardinmotorer:** sove (Zigbee) samt stue syd, stue vest 1 og spisestue vest
  (RF, antagne positioner, se `.claude/rules/gardiner_sol.md`).
  Børneværelset og terrassedøren har intet gardin.
  - **Stue vest højst 85 % ned** (der står ting under): luk = ned → stop efter
    `input_number.gardin_vest_ned_sekunder`, målt fra top. Et 2. luk uden en
    åbning imellem kører i bund, så hver luk-vej skal være én-gangs eller
    re-home først (`script.gardin_film_luk`).

## 2. Room mode: Auto ↔ Manual

- **Options:** Auto, Manual og Off.
  - **Off** bruges kun i sove, som presence-blok (`sove_rodret_button.yaml`,
    `sovevaerelse_morgen_beskyttelse.yaml`).
  - Dim/Bright-cyklussen og 31 %-tærsklen blev slettet 2026-10-07 (B198); ingen
    kaldte dem.
- **Hvad sætter Manual:**
  1. Ethvert Styrbar-tryk via `script.styrbar_stamp_press`. Det stempler
     `input_datetime.styrbar_last_press_<rum>`. Undtagelse: et stue-trin op
     der KUN ramte køkken-lyskæden stempler køkkenet, ikke stuen (2026-10-24).
  2. App-/dashboard-justeringer med `user_id` (`automations/manual_override.yaml`).
     Terrassen er udeladt, og der stemples kun når nogen er hjemme.
  3. Gæste-RODRET, entré-Styrbar og ~15 andre skrivere
     (`grep -rln '"Manual"' automations packages script_pkg`).
- Trykket sætter selv Manual. Skal en anden automation sætte Auto på samme
  tryk, skal den vente ~2 s.

### 2.1 Drift tilbage til Auto — `automations/room_drift_back.yaml`

Kill-switch: `input_boolean.drift_back_enabled`.

- **Tomt rum:** rummet drifter når alle dets sensorer har været off i
  - `input_number.global_drift_back_empty_minutes` (sove, børn, depot, entré, terrasse).
    Terrassen har ingen presence-sensor, så "tom" =
    `binary_sensor.terrasse_active` off (lys/Sherlock/åben terrassedør)
  - `input_number.open_plan_drift_back_empty_minutes` (stue, spisestue, køkken)
  - `input_number.badevaerelse_manual_til_auto_minutes` (bad)

  Triggerens `for:` bindes ved load, så en ændret slider kræver reload.
- **Race-vindue:** aldrig drift < 30 min efter et tryk. Bad og open plan bruger
  min(30, egen slider).
- **Optaget-fallback** (erstattede 12-t-loftet 2026-07-25): bliver man i
  rummet, drifter det når tiden siden sidste tryk ≥
  `input_number.room_manual_on_hold_hours`. Sove bruger
  `input_number.sovevaerelse_manual_on_hold_hours`, badet sin egen slider.
- **24-t hård fallback:** ikke-Auto i 24 t, målt på det skrevne stempel
  `input_datetime.room_mode_<rum>_ikke_auto_siden` (sat af
  `room_mode_ikke_auto_stempel` når rummet forlader Auto; overlever restart).
  Dens unikke rolle er at slippe et glemt dance-claim.
- **Selve driften** (`script.room_drift_back`):
  - Rummet sættes til Auto.
  - **Allerede tændte** lys glider over hardkodet 600 s mod Auto-niveauet;
    vinduesløse rum har højere baseline i `room_mode_apply`. Slukkede lys
    forbliver slukkede.
  - Ingen lys-gentagelse i sove/børn under godnat. Lamper med
    ejerskabsregister springes over.
- **Blokeringer:**
  - Hus-brede: `input_boolean.cinema_active` og `guest_mode`.
  - Pr. rum: `mood_pause_<rum>`, `aktivitet_pause`, `dance_claim`,
    `sove_evening_hold` og `open_plan_fuldt_lys` (sidstnævnte gælder ikke
    fallback).
- **Parallelt lag:** `binary_sensor.stue_manuel_lys_hold`
  (`input_number.manuel_lys_hold_timer`) holder sluk-veje væk fra
  stue-/spisestue-lys efter et manuelt tryk, uanset mode.

## 3. Fysiske knapper

### 3.1 Styrbar (IKEA Remote N2)

Filer: `automations/styrbar_rooms.yaml` + `script_pkg/styrbar_helpers.yaml`.
Parret i **sove, stue, børn, terrasse og bad**. Entré har en Styrbar med egen
handler (§3.2).

- Spisestue og køkken har ingen Styrbar.
- Depot styres af FoH/Hue-vægkontakten (`packages/depot_foh_switch.yaml`). Den
  gamle depot-Styrbar styrer nu Roborock (`roborock_styrbar.yaml`).

| Knap | Alle rum | Undtagelser |
|---|---|---|
| OP/NED klik | Lysstyrke-trappe 0 → 5 → 10 → 20 … 100 (grovere i AirBnB) | Sove: OP i mørke tænder kun lyskæden |
| OP hold | 100 %; holdes videre ~2 s → varm hvid 2700 K | — |
| NED hold | Sluk | Stue 20-06 (Normal/Home Vacation): = gæste-RODRET O — sluk open plan + entré + terrasse og armér Sleep Over; næste OP tænder som normalt, slipper holdet og giver open plan Auto |
| L/R klik | 16-farvers cyklus | Stue: HØJRE = sofa-zonens lamper on/off, VENSTRE = køkken/spisestue-kombinationer. Sove: varme-loop (`styrbar_sove_warmth.yaml`) |
| L/R hold | 80-farvers scroll, stop ved slip | Stue: kombinations-shuffle |

Øvrige regler:
- Terrassen styrer kun pærelyskæden med top/bund; L/R gør bevidst intet
  (`terrace_plug_control.yaml`).
- Børneværelset har putning-grene.
- Er Dark Mode tændt, fritager et OP-tryk rummet fra den (`packages/dark_mode.yaml`).

### 3.2 Entré-Styrbar — `automations/entre_somrig.yaml` (filnavnet er et levn)

| Tryk | Handling |
|---|---|
| TOP kort | Dæmp op / fortryd / AirBnB-velkomst; sætter `house_state` Active |
| TOP lang | **Nødlys** (`packages/noedlys.yaml`): alt lys fuldt hvidt, overstyrer alt, alle modes |
| 3 × TOP kort / 3 × pil inden for `input_number.noedlys_tryk_vindue_sek` | **Nødlys** (én fælles tæller) |
| BUND kort | Sluk alt uden gardiner (5 min grace), højttaleren fades til 0 over 8 s og stoppes (`script.hoejttaler_fade_ud`; ikke AirBnB), og armér en Dormant-**evaluering** (`packages/entre_ned_dormant.yaml`). Sætter IKKE selv Dormant. Under nødlys: slukker nødlyset først |
| BUND lang | Sluk alt (inkl. højttaler-fade) + Roborock fuld (under nødlys: som BUND kort, ingen robot) |
| L/R | Scene-cyklus auto → zen → all_bright → all_off |

Nødlyset stopper selv efter `input_number.noedlys_max_minutter` og afleverer
alle rum til Auto (gengiver ikke lyset fra før). Under nødlys gør TOP kort og
pilene intet. Rangen er 2 efter røgalarmen, som maler samme hvide.

"auto" rydder også `active_scene`, cinema/cirkus og sætter alle 9 rum til
Auto. Det er den eneste knap der bryder en override.

### 3.3 Gardin- og specialknapper — `automations/somrig_buttons.yaml`

Gardinknapperne er RODRET, ikke Somrig.

- **Sove:** top/bund kører helt op/ned (latchende). Samme knap under kørsel = stop.
- **Stue:** klik-sekvens.
  - NED: 1. tryk kører syd, 2. tryk (inden for
    `input_number.stue_rodret_seq_minutes`) kører vest.
  - OP: omvendt.
  - Modsat klik under kørsel stopper. Hold kører syd + vest 1 helt.
- **Spisestue vest:** har ingen knap.
- **Børneværelset:** RODRET = Dark Mode on/off.
- **Gæste-RODRET:** I tænder og O slukker open plan + entré; begge sætter Manual.
  O kl. 18-06 armerer Sleep Over (`script.gaest_sover_sluk`, som stue-Styrbar
  langt NED 20-06 også kalder).
- **Sove-Somrig** (husets eneste ægte Somrig) er godnat-knappen: kort ned =
  hele huset, lang ned = straks (`automations/godmorgen_godnat.yaml`).

## 4. Tilstedeværelse: tænd og sluk

### 4.1 Tænd (Auto)

Huset kører **ingen Adaptive Lighting-integration**.

- **Lux-gate:** presence tænder kun når rummet er mørkt nok.
  - Gate = `input_number.<rum>_lux_threshold` × 0,5 om dagen ×
    `sensor.global_lux_threshold_factor`.
  - Faktoren styres af `input_number.global_lux_sensitivity`.
  - Filer: `packages/room_lux_tuning.yaml` og `.claude/rules/lux_dagslys.md`.
- **Lysstyrke:** × `sensor.global_brightness_factor`
  (`input_number.global_light_aggressiveness`).
- **Farvetemperatur:** `sensor.auto_color_temp_evening` (sol-elevation ×
  `input_number.global_evening_warmth`).
- **Undtagelser:**
  - Badet bruger faste stadie-slidere (approach/medium/fuld/godnat).
  - Depotet har egen logik (`automations/depot_harry_potter.yaml`).
  - Entréen har egen kelvin-slider (`input_number.entre_kelvin`).
  - Børneværelset efter sengetid (`sensor.boern_bedtime_hour`) med børn hjemme:
    puttelys-udseendet (`script.puttelys_phase1_apply`, loft 30 % i
    `input_number.global_putte_loft_kelvin`) — aldrig rødt.

### 4.2 Sluk — der findes INGEN fælles 5-minutters regel

Sluk-tid = rummets basis × `sensor.global_absence_wait_factor`, der styres af
`input_number.global_turn_off_aggressiveness`. "Uden faktor" i tabellen
betyder at den globale faktor ikke anvendes.

| Rum | Autoritet |
|---|---|
| Sove | `sensor.rum_tom_sluk_sekunder` (`packages/room_absence_tuning.yaml`) |
| Børn | Som sove. Desuden 06 → sengetid: `input_number.boernevaerelse_uden_boern_sluk_sekunder` / `…_med_boern_sluk_sekunder`, uden faktor |
| Sofa-zonen | `input_number.stue_sofa_off_minutter` → `sensor.sofa_stue_off_sekunder` |
| Spisestue-loft | `input_number.spisestue_off_minutter` (hurtig-sluk ved flytning til sofaen). Begge open plan-tider klampes til `input_number.solo_tom_rum_sluk_minutter` når én person er hjemme uden for open plan |
| Køkken | `input_number.koekken_spots_off_seconds`, uden faktor. Køkken-lyskæden har ejerskabsregister (`ejerskab/`) |
| Bad | `input_number.badevaerelse_off_minutter` + stadier, uden faktor. **Ingen automatisk sluk uden en frisk fugt-måling** (`binary_sensor.badevaerelse_fugt_frisk`, user-spec 1/10) |
| Depot | `input_number.depot_quick_off_seconds` / `_medium_` / `_long_` (`packages/depot_visit_quality.yaml`) |
| Entré | `input_number.entre_off_sekunder` |

- **Fade:** `sensor.fade_living_effective` (sove, børn) og
  `sensor.fade_extended_effective` (stue, spisestue) = basis ×
  `sensor.global_fade_factor`, som styres af `input_number.global_fade_speed`.

### 4.3 Overrides og hold-alive

- `cinema_active` + `mood_pause_stue` gater kun sluk af sofa-zonen og
  spisestue-loftet. Andre rum har ingen sådan gate.
- Cirkus er rum-scoped via `mood_pause_<rum>` (`packages/scene_state.yaml`).
- Dark Mode tænder `cinema_active`.
- **Et Styrbar-tryk rører IKKE cinema-/cirkus-flaget.** Rummet går i Manual,
  og flaget bliver stående.
  - Kun entré L/R "auto" rydder flagene.
  - Fastlåste flag ryddes af `automations/mood_flag_safety.yaml`.

## 5. Hus-tilstande: to uafhængige akser + godnat-flag

- **`input_select.house_mode`** — Normal / AirBnB / Home Vacation (livsform).
  - Familie-logik = `in ['Normal','Home Vacation']`.
  - Kun-gæst = `AirBnB`.
  - Se CLAUDE.md 🏡.
- **`input_select.house_state`** — Active / Dormant (er nogen hjemme).
  - **Dormant sættes af:**
    - `packages/house_modes.yaml`: ingen hjemme længe, GPS langt væk,
      home-flags off, ingen fysisk aktivitet, AirBnB, manuel override.
    - `departure_dormant`, `dormant_idle` og `dormant_schedule`.
    - Entré BUND kort, men kun som en armeret evaluering.
  - **Active sættes af:** `house_state_to_active` (home-flags, occupancy,
    hoveddør, terrassedør, HA-start) og entré TOP.
- **Godnat er IKKE en `house_state`.** Det er `input_boolean.godnat_active`
  (+ `godnat_boern_active`, `godnat_voksne_active`, `godnat_pending`).
  - Sættes af sove-Somrig, `godnat_auto_declare` og Dark Mode.
  - AirBnB sætter flagene direkte (`packages/airbnb_natmode.yaml`).
  - Slutter ved aktivitet efter 06:00 — eller ved et brusebad efter 05:00
    (soveværelserne auto-tænder stadig tidligst 06:00).
  - Diagrammer: [docs/state_machine.md](docs/state_machine.md).

## 6. Gardin-forsvar

### 6.1 Sommer — `automations/summer_defense.yaml`

Kill-switch: `input_boolean.summer_defense_enabled`. Pauses af
`input_boolean.gardin_dormant_pause_active`.

- **Dormant:** kræver alt dette:
  - `sensor.timmerflotte_temperature` > `input_number.summer_defense_temp_threshold` i 5 min
  - kl. 09-20
  - skydække ≤ `input_number.summer_defense_max_cloud_cover`
  - `house_mode` Normal eller Home Vacation (ikke AirBnB)

  Så lukker:
  - open plan (alle tre), når solen er oppe (lux-gaten > 8000 kunne aldrig nås — fjernet 2026-10-10, B214)
  - sove, hvis lux > `input_number.sove_sol_blast_lux` (azimut som fallback)
- **Active:** over `input_number.summer_defense_active_temp_threshold` lukkes
  den sol-ramte side (azimut); sove følger lux.
- Genåbner med 1 °C hysterese og kun det den selv lukkede.

### 6.2 Vinter — `automations/winter_defense.yaml`

Måler **udetemperaturen** (`sensor.udetemp`), ikke indendørs.

- Under `input_number.winter_heating_season_temp`:
  - Dormant → gardiner til position 20.
  - Active + mørkt (sol < `input_number.natlys_sol_elevation`) → luk
    (`input_boolean.winter_active_dark_close_enabled`).
- **Sol-opvarmning** (åbner ved sol på ruden): `input_boolean.winter_solar_enabled`.
- **Kuldebølge** under `input_number.winter_cold_snap_temp` tvangslukker.
- Der er ingen samlet kill-switch og ingen generel "åbn om dagen"-regel.
