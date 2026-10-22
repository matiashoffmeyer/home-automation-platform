# Apollo MSR-2 Radar Calibration Baseline

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

LD2410 mmWave radar har 9 distance gates (g0-g8). Hver gate = ~0.75m bracket.
Lower threshold = more sensitive. Move thresholds = bevægelse, still = stillesidder.

**Konvention**: vi tuner KUN still thresholds (move thresholds beholder default).
Move detection er allerede god out-of-the-box; udfordringen er still-detection
(person der sidder/ligger uden at bevæge sig).

## Gate distance map

| Gate | Distance bracket |
|------|------------------|
| g0   | 0 - 0.75m        |
| g1   | 0.75 - 1.5m      |
| g2   | 1.5 - 2.25m      |
| g3   | 2.25 - 3.0m      |
| g4   | 3.0 - 3.75m      |
| g5   | 3.75 - 4.5m      |
| g6   | 4.5 - 5.25m      |
| g7   | 5.25 - 6.0m      |
| g8   | 6.0 - 6.75m      |

## Per-room calibration (sprint 2026-05-06 Blok D)

### Sove (calibrated 2026-05-05 — bed @ 2.5m)

| Gate | Default still | Tuned | Rationale |
|------|---------------|-------|-----------|
| g0-g1 | 0 | 0 | Blind nær sensor (PCB/mount interference) |
| g2 | 40 | **25** | More sensitive at 1.5-2.25m (head-of-bed) |
| g3 | 40 | **20** | Most sensitive — bed is HERE |
| g4 | 30 | **20** | More sensitive (foot-of-bed) |
| g5 | 30 | **25** | Slightly more sensitive |
| g6-g8 | 20 | 20 | Default (no targets here) |
| **timeout** | 5s | **15s** | Longer hold-on after person stills |

### Stue — FLYTTET bag radiatorskjuleren 2026-10-02 (B179)

Sofaen sidder nu på **1,6-2,3 m = g2**. Målt med user stille i sofaen
(engineering mode, 55 samples): still g2 p10/p50/p90 = 15/19/38, still g3
12/15/35, still g4 p50 10; move g0 konstant 18 og move g1 13-26 (nærfelt-ekko
fra skjuleren — begge gates står på 100). Live efter kalibrering: g2 still
**18** (var 44 = flap-jagtens bump ved gammel placering → set 22/55 s; 18 →
60/60 s), g3 still 15 (user), g2 move 26, g3/g4 15/15, g5-g8 100. Støjgulvet
bag skjuleren er umålt indtil nat-baselinen (`scripts/apollo_spoegelse_eval.py`
afsnit 5). Tabellen herunder er HISTORISK (hjørne-placeringen).

### Stue (calibrated 2026-05-06 — gammel hjørne-placering, forældet)

Apollo placeret i corner af stuen, peger ind. **FRB midlertidig** —
bracket calibration igen post-flyt. Defensiv tuning pga 5m parasitic ghost
(still_distance=461cm, still_energy=18 — ghost source uknown).

| Gate | Default still | Tuned | Rationale |
|------|---------------|-------|-----------|
| g0-g1 | 0 | 0 | Default |
| g2 | 40 | 40 | Default (under-sensor area) |
| g3 | 40 | **25** | Sofa @ 2-3m needs sensitivity |
| g4 | 30 | **20** | Spisebord @ 3-4m |
| g5 | 30 | **25** | Far side of room |
| g6 | 20 | **25** | DEFENSIVE — reject parasitic ghost @ 4.5-5.25m |
| g7 | 20 | **25** | DEFENSIVE — reject 5m parasitic specifically |
| g8 | 20 | 20 | Default |

### Spisestue (calibrated 2026-05-06)

Apollo dækker spisestue + køkken zone. Tune for detection mens folk sidder
ved spisebordet (= still ved bord).

| Gate | Default still | Tuned | Rationale |
|------|---------------|-------|-----------|
| g0-g2 | 0/0/40 | 0/0/40 | Default |
| g3 | 40 | **25** | Spisebord typisk @ 2-3m |
| g4 | 30 | **20** | Far side af bord |
| g5 | 30 | **25** | Køkken-area still detect |
| g6-g8 | 20 | 20 | Default |

### Bad (NOT calibrated)

User-decision 2026-05-05: works fine as-is. Defaults bibeholdes:
- g0-g1 still: 0 / g2-g3 still: 40 / g4-g5 still: 30 / g6-g8 still: 20
- timeout: 5s

### Boern (calibrated 2026-09-24 — engineering-mode, user til stede)

Aktive gates: g2 (15/15) og g3 (move 15 / **still 18**); resten 100.
Målt (min/median/max energi):

| Situation | g2 still | g3 still | g4 still | g2/g3 move |
|---|---|---|---|---|
| Tomt rum (20 min over to sessioner) | 6/8/11 | 7/11/**15** | 12/21/30 | ≤ 11 |
| User står/går i spisestuen ved væggen | ≤ 11 | ≤ 15 | ≤ 30 | ≤ 11 |
| Lig stille i sengen (225-235 cm) | 9/12/54 | **17**/48/100 | 52/100/100 | ≤ 13 |
| Sid stille på gulvet (~150 cm) | 71/100/100 | 100 | 59/84/100 | op til 100 |

g3 still stod live på 13 = INDE i tom-rums-støjen (fantom 08:39 → loft tændt).
18 ligger over tom-max 15 og ved sengens minimum 17 (ét sample; occupancy
holdt 39/39 s via radar-timeout). g4 SKAL blive på 100: tom-rums-støjen
når 30. Et sovende (mindre) barn kan falde under 18 — det slukker lyset i
et rum hvor der sover et barn, hvilket er den ufarlige retning. (B163)

## Re-calibration procedure

**Efter en FLYTNING (2026-10-02):** (1) nulstil rummets `input_text.<rum>_gate_floors`
+ `_gate_flapcount` til 36 nuller — gulve og bumps er lært mod den gamle
geometri; (2) mål user stille på den faktiske plads med engineering mode (≤ 10
min, sikkerheds-automationen slukker selv) → tærskel under users p10 på den
gate; (3) sæt **slideren** `input_number.<rum>_g<N>_still` (den er autoriteten
→ NVRAM), ikke `number.*` direkte; (4) bestil tomt-rum-baseline:
`input_text.apollo_kalib_bestilling` = `<rum>` → kører i nat, margin i
`ai_feedback/apollo_kalib_feedback.jsonl`. Manuelt nu (rummet tomt):
`python3 scripts/apollo_kalib_capture.py <rum> --sek 300`.

For at re-tune et gate (eg. hvis nyt rum) — NB den gamle opskrift herunder
skriver `number.*` direkte; brug slideren i stedet:

```bash
# 1. Mål baseline mens user sidder still på faktisk position
ssh ha "curl -s -H 'Authorization: Bearer \$HA_TOKEN' \
  'http://homeassistant.local:8123/api/states/sensor.STUE_apollo_radar_still_distance' | \
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[\"state\"])'"
# Output: e.g. 285 (= 285cm = gate 3)

# 2. Sæt threshold ned til match (eller lavere)
. .env && curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "number.STUE_apollo_g3_still_threshold", "value": 20}' \
  "http://homeassistant.local:8123/api/services/number/set_value"
```

Settings persisterer i ESP flash (overlever HA restart + power cycle).

## Diagnostic queries

```bash
# Live still target + distance + energy for alle 5 Apollos
ssh ha "for r in stue spisestue sovevaerelse boernevaerelse badevaerelse; do
  echo \"=== \$r ===\"
  for f in radar_still_target radar_still_distance radar_still_energy; do
    s=\$(curl -s -H \"Authorization: Bearer \$HA_TOKEN\" \\
      \"http://homeassistant.local:8123/api/states/binary_sensor.\${r}_apollo_\${f}\" 2>/dev/null || \\
      curl -s -H \"Authorization: Bearer \$HA_TOKEN\" \\
      \"http://homeassistant.local:8123/api/states/sensor.\${r}_apollo_\${f}\")
    echo \"  \$f: \$(echo \$s | grep -oE '\\\"state\\\":\\\"[^\\\"]+\\\"' | cut -d'\\\"' -f4)\"
  done
done"
```


---

## 🔥 ESPHome chip-wear — hvorfor writes til Apollo er farlige

Fuld baggrund, flyttet fra CLAUDE.md 2026-08-15. Den korte regel står
stadig i CLAUDE.md; incident-historikken og kode-eksemplet er her.

Vi har **bekræftet hardware-failures på 2 ud af 5 Apollos** indenfor 2 uger
efter parring. Begge er isolerede sensor-chip failures (ikke ESP-failures):
- **Stue Apollo (2026-05-05)**: LTR390 lux+UV chip døde
- **Boern Apollo (2026-05-19)**: DPS310 temp+pressure chip døde, bekræftet
  via ESPHome boot-log: `[E][dps310:096]: Communication failed`

Senere: **Spisestue Apollo** — DPS310 temp + tryk `unknown` i alle 1 172
udslag i udslags-loggen siden 2/10 (fundet 2026-10-22, B247; død et sted
mellem 15/6 og 2/10, ikke tjekket i boot-loggen). DPS310 virker altså kun i sove,
stue og køkken.

**Root cause** (mistænkt — korrelation, ikke 100% bevis):
`automation.apollo_global_radar_threshold_tuner_slider_driven` fyrede 181 gange
på 14 dage selv om slideren aldrig ændrede sig. Hver fire skrev 20 number
entities til alle online Apollos = ~3600 unødvendige UART-kommandoer til
LD2410 radar + ESP flash-preferences writes. Apollo's DPS310 + LTR390 chips
sidder fysisk **lige ved siden af** ESP32 på PCB'en — repeated thermal stress
fra konstant chip-aktivitet kan over tid svække solder joints på de mindst
robuste komponenter.

**Regel: VÆR PARANOID med writes til ESPHome devices.** Følg disse principper:

1. **ESPHome NVRAM er persistent.** Devices husker config på tværs af reboots
   og WiFi-disconnects. **Du skal IKKE re-skrive samme værdi** ved "device
   online" eller "HA start" events. Trust the chip's memory.

2. **Triggere skal kun fyre ved bruger-intent** (slider change, button press,
   scene activate). Ikke ved side-channel events som device-availability eller
   HA-lifecycle events.

3. **Value-comparison ALTID** før `number.set_value` på ESPHome entities:
   ```yaml
   - if:
       - condition: template
         value_template: "{{ (states(entity) | float(-1)) | round(0) | int != target }}"
     then:
       - service: number.set_value
         data: {entity_id: "{{ entity }}", value: "{{ target }}"}
   ```
   Selv hvis triggeren er legit, undgår dette no-op writes når kun nogle
   gates skal opdateres.

4. **Engineering mode + Bluetooth = ALDRIG ON i drift.** Engineering mode får
   LD2410 til at streame alle 18 gate-energies kontinuerligt = konstant ESP-
   arbejde = konstant varme. Kun ON under bevidst kalibrerings-session, og
   slå OFF igen straks efter.

5. **Når du skriver et nyt automation der pusher config til ESPHome:**
   - Spørg "kan dette fyre periodisk?" (= bad)
   - Spørg "kunne brugeren leve med at manuelt fire en gang post-pairing?" (= often yes)
   - Lav en `script.X_apply_now` for manual rerun i stedet for auto-triggers

**ESP-temperatur som canary:** Sove + boern Apollo ESP-temp dropper 1°C
indenfor 5 min efter tuner-fix deployment (47→46°C). Hold øje med
`sensor.*_apollo_esp_temperature` — hvis den stiger over ~50°C steady-state,
er der noget der hammer for hårdt på chippen.

**Manuel sync efter ny Apollo-parring eller factory_reset_radar:**
Kør `script.apollo_radar_apply_now` eller toggle slider 50→51→50 for at
pushe current threshold-factor til alle Apollos én gang.
