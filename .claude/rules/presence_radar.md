---
paths:
  - "packages/*apollo*.yaml"
  - "automations/*apollo*.yaml"
  - "packages/*presence*.yaml"
  - "automations/presence_*.yaml"
  - "packages/*ghost*.yaml"
  - "packages/people_estimate.yaml"
  - "packages/activity_state.yaml"
  - "packages/koekken_cooking.yaml"
  - "packages/sove_alarm_morgen.yaml"
  - "packages/valhorn_watchdog.yaml"
  - "entities/sensors/valhorn.yaml"
  - "automations/room_drift_back.yaml"
  - "automations/terrace_presence.yaml"
  - "automations/godmorgen_godnat.yaml"
  - "scripts/apollo_*.py"
  - "docs/apollo_calibration.md"
---

> *Danish. A path-scoped rule file: Claude Code loads it the first time a
> file matching `paths:` is read. See
> [docs/methodology.md](../../docs/methodology.md).*

# Presence og radar (Apollo/LD2410, Valhorn)

Path-scopet fra CLAUDE.md (Permanente fakta) — loades når du læser en fil
der matcher `paths:`. Samme genkendelses-lag: regel, signatur, entity-navn.
Den lange version (måledata, incidents): `docs/permanente_fakta.md`
(`grep -n "<nøgleord>"`). Ændrer virkeligheden sig, ret BEGGE lag.

- **En presence-sensors NAVN er et rum, dens FELT er en radius** (still ≈ 6 m).
  Overlapper to rum, skal du skelne på en akse feltet ikke deler — og den akse
  er **rum-specifik**. Et filter kan ikke kopieres mellem rum uden at dets
  diskriminator gentænkes.
- **En LEVENDE krop flytter `still_distance` konstant; et møbel holder værdien
  identisk til decimalen** → `binary_sensor.<rum>_apollo_frossen_ghost`.
  Sammenlign på **decimalen** — kvantisér, og en levende krop ligner et møbel.
- **Apollo gate-tærskler har TO lag, og SLIDEREN er autoriteten**
  (`input_number.<rum>_g<N>_<move|still>` → NVRAM). At lagene er enige beviser
  intet om værdien.
- **LD2410'eren leverer INGEN still-energi på gate 0 og 1**, og
  `*_radar_still_distance` **hviler på ~66-67 cm** uden mål → guard `gate_dead`.
  **MEN et "still g0"-artefakt er fixbart på MOVE-kanalen, én gate længere ude.
  Signatur:** still-mål på hvile-afstanden med still-energi under ALLE rummets
  still-tærskler = ekko af et move-blip → hæv MOVE-gaten + gulv i
  `input_text.<rum>_gate_floors`.
- **Et occupancy-udslag der varer PRÆCIS `number.<rum>_apollo_radar_timeout` er
  ét radar-blip = maskine** (5 s; sove 15 s). Gælder IKKE soveværelset.
  Mistænker du spøgelser: tæl udslags-VARIGHEDER først.
- **Soveværelsets Apollo fantom-fyrer i eftermiddagssolen** → brug **bredde**
  (en fantom rører ét rum, et menneske flere), ikke stilhed.
- **Sove-Apolloen taber en person der LIGGER STILLE i 5-15 min** → et "tomt"
  soveværelse er IKKE bevis for fravær. **Og "optaget igen" beviser ikke at
  nogen er STÅET OP** — en sovendes off-huller og en ægte anden krop
  OVERLAPPER, så ingen tids-tærskel kan skille dem → kræv `moving_target`.
- **Soveværelsets Apollo sidder LIGE VED DØREN, så `moving_distance` er husets
  eneste RETNINGS-signal** (ud = falder, ind = stiger; dørzone-slider
  `input_number.sove_morgen_2p_doerzone_cm`). Distance-sensorerne er `unknown`
  uden mål, og det ER diskriminatoren: en `below`-crossing fra et TAL over
  dørzonen er en ægte udgang, `unknown → 50` er en der kommer ind (`| float(-1)`).
- **Presence-instrumenterne er IKKE lige pålidelige, og blinde kanaler er
  NORMALT** (batteridrevne og gæste-slukkede vægkontakter). Da `unavailable`
  læses som `off` (#9), svarer en død kanal "her er tomt" med fuld
  selvsikkerhed. **Kør `./scripts/ha_health.sh blind` FØR du forklarer
  presence-adfærd.** Tvivl om ét rum må aldrig gates husdækkende → gate på
  rummets EGEN kanal, ikke `binary_sensor.activity_state_confident` (HUS-tal, #26).
- **Børne-Apolloen ser folk ved SPISEBORDET gennem væggen** (10-05: 24/26
  auto-tændinger uden børn i takt med spisestuens radar, klumpet om måltider;
  B163's poserede "står ved væggen ≤ 11" holdt ikke). **Signatur: et kort
  børne-ophold (13-42 s) der starter i samme sekund som spisestuen.** Inden for
  3 s (user-krav til tænd) skiller intet signal → fixet er på SLUK-siden: uden
  børn `input_number.boernevaerelse_uden_boern_sluk_sekunder`, med børn 06 →
  sengetid `…_med_boern_sluk_sekunder`; kun efter sengetid ~22 min.
  **Uden latens-krav (people count) skiller ALENE-TID:** optaget mens
  spisestuens RÅ radar er stille, ud over radar-timeouten (900 s om natten
  holder ellers ethvert blip 15 min) → `binary_sensor.boernevaerelse_solo_bevis`.
  Rå flanker/`boern_occupancy_4h` som børne-bevis = over-tælling (6/10: 4 med 2).
- **En Matter/Thread SLEEPY END DEVICE der mister sin forælder mens den melder
  `on`, sender aldrig sin `off`** — HA står `on` i op mod 40 min.

## Standing instruction: ESPHome chip-wear (flyttet fra CLAUDE.md)

#### 🔥 ESPHome chip-wear — vær paranoid med writes til Apollo MSR-2 (per 2026-05-19)

**2 af 5 Apollos fik bekræftede sensor-chip-failures** inden for 2 uger; mistænkt
årsag ~3600 unødvendige config-writes. Incident + kode:
[docs/apollo_calibration.md](../../docs/apollo_calibration.md).

1. **ESPHome NVRAM er persistent** — re-skriv ALDRIG samme værdi ved "device
   online" eller HA-start.
2. **Triggere kun ved bruger-intent** (slider, knap, scene) — aldrig ved
   device-availability eller HA-lifecycle-events.
3. **Value-comparison ALTID** før `number.set_value`.
4. **Engineering mode + Bluetooth = ALDRIG ON i drift** (18 gate-energies
   kontinuerligt = konstant varme). Kun under bevidst kalibrering.
5. Nyt ESPHome-config-push: spørg "kan dette fyre periodisk?" (= bad) og "kunne
   brugeren leve med ét manuelt kald?" (= ofte ja) → lav `script.X_apply_now`.

**Canary:** `sensor.*_apollo_esp_temperature` over ~50 °C steady-state. Efter ny
parring/factory-reset: `script.apollo_radar_apply_now`.
