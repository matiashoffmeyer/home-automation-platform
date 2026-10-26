# Ejerskab: `light.koekken_lyskaede` — Køkken-lyskæden
GENERERET fra `ejerskab/koekken_lyskaede.yaml` (registret ER prioriteten; ret dér + `python3 scripts/ejerskab.py gen`).
Ejer nu: `sensor.koekken_lyskaede_ejer` (state = krav-id eller `hus`). `binary_sensor.koekken_lyskaede_laant` = ejer ≠ hus.

| # | krav | aktiv når | slip |
|---|---|---|---|
| 1 | `roegalarm` Røgalarm | røgalarmen blinker (nødbelysning) | maal |
| 2 | `noedlys` Nødlys | entré-Styrbarens nødlys (alt fuldt hvidt) | maal |
| 3 | `timer_alarm` Timer-alarm | gestus-timerens alarm ringer | maal |
| — | `timer_nedtaelling` Timer-nedtælling | nedtælling kører — bursts via signal-kanalen; huset ejer udseendet | overlay |
| — | `kvittering` Kvitteringer | vink/puls/burst/grøn — sekunder lange, køet i script.koekken_lyskaede_signal | overlay |
| 4 | `vejrvarsel` Vejrvarsel | et vejr-blink kører (rører ikke kæden siden 23/9, se huller) | maal |
| 5 | `dyrespil` Dyrespil | hest/flodhest-blinket kører (3 røde eller blå blink) | maal |
| 6 | `dance` Dance | festlys danser i køkkenet (auto-shuffle ELLER låst event) | maal |
| 7 | `cirkus` Cirkus/fødselsdag | cirkus- eller fødselsdags-scenen kører | maal |
| 8 | `legetoejsdag` Legetøjsdag | disko-varslet kører | maal |
| 9 | `farve_preview` Farve-preview | du skruer på kædens farve/mætning/lysstyrke (viser den i N sek.) | maal |
| 10 | `styrbar_farveloop` Styrbar-farveloop | du holder stue-Styrbar L/R (kæden kører farver) | maal |
| 11 | `haand` Din hånd | du har selv sat udseendet (app-justering mens den lyser, sluppet farveloop, valgt scene, fuldt lys) — slipper ved sluk eller når madlavning er i gang | maal |
| 12 | `velkomst` AirBnB-velkomst | gæste-velkomsten kører (gæstens eget tryk = din hånd, slipper den) | maal |
| 13 | `sofa_zen` Sofa Zen | Sofa Zen låner kæden (køkkenet ikke i brug) | maal + genoptag |
| 14 | `morgenrampe` Morgenrampe | morgenrampen kører (viger for madlavning) | ingen |
| 15 | `nattur` Godnat/nattur | godnat er aktiv (nattur-lyset ejer kæden; viger for madlavning) | ingen |
| — | `hus` husets mål | ingen krav aktive | — |

**Når ejer = hus** vælger mål-sensorerne udseendet: dark_mode_stue > filmmoerke_koekken > madlavningslys/arbejdslys (morgen- og hjemkomstlys) > maaltidslys > hygge (sliders × elpris). Styrke: `sensor.koekken_lyskaede_target_brightness`; farve: `script.koekken_lyskaede_maal`.

**Regler (pre-commit `ejerskab.py lint` blokerer brud på 1):**
1. Enhver ny skriver skal stå i registret: under sit kravs `skrivere:` eller i `skrivere:` (rolle + via).
2. Ny låner = nyt krav på sin rang med `aflevering:` — og den skriver KUN når ejer = dens id (`wait_template` på `sensor.koekken_lyskaede_ejer`), ellers maler enforceren over den.
3. Husets udseende males kun af `koekken_lyskaede_maal`; blink/kvitteringer kun via `koekken_lyskaede_signal` (queued).
4. Aflevering = slip dit flag. Enforceren (`aflevering: maal`) eller genoptag maler næste ejer. Aldrig restore af et snapshot (fejlklasse #27).
5. Rum-logik og grupper må tænde/slukke lampen, aldrig sætte dens udseende (`sensor.lys_ejerskab`).
6. Ændrer du en rang eller et `naar`: kør `gen`, deploy, og tjek `sensor.<…>_ejer` live.

Kendte huller (baseline, må kun skrumpe): 17 — se `huller:` i registret.
