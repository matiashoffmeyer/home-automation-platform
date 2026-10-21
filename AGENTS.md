# AGENTS.md — fast-path navigation for AI sessions

> *Written in Danish. English overview: [README](README.md) ·
> [ARCHITECTURE](ARCHITECTURE.md).*

Ment til Claude (eller anden AI-assistent) der starter en ny session i dette repo. Læs dette FØR du gør noget arbejde — det er korteste vej til kontekst.

**Last reviewed: 2026-08-15** (token-effektivitets-sprint: stale hardware-/backlog-sektioner erstattet af pegepinde til levende kilder).

For backlog + standing instructions, se [CLAUDE.md](CLAUDE.md).
**📋 For "hvor lever koncept X på tværs af filer":** se [docs/cross_cutting_map.md](docs/cross_cutting_map.md) — single document der mapper alle cross-cutting concerns + flagger ⚠️ farlige steder at edit.

---

## 💰 Billigste vej til et svar — gå ned ad stigen, stop ved første trin der virker

Fuld regelsæt: **💰 TOKEN-ØKONOMI** i [CLAUDE.md](CLAUDE.md). Kort version — brug
det ØVERSTE trin der kan besvare spørgsmålet, ikke det grundigste:

| # | Værktøj | Brug når | Koster |
|---|---|---|---|
| 1 | Denne fil + `python3 scripts/hq.py find X` / `where X` | "hvad hedder X", "hvor bruges X" (live, fil:linje) | ~0 |
| 2 | `grep -rln "term"` | "hvilke filer rører X" (kun filnavne) | ~0 |
| 3 | `grep -rn "term" dir/` | "hvor og hvordan bruges X" | lille |
| 4 | `Read(f, offset=hit-25, limit=60)` | du skal se/rette koden omkring hittet | lille |
| 5 | Fuld `Read` | filen er < 300 linjer (`wc -l` FØRST) | middel |
| 6 | Explore-subagent | bredt "hvor findes X overhovedet" på tværs af repoet | dyrt |

**Filer der ALDRIG må Read'es helt** (grep + offset i stedet):
`dashboards/settings.yaml` (13000 linjer — faner: soeg, lys-styrke, koekken, tapo, bad, nat-boern, gardiner, maaltid, mad, hus, stoevsug, vandventil, notifikationer, varsler, el-pris, kill-switches, airbnb-tuning, sensorer-lux; ÉN sektion pr. emne; Tapo/Mad/Støvsug/AirBnB/Vandventil var egne dashboards indtil 2026-09-30 — Mad og Støvsug har igen et KONTROLPANEL som eget dashboard, `dashboards/mad.yaml` (+ subviews opskrift-1..16) og `dashboards/stoevsug.yaml`), `automations/init_user_preferences.yaml`
(1350; var 6230 før P1), `scripts/mad_planner.py` (2054), `BACKLOG.md`, `docs/sprint_log.md`.

**API-opslag skal filtreres ved kilden** — `curl /api/states` er ~1 MB rå:
```bash
. .env && curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://homeassistant.local:8123/api/states/input_number.koekken_spots_lux_threshold" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['state'])"
```

---

## Hvad er dette repo

Home Assistant Infrastructure-as-Code til familien Example Home.

- **Ejer:** Parent A + Parent B + Child A + Child B
- **Hardware:** Intel NUC, HAOS 18.2 / Core 2026.9.2 (pr. 2026-10-21), Nabu Casa ZBT-2 Zigbee koordinator
- **Stack:** ZHA (Zigbee) + ESPHome (WiFi for Apollo MSR-2 mmWave sensorer)
- **Adresse:** `home_name` i secrets.yaml, aldrig i git (flyttedag 2026-06-01)
- **Sprog:** Dansk i kommentarer, engelsk i identifiers
- **PROD branch:** `main` (ingen andre branches eksisterer)

## Hardware-status context

Familien er flyttet ind og hardwaren er sat op. **Denne fil holder IKKE
device-status** — den drifter hurtigere end nogen når at rette den. Live sandhed:

- **Hvad er online lige nu:** `./scripts/ha_health.sh zha` (utilgængelige
  devices) + diagnostik-dashboardet `/diagnostik-dash`.
- **Hvad mangler at blive købt/paret:** [docs/hardware_shopping.md](docs/hardware_shopping.md).
- **Hardware-quirks der IKKE kan gættes** (Apollo-lux, Thread-routere,
  batteri-devices' oppetid, Matter-ekkoer): CLAUDE.md's "💡 Permanente fakta".

Grovt: 5× Apollo MSR-2 (netdrevne, ~100 % oppetid), 5× Styrbar N2, 5× RODRET,
Matter-over-Thread gardiner + dørsensorer (batteridrevne, blinde 10-18 % af
tiden), Innr/Tradfri-pærer. Antal og rolle ændrer sig — verificér før du regner
på det.

---

## File-tree quick reference

```
homeassistant-main/
├── CLAUDE.md             ← Backlog + standing instructions (LÆS FØRST)
├── AGENTS.md             ← Du er her
├── MOVING_DAY.md         ← Runbook for flyttedag (skrevet til ikke-tekniker)
├── README.md             ← User-facing project overview
├── configuration.yaml    ← HA root config (recorder, mobile_app, packages-include)
├── customize.yaml        ← Per-entity overrides (ikke meget brugt)
├── script_pkg/           ← Splittet 2026-05-05 (Phase 2.1) — 5 filer:
│   ├── room_logic.yaml      (room_mode_apply, drift_back, gentle_fade_off, scene_toggle)
│   ├── house_routines.yaml  (godnat, godmorgen, sluk_alt)
│   ├── bulb_defaults.yaml   (innr_color, tradfri_white, innr_plug)
│   ├── styrbar_helpers.yaml (color_cycle, brightness_step, snap, stamp_press)
│   └── scenes.yaml          (12 scene_* scripts — cycle helper fjernet 2026-05-22)
├── scenes.yaml           ← Tomme/legacy
├── rosters/              ← Delte entity-lister (konsolidering P2): `entity_id: !include ../rosters/<navn>.yaml`
│                            Ret listen HER; forbrugere: grep -rn "rosters/<navn>" . — scripts/rosters.py
│
├── automations/          ← Hver fil = relateret bundt automations
│   ├── README.md         ← Index over hver automation-fil
│   ├── putning_auto_detect.yaml         ⭐ NEW (2026-05-07/08)
│   ├── morning_lights_sanity_check.yaml ⭐ NEW (2026-05-08)
│   └── init_user_preferences.yaml       ⭐ NEW (2026-05-07)
│
├── packages/             ← Helpers + template-sensors organiseret per concern
│   ├── README.md         ← Index over hver package
│   └── global_tuning.yaml               ⭐ NEW (2026-05-07): 4 sliders + 4 factors
│
├── script_pkg/           ← Splittet 2026-05-05 (Phase 2.1) — 6 filer:
│   ├── room_logic.yaml      (room_mode_apply, drift_back, gentle_fade_off, scene_toggle)
│   ├── house_routines.yaml  (godnat, godmorgen, sluk_alt)
│   ├── bulb_defaults.yaml   (innr_color, tradfri_white, innr_plug)
│   ├── styrbar_helpers.yaml (color_cycle, brightness_step, snap, stamp_press)
│   ├── scenes.yaml          (12 scene_* scripts — cycle helper fjernet 2026-05-22)
│   └── apollo_helpers.yaml  ⭐ NEW (2026-05-07): apollo_radar_tune_room
│
├── entities/
│   ├── device_inventory.yaml  ← SOURCE OF TRUTH for hver paeret device
│   ├── lights/                 (mest dokumentation)
│   ├── sensors/                (mest dokumentation)
│   └── covers/                 (mest dokumentation)
│
├── docs/
│   ├── cross_cutting_map.md    ⭐ NEW (2026-05-08): "hvor lever koncept X på tværs af filer"
│   ├── architecture.md         ← System-design overblik (LÆS FOR KONCEPT)
│   ├── state_machine.md        ← Mode/flag transition diagrams
│   ├── hardware.md             ← Host (NUC, BT, etc.)
│   ├── hardware_shopping.md    ← Mangelliste (Somrigs, Vallhorns, Parasolls etc.)
│   ├── zigbee.md               ← ZHA setup + mesh-recovery decision tree
│   ├── secrets_backup.md       ← Hvordan secrets.yaml backes op manuelt
│   ├── matter_pairing_playbook.md ← Thread/Matter commission procedure
│   └── apollo_calibration.md   ← Per-room radar baseline tuning
│
├── scripts/
│   ├── ha_validate.py          ← YAML + entity refs validator (skipper templated!)
│   ├── ha_smoketest.py         ← 18 functional tests af state machine
│   ├── ha_deploy.sh            ← Auto-deploy gate m/ smoke test + auto-revert
│   ├── ha_snapshot.sh          ← Dump+diff state for refactor verification
│   ├── gen_docs.py             ← Re-generate auto-doc (rooms + dependency map)
│   ├── hq.py                   ← Live HA-data: state/hist/flanks/who/auto/find/where (kompakt TSV)
│   ├── claude_rules.py         ← .claude/rules/: lint (pre-commit) + Bash-hook
│   ├── ha_offline.py           ← HA's egen validator/loader/runtime UDEN NUC (check, equiv, staging, refs)
│   ├── roster_drift.py         ← Kopierede entity-lister + drift (pre-commit JIT)
│   ├── ha_slug.py              ← ÉN HA-kompatibel slugify (importeres af de andre)
│   ├── session_start.sh        ← SessionStart-hook: synk git-hooks + bagud-tjek
│   └── pre-commit-hook.sh      ← Bash hook der fanger PLACEHOLDER device_ieee
```

---

## "Where do I look for X" lookup

### Auto-generated lookups (rerun `./scripts/gen_docs.py`)

| Spørgsmål | Find i |
|-----------|--------|
| **Hvor refereres entity X?** (alle filer + linjer) | `python3 scripts/hq.py where X` (live scan, ~1 s; template-byggede refs vises separat) |
| **Hvad affekter rum X?** (automations, entities, helpers) | [docs/auto/rooms/](docs/auto/rooms/) — 11 per-room dossiers |
| **Hvilke entities er hot?** (refed i mange filer) | [docs/auto/dependency_map.md](docs/auto/dependency_map.md) |

### Manually-curated lookups

| Spørgsmål | Find i |
|-----------|--------|
| Hvordan tændes/dimmes lys ved presence i rum X? | [automations/presence_X.yaml](automations/) (per-room siden 2026-05-05) |
| Lux-baseret reactive lighting (alle rum) | [automations/presence_lights.yaml](automations/presence_lights.yaml) |
| Hvordan virker Styrbar-knap? | [automations/styrbar_rooms.yaml](automations/styrbar_rooms.yaml) (universal handler) |
| Hvordan virker entré-Somrig (RODRET)? | [automations/entre_somrig.yaml](automations/entre_somrig.yaml) |
| Hvordan virker entré-motion (Myggspray Matter)? | [automations/entre_motion.yaml](automations/entre_motion.yaml) |
| Hvordan drifter mode tilbage til Auto? | [automations/room_drift_back.yaml](automations/room_drift_back.yaml) |
| **Hvordan virker putning detection?** ⭐ NEW | [automations/putning_auto_detect.yaml](automations/putning_auto_detect.yaml) + [docs/cross_cutting_map.md](docs/cross_cutting_map.md) #6 |
| **Hvordan virker kalde-knap?** | [automations/godnat_night.yaml](automations/godnat_night.yaml) (godnat_kalde_on + putning_short_down) |
| **Hvad slukker boern lys ved godnat?** ⭐ NEW DRY | [automations/godnat_night.yaml](automations/godnat_night.yaml) (godnat_boern_active_on_actions = single source of truth) |
| **Hvad er kids_home flag og hvorfor?** ⭐ NEW v2 | [packages/activity_state.yaml](packages/activity_state.yaml) (binary_sensor.kids_home + 4 signaler) + [docs/cross_cutting_map.md](docs/cross_cutting_map.md) #3 |
| **Auto-off lys hvis bright/empty (morgen)?** ⭐ NEW | [automations/morning_lights_sanity_check.yaml](automations/morning_lights_sanity_check.yaml) |
| **Global tuning sliders (4 stk)?** ⭐ NEW | [packages/global_tuning.yaml](packages/global_tuning.yaml) + dashboard tile under "Global Tuning" |
| **Apollo radar tuning (NVRAM writes)?** | [packages/apollo_per_gate.yaml](packages/apollo_per_gate.yaml) (`script.apollo_radar_apply_now`) — læs 🔥-reglen i CLAUDE.md først |
| Aktivitets-detektion (cooking/dining/etc) | [packages/activity_state.yaml](packages/activity_state.yaml) |
| Mood-flags (cinema/cirkus/godnat/guest_mode) | [packages/house_modes.yaml](packages/house_modes.yaml) |
| Helpers per rum (room_mode, last_press, etc) | [packages/room_modes.yaml](packages/room_modes.yaml) |
| Tunable konstanter (fade-tider, lr_grace, godnat brightness/kelvin) | [packages/constants.yaml](packages/constants.yaml) |
| Light-groups (per-rum + cross-room) | [packages/light_groups.yaml](packages/light_groups.yaml) |
| Scene-scripts (cinema, party, zen, etc) | [script_pkg/scenes.yaml](script_pkg/scenes.yaml) `scene_*` |
| Helper-scripts (stamp_press, color_cycle, etc) | [script_pkg/styrbar_helpers.yaml](script_pkg/styrbar_helpers.yaml) `styrbar_*` |
| Room logic (drift_back, mode_apply, gentle_fade) | [script_pkg/room_logic.yaml](script_pkg/room_logic.yaml) |
| House routines (godnat, godmorgen, sluk_alt) | [script_pkg/house_routines.yaml](script_pkg/house_routines.yaml) |
| Bulb defaults (innr_color, tradfri_white, innr_plug) | [script_pkg/bulb_defaults.yaml](script_pkg/bulb_defaults.yaml) |
| Matter Thread/Border Router setup | [docs/matter_pairing_playbook.md](docs/matter_pairing_playbook.md) |
| Hvilken IEEE har devicet X? | [entities/device_inventory.yaml](entities/device_inventory.yaml) |
| Hvad mangler vi at købe? | [docs/hardware_shopping.md](docs/hardware_shopping.md) |
| Hvad gør jeg på flyttedag? | [MOVING_DAY.md](MOVING_DAY.md) |
| Hvad gør knap/tilstand X i dag, og hvilken slider ejer tallet? | [system_design.md](system_design.md) — hvorfor-et-tal: kommentaren ved slideren + `grep` i docs/sprint_log.md |
| Hvad er der OPEN i backlog'en? | [CLAUDE.md](CLAUDE.md) |
| Hvilke validators / helpers / scripts har vi? | [scripts/README.md](scripts/README.md) |

### Workflow scripts (use før refactoring)

| Værktøj | Brug |
|---|---|
| `./scripts/ha_validate.py` | Find broken entity refs, dups, jinja errors |
| `./scripts/ha_snapshot.sh` | Dump+diff state for refactor verification |
| `./scripts/ha_smoketest.py` | 9 functional tests af state machine |
| `./scripts/gen_docs.py` | Re-generate auto-doc (rooms + dependency map) |
| `python3 scripts/hq.py` | Live state, historik/fordelinger, flanker, hvem-skiftede-X, automation fil:linje |
| `./scripts/matter_preflight.sh` | Pre-pair check for Matter devices |
| `./scripts/matter_commission.sh` | Full Matter commissioning flow |

---

## Critical conventions

### Entity naming

`<domain>.<rum>_<devicetype>[_<extra>]_<sub_feature>`

- `<domain>`: light / switch / sensor / binary_sensor / number / select / button / update
- `<rum>`: stue / koekken / spisestue / sovevaerelse / boernevaerelse / badevaerelse / entre / depot / terrasse / altan
- `<devicetype>`: loft / pendel / strip / lampe / apollo / valhorn / parasoll / plug / styrbar / somrig
- `<extra>`: optional placement (`_sofa`, `_bord`)
- `<sub_feature>`: sub-entity-funktion (`_on_level`, `_battery`, `_illuminance`, etc.)

Eksempler:
- `binary_sensor.sovevaerelse_apollo_occupancy`
- `light.stue_sofa_lampe`
- `sensor.terrasse_plug_power`
- `cover.gardin_sovevaerelse`

### Direkte HA-adgang (CLI)

Claude har **fuld terminal-access** til HA via Bash tool. Primary commands:
- `bash scripts/ha_deploy.sh` — auto-deploy + smoke test + auto-revert
- `ssh ha "cat /config/<file>"` — verify deployed state
- `. .env && curl -H "Authorization: Bearer $HA_TOKEN" http://homeassistant.local:8123/api/states/<entity>` — REST query

Full SSH/REST examples + setup details: se [CLAUDE.md](CLAUDE.md) standing instructions
+ [docs/remote_workflow.md](docs/remote_workflow.md). Valider med
`python3 scripts/ha_offline.py check`, ikke `ha core check`.

### Mode-flags hierarchy (overview)

Use `binary_sensor.godnat_any_active` (union) **NOT** `godnat_active` (master)
for godnat-aware gating — sub-flags can be on alone (sprint 2026-05-05 fix).

Categories:
- **Master gate:** `presence_sensors_available`
- **Godnat sub-flags:** `godnat_active`, `voksne_active`, `boern_active`, `pending`, `kalde_active` → union via `godnat_any_active`
- **Mood:** `cinema_active`, `cirkus_active` (pauser presence-fades + drift-back)
- **Activity:** `guest_mode`, `bedroom_only_winddown` (auto-set fra activity_state)
- **Kids state:** `binary_sensor.kids_home` v2 + `input_boolean.kids_home_manual` (sprint 2026-05-08)
- **Kill switches:** `auto_godnat_enabled`, `auto_putning_enabled`
- **Scenes:** `input_select.active_scene` + 10× `binary_sensor.scene_*_active`

**DRY single-source-of-truth (sprint 2026-05-08):** ALLE entry-points (kalde-knap,
putning auto-detect, dashboard tile, script.godnat) sætter blot `godnat_boern_active=on`.
`automation.godnat_boern_active_on_actions` (i godnat_night.yaml) cascader actions
(slukke boern lys + lukke gardin) — DRY pattern.

Full chain + consumers: [docs/cross_cutting_map.md](docs/cross_cutting_map.md) #2-#6.

---

## Common task recipes

**Tilføje en ny lyspære:**
1. Par via ZHA UI → omdøb til konvention → tilføj til `light.<rum>_all` + `light.alle_lys` i [packages/light_groups.yaml](packages/light_groups.yaml)
2. Tilføj entry i [entities/device_inventory.yaml](entities/device_inventory.yaml)
3. Commit + push + `bash scripts/ha_deploy.sh`. Scripts bruger groups → ingen edits.

**Tilføje et nyt rum:** Større arbejde — se [docs/architecture.md](docs/architecture.md) "Adding a new room"-sektion.

**Debug hvorfor en automation ikke fyrede:**
- HA UI → Settings → Automations → find → Traces (viser failed condition)
- Eller: Developer Tools → Events → listen til `state_changed` for trigger entity
- Hvis sensor unavailable: tjek `binary_sensor.presence_sensors_available`

**Test en scene uden Styrbar:** Developer Tools → Services → `script.scene_party` (eller en hvilken som helst `script.scene_<name>`). Scene-cycle helper findes ikke længere — brug dashboard-tiles eller direkte script-kald.

---

## Critical gotchas (lessons learned)

- **🧠 Fejlklasserne står i CLAUDE.md** (auto-loaded, kort form) med den fulde
  version i [docs/fejlklasser.md](docs/fejlklasser.md). Gentag dem ikke her —
  to kopier divergerer (det er selv fejlklasse #2).
- **`replace_all` på numeriske patterns** — `transition: 60` matcher prefixet af `transition: 600`. ALDRIG bulk-replace numerics uden line-end anchor (`pattern$`). Brød HA boot 2026-04-29.
- **`enabled: false` i automations** — deprecated i modern HA. Brug fake-IEEE `"00:00:00:00:00:00:00:00"` der aldrig matcher i stedet.
- **HA workday platform via YAML** — deprecated. Skal sættes op via UI Config Flow.
- **`ha core check` var buggy i 2026.4** (`KeyError: 'triggers'`, rettet i 2026.9.2) — valider stadig med `python3 scripts/ha_offline.py check` og genstart med `bash scripts/ha_restart.sh` (gemmer restore-state først).
- **Apollo MSR-2 entity-navne** — efter rename i HA UI bliver de `<rum>_apollo_<sub>`. Pre-rename hedder de `apollo_msr_2_<test_id>_<sub>`. Mange historiske automations refererer pre-rename navne — nu sweep'd.
- **Templater i `for:` field** — virker i HA 2024+. Men husk at tuning af input_number kræver HA restart for at trigger picker det op.
- **scene.create snapshot_entities** — kan templates med `expand()` for dynamic. Plug switches og covers er separate entity-typer end lights.
- **⚠️ Templated entity_id refs (`light.{{ room }}_all`)** — ha_validate.py KAN IKKE catch broken refs til templated patterns. Sletning af `light.<rum>_all` group breaker silent ALLE Styrbar handlers + room_logic scripts. Smoke test `test_room_light_groups_exist` catches post-deploy. Se [docs/cross_cutting_map.md](docs/cross_cutting_map.md) #1.
- **`last_changed` ≠ "last seen recently"** — last_changed = state TRANSITION timestamp. Hvis state har været continuously 'on' i 4h, last_changed = 4h ago. For "currently active" check, BRUG `state == 'on'` direkte (ikke `last_changed < X`).
- **`initial:` field på input_number** — TVUNGEN reset på hver HA restart. FJERN initial:; fresh-install-defaulten er snapshottet (`config_snapshots/helper_values.yaml`, gendannet af init_user_preferences — P1 2026-10-04).
- **Sub-flag stuck detection** — sub-flag-only states ER legitimate (godnat_boern alene = "kids in bed, adults staying up"). Smoke test bruger age-based detection (>12h = stuck), ikke "must be paired with master".
- **Phone notifications inconsistent** — water_leak/battery/device_health KUN notify Parent A (mobile_app_phone_a). Parent B får IKKE alerts. Backlog F2 venter på fix.
- **kalde-RODRET er sleepy ZED** — efter battery-skift kan device være droppet ud af mesh. Re-pair via ZHA permit_join (preserver IEEE → automations virker uden ændringer).

---

## Backlog

Ligger i **[BACKLOG.md](BACKLOG.md)** (B/F/O/M-items), som bevidst IKKE
auto-loades. `grep` i den frem for at Read'e den — den er 1800+ linjer. Læs den
kun hvis user beder om triage eller spørger "hvad er næste".
---

## Den menneskelige side

- **Parent A** + **Parent B**: 2 voksne. Parent B vil have ting til at "bare virke" (UX > clever).
- **Child A + Child B**: 50% delebørn (out of sync). Child A kan røre Styrbar utilsigtet (robust mod chaos). Child B sover random tider (ingen pinlige lys-skift dag).
- **AirBnB roadmap** — privacy-tradeoffs (F1 backlog).

**Prioriteter:** subtile smooth fades over snap-skift • ingen pinlige auto-ændringer med gæster • manuel kontrol respekteres (user-dim overskrives ikke).
