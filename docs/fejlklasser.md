# Fejlklasser — de fejlmønstre der gentager sig i dette repo

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Auto-loades IKKE.** CLAUDE.md bærer den korte liste (signatur + metode for
hver klasse) — det er den du tjekker rutinemæssigt. Denne fil er den lange
version: det konkrete incident bag hver regel, måledata og fuld begrundelse.

**Læs den når:** du genkender en signatur i CLAUDE.md's liste og vil vide
præcis hvordan fejlen så ud, eller du er i tvivl om en kant-situation hører
under klassen. `grep -n "#20" docs/fejlklasser.md` frem for at Read'e alt.

Uge-reviewet 2026-07-02 fandt de samme fejlmønstre igen og igen i tidligere
sessioners arbejde. Tjek disse aktivt — de er billige at undgå, dyre at opdage:

1. **"Single owner"-designs har skjulte med-ejere.** morning_curtains var
   "eneste åbner" af open-plan-gardiner — men godnat_auto_clear åbnede dem
   også (bug ramte user i praksis). Metode: før du påstår at X er eneste
   styring af en entity, `grep -rn "entity_navnet" automations/ packages/`
   og gennemgå ALLE hits. Gælder også når du SKABER et single-owner-design.

   **Samme beviskrav gælder den NEGATIVE påstand — "intet vogter X", "ingen
   opdagede det", "der findes ingen watchdog for dette".** Huset har flere
   watchdogs end man husker, og de er spredt over `packages/` under navne der
   ikke nævner symptomet. En negativ påstand er en påstand om at et grep over
   HELE repoet er tomt; har du ikke kørt det grep, ved du det ikke.

   **Incident 2026-09-16 (B147):** noten om fem batteri-SED'er der gik
   `unavailable` blev oprindelig skrevet med sætningen **"intet opdagede
   det"** — om et udfald `packages/batteri_watchdog.yaml` havde varslet
   **præcist** om: pushes 17:25 / 17:30 / 17:35 / 17:45, altså nøjagtigt dens
   60-minutters-tærskel efter hvert enkelt drop. Og `binary_sensor.thread_net_i_live`
   stod korrekt `on`, fordi dens vidner (`parasoll_hoveddoer` + de to
   bad-occupancy, med `light.entre_loft` som veto) aldrig faldt — det var et
   DELVIST udfald, ikke et net-udfald. Systemet gjorde det rigtige; rapporten
   påstod det modsatte.

   **Hvorfor fejlen opstod:** samme note daterede også nedfaldet til 14:20 i
   stedet for 16:20. Begge fejl var **fejlklasse #18** — `/api/states` svarer i
   **UTC**, `sqlite3 … 'localtime'` svarer lokalt, og de to blev sammenlignet
   direkte. Med et 2-timers skæv så watchdog'ens punktlige varsel ud til at være
   "3 timer for sent", hvilket blev læst som "den fangede det ikke". **En negativ
   påstand om overvågning er ekstra skrøbelig, fordi den kan fabrikeres af en
   ren tidszone-fejl.**

   **Metode:** før du skriver "intet opdagede X", kør
   `grep -rln "watchdog\|overvaag\|varsel" packages/ automations/` og tjek de
   kandidater der rører den ramte kanal — og normalisér ALLE tidsstempler til
   samme zone før du konkluderer at et varsel kom for sent eller slet ikke kom.
   Rettelsen står i B147-noten selv (`grep -n "B147" BACKLOG.md`).
2. **Samme regel kodet 2 steder divergerer.** Bad-natlys-definitionen blev
   ændret 2026-06-26 i presence-filen men IKKE i faser-pakken (stale sol-gate).
   Metode: når du ændrer en regel/betingelse, grep efter dens nøgle-udtryk
   (entity + operator) og opdatér alle forekomster — eller konsolidér til ét anker.
3. **Kommentar-påstande ≠ kode.** "Manuel åbning vinder altid" var falsk —
   en /15-backstop re-lukkede. Metode: en `time_pattern`-backstop RE-ASSERTER
   sin tilstand; enhver "manuel vinder"-påstand kræver en grace-/stempel-
   mekanisme (stamp + sammenlign timestamps).
   **Manuel = `context.user_id is not none` — ALDRIG `parent_id is none`**
   (korrigeret 2026-08-20; den gamle formulering stod her og var forkert).
   `parent_id` sættes kun når automationen selv blev trigget af en anden
   context, så en tids-/numeric_state-trigget automation ser præcis ud som en
   bruger. Kostede gardinerne 2026-07-30 og køkken-lyskæden 2026-08-20. NB
   knap-tryk (Styrbar/`zha_event`) bærer heller ikke user_id → skal de tælle som
   manuelle, stemples de i handleren.
4. **Flanke-triggers mangler re-arm.** Watchdog så aldrig strøm-tilbage-stien;
   quiet-window slugte nat-peaks uden morgen-recheck. Metode: for hver
   edge-trigger, spørg "hvad re-fyrer hvis flanken sker MENS vi er blokeret?"
   → tilføj recheck-trigger ved blokeringens udgang eller en langsom backstop.
   **Variant (2026-09-02b, AirBnB): to automations deler ÉN flanke, og den ene
   SÆTTER den betingelse den anden LÆSER.** Gæstens første bevægelse trigger
   både `house_airbnb_to_active` (som sætter `house_state` = Active) og rummets
   `presence_light_*_on` (som har `house_state == Active` som condition).
   Condition-evalueringen sker FØR `select_option` lander, så læseren taber
   **hver gang** — det er ikke et race. Og fordi trigger-sensoren
   (`*_occupancy_filtered`) LATCHER, kommer der aldrig en anden chance: gæsten
   står i mørke til rummet tømmes og betrædes igen. **Signatur:** "det virker
   kun hvis jeg også gør Y", hvor Y er en ANDEN trigger-vej til samme handling
   (her: at åbne hoveddøren). Metode: sætteren re-armer selv læseren med
   `automation.trigger` + `skip_condition: false` — nul kopieret logik (#2), og
   en disabled automation forbliver en no-op. To faldgruber: målet må ikke
   referere `trigger.` (UndefinedError aborterer HELE kalderens script), og
   rosteret skal filtreres på den tilstand målet ikke selv re-tjekker (ON-vejene
   re-tjekker ikke deres egen occupancy → ufiltreret kald tænder i tomme rum).
5. **"Live sat via API"-skridt bliver glemt.** En slider stod på fresh-min 1.0
   fordi det dokumenterede API-set aldrig skete. **Metode: ny slider = FIRE
   skridt i SAMME session** (2026-10-04, konsolidering P1: init-default-
   skridtet er VÆK — `init_user_preferences` gendanner alle input_numbers fra
   snapshottet på en frisk install (via den afledte
   `config_snapshots/fresh_install/input_number.yaml`), så snapshottet
   ER defaulten. Før: 305 håndskrevne blokke, hvoraf 283 af 644 værdier var
   forældede fabriks-defaults målt i staging):
   1. **API-set** af liveværdien (`input_number.set_value` via REST)
   2. **settings-tile** i `dashboards/settings.yaml` (inkl. scope-note)
   3. **snapshot-export** (`python3 scripts/helpers_export.py` + commit) —
      det er OGSÅ fresh-install-defaulten nu; glemmes den, står slideren på
      min efter en geninstallation
   4. **verificér liveværdien til sidst** (`/api/states/input_number.x`)

   **Skridt 1 seeder HUSET, skridt 3 seeder en FRISK install.**
   Siden **2026-09-14** er ALLE init-blokke gatet på `prefs_fresh_install`
   (`{{ is_state('input_boolean.user_prefs_initialized','off') }}`), så
   `init_user_preferences_first_boot` kun rører en **ægte fresh install**. Et
   `prefs_code_version`-bump seeder derfor **ingenting** længere på en
   eksisterende install. Behold bumpet som bogføring (det dokumenterer hvornår
   slideren kom til), men forvent ikke at det sætter nogen værdi.

   **Det var netop bumpet der før var farligt.** Guarden "aldrig sat af et
   menneske" var `value == min AND last_changed < 60s`. Men automationen fyrer
   på `platform: homeassistant, event: start` — og `last_changed` nulstilles ved
   præcis den event (jf. CLAUDE.md's permanente faktum om at
   `last_updated`/`last_changed` ikke overlever en restart). Friskheds-halvdelen
   var derfor **altid sand**, og den reelle guard var `value == min` **alene**.
   Den kan ikke skelne en fresh install fra en user der bevidst vælger MINIMUM —
   min er en lovlig user-værdi, og "value <= min" var aldrig en self-guard.

   **Målt offer 2026-09-14:** user satte
   `input_number.koekken_session_aktiv_minutter` til **1** (= min) kl.
   **12:58:47**; `prefs_code_version`-bumpet 17 → 18 skrev den til **3** kl.
   **21:57:40** med **tom `context_user_id_bin`**. Han satte den tilbage kl.
   **22:22:51**. Alle **301** default-blokke havde den fejl, inkl. fem v18-blokke
   der slet ingen freshness-test havde. Commit `f018aa2`.

   **Signatur:** en slider står på sin init-default med **tom
   `context_user_id_bin`** i recorderen, **~30 s efter en restart** — init-
   automationen har en `delay: seconds: 30` før den seeder, så tidsstemplet er
   dens fingeraftryk. (Husk `*_bin` + `hex()`: `context_user_id`-kolonnen er tom.)

   Slægtning: `initial:` RESTORER ikke, den PÅTVINGER. Samme commit fjernede
   `initial: 10` fra `vandventil_max_sekunder`, der påtvang max ved hver
   HA-start; seedingen flyttede ind i init-blokken. Resterende `initial:` på
   `input_number` er runtime-cursorer (styrbar-palette, `scene_spread`), hvor
   nulstilling ER meningen.
6. **"Live-testet" med syntetiske events beviser intet.** Sove-Styrbar blev
   "testet" med arrow_*-events; den fysiske knap sender gammel quirk-form →
   featuren virkede aldrig. Metode: test med ÆGTE device-events, eller find
   bevis i history/logbook på at den rigtige event-form er set.
7. **Tæl trigger-fires × API-kald før deploy.** /5-tick + duplikat-triggers
   gav ~800 Nordpool-kald/dag. Metode: fires/dag = 1440/interval × antal
   duplikat-triggers; foretræk state-change-triggers + /1t-backstop.
8. **Midnats-vinduer:** `today_at()` efter kl. 00 peger på NÆSTE nat/vindue —
   shift 86400 bagud når "i nat" skal betyde den igangværende nat.
9. **`unavailable` er hverken on eller off.** is_state-tjeks er stille-false
   under Thread/Zigbee-flap → gate enforce-logik på health-sensorer
   (fx matter_spots_ok) i stedet for at handle på skæv state.
10. **Verificér fund før du "fixer".** B4 "div-zero" var false positive —
    alle forbrugere guardede allerede. Læs den faktiske consumer-kode før
    du ændrer noget; et unødvendigt "fix" er også en diff-risiko.
11. **API-tests efterlader spor der ligner user-handlinger.** Et API-turn_off
    bærer user_id → manual-off-trackere stempler det som brugerens sluk →
    grace-vinduer blokerer auto-tænd i minutter/kvarter efter testen (ramte
    user 2026-07-08: lyskæde-test → 20-min grace → "lyskæden tænder ikke ved
    session"). Metode: efter lys-tests, ryd de stempler testen kan have sat
    (fx `input_datetime.koekken_lyskaede_manual_off_at` → 1970) og tjek
    room_mode/last_press ikke flippede.

    **Værste variant: sporet er ikke ét kald, men en SCENE — og den sætter N
    rum på én gang.** Et `scene.turn_on` arver den context der startede
    automationen, og udsender interne `light.turn_on` der **hver især bærer den
    context inkl. `user_id`**. Kører du et varsel manuelt (dashboard-tap eller et
    API-kald under test), ligner en snapshot-**RESTORE** derfor N
    app-justeringer i samme sekund — og en restore er pr. definition "sæt det
    tilbage som det var", aldrig en overstyring.

    **Målt 2026-08-30 kl. 07:25:33:** en test af morgen-vejrvarslet satte
    `input_select.room_mode_stue` = **Manual i 3 timer**, hvorved køkkenets
    madlavnings-spots var hård-blokeret hele morgenen: **0 sessioner**, mod
    **5-19** de foregående 8 dage med første start 06:10-07:36.

    **Discriminatoren er eksakt og målt:** scenens EGEN `context.id` er den
    context lys-kaldene bærer — ctx `7159CE0E` stod på både
    `scene.vejr_flash_restore` og `light.spisestue_loft` i samme sekund. Derfor
    står restore-scenerne som en **allowlist** i
    `automations/manual_override.yaml` (~linje 127), sammenlignet på
    `states[s].context.id == trigger.event.context.id`:
    `scene.vejr_flash_restore`, `scene.vejr_aften_flash_restore`,
    `scene.predark_restore`, `scene.entre_somrig_undo_snapshot`,
    `scene.legetoejsdag_restore`.

    **Hvorfor en allowlist og ikke `states.scene` bredt:** en HÅNDLAVET scene
    (`snap_zen`, `full_bright`) tappet med en finger **ER** en overstyring og
    skal stadig sætte Manual. Kun snapshot-restore-scener hører på listen.
    **Bygger du en ny `scene.create`-restore et sted i huset, skal den tilføjes
    dér** — ellers stempler den tavst hvert berørt rum Manual (#16: samme
    roster, flere med-ejere).
12. **Beskyttelse tilføjes asymmetrisk på søster-automations.** Regn-dør-varslet
    fik 60-min dedupe pga. flap-risiko — kulde-dør-varslet (SAMME trigger-fysik:
    temp oscillerer omkring grænsen når varmen kæmper mod åben dør) fik ingen
    (fundet+fixet 2026-07-15c). Metode: når du giver ét varsel dedupe/grace/
    gate, gennemgå søskende i samme fil/pakke med samme flap-fysik.
13. **Flanke-trigger + dedupe-stempel = ingen re-push under vedvarende
    episode.** numeric_state/state-flanker re-fyrer ALDRIG hvis tilstanden
    forbliver over/under grænsen — et "6t dedupe"-stempel antyder gen-varsling,
    men uden backstop kommer push nr. 2 aldrig (ESP-canary, fundet+fixet
    2026-07-15c). Specialtilfælde af #4. Metode: dedupe på en flanke kræver
    en time_pattern-backstop; gate backstoppen til igangværende episode
    (stempel-alder < N) så den ikke bliver en selvstændig svag detektor.
14. **Analoge sensorers `last_changed` kan IKKE bevise "sustained".**
    En temp/lux-sensor rapporterer løbende → last_changed nulstilles ved HVERT
    report — `(now() - last_changed) > N` virker KUN for binære/enum-states.
    "Har X været over grænsen i 15 min" kræver en `for:`-trigger (eller
    statistics/history_stats), ikke et condition-template.
15. **Disable/enable-vinduer sluger events.** En automation der er slået FRA
    (`automation.turn_off`, fx mode-lockdowns) modtager INGEN triggers —
    transitions i vinduet er tabt for altid ved re-enable. Et resume-flow der
    gen-enabler edge-trigget logik SKAL selv re-evaluere den tilstand logikken
    vedligeholder (AirBnB-resume genskabte ikke parent_a/parent_b_home fra live
    tracker → flag stuck off til næste ud-og-hjem-tur; fixet 2026-07-15d).
    Søster til #4: dér blokerer en condition, her er selve triggeren død.
16. **Entity-rosters drifter ved device-tilføjelse.** Samme occupancy-liste
    (7-8 sensorer) er copy-pastet i mange filer; tilføjes et device i én,
    misses søster-kopierne (køkken-Apollo: 07-15-fixet ramte house_modes+
    airbnb-listerne men missede dormant_schedule ×3 + roborock ×1 — fundet
    2026-07-15d). Metode: grep et roster-fingerprint-medlem (fx
    `spisestue_apollo_occupancy_filtered`) og opdatér ALLE hits. Special-
    tilfælde af #2 — rosters er værre fordi de LIGNER hinanden og diffen er
    én linje midt i en liste.
17. **Kun `zone.home` giver tracker-state `'home'`.** En YAML-zone med andet
    navn ("Hjem") bliver en EKSTRA zone (tracker-state = zonens navn) — den
    tilsigtede 200 m-geofence virkede aldrig (effektiv radius = core-defaultens
    100 m), og en ubrugt bredere zone ("Nærområde") skyggede afgangs-detektion
    til 500 m. Override af home-zonen kræver præcis `name: "Home"`. Generelt:
    verificér zone-/platform-antagelser mod live `/api/states` (fundet+fixet
    2026-07-15d).
18. **⏰ HA history/logbook-API'et returnerer tidsstempler i UTC — IKKE lokal
    tid.** `last_changed`/`last_updated`/logbook-`when` ender på `+00:00`.
    Huset følger dansk tid: UTC+2 om sommeren, UTC+1 om vinteren (sommertiden
    sluttede 2026-10-25 kl. 03:00 → 02:00; reglen sagde "læg 2 timer til" og blev
    forkert samme nat). Klassisk selv-fejl: læse "22:42:46" fra history som 22:42
    aften, men det er 00:42 lokal om sommeren (23:42 om vinteren). Konsekvens:
    forkert nat, forkert korrelation med godnat/mode/soltider, forkerte
    konklusioner. Metode: konvertér ALTID i din parser
    (`datetime.fromisoformat(t).astimezone(ZoneInfo('Europe/Copenhagen'))`) FØR
    du ræsonnerer om timingen — **aldrig en fast `timedelta(hours=N)`**. Natten
    til skift-dagen har ét klokkeslæt to gange (02:00-03:00 i oktober): læs
    offsettet med (`hq.py` viser `+02`/`+01` omkring skiftet). Tider du SENDER
    til API'et skal have eksplicit offset eller være UTC.
19. **⏱️ En blokeret automation fyrer i SAMME sekund blokeringen ophæves.**
    Ikke det samme som #4/#15: triggeren går ikke tabt, den bliver **opsamlet**
    og udløst præcis i det øjeblik gaten åbner — så alle side-effekter lander på
    det værst tænkelige tidspunkt. Fundet 2026-08-05 (user: "kritisk"):
    `summer_defense_active` er betinget af `godnat_any_active == off` og var
    spærret hele natten; dens `/15`-tick fyrede **06:00:00 præcis**, i samme
    sekund `godnat_auto_clear` ryddede flaget, og rullede stue-gardinerne op
    over en sovende familie uden alarm. Featuren "virkede" i to måneder, fordi
    den kun kunne observeres på det ene sekund om dagen hvor gaten skiftede.
    **Metode:** for hver langtidsholdende gate (godnat, Dormant, AirBnB,
    lockdown, snooze, natmode), spørg: *hvad fyrer i det sekund den slipper, og
    er det tidspunkt passende for HANDLINGEN?* Er svaret nej, skal handlingen
    have sin **egen** betingelse — ikke arve gatens. Signatur i history: en
    handling der sker på det **samme klokkeslæt hver dag** uden at nogen
    parameter varierer.
20. **📈 En akkumulator over en LATCHENDE sensor måler ikke det dens navn
    siger — den måler tid siden vinduets start.** `history_stats type: time`
    over en binær sensor der hænger `on`, med et vindue klampet til et fast
    klokkeslæt, når sin tærskel **præcis `tærskel` minutter efter vinduet
    åbner** — hver dag, uanset virkeligheden. Fundet 2026-08-05:
    `sensor.open_plan_active_recent` (over `open_plan_occupied`, vindue fra
    06:00) fik gardinerne til at åbne 06:03 / 06:24 / 06:30 / 06:46 / 06:52 —
    klokkeslættet fulgte sliderens værdi, ikke familien; stue-Apolloen stod
    `on` kl. 06:00 på 5 af 14 morgener, længste ubrudte forløb **35,5 timer**.
    **Signatur:** en gate der udløses med det samme faste offset hver dag, og
    hvis klokkeslæt flytter sig når du ændrer tærsklen. **Metode:** kræv
    **friskhed**, ikke bare `on` — at forløbet er BEGYNDT efter vinduets start
    (`last_changed >= vinduets_start`), kalibreret mod historikkens fordeling af
    forløbs-alder. Jf. fejlklasse #14: den advarer mod at måle "sustained" på
    analoge sensorer; denne advarer mod det modsatte — at måle "aktivitet" på
    en binær sensor der aldrig falder tilbage.
21. **🔌 Et kill-switch der ikke er en `condition` på hver eneste vej ind, er
    pynt.** En `input_boolean.<feature>_enabled` beskytter kun de automations
    der faktisk læser den. Har featuren flere indgange (backstop-tick,
    restart-recovery, manuel-script, søster-automation), er den u-gatede vej
    den eneste der tæller — og brugeren oplever "kontakten virker ikke".
    **Metode:** `grep -rn "<feature>_enabled" automations/ packages/ scripts/`
    og hold hits op mod `grep -rn "<featurens handling>"`; hver skriver skal
    enten være gated eller bevidst undtaget med en kommentar der siger hvorfor.
    Samme tjek som #1, men rettet mod OFF-vejen i stedet for ON-vejen.
22. **🔇 En automation i `unavailable` er ikke støj — den er VALIDERINGS-FEJLET
    og fuldstændig stum.** HA disabler HELE automationen ved den mindste
    template-syntaksfejl et vilkårligt sted i dens `action:`, uden at røre resten
    af filen — søster-automations i SAMME fil kører videre, så filen "virker".
    Der kommer **ingen** advarsel ved commit, deploy eller reload; eneste spor er
    én ERROR-linje i core-loggen. Fundet 2026-08-06: `trainer_dug_ask` havde
    ligget død siden 08-02 (4 tabte dug-morgener) fordi en `{#`-kommentar stod
    mellem to dict-nøgler **inde i** et `{{ }}`-udtryk — Jinja-kommentarer er
    statement-niveau og kan ikke ligge i et print-udtryk. **Metode:** efter
    ENHVER deploy, kør `./scripts/ha_health.sh deploy` og list `automation.*` i
    `unavailable`.

    **Diskriminatoren er `restored`-attributten — ikke et config-grep.**
    (Rettet 2026-09-17; denne fil anbefalede før den langsomme vej: "findes
    entity'ens `unique_id` i config".)

    | `attributes.restored` | Betydning |
    |---|---|
    | `true` | **Registry-orphan** — entity'en findes kun i entity-registry'et efter en sletning/omdøbning. Harmløs støj. |
    | mangler/falsy | **ÆGTE valideringsfejl** — automationen er stum. Handl. |

    Grunden til at det skal være en attribut-test og ikke et grep: orphanerne er
    **mange**, så et config-grep skal køres pr. entity og drukner signalet.
    CLAUDE.md nævner 61; **målt 2026-09-17: 74 restored-orphans, 0 ægte fejl** —
    tallet drifter opad hver gang en automation omdøbes, så brug det som
    størrelsesorden, ikke som facit. `ha_health.sh`'s `check_deploy` (linje
    ~31-41) filtrerer præcis sådan:

    ```python
    bad = [s for s in states
           if s["entity_id"].startswith("automation.")
           and s["state"] == "unavailable"
           and not s["attributes"].get("restored")]
    ```

    Årsagen står i
    `curl -H "Authorization: Bearer $SUPERVISOR_TOKEN" "http://supervisor/core/logs?lines=500"`
    → `grep "could not be validated"`. Slægtning til #6: koden var reviewet og
    havde aldrig kørt.

23. **🔁 En restart-recovery må ikke bevise sin præmis med den kanal der var i
    stykker.** Fundet 2026-08-15b (user: "har du lige tændt alt stuelys? eller
    bug. hele open plan"). En `ha core restart` **06:37:53** → HA-start-trigger
    06:38:01 → `presence_resync_open_plan_on_start` lavede sit one-shot-tjek 2
    min senere og tændte `light.stue_all` (stue + spisestue-loft + køkken-
    lyskæde) på 60 % kl. **06:40:01** over en sovende familie. Præmissen
    "mindst én open-plan Apollo står `on`" var opfyldt af
    `stue_apollo_occupancy` med `last_changed` = **selve boot-tidspunktet** —
    en *restored* latch, ikke en flanke; alle tre `moving_target` var off hele
    vejen. Automationen findes præcis fordi occupancy booter hængende `on` uden
    flanke, så **den latch kan pr. konstruktion ikke også være dens bevis for
    et menneske**.
    **Metode:** kræv en ANDEN kanal end den der var i stykker — her en ægte
    `moving_target`-flanke inden for et vindue efter boot (op til 15 min: en
    der sidder stille bevæger sig indenfor vinduet, et tomt rum aldrig).
    Re-tjek gatesne EFTER ventetiden (den er lang), og begræns handlingen til
    det rum beviset kom fra, ikke hele zonen. Boot-tidspunktet fanges i en
    `variables:` FØR delayen — huset har ingen `sensor.uptime` for HA selv.
    Slægtning til #20 (latch ≠ aktivitet) og #5 (restore'ede helpers duer ikke
    som friskheds-mål).

24. **📝 En template-attribut med `now()` skriver en DB-række hvert minut — og
    kan smugle en recorder-ekskluderet entity tilbage i databasen.** Fundet
    2026-08-15: `binary_sensor.sove_radar_frossen` var husets mest skrivende
    entity med **5403 rækker/døgn** — men kun ~10 var ægte tilstandsskift.
    Resten var attribut-ændringer fra `on_since_min`, der beregnede
    `(now() - still_target.last_changed)` og derfor talte et minut op hver
    eneste minut, i al evighed, også mens sensoren var `off` og intet skete.
    Oveni nulstilledes den ved hvert `still_target`-skift — og netop
    `binary_sensor.*_apollo_radar_still_target` er **bevidst ekskluderet fra
    recorderen** (configuration.yaml, ~40.000 events/døgn sparet). Attributten
    gav ~4000 af dem tilbage ad bagvejen.
    Attributten havde **nul forbrugere**: ingen automation, intet script, intet
    dashboard læste den (dashboardene viser kun entity'ens state). Den var
    desuden mislabelt — mens target var `off`, målte "on_since_min" tid siden
    den gik OFF.
    **Metode:** (a) `ha_health.sh noisy` → for en topscorer, tjek om rækkerne er
    attribut-ændringer: `SELECT COUNT(*) ... WHERE last_changed_ts IS NOT NULL`
    (non-null = state uændret, kun attributter). (b) Grep efter forbrugere af
    attributten før du gør noget andet — findes ingen, er churnen ren spild.
    (c) Gate attributten på den tilstand hvor den er meningsfuld og returnér en
    konstant ellers, og (d) kvantisér mod den tærskel den sammenlignes med
    (her: 5-min-trin mod en 30-min-tærskel). Efter fixet: 0 rækker mens rummet
    er tomt. HA skriver ikke en ny række når state OG attributter er uændrede,
    så en konstant attribut koster ingenting.
    Slægtning til #7 (tæl skrivninger før deploy) — men her er prisen recorder-
    volumen, ikke API-kald.
25. **⏳ "X har været `off` i N minutter" på en radar-afledt binær er
    uopfyldelig — ét 1-sekunds blip sletter hele den opsparede tid**, og jo
    større N, jo mere sikkert er gaten død. Fundet 2026-09-11: to fixes der
    hver især var rigtige gjorde tilsammen kravet umuligt. B117 flyttede
    varigheden ind i betingelsen, B120 hævede kravet 30 → 90 min — og
    stue-Apolloen fyrer et spøgelse hvert ~5. min i en beviseligt tom lejlighed
    (længste rolige hul målt: **16,4 min** mod et krav på 90). Huset stod
    derfor Active i **21,6 t**, og B120's hævning gjorde det strengt værre.
    **Hvorfor det var usynligt:** B120's replay filtrerede *historiske
    overgange* i stedet for at måle **flanke-AFSTANDEN** fremadrettet. Et replay
    af fortiden ser sundt ud, fordi det aldrig stiller spørgsmålet "hvor længe
    går der mellem to flanker?".
    **Signatur:** en gate der ALDRIG fyrer, hvor hver enkelt betingelse ser
    rimelig ud hver for sig.
    **Metode:** mål stilhed på et **anker der kun flyttes af en flanke der
    HOLDER** — `sensor.last_sustained_presence` — ikke på kanalens egen
    `last_changed`. Den korte 12 s-tier kunne ikke genbruges: spøgelser på 13-95
    s opfylder den og bumpede ankeret 26× på 4,3 t i et tomt hus, så der måtte
    en ny lang tier på **120 s** til. At hæve den korte i stedet ville gøre hele
    huset blindt (= 09-09d's fejl på tids-aksen).
    Spejlbillede af #14: dér måles sustained forkert på en ANALOG sensor, her
    slettes opsparet stilhed af en BINÆR der blipper.

26. **🏠 En HUS-BRED gate på en RUM-SCOPET tilstand låser alle de rum
    tilstanden intet har med at gøre.** Set to gange i samme fil,
    `automations/room_drift_back.yaml`, med halvandet års mellemrum i
    konsekvens: 2026-08-16 holdt en mood der kun ejede 3 rum de øvrige 4 låst
    på Manual hele sessionen (= mørke), og gaten blev flyttet ned i rum-loopet
    som `binary_sensor.mood_pause_<rum>`. Den nabo-condition der gjorde
    NØJAGTIG det samme — `sensor.activity_state` — blev ikke rørt, og 2026-09-17
    låste den depotet: et app-"sluk alt" kl. 08:58:35 stemplede alle 8 rum
    Manual (bevidst, user-spec 2026-08-01), depotet stod derefter tomt
    09:31-10:18 = 47 min, og den ENE /15-tick der kunne have sluppet det (10:15)
    blev afvist fordi huset stod `sofa_relax` — en tilstand hvis egen definition
    lyder "kun stue". Da user gik ind i depotet 10:18 var rummet stadig Manual.
    **Hvorfor det var usynligt:** symptomet var et lys der ikke tændte i ét rum,
    mens årsagen sad i en condition om et HELT andet rum, i en tredje fil.
    **Signatur:** en feature virker kun delvist ("kun early-detect tænder"),
    hvor den del der virker er den der IKKE har rum-mode-gaten.
    **Metode:** når du fixer en hus-bred gate ved at rum-scope den, så gennemgå
    dens NABO-conditions i samme `condition:`-blok — de er der af samme grund og
    har typisk samme fejl (#12: beskyttelse tilføjes asymmetrisk). Og hent
    scopet ordret fra den kildes egen definition, gæt det ikke: hver
    activity_state-værdi er dokumenteret med sine rum i
    `packages/activity_state.yaml` linje 8-27.

27. **En låners AFLEVERING skriver et snapshot fra FØR lånet.**
    Et blink/varsel/en scene der `scene.create`'r, holder lamperne i tiden
    mellem snapshot og `scene.turn_on` — og afleveringen er det **sidste** kald
    i vinduet. Alt hvad huset selv besluttede imens, rulles tilbage uden én
    fejllinje.
    **Den oprindelige retning (2026-09-19c):** et lys der **SLUKKER** kort efter
    at en midlertidig ejer slap det, fordi snapshottet var taget før brugeren
    tændte. Ingen flanke at rette på.
    **Spejlbilledet (2026-09-20, user-bug "køkkenlyset har hængt i dag") rammer
    bredere, fordi det også koster ofret dets egen re-arm:**
    `automation.open_plan_dagslys_probe` slukkede køkken-lyskæden **07:45:05**
    for at skaffe et rent lux-sample. `scene.vejr_flash_restore` tændte den igen
    **07:45:27** fra et snapshot `scene.create`'t **07:45:00** — altså før
    proben besluttede noget. Oveni var probens 45-minutters cooldown brændt på
    et forsøg der aldrig fik lov at måle, så huset stod blindt og lyset brændte
    til over 08:30.
    **Kollisionen var systematisk, ikke uheldig:** blinket trigges `/1` og
    proben `/5`, så probens tick ligger inde i blinkets ~40 s lånevindue de
    fleste varsel-morgener. Blinkets egen kommentar påstod tilmed at
    "snapshot-restore giver pre-blink-state tilbage" — sandt, og præcis derfor
    forkert (#3: kommentar-påstande ≠ kode).
    **Signatur:** et lys der TÆNDER igen ~40 s efter at en automatik slukkede
    det, uden nogen trigger der forklarer tændingen.
    **Metode:** et varsel der `scene.create`'r er **med-ejer af hver beslutning
    i sit vindue** (#1). Fang lånets start i `variables:` FØR delayene (`now()`
    ville ellers rendere ved afleveringen og gøre vinduet nul sekunder langt),
    og lad afleveringen spørge huset igen: er en anden autoritets stempel nyere
    end lånets start, gentag dens beslutning i stedet for at gengive
    snapshottet. Giv søster-varslerne samme værn med det samme (#12).
    Implementeret i `automations/rain_warning.yaml` for morgen- OG aften-blinket.

28. **📈 Et high-water-mark på et flimrende signal gemmer flimmerets TOP — og
    en bonus betinget af en radar arver radarens flimmer.** Fundet
    2026-09-30g i `packages/people_estimate.yaml`: børne-bonussen (+2) krævede
    at børneværelsets Apollo var on LIGE NU, og den taber sovende børn
    (29/9: 12 on + 11 off på én time). Estimatet svingede derfor 2↔4 i takt med
    radaren, og gulvet ("højeste set siden hoveddøren") løftede sig på hver
    top og holdt den i 20 min pr. decay-trin. Samme mekanik med terrassedøren,
    bad-grenen og trailing: på børnefri dage viste estimatet flere end de
    voksne i 17,4 % af tiden, og 12,7 %-point af det var gulvet over en top på
    få sekunder. Facit: alle 5 gæt på 2 i børne-uger var "for få", 8 af 12 gæt
    på 4 "for mange".
    **Hvorfor det var usynligt:** hver regel var rigtig hver for sig — "børn i
    seng ses som én zone" og "ingen kan gå uden at bruge døren" er begge sande
    præmisser. Fejlen opstår først i kompositionen: latchen ganger hvert blip
    op til decay-tiden.
    **Signatur:** et tal der springer mellem to værdier i takt med én radar,
    og som hænger på den høje værdi i præcis decay-tiden efter hvert blip.
    **Metode:** (1) latch kun værdier der har HOLDT — `for:`-trigger OG samme
    hold-krav (`last_changed ≥ hold`) på hver re-arm-vej (#21), plus et
    /N-backstop fordi en genstart dræber den ventende `for:`. (2) Læg gulvet
    kun på den del der IKKE allerede er bevist af en stabil kilde (v4:
    familien fra hjemme-flag har intet gulv; kun radar-tallet UD OVER familien
    har). (3) En betingelse der skal bygge bro over en radars huller, læses
    fra en history_stats over et vindue (restart-sikker), ikke fra radarens
    øjebliks-state. Replay: over-tælling 17,4 % → 4,9 %, skift 23 → 11/døgn.

---

## Jinja-gotchas — den fulde liste

CLAUDE.md bærer en komprimeret udgave af denne liste. Her er den lange, med
mekanik og modgift. To af dem (typning og udefinerede script-felter) aborterer
HELE automationen og hører derfor sammen med #22.

### Typning: et StrEnum i en dict-variabel gør HELE dict'en til en streng

Samme mekanik som `false` nedenfor: HA kører `ast.literal_eval` på
render-resultatet, og en dict-repr med `<ColorMode.XY: 'xy'>` i sig kan ikke
evalueres → variablen bliver en repr-STRENG, og `to_json` gemmer den som tekst.
Ramte 2026-10-02 måle-pakken (`packages/lux_lampe_maaling.yaml`): både
`color_mode` og `dict(states[x].attributes)` (nøglerne `icon`/`friendly_name`
er `EntityStateAttribute`-enums) blev strenge i JSONL'en.

- **`| string` redder det IKKE:** et StrEnum ER allerede en `str`, så Jinjas
  `soft_str` lader det passere uændret. Målt i `/api/template`:
  `{'a': x | string, 'b': '' ~ x}` → `{'a': <ColorMode.XY: 'xy'>, 'b': 'xy'}`.
- **Modgift:** `'' ~ x` (sammenkædning kalder `str()`), og byg dicts af KENDTE
  nøgler via `state_attr` i stedet for `dict(states[x].attributes)`.

### Typning: en templated `false` er en truthy STRENG

En `variables:` (og enhver anden ikke-boolsk kontekst) der renderer den **bare
tekst** `false` eller `true`, producerer en **streng**, ikke en bool. HA forsøger
`ast.literal_eval` på render-resultatet, og den kender kun Pythons `False`/`True`
med stort begyndelsesbogstav — `"false"` med lille f fejler evalueringen og
bliver stående som streng. En ikke-tom streng er **truthy**, så din "slukkede"
variabel er tændt.

- **Skriv `{{ false }}`**, ikke `false` som bar tekst, når værdien skal være
  boolsk. (`{{ false }}` renderer `False` → `literal_eval` giver `bool`.)
- **`| default(false, true)` redder det IKKE.** `default(x, true)` udskifter kun
  værdier der er *falsy* — og `"false"` er en ikke-tom streng, altså truthy.
  Filteret ser en gyldig værdi og lader den passere.
- **I `value_template` er det harmløst.** Template-conditions og binary_sensors
  køres gennem HA's `result_as_boolean`, der tolker resultatet som et
  HA-boolean i stedet for at spørge om strengen er tom. Verificeret mod
  `/api/template` 2026-09-17: `'false'`, `'no'`, `'off'`, `'0'` og `'False'`
  giver alle `False` (uparselige værdier falder også til `False`). Derfor kan den samme
  skrivemåde virke i en `condition:` og være forkert i en `variables:` ti linjer
  længere nede — **konteksten afgør det, ikke syntaksen.**
- **Signatur:** en gren der altid tages, hvor variablen "tydeligvis" er falsk;
  eller et `{{ min_flag }}` der printer `false` i Template-editoren mens
  `{{ min_flag | bool }}`-agtige tjeks opfører sig omvendt.

### Et SCRIPT-FELT der ikke sendes med i kaldet er UDEFINERET

Kalder du `script.x` uden feltet `y`, findes `y` ikke — den er ikke tom, ikke
`None`, den er **Undefined**.

- **`| int(0)` redder det IKKE.** Filter-defaults gælder en værdi der **findes**
  men ikke kan konverteres; de gælder ikke et navn der ikke er defineret. Jinja
  rejser `UndefinedError` på selve navne-opslaget, før filteret nås.
- **Konsekvensen er total:** `UndefinedError` aborterer **hele** automationen /
  scriptet på det sted den rammer — ikke kun den ene linje. Alle efterfølgende
  steps springes over, og ved validering giver det en #22-stum automation.
- **Modgift:** `{{ y | default(5) | int(5) }}` på **ethvert valgfrit felt** —
  `default()` skaffer en værdi, `int()` sikrer typen. Begge, i den rækkefølge.
- Samme fælde rammer `trigger.` i et script der kaldes fra et andet script
  (jf. #4): kalder du et mål der læser `trigger.x` uden selv at være trigget,
  aborterer KALDERENS script.

### Ukendte attributter fejler ikke — de forsvinder

`state_attr(e, 'findes_ikke')` og `x.attributes.typo` giver **Undefined**, ikke
en fejl. Forbrugerens `| int(0)` / `| default()` maskerer det til en plausibel
værdi (typisk 0), så kæden logger "OK" hele vejen ned mens den regner på
ingenting. Dræbte disko-varslet i uger (08-07). **Verificér feltnavne mod det
faktiske payload/`/api/states`, ikke mod dokumentationen.**

### Syntaks og struktur

- **Ingen list-comprehensions.** Brug `selectattr`/`map`/`rejectattr` + `list`,
  eller en `namespace` + `for`-løkke.
- **En foldet `{% %}`-blok returnerer en STRENG**, også når indholdet ser ud som
  en liste — split først i target (`entity_id: "{{ x }}"` med komma-separeret
  streng virker; en rigtig liste gør ikke).
- **`repeat.index0` findes IKKE.** Kun `repeat.index` (**1-baseret**),
  `repeat.first`, `repeat.last`, `repeat.item`.
- **`{# #}` kan ikke ligge inde i `{{ }}`** — Jinja-kommentarer er
  statement-niveau. En kommentar mellem to dict-nøgler inde i et print-udtryk
  dræbte `trainer_dug_ask` i fire dage (#22).
- **Et literal `#}` i selve kommentar-TEKSTEN lukker kommentaren for tidligt.**
- **`%` skal IKKE escapes som `%%`** (det er ikke printf).
- **Template-sensorens name-slug SKAL matche `unique_id`** — og entity_id'et
  afledes af `name:`, aldrig af `unique_id:`.
- **Entity_ids er danske alias-slugs** — list `/api/states`, gæt aldrig.
- **En `template:`-blok er ALT-ELLER-INTET pr. fil:** én ugyldig sensor dræber
  HELE `template:`-nøglen i filen, mens filens `automation:`/`input_*:` loader
  normalt. Entities er så hverken `unavailable` eller i registry, men
  **fuldstændig fraværende** — grep loggen efter `template|package` +
  `error|invalid`, ikke efter entity-navnet.
