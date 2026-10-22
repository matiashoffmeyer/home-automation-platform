# CLAUDE.md — Standing Instructions

> **English summary.** This file is written in Danish, the working language
> of the household. It is the instruction set the AI coding agent (Claude
> Code) loads at the start of every session: recent lessons, permanent
> platform facts, standing rules and recurring failure classes, each kept to
> a one-line signature with a pointer to the long version.
> [docs/methodology.md](docs/methodology.md) describes the method in
> English. Links to operational logs (sprint log, backlog, feedback data)
> point to files that are not part of this repository.

Auto-loaded ved HVER session. **Alt herinde betaler du for i hver eneste
fremtidig samtale — også dem der aldrig rører emnet.** Derfor er filen et
*genkendelses-lag*: reglen, dens signatur, en pegepind. Historien bag, måledata
og incident-forløb ligger i docs/ og koster kun tokens når nogen læser dem.

| Vil du vide | Så læs (auto-loades IKKE) |
|---|---|
| Hvordan så fejlen konkret ud? | [docs/fejlklasser.md](docs/fejlklasser.md) |
| Hvorfor blev det bygget sådan? | [docs/sprint_log.md](docs/sprint_log.md) — `grep`, læs den aldrig helt |
| Hvad er næste opgave? | [BACKLOG.md](BACKLOG.md) — kun ved triage-spørgsmål |
| Hvor lever koncept X? | [docs/cross_cutting_map.md](docs/cross_cutting_map.md) |
| Hvad hedder entity X? | `python3 scripts/hq.py find <ord…>` (live, æøå-foldet; `--offline` i cloud) |
| Live state / historik / hvem skiftede X? | `hq.py state\|hist --stats\|flanks\|who X` — lokal tid, ≤ 40 linjer |
| Hvor bruges entity X? | `hq.py where X` — fil:linjer, live scan (~1 s), template-byggede refs separat |
| Hvem må skrive lampe X, i hvilken rang? | `docs/auto/ejerskab/<lampe>.md` (genereret; hooken giver dig den selv når du rører lampen) |
| Hvad rører rum X overhovedet? | `docs/auto/rooms/<rum>.md` (genereret, 100-400 linjer) — billigere end et grep-sweep over 66 filer |
| Validere / bevise et refactor UDEN NUC? | `python3 scripts/ha_offline.py check\|equiv\|staging\|refs` — [docs/konsolidering.md](docs/konsolidering.md) |

---

## 🕐 Seneste sprints — hvad huset lærte sidst

Ét facit pr. sprint, 3-5 linjer, **max 3 noter** (`claude_rules.py check` tæller);
ældste rulles ud i SAMME commit. **Fuld note med
måledata: `grep -n "Sprint <dato>" docs/sprint_log.md`.** Er en lærdom permanent,
hører den i "Permanente fakta" eller som en fejlklasse — ikke i en sprint-note.

- **2026-10-20 — et spørgsmål du kender svaret på er støj.** 699 pushes på 14
  dage: aktivitets-træneren spurgte om gæt med 8/8 rigtige, "Nattens vejr" kom 3×
  med samme tekst. Nu spørger trænerne kun når gættets seneste svar er i tvivl
  (`scripts/trainer_tvivl.py`, `trainer_sikker_*`), vejret kun igen ved ændring,
  og tekster får danske navne + decimal-komma fra `custom_templates/tekst.jinja`. B241.
- **2026-10-21 — en regel der vogter DELE af tallet, vogter ikke tallet.**
  "Kun ned ved hoveddøren" lækkede 51 gange på 14 døgn: v5 låste familie- og
  ekstra-delen, mens Dormant, geofence-exit, familie-vækst, rå zoner og manuel-
  udløb sænkede det VISTE tal. v6: ét holdt tal, ned kun i dør-vinduet; tjek
  `ha_health.sh people`. Samme dag: bad-boksen beviser ≥ 2. B245, B246.
- **2026-10-22 — en dom der lander efter vinduet, er stadig dørens dom.** Dør
  08:10; et sove-spøgelse holdt buddet på 1 og gen-låste ekstra-gulvet, og
  Dormant kom 27 s før dør-vinduet lukkede → 1 i et tomt hus hele dagen. Nu
  sætter Dormant ≤ `people_afgang_dom_minutter` (120) efter døren 0 og rydder
  ekstra (30 døgn: dommen 35-104 min, første forkerte Dormant 284 min). B246.
---

## 💡 Permanente fakta (destilleret fra arkiverede sprints)

Hardware-/platform-sandheder der stadig gælder. **Dette er et GENKENDELSES-lag:
reglen, dens signatur, et entity-navn — intet andet. Måledata, incidents og
begrundelser står i [docs/permanente_fakta.md](docs/permanente_fakta.md)**, hvor
hver bullet har sit lange modstykke (`grep -n "<nøgleord>"`, Read aldrig filen
helt). Ændrer virkeligheden sig, skal BEGGE lag rettes (det korte står her ELLER
i `.claude/rules/<domæne>.md`; `scripts/claude_rules.py check` er linten).

**Home Assistant — husdækkende** (forfatter-fælderne: `initial:`, slugify,
`!include`, `input_datetime`/`input_text`, `statistics`/`history_stats`, Jinja-
gotchas m.fl. står i `.claude/rules/ha_yaml.md`, som loades ved første YAML-læsning)
- **En HA-restart dræber ethvert `to: X for: N` der VENTER på en flanke der
  allerede er sket** (især sluk-/oprydnings-veje) → time_pattern-backstop der
  måler tiden med et condition-template. To følge-huller: en automation der ikke
  lytter endnu modtager INGEN triggers, og `from: "off"`-guarden gør
  restart-flanken usynlig for TÆND-veje. Fix: `platform: homeassistant,
  event: start` + settle-delay som ekstra id på den EKSISTERENDE gren.
- **`template.reload` er IKKE en gratis deploy** — hver template-entity gennem
  `unavailable`, og `unavailable → off` fyrer sluk-veje. **Signatur:** en
  handling i præcis samme sekund som et reload. → eksplicit `from:` på `to:`-
  triggers på template-entities (**`scripts/b103_scan.py` blokerer i
  pre-commit**; er flanken selve BEVISET → dens `ALLOWLIST` med et hvorfor).
  **Og en `delay_on`-sensor laver en ÆGTE `off → on` præcis `delay_on` efter
  reloadet** → guard på off-fasens længde; reload automations FØR templates.
- **HA SEGFAULTER under nedlukning (pychromecast-tråd, Python 3.14) → den
  afsluttende restore-state-skrivning sker ALDRIG**; kun 15-min-dumpet overlever.
  **Signatur: skyder-/boolean-ændringer fra de sidste < 15 min før en restart
  er væk, uden context, og `home-assistant.log.fault` har mtime = restart.** →
  genstart KUN med **`bash scripts/ha_restart.sh`** (gemmer først;
  `scripts/restart_guard.py` afviser en bar `ha core restart`).
- **`last_updated`/`last_changed` nulstilles ved HA-restart** → duer ALDRIG som
  friskheds-mål. Brug et **skrevet** stempel (#5). Apollo-ophold:
  `input_datetime.<rum>_apollo_occ_since` (restart-sikker, 1970 når off).
- **ENHVER automatisk sluk af badet venter på `binary_sensor.badevaerelse_fugt_frisk`
  og afgør derefter på `brusebad_hold`** (user-spec 1/10: "aldrig sluk uden en
  frisk fugt-måling"). En ny bad-sluk-vej uden blokken er en regression (#21) —
  `grep -rn fugt_frisk`. Kun max-on watchdog'en er bevidst undtaget.

- **Inde-fugt/-temp læses via `sensor.inde_absolut_fugt` (g/m³) /
  `sensor.indoor_humidity_resilient` (%RH) / `sensor.indoor_temperature_resilient`
  (°C), aldrig `timmerflotte_*` direkte** — køkken-TIMMERFLOTTE falder af
  Thread; depotets Broadlink er reserve (attribut `kilde`). `grep -n "TO fugt-instrumenter" docs/permanente_fakta.md`.

**Domæne-fakta — path-scopet i `.claude/rules/`.** Hver fil loades automatisk
når du læser en fil der matcher dens `paths:`. **Forklarer du adfærd i et
domæne UDEN at læse dets filer** (fx kun via `hq.py`), så læs reglen selv først.

| Regel-fil | Dækker |
|---|---|
| `lux_dagslys.md` | Apollo LTR390: LED og egne lamper i målingen, ~20 lx-trinnet, rene samples, gate-kilder, fradrag |
| `presence_radar.md` | Apollo/LD2410 + Valhorn: felter vs. rum, ghosts, gate-lag, sove-Apolloen, blinde kanaler (`ha_health.sh blind` FØR du forklarer presence), sleepy end devices, 🔥 ESPHome chip-wear |
| `thread_matter.md` | Thread-routere, partition-split, BLE-adaptere, GRILLPLATS, telefon-commissioning, RCP-hæng |
| `lys_paerer.md` | pære-quirks (TRADFRI 2 %, RGBW, power_on_behavior, OTA), stuens fire lys, pærer der falder af nettet |
| `lys_effekter.md` | gruppe-kald venter på langsomste pære, farve = 2 frames, ZHA-gruppen, Matter-rapportering, transition-fælder |
| `gardiner_sol.md` | antagne RF-positioner, hold-ankerets to lister, sol-indtrængning (mosbilledet, 333°) |
| `energi.md` | delta-rapporterede effekt-plugs, cykel-laderne, Energi Data Service-prisen |
| `stemme_gestus.md` | kamera-API død (kun RTSP), hand_recognition-fingre, Speech-to-Phrase, Android-timeren |
| `nemlig.md` | søgningen er ikke ascii-foldende, varetræet, multipak-pris |
| `roborock.md` | sug + mop er én tilstand, sky-status med forsinkelse, robotten ER bevægelsen |
| `vejr.md` | DMI-host og versioner, REST-sensorer der fryser, met.no's sky-bias om natten |
| `personer_telefon.md` | GPS-proxyer, iOS Always-tilladelse, zone.home, alarm-sensorer i UTC, knapsvar kræver netværk |
| `scripts_api.md` | shell_command-token, POST /api/states-entities, /api/template, recorderens context-felter, history-end_time |
| `dashboards.md` | visibility-betingelser, ingen scroll-til-kort, statistics-graph side om side, tekst-reglen |
| `addons.md` | deploy fra /addons/<slug>/, ikke git-kopien — verificér på version |
| `ha_yaml.md` | al automations/packages/script_pkg-YAML: `initial:`, slugify, `!include`, template-blokke, `input_datetime`/`input_text`, `statistics`/`history_stats`, `delay_on`/`delay_off`, Jinja-gotchas |

**Radio — husdækkende** (gælder enhver YAML der rører lys eller Matter)

- **`light.spisestue_pendel` ER SOVE-LOFTET** (flyttet 06/2026, navnet beholdt;
  eneste medlem af `light.sovevaerelse_all`). Tag den aldrig med i et open-plan-kald.
- **En Matter-node der kommer tilbage genopstår med sin SIDSTE kendte værdi** →
  `unavailable → on` er et ekko. Tænd-triggers kræver `from: "off"`.
- **CHIP Error 0x00000032 (Timeout) aborterer HELE automation-scriptet** →
  `continue_on_error: true` på Matter-lys-kald, også via lysgrupper
  (`ha_validate.py --check matter` blokerer i pre-commit; templatede mål ser den ikke).

**📋 Cross-cutting concerns map:** [docs/cross_cutting_map.md](docs/cross_cutting_map.md)
— FIRST READ for AI sessions der skal ændre tværgående logik.

---

## Andre meta-docs

- **[AGENTS.md](AGENTS.md)** — fast-path navigation: file-tree, "hvor-finder-jeg-X", konventioner, recipes
- **[system_design.md](system_design.md)** — verificeret Holy Grail-spec (knapper, drift-back, sluk-tider,
  hus-tilstande, gardin-forsvar) med den slider der ejer hvert tal; ret den i samme commit som adfærden
- **[docs/architecture.md](docs/architecture.md)** — Holy Grail-filosofi, activity-tree, mode-flag-prioritet
  (permanente_fakta / standing_instructions / fejlklasser er linket fra hver sin sektion herunder)
- **[docs/README.md](docs/README.md)** · [automations/README.md](automations/README.md) · [packages/README.md](packages/README.md) — indexes

---

## Standing instructions

**Den lange version — begrundelser, incidents, kode-eksempler og
recovery-opskrifter: [docs/standing_instructions.md](docs/standing_instructions.md)**
(`grep -n "<nøgleord>"`). Reglerne herunder er bindende som de står. Ændrer en
user-spec sig, skal BEGGE lag rettes.

### 🔄 Tjek status FØR du koder (per 2026-07-29, user-spec)

**Første handling i enhver kode-opgave**, før du læser filer:
`git fetch origin && git status && git rev-list --left-right --count origin/main...HEAD`.
Bagud → `git merge --ff-only origin/main` FØR du rører noget, og genlæs CLAUDE.md
+ relevante pakker fra det friske træ. Checkouten er rutinemæssigt 30-200 commits
bagud, og arbejde mod en stale base ruller stille nyere features tilbage.

### 💰 Token-økonomi & Cache — overhold altid disse (per 2026-09-21, user-spec)

Filosofien er uændret (**langsomt + grundigt frem for hurtigt**) — pengene skal
bruges på diagnose og verifikation.

- **Klassificér opgaven FØRST:** Er det SIMPEL (ændre én kendt slider/tærskel) = `< 10 tool-calls, INGEN fuld fil-Read`. Er det UNDERSØGELSE (bug-hunt/ny feature) = fuld log/history-graving. Det dyre anti-mønster er fuld udgravning til en tekstrettelse.
- **Kontekst-længden ER regningen (målt 2026-10-08):** hvert kald genlæser hele samtalen — cache-reads ≈ 70 % af forbruget, og modellens egen thinking er ca. halvdelen af væksten. Loft: `autoCompactWindow: 200000` i NUC'ens `~/.claude/settings.json` (1M-vinduet compactede aldrig; sessioner nåede 820k). `/clear` mellem urelaterede opgaver. Cache-TTL'en (1 t) styrer Claude Code selv: efter en pause > 1 t skrives HELE konteksten igen til dobbelt pris → stor kontekst før en lang fysisk test = bed user om `/compact` først. Genlæs aldrig det du allerede har; hent kun det nye.
- **Spar ALDRIG på:** logs/history-graving ved en bug, kalibrering mod ægte data, eller verifikation efter deploy.
- **Anti-mønstre:** re-Read'e en fil du selv lige har rettet · dumpe rå `/api/states` i stedet for at filtrere med python/grep. 

### 🚦 Subagenter — arbejd selv, deleger kun brede sweeps (per 2026-09-21, revideret 2026-10-08, user-spec)

Målt 8/10: subagenternes andel steg 4 % → 33 % af forbruget. Hver agent starter med 50-65k tokens
skrevet til cache til dobbelt pris FØR den gør noget, og dens fund verificeres alligevel her.
1. **Arbejd selv:** opslag, få-fils-læsninger og kodeændringer laves inline (`grep`/`hq.py`/targeted Read). Subagent kun til ægte brede sweeps (dusinvis af filer, bug-hunt-workflows) — og den returnerer *kun konklusionen*.
2. **Kode skrives af Opus** (user-spec 2026-10-07). Kører hovedsessionen på Sonnet og skal der committes kode: bed user om `/model opus` frem for at delegere — en Opus-subagent starter koldt og læser alt igen (7/10: 3 Opus-agenter kostede 4× hovedsessionen). Kan user ikke svare nu (🚀): ÉN Opus-subagent. Sonnet (`model: "sonnet"`, aldrig et versionsnummer) kun til read-only triage som bug-hunt-findere; `subagent_type: "fork"` kører altid på hovedmodellen.
3. **Ingen løbske parallel-flåder (Pro-plan kvote):** Max 1-2 subagenter ad gangen. For mange parallelle agenter brænder API-kvoten midtvejs, alle dør UDEN at returnere rapport og må køres igen. Store reviews: kør SEKVENTIELT. **Gælder også Workflow-værktøjet og "ultracode" — intet ophæver reglen** (brudt 10/10: Opus-findere + skeptiker pr. fund, kvoten døde). `scripts/agent_guard.py` (PreToolUse) afviser workflows uden `model:'sonnet'` på hver agent(), med `pipeline()`/`while` eller `parallel()` uden `.slice(i, i + 2)`, og en 3. samtidig Agent. Afvist = byg det mindre, aldrig omgå.

### 🚀 Fix + commit + push FØRST — spørg opklarende BAGEFTER (per 2026-07-27, user-spec)

Når user beder om et fix: **lav ændringen, commit og push FØRST**, og stil
derefter evt. opklarende spørgsmål. Spørg IKKE først og vent, **med mindre user
eksplicit skriver at han er til stede og kan svare nu** — blokerer du på et
spørgsmål han ikke ser (asynkron/telefon), går arbejdet tabt. Konkret: (1) vælg
den mest sandsynlige, laveste-risiko fortolkning ud fra logs; (2) implementér +
commit + push + deploy + notificér; (3) SÅ spørg, tydeligt markeret ("shippet X
med default Y — bekræft/justér:"). Dette **modificerer** 🤔-reglen: stop-og-spørg
gælder kun når user kan svare, eller når ændringen er ægte
irreversibel/destruktiv.

### 📏 MÅL altid selv — stil ALDRIG en værdi efter en sprint-note (per 2026-08-29, user-spec)

**"ALTID måle det, ALDRIG stil blindt på sprint noter — for så kan vi nedarve
fejl og de kan vokse."** Sprint-noter og kode-kommentarer er *hypoteser med
tidsstempel*, ikke måledata. Skal du sætte, hæve eller sænke en tærskel, en
timing eller en offset: **træk fordelingen af den kanal gaten faktisk læser**
(percentiler + "hvor mange samples ligger over/under?") over 2-3 døgn, FØR du
skriver tallet. Er dine tal uenige med noten, er det noten der er forældet — ret
den i samme commit. **Signatur:** en tærskel der er en ensom outlier blandt sine
søskende på SAMME måleskala. **Historik og fordelinger: `python3 scripts/hq.py
hist <entity> --stats [--gate X]`** (samples + tids-vægtet, lokal tid) — ikke
ad hoc curl.

**Og mål den rigtige FORDELING, ikke bare nok samples:** et negativ-sæt du selv
mærker er POSERET — driften leverer hele kontinuummet, så kløften du måler er
bredere end den du får. **Signatur: de falske positiver spreder sig ikke, de
klumper sig LIGE under tærsklen.** En gate må heller aldrig stilles efter sine
egne udslag alene — de er per definition kun dem der slap igennem.

### 🔍 Løs opgaver ud fra faktisk adfærd + real-world data (per 2026-07-23, user-spec)

Opgaver løses ved at undersøge **faktisk adfærd de seneste 2-3 døgn** — ikke ud
fra antagelser om hvordan setuppet "burde" opføre sig. (1) **Træk historikken**
for de involverede entities (`hq.py hist|flanks|who`, ai_feedback-JSONL'erne,
`./scripts/ha_health.sh noisy`). (2) **Lad de rigtige
tal drive parametre**. (3) **Verificér mod virkeligheden til sidst** (#6/#14):
"live-testet" betyder ægte device-events + bevis i history, ikke syntetiske
events. Brugeren fodrer løbende systemet med facit (ai_feedback-trænere,
korrektioner) — brug det som ground truth. Undtagelser: triviel syntaks/docs,
eller når brugeren eksplicit dikterer adfærden.

### 🤔 I tvivl om ØNSKET ADFÆRD → spørg. I tvivl om teknik → slå op

**Behavior-spørgsmål (SPØRG, med konkrete a/b/c-options i prosa):** "hvad skal
ske hvis X timeouter?", "skal Y fyre i Dormant også?", "hvor lyst = subjektivt".
**Tech-spørgsmål (bare gør det):** syntaks, entity_id, versioner — slå op/test.
I tvivl om hvilken slags: spørg alligevel. Se dog 🚀-reglen: kan user ikke svare
lige nu, så ship den mest sandsynlige fortolkning og spørg bagefter.

### 📲 Notificér brugeren ved ændringer (per 2026-06-27, user-spec)

Efter **deployede ændringer**: send én kort, punktvis push pr. arbejds-batch
(ikke pr. fil) der siger hvad der er live nu + evt. manuelt skridt der mangler.
Skip kun ved ren research uden deploy. Kanal: `notify/mobile_app_phone_a` via
`curl -X POST http://supervisor/core/api/services/notify/mobile_app_phone_a` med
`Authorization: Bearer $SUPERVISOR_TOKEN`.

**⚠️ UNDTAGELSE — AirBnB-mode = SILENT (per 2026-07-13, user-spec):** er
`input_select.house_mode` == `AirBnB`, send INGEN push (heller ikke
deploy-opsummeringen) — telefonen kan være i gæstens hænder. **Tjek mode FØR du
pusher.** Kode/dashboards/reloads er fine; det er kun notifikationerne der
undertrykkes. Nævn i din tekst-opsummering at pushen blev sprunget over.
**Én bevidst undtagelse (user-spec 2026-09-11):** `packages/kamera_airbnb_vagt.yaml`
SKAL pushe i AirBnB — varslet rammer user i det sekund HAN selv flipper mode.

### 🧪 Test fysisk + mål når nyt går live (per 2026-05-03)

Har ændringen **observerbar fysisk effekt** (lys, gardiner, lyd, timing): deploy
+ verificér at HA reelt er klar (state opdateret, ikke kun "Command completed")
→ **mål faktisk adfærd** før du erklærer succes (tidsstempl events via REST, læs
`state_attr('light.X','hs_color')` post-action, brightness er 0-254 raw) →
matcher observationen ikke design-intent, itererér med målinger. **Stop ikke ved
første "ser ud til at virke".** **HA's reelle throughput er ~5-10
light-kald/sek** — loop-designs der antager >10/sek fejler silently.

### 🎛️ Tjek eksisterende slidere FØR du bygger nyt (per 2026-05-17)

Skal en parameter justeres (timing, brightness, tærskel, varighed), så grep
FØRST i `packages/global_tuning.yaml`, `packages/constants.yaml` og dashboards'
Global Tuning-sektion. **Findes der allerede en slider → sig det til brugeren
før du ændrer noget.** Er det nyt territorium: byg slider + factor-sensor +
dashboard-tile + snapshot-export i ÉN commit (snapshottet ER fresh-install-
defaulten siden P1 2026-10-04 — ingen ny blok i init_user_preferences).
Hardcodede magic numbers skal helst være tunable.

**Gælder ENHVER knap, ikke kun parametre** (2026-09-19): grep X's FUNKTION før du
bygger — helperen kan hedde noget andet end rummet. **Signatur: user beder om en
knap der FINDES, fordi den ligger på en anden side end den han står på** →
opgaven er placering + scope-tekst, ikke en ny helper (en dublet deler staten).

**Scope skal beskrives (per 2026-07-02, user-spec):** rammer en slider ikke alle
pærer — eller ikke alle i det rum den nævner — SKAL undtagelsen stå under tilen
som ÉN linje ("Gælder ikke: …", jf. tekst-reglen under 📊). Ændrer du en sliders
scope, opdatér ALLE berørte beskrivelser i samme commit. Scope-påstande
verificeres i koden, ikke gættes (#1/#3).

**Værdier snapshottes til git (per 2026-06-17):** sliders lever i `.storage`,
ikke i git → `python3 scripts/helpers_export.py` → commit **`config_snapshots/`**
(begge filer — pre-commit afviser et staget par der ikke passer; håndrettet
snapshot → `--derive`); `helpers_restore.py [--apply]` gendanner.
NB export'en kører på en **allowlist** (`DATETIME_CONFIG`/`SELECT_CONFIG` i
scriptet) — en ny konfig-`input_datetime`/`input_select` skal tilføjes dér,
ellers snapshottes den tavst ikke.

### 🚀 Deploy + Multi-Claude sync — aldrig blind `reset --hard`

Claude har fuld adgang (SSH + REST) og udfører **selv** deploy, restart,
state-queries og service-calls; brugeren bruger kun HA's UI til det fysiske
(parre devices, addons, OAuth). Arbejder han også fra telefonen, kan `/config`
have lokale commits. **Sikker sekvens:** commit lokalt → fetch → inspicér
`git log --oneline @{u}.. -5` → `pull --ff-only` (fejler ved divergens = tving
manuel review) → `bash scripts/ha_restart.sh` (skip restart ved docs-only). Fuld procedure:
[docs/commit_workflow.md](docs/commit_workflow.md).

**`git stash && git pull && git stash pop` er en FÆLDE på /config:** stasher
`git stash` intet (rent træ), returnerer den 0, og `pop` popper så en FREMMED
stash fra en tidligere session. Tjek `git stash list` FØR, eller brug
`git stash push -m "<navn>"` og pop kun hvis din egen entry blev oprettet.

**Commit ALTID selv — spørg ALDRIG "skal jeg committe?"** (per 2026-06-16,
user-spec). Skip `ha core check`; brug `python3 scripts/ha_offline.py check`
(HA's egen validator offline, ~13 s, kører også i pre-push). 2026.4-buggen var
`KeyError: 'triggers'` i check_config — rettet upstream i 2026.9.2.
**Efter hver deploy: `./scripts/ha_health.sh deploy`** — fanger
automations der er valideringsfejlet og dermed fuldstændig stumme (#22).

### 👁️ Monitoring — `./scripts/ha_health.sh`

Ét script dækker det ugentlige helbreds-tjek. Subkommandoer: `deploy` (fejlede
automations — kør efter HVER deploy), `flags`, `lights`, `noisy`, `zha`, `docs`,
`backup`, `sys`, `log [n]`, `blind`, `kamera`. Uden argument køres alle.

**Git-hooks er installeret** (`.git/hooks/pre-commit` + `pre-push`, kopier af
`scripts/*-hook.sh`). Bliver de væk (`ls .git/hooks/pre-*`) eller advarer
hooken "ruff mangler", kør **`bash scripts/dev_setup.sh`** (hooks + de pinnede
ruff/yamllint/gitleaks i `.cache/dev-venv`, som HA's backup springer over).
Pre-commit blokerer på `ruff check`/`ruff format --check` → kør
`.cache/dev-venv/bin/ruff format <fil>` før commit.

**`docs/auto/*` er GENERERET og bliver stale i tavshed** — rør ikke filerne i
hånden; kør `python3 scripts/gen_docs.py` og commit resultatet når du har
tilføjet entities.

### 🔥 ESPHome chip-wear — vær paranoid med writes til Apollo MSR-2 (per 2026-05-19)

Writes til Apollo MSR-2 er paranoide (2 af 5 fik chip-fejl af ~3600 unødvendige
config-writes): aldrig samme værdi igen, kun ved bruger-intent, value-compare før
`number.set_value`, engineering mode/BT aldrig ON i drift. **Fuld regel + canary:
`.claude/rules/presence_radar.md`** (loades når du rører Apollo-filerne).

### 🏡 ALT vi bygger skal spille med AirBnB-mode (per 2026-07-28, user-spec)

Gælder **hver eneste ændring**, ikke kun dem der "handler om AirBnB":

1. **`house_mode` har TRE options** — `Normal`, `AirBnB`, `Home Vacation`. En
   `state: "Normal"`-condition udelukker også Home Vacation = næsten altid
   utilsigtet. Familie-logik = `in ['Normal','Home Vacation']`; kun-gæst = `AirBnB`.
2. **Suppressorer/enforcere er farligst.** Spørg altid: *hvordan slipper en gæst
   ud af denne tilstand uden at kende systemet?* Der SKAL være en automatisk udgang.
3. **Nye flags:** skal de ryddes ved AirBnB-**entry** og **exit**? Se flag-clear-
   og lockdown-listerne i `automations/airbnb_mode.yaml` (+ mirrors i
   `automations/light_power_recovery.yaml`). Afslører flaget familie-mønstre →
   med i privacy-purge-globs (#16).
4. **AirBnB har sit eget nat-regime** (`packages/airbnb_natmode.yaml`) der
   sætter godnat-flagene DIREKTE, ikke via `script.godnat` → det rydder IKKE
   cinema/scene-flag.
5. **Påtving aldrig familie-rutiner på en gæst** — vælg den neutrale handling:
   SLIP en blokering frem for at tvinge en tilstand.

### 📊 Hold de kuraterede dashboards opdateret

De er hånd-kuraterede og **drifter derfor når koden ændres**. Opdatér i SAMME
sprint som ændringen:

- **Tekst på dashboards (per 2026-09-29, user-spec):** kun korte danske
  tile-navne, én linje scope og live-status — hvorfor/måledata hører i en
  YAML-kommentar. Fuld regel (Indstillinger-faner, søg, kontrolpaneler):
  `.claude/rules/dashboards.md`.
- **Nyt/droppet device** → `dashboards/status.yaml`, `dashboards/lights.yaml`,
  [docs/hardware_shopping.md](docs/hardware_shopping.md). Tjek med et grep på det
  nye entity-navn i begge dashboards — 0 hits = tilføj det.
- **Automation der tænder/slukker/farve-skifter en pære, eller kører et gardin**
  → `dashboards/triggers.yaml` (per 2026-07-03, user-spec). Husdækkende adfærd =
  topsektionen ÉN gang; rum-specifikt = det berørte rum-kort. Verificér med
  `python3 scripts/triggers_scan.py` (ON/farve via scripts eller templated
  entity_ids vises som DYNAMISK → kuratér manuelt, jf. #1).
- **Alt der kun gælder i AirBnB** (eller en AirBnB-gate i delt logik) →
  🏡 AirBnB-fanen i `dashboards/settings.yaml` (per 2026-07-08, user-spec), samme
  commit. `grep AirBnB` for at finde alle med-ejere. NB entity_id beholder den GAMLE slug ved
  alias-rename.

### Andre standing instructions

- **People count falder KUN efter hoveddøren** (user-spec 07-22, gentaget 10-01 og
  10-21: "again and again … stick to that guess until the main door opens").
  `sensor.people_estimate` viser ét HOLDT tal (`input_number.people_gulv`): op når
  buddet har holdt, ned kun i dør-vinduet, ved dørens tom-dom (Dormant ≤
  `people_afgang_dom_minutter` efter døren → 0, 22/10) eller ved brugerens egen
  rettelse. Ingen ny vej ned (geofence, Dormant UDEN dør foran, decay, familie-
  vækst) — for højt rettes ved KILDEN.
  Bevis: **`./scripts/ha_health.sh people`** (tjekker det viste tal, ikke delene).
- **Nye problemer** → [BACKLOG.md](BACKLOG.md) i rette kategori med næste ledige
  ID (`python3 scripts/backlog_ids.py --next`; genbruges aldrig). **Løste** →
  "Done" med dato, eller slet hvis trivielt.
- **Permanent, nyttigt faktum** (hardware-quirk, stabilt miljø-fakta, gentaget
  gotcha) → ÉN kort bullet i "Permanente fakta" + det lange i
  `docs/permanente_fakta.md`. Kriterie: ville en fremtidig session spilde tid
  uden at vide det? Task-specifikt hører i memory eller BACKLOG.
- **Lamper med ejerskabs-register** (`ejerskab/<lampe>.yaml`; i dag køkken-lyskæden):
  rangen ER koden → genereret `sensor.<lampe>_ejer`. Ny skriver/låner = registret +
  `python3 scripts/ejerskab.py gen` (pre-commit blokerer ellers). Ny lampe i ordningen =
  ny registerfil, valgt efter `ejerskab.py steder <entity>` — ikke pr. rum.
- **`replace_all` på numeriske patterns er farligt:** `transition: 60` matcher
  også prefixet af `transition: 600`. Brød HA boot 2026-04-29.
- **Hardware shopping list** vedligeholdes i
  [docs/hardware_shopping.md](docs/hardware_shopping.md).

---

## 🧠 Fejlklasser — tjek FØR du erklærer noget færdigt

Samme mønstre gik igen i tidligere sessioners arbejde: billige at undgå, dyre at
opdage. **Her står kun signatur → metode. Incident, måledata og fuld begrundelse:
[docs/fejlklasser.md](docs/fejlklasser.md)** — `grep -n "^20\." docs/fejlklasser.md`.

**Ejerskab, duplikering og påstande**

1. **"Single owner"-designs har skjulte med-ejere.** → `grep -rn "<entity>"
   automations/ packages/ script_pkg/ rosters/` (et rosters/-hit → grep
   `rosters/<navn>` for forbrugerne) før du påstår — eller bygger — at X er eneste
   styring. **Samme beviskrav til den NEGATIVE påstand** ("intet vogter X"):
   huset har flere watchdogs end man husker (B147).
2. **Samme regel kodet 2 steder divergerer.** → Grep reglens nøgle-udtryk
   (entity + operator) og opdatér alle forekomster, eller konsolidér til ét anker.
   **Samme fælde i TID: `mode: single` udelukker kun scriptet fra SIG SELV, så
   to scripts der rører samme lampe kører samtidig — og den der starter midt i
   den anden læser dens mellemtilstand som "normalen" og skriver den tilbage.
   Signatur: flere state-rækker på én entity inde i ét sekund, mens hver kilde
   ser velopdragen ud i sin egen fil.** → ÉN `queued`-kanal for handlingen.
3. **Kommentar-påstande ≠ kode.** En `time_pattern`-backstop RE-ASSERTER sin
   tilstand, så "manuel betjening vinder altid" er falsk uden en grace-/
   stempel-mekanisme. → **Manuel = `context.user_id is not none`, ALDRIG
   `parent_id is none`.** NB knap-tryk bærer heller ikke user_id → skal de tælle
   som manuelle, stemples de i handleren.
10. **Verificér fund før du "fixer"** — et unødvendigt fix er også en
    diff-risiko. → Læs den faktiske consumer-kode.
16. **Entity-rosters drifter ved device-tilføjelse** — samme liste er copy-pastet
    i mange filer, og diffen er én linje midt i en liste der ligner de andre. →
    Grep et roster-fingerprint-medlem og opdatér ALLE hits. **En liste der står
    flere steder, bor i `rosters/<navn>.yaml`** (`entity_id: !include
    ../rosters/<navn>.yaml`) — ret den dér; `roster_drift.py` viser resten. I Jinja: `{% from 'rosters.jinja' import <navn> %}`
    (genereret: `python3 scripts/rosters.py jinja`).
21. **Et kill-switch der ikke er en `condition` på hver eneste vej ind, er
    pynt** (backstop-tick, restart-recovery, manuelt script, søster-automation).
    → `grep -rn "<feature>_enabled"` holdt op mod `grep -rn "<handlingen>"`.
26. **En HUS-BRED gate på en RUM-SCOPET tilstand låser alle rum til noget de
    ikke har med at gøre. Signatur:** featuren virker kun delvist — og den
    virkende del er den UDEN gaten. → rum-scop gaten OG dens nabo-conditions (#12).
27. **En låners AFLEVERING skriver et snapshot fra før lånet — og den er det
    SIDSTE kald, så et udløbet snapshot vinder. Signatur:** et lys der SLUKKER
    (ikke fejlfarves) kort efter at en midlertidig ejer slap det → ingen flanke
    at rette på. → spørg huset igen ved afleveringen, gengiv ikke snapshottet.
    **Spejlbilledet er lige så slemt og rammer bredere: et lys der TÆNDER igen
    ~40 s efter at en automatik slukkede det — lånet slugte beslutningen, og
    låneren brændte samtidig ofrets cooldown.** Et blink/varsel der `scene.create`'r
    er derfor en med-ejer af HVER beslutning i sit vindue (#1).

**Triggers der aldrig fyrer — eller fyrer på det værst tænkelige tidspunkt**

4. **Flanke-triggers mangler re-arm.** → "Hvad re-fyrer hvis flanken sker MENS vi
   er blokeret?" **Værste variant: to automations deler ÉN flanke, og den ene
   SÆTTER den betingelse den anden LÆSER.** **Signatur:** "virker kun hvis jeg
   også gør Y", hvor Y er en ANDEN trigger-vej til samme handling. → Sætteren
   skal selv re-arme læseren (`automation.trigger` + `skip_condition: false`) —
   men kun hvis målet ikke læser `trigger.` (UndefinedError aborterer scriptet).
15. **Disable/enable-vinduer sluger events** — en automation slået FRA modtager
    INGEN triggers. → Et resume-flow SKAL selv re-evaluere den tilstand den
    gen-enablede logik vedligeholder.
19. **En blokeret automation fyrer i SAMME sekund blokeringen ophæves.**
    **Signatur:** en handling på samme klokkeslæt hver dag uden at nogen
    parameter varierer. → For hver langtids-gate: passer udgangs-tidspunktet til
    HANDLINGEN? Nej → handlingen skal have sin egen betingelse.
13. **Flanke-trigger + dedupe-stempel = ingen re-push under vedvarende episode.**
    → Dedupe på en flanke kræver en time_pattern-backstop, gatet til igangværende
    episode (stempel-alder < N).
12. **Beskyttelse tilføjes asymmetrisk på søster-automations.** → Giver du ét
    varsel dedupe/grace/gate, gennemgå søskende med samme fysik.

**Sensorer der lyver — eller måler noget andet end deres navn siger**

9. **`unavailable` er hverken on eller off** — is_state er stille-false under
   Thread/Zigbee-flap. → Gate enforce-logik på health-sensorer, ikke på skæv state.
14. **Analoge sensorers `last_changed` kan IKKE bevise "sustained"** — den
   nulstilles ved HVERT report. → "Over grænsen i 15 min" kræver en
   `for:`-trigger eller history_stats, aldrig et condition-template.
20. **En akkumulator over en LATCHENDE sensor måler tid siden vinduets start —
   ikke aktivitet.** **Signatur:** en gate der udløses med samme faste offset
   hver dag, og hvis klokkeslæt flytter sig når du ændrer tærsklen. → Kræv
   **friskhed**, ikke bare `on`.
23. **En restart-recovery må ikke bevise sin præmis med den kanal der var i
   stykker** — en sensor der booter hængende `on` har `last_changed` =
   boot-tidspunktet, ikke en observation. → Kræv en ANDEN kanal, re-tjek
   gatesne EFTER ventetiden, og begræns handlingen til det rum beviset kom fra.
24. **En template-attribut med `now()` skriver en DB-række hvert minut — for
   evigt.** **Signatur:** en entity i toppen af `ha_health.sh noisy` hvor næsten
   alle rækker er attribut-ændringer. → Gate attributten på den tilstand hvor
   den er meningsfuld og kvantisér mod den tærskel den sammenlignes med.
25. **"X har været `off` i N minutter" på en radar-afledt binær er uopfyldelig —
   ét 1-sekunds blip sletter hele den opsparede tid.** **Signatur:** en gate der
   ALDRIG fyrer, hvor hver betingelse ser rimelig ud, og hvor et replay af
   *historiske* hændelser ser sundt ud. → Mål stilhed på et anker der kun
   flyttes af en flanke der HOLDER (`sensor.last_sustained_presence`).
   Spejlbillede af #14.
28. **Et high-water-mark på et flimrende signal gemmer flimmerets TOP, og en
   bonus betinget af en radars øjebliks-state arver dens flimmer. Signatur:**
   et tal der springer i takt med én radar og hænger på den høje værdi i
   præcis decay-tiden. → latch kun hvad der har HOLDT (`for:` + samme krav på
   alle re-arm-veje), gulv kun på det ingen stabil kilde beviser (people v4).

**Tid, test og spor**

18. **history/logbook-API'et svarer i UTC** — vi er UTC+2, så **læg 2 timer til**
   i din parser, ikke i hovedet.
8. **Midnats-vinduer:** `today_at()` efter kl. 00 peger på NÆSTE vindue → shift
   86400 bagud når "i nat" skal betyde den igangværende nat.
5. **"Live sat via API"-skridt bliver glemt.** → Ny slider = **4** skridt SAMME
   session: **API-set + settings-tile + snapshot-export + verificér liveværdien
   til sidst**. **API-set seeder HUSET; snapshot-exporten seeder en FRISK
   install** (exporten afleder `config_snapshots/fresh_install/`, som init læser
   siden P1 2026-10-04 — en slider der mangler i snapshottet står på min efter
   en geninstallation; runtime-tællere hører i `RUNTIME_NUMBERS`).
   **Signatur: en slider står på sin init-default med tom `context_user_id_bin`,
   ~30 s efter en restart.**
6. **"Live-testet" med syntetiske events beviser intet** — den fysiske knap kan
   sende en gammel quirk-form. → Test med ÆGTE device-events, eller find bevis i
   history på at den rigtige event-form er set.
11. **API-tests efterlader spor der ligner user-handlinger** — et API-turn_off
    bærer user_id → manual-off-trackere stempler det som brugerens sluk. → Ryd de
    stempler testen kan have sat, og tjek at room_mode/last_press ikke flippede.
    **Værste variant: sporet er ikke dit ene kald, men en SCENE** — et
    `scene.turn_on` udsender interne `light.turn_on` med scenens context inkl.
    user_id, så en snapshot-RESTORE ligner N app-justeringer på én gang.
    Restore-scener er allowlistet i `automations/manual_override.yaml`.
7. **Tæl trigger-fires × API-kald før deploy** (fires/dag = 1440/interval ×
   antal duplikat-triggers). → Foretræk state-change-triggers + /1t-backstop.
22. **En automation i `unavailable` er ikke støj — den er VALIDERINGSFEJLET og
    fuldstændig stum.** HA disabler HELE automationen ved den mindste
    template-fejl i dens `action:`, uden advarsel ved commit, deploy eller
    reload. → `./scripts/ha_health.sh deploy` efter enhver deploy. (Ægte fejl =
    `restored` mangler; `restored: true` = harmløs registry-orphan, huset har ~74.)

**Jinja-gotchas** (`variables:` der bliver en truthy streng, udefinerede
script-felter, `trigger.` via `automation.trigger`, StrEnum, TupleWrapper,
`repeat.index0` …) står i `.claude/rules/ha_yaml.md`; den fulde liste med
eksempler: `grep -n "Jinja-gotchas" docs/fejlklasser.md`.
