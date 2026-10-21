# Konsoliderings-indsatsen (startet 2026-10-04, B188)

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Mål:** færre gentagne fejl og billigere sessioner, ved at gøre de løsninger der
oftest går i stykker til *værktøj* i stedet for *huskeregler* — og ved at kunne
konsolidere sandslottet uden at lave nye bugs.

**Kernen er tre beviser, som alle kører UDEN NUC'en** (`scripts/ha_offline.py`,
HA's egen kode i et venv):

| Spørgsmål | Kommando | Tid | Hvad den beviser |
|---|---|---|---|
| Er det **gyldigt**? | `ha_offline.py check` | ~13 s | HA's check_config: ingen stum automation (#22), ingen død template-blok |
| Er det **uændret**? | `ha_offline.py equiv HEAD` | ~4 s | Den resolvede config (efter `!include` + packages) er identisk → adfærds-neutralt |
| **Opfører** det sig? | `ha_offline.py staging` | ~1 min | Huset booter headless som FRISK install: aborts, manglende services, faldne templates |
| Findes det jeg **refererer**? | `ha_offline.py refs` | ~20 s | unique_id-form-refs, ø→o-slugs, udefinerede helpers |

Et refactor er enten **strukturelt** (equiv SKAL være tom) eller **adfærd** (equiv
lister præcis de tilsigtede ændringer, og staging før/efter sammenlignes entity for
entity). Der er ingen tredje kategori.

---

## 1. Evidensen — hvad commit-historikken siger

Målt 2026-10-04 på 1.984 commits (2026-03-28 → 2026-10-04), 489 af dem fix-agtige.

**Fejlklasse-citater i commit-beskeder:** #2 (samme regel to steder) **111** ·
#4 (flanke uden re-arm) 51 · #3 (kommentar ≠ kode) 44 · #12 (asymmetrisk
beskyttelse) 41 · #5 (slider-ceremonien) 40 · #16 (roster-drift) 33 · #1 28 · #9 27.
Duplikering (#2/#12/#16) er altså den dominerende fejlform, ikke enkeltfejl.

**Mest rettede filer:** `helper_values.yaml` 393 · `init_user_preferences.yaml` 390 ·
`dashboards/settings.yaml` 389 · `dashboards/triggers.yaml` 229. **De fire øverste er
alle slider-/dashboard-ceremonien.** Blandt fix-commits: init 65, settings 57,
presence_lights 44, godmorgen_godnat 43, entre_motion 38.

**Konkrete målinger der drev prioriteringen:**

- **Slider-ceremonien:** 656 input_numbers uden `initial:`. `init_user_preferences.yaml`
  havde 321 håndskrevne seed-blokke (6.230 linjer, fem nøglenavne for samme felt).
  Staging (= frisk install) viste: **283 af 644 sliders fik en forældet fabriks-default,
  32 fik ingen værdi** — og init *aborterede* faktisk ved step 55 siden 30/7 pga.
  `input_datetime.set_value` (findes ikke). Ingen havde opdaget det, fordi det kun
  rammer en frisk install.
- **Rosters:** 305 entity-lister ≥ 3. **25 står ordret i flere filer (152 kopier)**;
  92 par er nær-dubletter (Jaccard ≥ 0,6). Største: godnat-flag-sættet 20×,
  stue-lysene 14×, open-plan-gardinerne 13×, occupancy-8 13×, bad-spots 10×.
- **Slug:** 43 commits nævner slug. Tre scripts havde hver sin slugify og var
  uenige (b103_scan: å→"aa"). `ha_validate.py` registrerede `sensor.<unique_id>` som
  defineret — det **skjulte** netop slug-klassen (86a51787, d1420cc4, 2cfed6f6, 7bf32af0).
- **#22 / template-blok:** HA's egen validator ville have fanget **5 af 7** replayede
  hændelser før commit (06309115, d323d188, b616b01a, 23c9249a, d7c39571). De to
  den ikke fanger: en foldet `{% if %}` → strengen "false" (semantik) og
  `hassio.addon_update` (domænet findes kun i prod).
- **Hooks følger ikke med en clone.** Denne cloud-checkout havde ingen; 590 commits
  er lavet uden for NUC'en (PC/cloud) — om de havde hooks kan ikke afgøres bagud.
- **`ha core check` blev droppet som "buggy i 2026.4.0":** årsagen er en upstream-bug
  (check_config satte aldrig trigger-helperen op → `KeyError: 'triggers'`), rettet i
  2026.9.2. `ha_offline.py` shimmer den for ældre versioner.

---

## 2. Leveret (branch `ccr-a9defbaf-p8ulxr`, tre commits)

**F0 — sikkerhedsnettet (21709ab7, kun værktøj + én bug-fix):**

| Fil | Hvad |
|---|---|
| `scripts/ha_offline.py` | check / equiv / staging / refs / slugcheck (se tabellen øverst) |
| `scripts/ha_offline_version.txt` | HA-versionen der valideres mod — **skal = prod** |
| `scripts/ha_slug.py` | ÉN slugify; = HA's over 4.767 navne (`ha_offline.py slugcheck`) |
| `scripts/roster_drift.py` (+ `_allow.txt`) | rapport + `--staged` JIT: "13 tvillinger har stadig den gamle liste" |
| `scripts/session_start.sh` + `.claude/settings.json` | SessionStart: synk git-hooks, bagud-tjek, cloud-venv i baggrunden |
| `scripts/pre-push-hook.sh` | kører `ha_offline.py check`, blokerer på FEJL (kun hvis venv findes) |
| `scripts/pre-commit-hook.sh` | `roster_drift.py --staged` (advarsel) |
| `scripts/ha_validate.py` | template-entities via `default_entity_id`/`slugify(name)`, ikke unique_id |
| `scripts/b103_scan.py`, `ejerskab.py` | bruger `ha_slug` (output byte-identisk) |
| `automations/init_user_preferences.yaml` | `input_datetime.set_value` → `set_datetime` (frisk install aborterede) |

**P1 — pilot-konsolidering (15314261):** init gendanner input_numbers fra
snapshottet (ét loop) i stedet for 321 blokke. 6.230 → ~1.350 linjer. Gate-seeds er
væk, så Apollo-NVRAM-pushet skubber de TUNEDE gates. Live-huset er uberørt
(`prefs_code_version` = 20 → kører kun på en ægte frisk install). Ceremonien for en
ny slider er nu **4 skridt** (CLAUDE.md #5 rettet).

**P1-hærdning (efter adversarial review, se §6):** init `!include`'r IKKE længere
det rå snapshot, men en AFLEDT fil, `config_snapshots/fresh_install/input_number.yaml`
(kun tal, skrevet atomisk af `helpers_export.py`, gen-afled med `--derive`), via
`!include_dir_named` — en manglende mappe giver `{}` i stedet for recovery mode
(målt), og `.gitattributes merge=binary` gør at en merge/stash-pop aldrig skriver
konflikt-markører ind i den (målt). Pre-commit (`--check-derived`) kræver at den
passer til `helper_values.yaml`. Syv runtime-tællere er holdt ude af snapshottet
(`helpers_export.RUNTIME_NUMBERS`), exporten beholder forrige værdi for en defineret
helper der er unavailable under eksporten, strenge quotes som JSON (backslash-sikkert),
og restore bruger samme parser. Staging (frisk install): **637/637 sliders = snapshot**
(før P1: 329/644 + 32 på min), runtime-tællerne på 0 som i den gamle init, eneste
andre forskelle er to GPS-tidsstempler (opstartstid).

**Dokumentation (denne commit):** dette dokument, B188, CLAUDE.md-pegepinde.

---

## 3. Til den lokale session — verificér og implementér

Rækkefølgen er vigtig: intet af dette kræver en restart før punkt 7.

1. **Hent branchen** og læs dette afsnit: `git fetch origin && git checkout ccr-a9defbaf-p8ulxr`.
2. **HA-versionen = prod?**
   `curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/config | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])'`
   Afviger den fra `scripts/ha_offline_version.txt` (2026.9.2, sidst kendt fra git), så
   ret filen. Hele værktøjskassen validerer mod den version.
3. **Byg venv'et** — helst på PC'en: `pip install --user -U uv` og så
   `python3 scripts/ha_offline.py check`. På NUC'ens SSH-add-on: ukendt om
   Python ≥ 3.14.2 kan hentes (musl); prøv, og dokumentér resultatet her. Venv'et er
   ~1,1 GB; `.cache/*` er udelukket fra HA's backups (core 2026.9.2), ellers
   `HA_OFFLINE_CACHE=/sti`.
   **Målt 2026-10-04: native Windows virker IKKE** — HA's `runner.py` importerer
   `fcntl`. PC'en kører det i Docker Desktop (Linux-engine):
   `docker run -d --name haoffline -v "<repo>:/repo:ro" -v haoffline-cache:/cache -e HA_OFFLINE_CACHE=/cache python:3.14-slim sleep infinity`,
   så `apt-get install -y git build-essential && pip install uv` og `git clone /repo /work`
   i containeren. **`build-essential` er nødvendig:** uden C++-compiler kan
   `pymicro-vad`/`pyspeex-noise` ikke bygges → `assist_pipeline`/`mobile_app` falder
   (5 falske advarsler i `check`, manglende services i staging).
4. **Kør de fire:** `check` (forventet: 0 fejl, 2 mqtt-begrænsninger) · `staging`
   (0 fejl, 4 kendte begrænsninger) · `refs` · `equiv origin/main`
   (forventet: kun init_user_preferences_first_boot). Afvigelser → undersøg FØR merge.
5. **Prod-entity-listen** (gør `refs` fuldt afgørende og fanger device-refs):
   ```bash
   curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/states \
     | python3 -c 'import json,sys; print("\n".join(sorted(s["entity_id"] for s in json.load(sys.stdin))))' \
     > config_snapshots/entity_ids.txt
   ```
   Kør `refs` igen. De 16 ❓ (`binary_sensor.scene_*_active` ×14,
   `binary_sensor.sove_radar_frossen`, `light.boernevaerelse_all`) forventes at blive
   ⚠️ "registry-låst" = virker i prod, brækker ved frisk install → P3. Bliver nogen ❌,
   er det en ægte bug i dag. Commit listen (den er ikke hemmelig; refresh ved nye devices).
6. **Gennemgå P1 + hærdningen** (§6 har review-resultaterne): (a) gentag staging-
   målingen (§2-tallene); (b) kør `python3 scripts/helpers_export.py` én gang på
   NUC'en — den skriver nu OGSÅ `config_snapshots/fresh_install/input_number.yaml`
   og skal give en tom/lille diff mod det committede; (c) beslut merge.
7. **Merge + deploy** som normalt (commit_workflow.md): `git merge` til main, pull på
   NUC'en, `bash scripts/ha_restart.sh`, **`./scripts/ha_health.sh deploy`**. Tjek bagefter:
   init-automationen (id `init_user_preferences_first_boot`; i staging hed den
   `automation.init_user_preferences_default_values_first_boot_only`) er `on` (ikke
   `unavailable`), `input_number.user_prefs_version` er stadig 20, og ingen slider har
   en ny `last_changed` med tom `context_user_id_bin` ~30 s efter restarten.
8. **Hooks på NUC'en** synkes af SessionStart-hooken næste gang en session starter
   (eller `cp scripts/pre-*-hook.sh .git/hooks/` manuelt).
9. **Notificér** (📲 — tjek `house_mode` for AirBnB først).

**Resultat, lokal session 2026-10-04 (Docker, core 2026.9.2 = prod).** Målt to gange:
på `43bbc8f` og igen på `e2c26ad` (P1-hærdningen, §6) — tallene her er de sidste.
`check` 0 fejl / 0 advarsler / 2 mqtt · `staging` 0 fejl / 4 begrænsninger / 3
runtime-advarsler; init kører igennem (`user_prefs_version` 20, initialized `on`) ·
`equiv origin/main` (6b81ade) 325 kode-forskelle, ALLE i `init_user_preferences_first_boot`
(+ 637 fresh-install-værdier, rapporteret for sig; F0 alene: 1 = `set_datetime`; P1 alene:
323) · sliders før P1 329/283/32 (= §2), **efter 637/637 = fresh-filen**, runtime-tællere 0.
(På `43bbc8f` var det 643/644: `roborock_aktiv_minutter_akkumuleret` 709 → 724 = ét
`roborock_aktiv_timer_tick` efter gendannelsen — den er nu ude af snapshottet.) ·
`refs` uden prod-liste: 16 ❓; med `config_snapshots/entity_ids.txt` (4.093 entities):
16 ⚠️ registry-låst + **5 ❌ der alle er scanner-falske-positiver**:
`trigger.event.data`/`.context` matcher `event.`-domænet; `automation.trigger` i en
`{# #}`-kommentar; `sun.elevation` i en `description:`; `scene.entre_somrig_undo_snapshot`
oprettes med `scene.create` → refs skal lære dem, før den kan være en gate (P9). En 6.
(`input_number.yaml` = filnavnet i init's logbook-tekst fra §6) blokerede også
pre-pushens `ha_validate --live` → teksten siger nu "mappen config_snapshots/fresh_install".
**Deployet 2026-10-04 20:41** (merge `a1c77a4`, save_persistent_states → restart): `ha_health.sh deploy` 0 fejl; `init_user_preferences_first_boot` = `on`, kørte ikke (sidst 1/10), `user_prefs_version` 20, 0 input_numbers ændret efter boot (målt +93 s). Hooks på NUC'en synkes af SessionStart.
Ét `refs`-løb hang 10+ min (genkørsel 43 s; årsag ikke bevist) → `block_till_done`
har nu et 60 s-loft der logger de kørende tasks.

Bliver noget i 4-7 rødt: ret det på branchen eller revert den enkelte commit —
F0 og P1 er uafhængige (P1 kan revertes alene).

---

## 4. Næste konsolideringer (prioriteret efter citater × risiko)

Hver linje angiver beviset der kræves. **Strukturel** = `equiv` skal være tom.

| # | Hvad | Type | Bevis | Gevinst |
|---|---|---|---|---|
| P2 | **De 25 identiske rosters** → `rosters/<navn>.yaml` + `entity_id: !include ../rosters/<navn>.yaml`. **Batch 1 udført 2026-10-04, batch 2 2026-10-05** (se nedenfor): 10 rosters, 66 kopier. **Jinja-kopierne udført 2026-10-10** (52 steder, 27 filer → `custom_templates/rosters.jinja`, se nedenfor). Tilbage: open-plan-lys (overlapper `stue_sofa_lys` — kræver sammensætning) og køkken-gruppen (indeholder `koekken_lyskaede`, ejerskabsregister). Jinja-lister (`{% set x = [...] %}`) kan ikke `!include`'s — dér: `{% from 'rosters.jinja' import x %}`. | Strukturel | `equiv` tom | #16/#2: én rettelse i stedet for 20 |
| P3 | **Pin entity_ids** med `default_entity_id:` på template-entities hvis ref ≠ name-slug (de 16 fra punkt 5). Overvej husregel: ALLE nye template-entities får `default_entity_id` — så findes slug-afledning ikke. Light-grupper har ikke feltet → ret `name:` så sluggen matcher. | Prod: no-op (registry vinder); frisk install: rettelse | `refs` → 0 ❓/⚠️ | Slug-klassen lukket ved roden |
| P4 | **De 92 nær-dubletter:** hvert par er enten bevidst (→ `roster_drift_allow.txt` med grund) eller drift (→ fix). Fx `light_groups.yaml:163` vs `:190` og `fest_ankomst.yaml:120` vs `:346` (begge mangler kun `light.terrasse_paerelyskaede` i den ene). | Adfærd | equiv-diff = kun de rettede lister + bruger-afklaring | Her gemmer de ægte bugs sig |
| P5 | **AirBnB flag-clear/lockdown-listerne** (airbnb_mode.yaml + spejlet i light_power_recovery.yaml) → én roster-fil | Strukturel | `equiv` tom | CLAUDE.md-regel 🏡3 bliver mekanisk |
| P6 | **Slider-dækning som lint:** ny input_number uden tile (18 i dag) eller uden snapshot-post (13 i dag, flere runtime med vilje) → pre-commit-advarsel | Værktøj | — | #5 håndhæves |
| P7 | **CI:** GitHub Action der kører `ha_offline.py check` + `roster_drift.py` på hver push — virker selv når hooks er sprunget over | Værktøj | grøn på main | Uafhængigt af hvor der committes |
| P8 | **Smoke-tests mod staging i stedet for prod:** `ha_smoketest.py`-scenarier i staging efterlader ingen spor (#11) | Værktøj | — | Test uden at røre huset |
| P9 | Rester: `b103_scan.py` melder 1 sårbar trigger på main (`sove_voksen_afgang_sweep`, `to: 'on'` uden `from:`) — vurdér eller allowlist; kommentarer i packages om "Default X sættes af init_user_preferences" er forældede efter P1 (kosmetisk) | — | — | — |

**P2 batch 1 (2026-10-04, lokal session).** `rosters/godnat_flag.yaml` (20 kopier: hver
`input_boolean.turn_off` der afslutter natten) og `rosters/stue_sofa_lys.yaml` (13 kopier: scener +
stue-presence; den 14. er en Jinja-liste i `styrbar_rooms.yaml`). Bevis: `equiv` = 34 linjer, ALLE
positionsbytninger i 9 godnat-targets — maskinelt bevist som rene permutationer af samme 5 flag
(rækkefølgen på et `turn_off`-target er ligegyldig); alt andet byte-identisk. check 0 fejl, staging
0 fejl, refs 0 fejl. **Værktøjerne lærte rosters** (`scripts/rosters.py`): `triggers_scan`/`ejerskab`
så før sti-strengen i stedet for lamperne, `gen_docs` mistede forbrugerne, `refs`/`roster_drift` scannede
ikke mappen — bevist uændret output mod forrige commit. **Deploy:** kun pull på NUC'en (natten:
ingen `automation.reload`, der dræber igangværende runs); da den resolvede config er den samme mængde,
loader næste reload/restart det. **Live 2026-10-05 06:36** (restart på user-ønske): `ha_health.sh deploy` 0 fejl/0 template-fejl, alle 22 automations og 11 scripts med en roster-`!include` er loadet (21 `on`; `wakeup_adults_weekday` `off` som før restarten), init kørte ikke, 0 sliders skrevet efter boot.
**Huskeregel:** et "single owner"-grep skal nu også dække `rosters/` (CLAUDE.md #1/#16).

**P2 Jinja-kopierne (2026-10-10).** En liste INDE i en template kan ikke `!include`'es, men HA's
`custom_templates/*.jinja` kan importeres: `scripts/rosters.py jinja` genererer
`custom_templates/rosters.jinja` (én `{% set <navn> = [...] %}` pr. roster; pre-commit 0d afviser en
stale fil), og templaten skriver `{% from 'rosters.jinja' import <navn> %}` lige før det tag der brugte
listen. 52 steder i 27 filer, 3 nye rosters (`open_plan_gardiner`, `bad_occupancy`, `bad_kajplats`).
Kun lister i SAMME rækkefølge som rosteren — plus 4 håndlæste steder der kun tæller. Bevis: (1) YAML-
træerne gammel/ny er ens med teksten UDEN for tags byte-identisk (en flerlinjet liste i en `>`-blok
bevarer sidste linjes indrykning, ellers ændrer foldningen output-whitespace); (2) hver roster-variabel
`== ` sin liste live; (3) alle 50 ændrede strenge renderet gammel vs. ny via `/api/template`: 45 ens,
5 fejler ens (udefineret `trigger`). `ha_offline.py` kender IKKE custom_templates — en forkert import
fanges kun live. `rosters.text_refs` læser importen, så `hq.py where` og docs/auto ser entities.

**P2 batch 2 (2026-10-05).** 8 rosters, 33 kopier i 19 filer: `bad_spots` (8), `alle_gardiner` (4),
`boern_morgenlys` (3), `alle_rum_mode` (5), `apollo_occupancy` (3), `sove_lys` (4), `boern_morgen_flag` (3),
`styrbar_sidste_tryk` (3). Omskriveren vælger nu grupper efter roster-filens indhold og flytter kommentarer
der stod mellem nøgle og liste/inde i listen op over nøglen (begrundelsen om `spisestue_pendel` = sove-loftet
står lige over sin `!include`); hardware-noter pr. entity flytter ind i rosteren. Bevis mod 15aa1b6: `equiv` = 21
linjer, alle `~` i 5 lister, maskinelt bevist som rene permutationer (trigger-liste, tre service-targets og en
liste AirBnB-sweepen kun bruger som mængde); check/staging/refs 0 fejl; `group.alle_gardiner` har samme 4
medlemmer i staging før/efter. Værktøjer uændrede (triggers_scan identisk, gen_docs 2523 = 2523, `ejerskab
steder` identisk for bad/sove/børne-lys + koekken_lyskaede).

**Bevidst IKKE foreslået:** at generere `dashboards/settings.yaml` (håndkurateret efter
user-spec 📊) eller at slå automations sammen på tværs af rum (#26: rum-specifikke
diskriminatorer kan ikke kopieres). Konsolidering må aldrig flytte en beslutning
væk fra det rum den gælder.

---

## 5. Begrænsninger at kende

- **staging har ingen devices og ingen config entries** (ZHA, Matter, MQTT, Roborock,
  Nordpool …). Det fanger strukturelle fejl og helper-/template-logik, ikke fysik.
  mqtt-triggers og `mqtt.publish`/`nordpool.*` vises som ℹ️ begrænsninger.
- **Runtime-advarsler i staging** (fx `'None' has no attribute 'last_changed'`) er
  ofte en device der mangler — men en template der vælter på
  `states.x.y.last_changed` ved opstart gør det også i prod, hvis x.y oprettes efter.
- **`refs` uden `config_snapshots/entity_ids.txt`** kan ikke afgøre device-refs og
  unique_id-form-refs til registry-låste entities (vises som ❓).
- **equiv** sorterer lister hvor rækkefølgen er ligegyldig for HA (automations,
  template-blokke, platform-lister); action-sekvenser sammenlignes MED rækkefølge.
- HA-venv'et skal matche prod-versionen; et `--version <ny>` før en core-opdatering
  er en gratis generalprøve (legacy-template-lintet ville have fanget d7c39571).

---

## 6. Adversarial review af P1 (2026-10-04, 9 agenter + fuld staging før/efter)

Spørgsmålet fra den lokale session: *"hvilke sliders havde en seed-blok i den gamle
init, men står IKKE i snapshottet (de mister nu deres fresh-install-default)?"*

- **Svar: ingen.** Gammel init seedede 604 input_numbers; eneste uden for snapshottet
  er `user_prefs_version` (bevidst udeladt init-markør, sættes stadig). Bevist tre
  veje: min statiske parser, en uafhængig refuter (token-scan + egen walker + jinja-
  evaluering af hver gammel condition) og fuld staging af gammel mod ny init — de 28
  input_numbers uden for snapshottet er identiske før og efter.
- **Syv sliders står på min i snapshottet**, mens den gamle default var en anden
  (`badevaerelse_airbnb_off_forsigtighed` 0/50, `badevaerelse_brusebad_fald_point` 3/12,
  `cost_markup_kr_kwh` 0/0,10, `gestus_hold_frames` 2/3, `koekken_lav_krop_min_sekunder`
  2/4, `koekken_session_aktiv_minutter` 1/3, `mosbillede_solnedgang_fri_grader` 0/5).
  Git-forensik pr. slider: **alle syv er bevidste brugervalg** (flyttet ned fra ikke-min,
  ofte i batches hvor søster-sliders landede på håndvalgte værdier). Ny init gengiver
  prod; den gamle overskrev brugeren (dokumenteret to gange for session_aktiv_minutter).
  Én af dem er en beslutning værd: airbnb-forsigtighed 0 = gæster får familiens hurtige
  sluk-veje → **B189**.
- **Fund P1 selv indførte — alle rettet i hærdningen:** (1) HA loadede det rå snapshot
  → backslash/Jinja/konflikt-markør = recovery mode for HELE huset; (2) runtime-tællere
  (robot-akkumulatoren 709 → robotten ville køre før tid; sengetælleren) blev gendannet;
  (3) exporten droppede tavst en defineret slider der var unavailable under eksporten;
  (4) `| float` på en ikke-numerisk værdi kaster TemplateError, som `continue_on_error`
  ikke fanger; (5) b103_scan sprang init (og `configuration.yaml`) tavst over; (6) hver
  eksport lignede en adfærds-ændring i `equiv` (nu særskilt, `--strict` tæller den med);
  (7) `refs` overskrev en fuld staging-kørsels output.

**Anden runde — review af selve hærdningen (12 agenter, hvert medium-fund
reproduceret af en uafhængig verifikator), alle rettet:** (1) `--check-derived`
læste arbejdstræet, så et commit med KUN `helper_values.yaml` staged (den gamle
doc-regel) sendte et par der ikke passer til git → pre-commit tjekker nu det
STAGEDE (`--staged`), pre-push tjekker HEAD (`--rev HEAD`, for rebase/cherry-pick
kører ikke pre-commit), og docs siger "commit `config_snapshots/`"; (2) `--derive`
filtrerede ikke på `is_config`, så et merget gammelt snapshot kunne føre runtime-
tællere tilbage; (3) `equiv` gemte snapshottets FORM sammen med dataene, så en
stavefejl i include-stien (= 0 gendannede sliders) bestod som "ækvivalent" og
`check` sagde 0 fejl → nu er kun slider-værdierne data, og `check` fejler hvis
fresh-install-snapshottet giver 0 sliders; (4) eksporten crashede på et
konfliktramt snapshot (netop når en frisk eksport er løsningen) og slog
carry-forward tavst fra uden PyYAML; (5) `helpers_restore.py` gendannede kun
`*_enabled`-booleans — 162 af 283 snapshottede booleans blev aldrig gendannet
(gammelt hul, lukket med samme `is_config`-autoritet). Negative tests (T1-T6:
stavefejl i sti, forkert include-type, delvist staget commit, runtime via
--derive, inkonsistent HEAD, konflikt i snapshot) fanges alle.

**P9 delvist lukket samme omgang:** de 5 `refs`-falske-positiver den lokale
verifikation fandt (`trigger.event.data`, en ref i `{# #}`, `sun.elevation` i en
`description:`, en `scene.create`-scene) er væk — kun `description`/`alias` (som HA
aldrig renderer) og Jinja-kommentarer springes over; `message:`/`title:` scannes
stadig, for de er templates der LÆSER entities. Diff mod den gamle scanner: kun
prosa-forekomster forsvandt. Resultat med prod-listen: **0 ❌, 16 ⚠️** — og et replay
af 86a51787^ fanger stadig præcis de 2 slug-fejl. `refs` kan dermed blive en gate
(fx i pre-push efter `check`; koster ~40 s).
