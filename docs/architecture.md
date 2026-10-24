# Architecture — system-design overblik

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Dette doc beskriver HVORDAN systemet hænger sammen konceptuelt. For HVAD-er-hvor reference, se [AGENTS.md](../AGENTS.md). For HVAD-hver-knap-og-tilstand-gør-i-dag (og hvilken slider der ejer tallet), se [system_design.md](../system_design.md).

---

# Holy Grail design philosophy

Tre principper:

**1. Lyset ændrer sig aldrig brat.** Hver auto-ændring fader smooth. Ingen "snap" der overrasker. Fade-tider standardiseret per zone-type.

**2. Manuel kontrol respekteres.** Hvis brugeren har dimmet til hyggelampe-niveau, auto-systemet rører det IKKE. Re-entry til rummet tænder kun lys hvis det er fuldt slukket.

**3. Auto kun når brugeren ikke modsiger.** Systemet observerer faktisk aktivitet (`activity_state`) og pauser auto-ændringer under social/gæste-aktivitet (`guest_mode`).

---

# Room-mode state machine

Hvert af **9** rum har en `input_select.room_mode_<rum>` (open plan er delt i
stue/spisestue/køkken siden 2026-09-03d). I drift skrives kun **Auto ↔
Manual**: et Styrbar-tryk eller en app-justering → Manual, drift-back → Auto.
Dim/Bright/Off-cyklussen via L/R findes ikke længere (L/R er farve/varme), og
Off bruges kun i sove som presence-blok.

**Den verificerede beskrivelse — knapper, drift-back-sliders, blokeringer og
sluk-tider pr. rum — står ÉT sted: [system_design.md](../system_design.md) §2-4.**
Gentag den ikke her (fejlklasse #2: denne sektion beskrev indtil 2026-10-07
en L/R-mode-cyklus og to slettede slidere).

---

# Activity-state classification

Implementeret i [packages/activity_state.yaml](../packages/activity_state.yaml).

`sensor.activity_state` evalueres ved hver presence-sensor-ændring. Tree:

```
              ┌─────────────┐
              │ voksen-/fuld │ → "godnat"   (2026-10-23: børne-putning
              │ godnat on?   │               tæller IKKE — kun active/voksne/pending)
              └──────┬───────┘
                     │ no
              ┌──────▼───────┐
              │ total_zones  │ → "idle"
              │    == 0?     │
              └──────┬───────┘
                     │ no
              ┌──────▼───────┐
              │ total_zones  │ → "social_party"
              │    >= 4?     │
              └──────┬───────┘
                     │ no
              ┌──────▼───────────────┐
              │ terrasse_active +    │ → "terrasse_only"
              │ no indoor activity?  │
              └──────┬───────────────┘
                     │ no
              ┌──────▼───────────────┐
              │ terrasse + (stue OR  │ → "terrasse_with_indoor"
              │ spisestue) on?       │
              └──────┬───────────────┘
                     │ no
              ┌──────▼─────────────────┐
              │ kun sove/boern aktive? │ → "bedroom_only"
              └──────┬─────────────────┘
                     │ no
              ┌──────▼─────────────────┐
              │ stue + spisestue       │ → "social_dining" (17-23h)
              │ open-plan?             │ → "cooking" (andet tidspunkt)
              └──────┬─────────────────┘
                     │ no
              ┌──────▼──────┐
              │ kun stue?   │ → "sofa_relax"
              └──────┬──────┘
                     │ no
              ┌──────▼─────────┐
              │ kun spisestue? │ → "dining"
              └──────┬─────────┘
                     │ no
              ┌──────▼─────────────────┐
              │ bedroom + bath, ingen  │ → "nightwalk"
              │ stue?                  │
              └──────┬─────────────────┘
                     │ no
              ┌──────▼──────┐
              │ kun bath?   │ → "bath_visit"
              └──────┬──────┘
                     │ no
              ┌──────▼─────────────┐
              │ kun entre eller    │ → "transit"
              │ entre+bath?        │
              └──────┬─────────────┘
                     │ no
                 "active" (fallback)
```

## Terrasse-detektion (uden sensor)

Terrasse har ingen Apollo. To proxies:

1. **`terrasse_lights_on`** — lyskæde eller pærelyskæde er ON
2. **`likely_on_terrasse`** (Sherlock Holmes) — open-plan blev tom <10 min siden, og INGEN indoor-rum (boern/sove/bad/entre) blev aktiv siden. Eneste anden udgang er terrasse → de er der.

`terrasse_active` = OR af de to. Bruges som zone-input til activity_state.

---

# Mode-flag interactions

Mange flags kan være ON samtidig. Hierarki + interaktioner:

```
PRESENCE_SENSORS_AVAILABLE (master gate)
├── OFF (pre-flyt) → ALLE presence-drevne automations skipper
└── ON  → automations evaluerer normalt

CINEMA_ACTIVE / CIRKUS_ACTIVE
├── Set af scene_cinema / scene_cirkus (sidste step i scriptet)
├── Cleared af scene_toggle dispatcher (dashboard) eller entré Styrbar L/R auto-mode
├── Cleared af mood_flag_safety hvis on >4h + stue tom 30+ min
├── Pauser presence_lights, drift-back, presence_lux automations

GODNAT_ACTIVE / _PENDING / _VOKSNE / _BOERN / KALDE_ACTIVE
├── godnat_voksen_start (somrig_6 click op) sætter pending + voksne
├── Når BÅDE voksne + boern er on + pending off → godnat_active = on
├── kalde_active set af kids' kalde-knap (somrig_7) under godnat
├── godnat_active blokerer presence_lights, wakeup, etc.
├── Cleared af godmorgen_forced eller wakeup_adults eller manual UI

GUEST_MODE
├── Auto-set af activity_aware ved social_dining/social_party/cooking/
│   terrasse_with_indoor i 30+ min (eller 10 min for social_party)
├── Auto-clear ved idle/bedroom_only/godnat i 15+ min
├── Pauser drift-back, klima-notifikationer, batteri-warnings (ikke kritiske)

BEDROOM_ONLY_WINDDOWN
├── Auto-set af activity_aware ved bedroom_only state efter 21:00 i 10 min
├── Trigger soft fade af stue/koekken-lys (5 min smooth)
├── Cleared kun ved DEFINITIV session-slut (godnat-flag, kl 07, eller
│   sustained 5 min skift væk fra bedroom_only via idle/sofa_relax/cooking)

ENTRE_SOMRIG_UNDO_GRACE
├── Set ved bund-quick "vi gaar" (10 min vindue til undo-exit)
├── Cleared af top-quick (undo) eller auto efter 10 min
```

---

# Sensor-gate (pre-flyt protection)

`binary_sensor.presence_sensors_available` er master-gate template:

```jinja
ON  hvis MINDST 1 af 8 presence-sensorer rapporterer state on/off
OFF hvis ALLE er unavailable/unknown
```

8 sensorer overvåges:
- `binary_sensor.stue_apollo_occupancy`
- `binary_sensor.spisestue_apollo_occupancy_filtered`
- `binary_sensor.koekken_apollo_occupancy`
- `binary_sensor.badevaerelse_inde_occupancy`
- `binary_sensor.sovevaerelse_apollo_occupancy`
- `binary_sensor.boernevaerelse_apollo_occupancy`
- `binary_sensor.depot_valhorn_occupancy`
- `binary_sensor.entre_valhorn_occupancy`

Gate OFF (alle unavailable) → 24+ automations skipper. 1 online → gate ON.

Gated automations:
- 17× presence_lights (alle stue/koekken/sove/boern/bath/lux varianter)
- 2× entre_motion (dag + nat)
- 1× depot_harry_potter
- 4× terrace_presence
- 2× light_power_recovery (fixer pre-flyt sove-Innr-bulb der auto-tændte ved mesh-flicker)
- 2× arrival_entre_light + arrival_welcome_light
- 2× wakeup_adults_weekday + wakeup_kids_weekend (wakeup_kids_weekday var allerede gated)
- 1× likely_on_terrasse template

---

# Scene system

Implementeret i [script_pkg/scenes.yaml](../script_pkg/scenes.yaml) (`scene_*` sektioner). Phase 2.1-split fra tidligere `scripts.yaml` (2026-05-05).

12 scenes tilgængelige via dashboard-tiles: cinema, zen, sofa_laesning,
spisestue_middag, cirkus, party, full_bright, private, blue, happy, sunset,
cyberpunk.

**Entré Styrbar L/R** (sprint 2026-05-22 redesign): cycler 4 modes —
`auto` (clear scene + room_modes til Auto), `zen` (script.scene_zen),
`all_bright` (alle_lys 100%), `all_off` (script.sluk_alt). Den gamle
10-scene cycle (`script.entre_scene_cycle` + `input_number.entre_scene_idx`)
er nedlagt — de fleste scenes var lange uden naturlig "next" på fysisk knap.
Se [automations/entre_somrig.yaml](../automations/entre_somrig.yaml).

cinema og cirkus scenes sætter deres egne flags (cinema_active, cirkus_active)
som sidste step. Disse cleares af `script.scene_toggle` (dashboard-vej) eller
af entré Styrbar L/R `auto`-mode.

---

# Pre-flyt vs post-flyt behavior summary

| Aspect | Pre-flyt (nu) | Post-flyt |
|--------|---------------|-----------|
| `presence_sensors_available` | OFF | ON |
| Apollo occupancy entities | unavailable | on/off |
| presence_lights firer | NEJ | JA |
| activity_state | "godnat" hvis godnat-flag stuck, ellers "idle" | dynamisk per aktivitet |
| guest_mode auto-set | aldrig (ingen activity-evidence) | per design |
| terrasse_active | kun via terrasse_lights_on proxy | + Sherlock-deduktion |
| drift-back | aldrig fyrer (sensor unavailable) | virker per design |
| arrival.yaml | aldrig (parasoll ikke paret) | aktiv |
| wakeup-flow | aldrig (sensor + arbejdsdag conditions fejler) | aktiv |
| godnat-flow | aldrig (somrig_6/7 ikke paret) | aktiv |

---

# Adding a new room

Hvis et 8. rum tilføjes (fx loftsrum), her er checklisten:

1. **packages/room_modes.yaml**
   - Add `input_select.room_mode_<rum>` med Auto/Manual/Dim/Bright/Off
   - Add `input_datetime.styrbar_last_press_<rum>`
   - Add `input_number.styrbar_color_idx_<rum>` (16-color short-press) + `styrbar_palette80_idx_<rum>` (80-color long-press, kun hvis rummet får Styrbar)
   - Add `input_boolean.styrbar_lr_grace_<rum>` + `styrbar_up_holding_<rum>` + `styrbar_lr_holding_<rum>` (sidste kun hvis rummet får Styrbar)

2. **automations/room_drift_back.yaml**
   - Add sensor → `presence_map[<rum>]`
   - Add sensor → `sensor_to_room` mapping
   - Add state-trigger til hver rummets sensor (off + for: 20)

3. **packages/light_groups.yaml**
   - Add `light.<rum>_all`, evt. `_ceiling` og `_accent`
   - Tilføj rummets lights til `light.alle_lys`

4. **packages/activity_state.yaml**
   - Tilføj rummet i `presence_sensors_available` template
   - Hvis rummet skal påvirke `sensor.activity_state` (distinkt zone), opdater logic

5. **automations/styrbar_rooms.yaml** (hvis rummet får Styrbar)
   - Tilføj IEEE → rum mapping i `ieee_to_room`
   - Tilføj per-rum lr_grace automation (~12 linjer)

6. **script_pkg/room_logic.yaml** lux_sensor map (hvis rummet har sin egen Apollo)

7. **entities/device_inventory.yaml**
   - Tilføj alle nye devices med IEEE + entity_ids + paired-dato

Estimat: 30-60 min hvis du har checklisten.

---

# Adding a new bulb (eksisterende rum)

1. Par i ZHA via HA UI
2. Omdøb device til konventionen
3. Tilføj entity til relevant gruppe i [packages/light_groups.yaml](../packages/light_groups.yaml)
4. Tilføj entry i [entities/device_inventory.yaml](../entities/device_inventory.yaml)
5. Commit + push + NUC restart

Alle scripts (room_mode_apply, styrbar_*, sluk_alt) bruger groups → ingen yderligere edits.

Estimat: 5-10 min.
