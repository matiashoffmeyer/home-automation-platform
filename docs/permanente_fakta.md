# Permanente fakta — den lange version

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Auto-loades IKKE.** Genkendelses-laget (reglen, dens signatur og et
entity-navn) står i CLAUDE.md for de husdækkende fakta og i
`.claude/rules/<domæne>.md` for domæne-fakta (path-scopet siden 2026-10-05:
lux, presence, Thread/Matter, pærer, effekter, gardiner, energi, stemme,
Nemlig, Roborock, vejr, personer, scripts/API, dashboards, add-ons). Denne fil
bærer måledataene, incident-forløbet og de begrundelser der forklarer HVORFOR
reglen ser ud som den gør.

**Læs den når:** du genkender en bullet i CLAUDE.md eller en regel-fil og skal
bruge tallene bag — fx hvilken måling en tærskel er kalibreret mod, hvor mange
døgn den er målt over, eller hvilken hændelse der afslørede quirken.
`grep -n "<nøgleord>" docs/permanente_fakta.md` frem for at Read'e hele filen.

Ændrer virkeligheden sig (ny hardware, ny firmware), skal BEGGE lag rettes —
den korte bullet (CLAUDE.md eller regel-filen) og afsnittet her.

---

**Home Assistant / Jinja**
- **HA springer SELV `unavailable` entities over i service-kald.** I
  `homeassistant/helpers/service.py` (linje ~785 i HAOS 2026.x) står
  `entity_candidates = [e for e in entity_candidates if e.available]`, og der er
  tilsvarende `if not entity.available: continue` to steder mere. Kaldet logger
  en WARNING (*"Referenced entities … are missing or not currently available"*)
  og fortsætter. **Konsekvens:** en død pære i et roster koster nul radiotid, og
  et runtime-filter på availability foran et `light.turn_on` er ren duplikering
  af noget HA allerede gør. Verificeret 30/8 under jagten på vejr-varslets
  ujævne blink, hvor tre strømløse stue-pærer (B91) var den første — og
  forkerte — mistanke. Døde pærer gør et varsel mindre SYNLIGT (det kørte på 3
  lamper i stedet for 6), men de gør det ikke langsommere.
- **En HA-restart dræber ethvert `to: X for: N` der VENTER på en flanke der
  allerede er sket.** Sensorerne restaureres i den tilstand de stod i, så der
  kommer aldrig en ny flanke — automationen er stum til virkeligheden tilfældigvis
  skifter igen. Rammer især oprydnings-/sluk-veje, hvor "stille i N min" er hele
  betingelsen: er rummet stille FØR restarten, rydder ingen op. Målt 08-13:
  bad-lyset brændte 49,5 min fordi alle fire sluk-veje var flanke-baserede.
  Har en feature kun flanke-triggers, skal den have en time_pattern-backstop der
  måler tiden med et **condition-template** (last_changed tæller fra restarten =
  fuld frist, ikke nul og ikke evigt). Slægtning til fejlklasse #4/#15.

  **To følge-huller, og de rammer hver sin retning:**
  1. **En automation der ikke lytter endnu, modtager INGEN triggers.** Under
     opstarten er automationen ikke armeret, så flanker der sker i vinduet er
     tabt for altid — ikke forsinket, tabt. (Samme mekanik som fejlklasse #15's
     disable/enable-vindue: en `off`-automation er ikke en kø.)
  2. **Den `from: "off"`-guard som Matter-ekkoet KRÆVER, gør enhver
     restart-flanke usynlig for TÆND-veje.** Sensorer kommer efter en restart
     tilbage som `unknown → on`, ikke `off → on`, så guarden — der er helt
     korrekt, og som beskytter mod at en genopstået Matter-node ligner bevægelse
     — filtrerer også den ægte opstartsflanke væk. De to krav kan ikke opfyldes
     af den samme trigger.

  **Fix for BEGGE: `platform: homeassistant, event: start` med en settle-delay,
  tilføjet som et EKSTRA `id:` på den EKSISTERENDE gren.** Aldrig en kopi af
  automationen (fejlklasse #2 — to kopier af samme regel divergerer), og aldrig
  en slækket `from:` (det genindfører Matter-ekkoet permanent for at redde én
  flanke om måneden). Delayen skal være lang nok til at sensorerne er kommet ud
  af `unknown`, og gatesne skal re-tjekkes EFTER ventetiden, ikke før
  (fejlklasse #23).
- **Huset har INGEN `sensor.uptime` for HA selv** (kun Apollo'ernes) → skal en
  automation kende sit eget boot-tidspunkt, fang det i en `variables:` FØR en
  `delay`, ikke bagefter.
- **`initial:` på en helper RESTORER IKKE — den PÅTVINGER** ved hver HA-start.
  Et `input_boolean` med `initial: off` er derfor nulstillet efter hver restart,
  uanset hvad brugeren satte. Skal værdien overleve, så udelad `initial:` helt.
  Og **`input_boolean.reload` gen-påtvinger ALLE `initial:` i hele huset** — ikke
  kun dem i den fil du lige rettede. Kør den aldrig for at aktivere én ny helper
  uden først at tjekke hvad husets ØVRIGE `initial:` ville sætte tilbage (kostede
  næsten dance-rosteret midt i en fest 2026-08-21).
- **Auto-åbnere af gardiner deler ét hold-anker:** `sensor.gardiner_manual_hold`
  (samme sted som putning-holdet). Bygger du en ny auto-åbner, læs DEN — så
  arver den gæste-/putte-beskyttelsen gratis (#1/#16). Manuel betjening læser
  ikke `held` og vinder stadig.
- **Et Styrbar-tryk sætter selv rummet i Manual** (`styrbar_brightness_step` →
  `styrbar_stamp_press`). Vil en ANDEN automation sætte `room_mode_<rum>` →
  Auto på SAMME tryk (fx "OP frigiver et gæste-hold"), skal den vente **~2 s**
  først — ellers er rækkefølgen en lodtrækning, og "OP = tilbage på Auto"
  holder kun nogle gange. Gælder begge gæste-hold (børn + open plan).
- **`last_updated`/`last_changed` nulstilles ved HA-restart** → duer ALDRIG som
  friskheds-/liveness-mål. Friskhed skal komme fra en **skrevet** værdi
  (`input_datetime`-stempel). Gælder også restore'ede helpers (fejlklasse #5).
  Apollo-occupancy har ét færdigt: `input_datetime.<rum>_apollo_occ_since`
  (packages/apollo_latch_detect.yaml) — stemples ved →on, ryddes til 1970 ved
  →off, og røres IKKE af en restart (automations lytter ikke endnu ved boot-
  flanken; målt 10-05 06:35: stempel fra 06:34:30 overlevede). 2026-10-05:
  morgenradioens "alene oppe" og sove-morgenens anden-krop-gap brugte
  last_changed — huset genstartes 1-3 gange hver morgen under dev-sessioner.
- **history/logbook-API'et svarer i UTC** — læg 2 t til for lokal tid (#18).
- **Recorderens `context_user_id`-kolonne er TOM** (0 rækker i hele DB'en);
  brugeren står i **`context_user_id_bin`**. Læser du den gamle kolonne, ligner
  hvert eneste fingertryk en automation, og "hvem gjorde det?" besvares forkert.
  Samme gælder `context_id`/`context_parent_id` → brug `*_bin` + `hex()`.
- **Årsagssammenhæng mellem to state-skift aflæses på `parent_id`, aldrig på
  `context.id` — og ALDRIG på et afkortet ID.**

  Et HA-context-ID er en ULID: de første ~10 hex-tegn koder tidspunktet i
  millisekunder, resten er tilfældigt. Sætter automation A entity B, arver B's
  state-skift `parent_id = A's context.id`, mens B får sit eget nye `id`. Fordi
  de to skift sker i samme millisekund, er **ULID-præfikset identisk** — netop
  det felt et debug-print typisk beholder.

  Målt 2026-09-05 08:30:35 (B116), hvor `house_mode` → AirBnB tvang
  `house_state` → Active:

  ```
  house_mode   id     = 01A0704305C872F613971E05615312F4
  house_state  id     = 01A0704305EDF9409F4D7D7588FC04DB   ← IKKE ens
  house_state  parent = 01A0704305C872F613971E05615312F4   ← slægtskabet
  ```

  Et `[:10]`-print viser `01A0704305` for begge og "beviser" en lighed der ikke
  findes. En gate skrevet på `context.id != mode.context.id` bliver derfor en
  **no-op** — den er sand hver eneste gang. Fejlen blev kun opdaget fordi
  replayet over 43 flanker gav 0 undertrykkelser, inklusive den hændelse der var
  målt. Med `parent_id` i testen ramte den 1 af 43 — netop hændelsen.

  **Regel:** sammenlign fulde ID'er, test `parent_id`, og når et replay siger
  "din nye regel gør ingenting", så mistænk reglen før replayet.
- **Et urørt `input_datetime` med `has_date: true` står på DAGENS midnat**
  (ikke 1970). Guard på tidsdelen: `states(x)[11:] == '00:00:00'` = ikke sat.
  Sæt med **`set_datetime`** (`set_value` giver bart `400: Bad Request`).
- **`as_timestamp(states('input_datetime.X'), 0)` er FORKERT — resultatet ligger
  UTC-offsettet (nu 2 t) for sent. Brug `state_attr(x, 'timestamp')`.**

  Entityens *state* er en naiv lokal streng (`'2026-07-17 00:00:00'`).
  `as_timestamp()` parser naive strenge som **UTC**, så resultatet skydes frem
  med offsettet. `timestamp`-attributten regner derimod korrekt lokal-bevidst
  — inkl. historisk sommertid.

  Målt 2026-09-09 via `/api/template` på to helpers:

  | | state | `state_attr(...,'timestamp')` | `as_timestamp(states(...),0)` |
  |---|---|---|---|
  | urørt (dagens midnat) | `2026-07-17 00:00:00` | `2026-07-17T00:00:00+02:00` ✅ | `2026-07-17T02:00:00+02:00` ❌ |
  | sat via `set_datetime` | `2026-09-05 09:30:35` | `2026-09-05T09:30:35+02:00` ✅ | `2026-09-05T11:30:35+02:00` ❌ |
  | kontrol på `now()` | — | — | `DIFF = 7200 sek` præcis |

  **Signaturer:** et "aldrig sat"-stempel ser friskt ud mellem **02:00-02:02**
  (det var den observation der oprindeligt — og fejlagtigt — blev skrevet ned
  som *"attributten læses 2 t forskudt"*, hvilket pegede læseren mod netop det
  ødelagte idiom); en armering åbner 2 t for sent; et grace-/dedupe-vindue varer
  2 t for længe.

  **Fejlen ER offsettet**, ikke en konstant: **2026-10-25 skifter den til +1 t**.
  Alt der er kalibreret oven på den forkerte adfærd flytter sig den nat.

  Fundet under AirBnB-auditten 2026-09-09. Auditten talte 17 kopier i 10 filer;
  den rigtige optælling var **29 i 20**, alle ryddet samme dag (B121). Forskellen
  er ren grep-metode: **14 sites lægger entityen i en `{% set %}`-variabel først**
  (`{% set d = 'input_datetime.X' %} ... as_timestamp(states(d), 0)`), og fire
  skriver `as_timestamp(VAR)` helt uden `, 0`-default. Et grep på den direkte
  form finder altså under 60 % af dem. Værste udslag var
  `packages/airbnb_velkomst.yaml:437`, hvor velkomst-ceremonien holdt seks rum i
  Manual i **2 t 10 min i stedet for 10 min** (10 + 120) — efter fixet målt til
  10,0 min. Det korrekte idiom var i forvejen i brug i
  `packages/gardin_manual_grace.yaml:125` → fejlklasse #2.

  **To fælder ved oprydningen:**
  1. **Begge sider af en sammenligning kan være buggy, så fejlen udligner sig
     selv.** `packages/roborock.yaml:597` (direkte form) og `:598` (variabel-form)
     sammenlignes med hinanden; kun `:597` matchede det oprindelige grep, og et
     fix af den alene ville have **indført** en 2-timers skævhed i en gate der
     virkede. Konvertér altid begge sider i samme edit.
  2. **Varianten `as_timestamp(states(x), 0) - now().utcoffset().total_seconds()`
     er KORREKT** — en mekanisk erstatning ville lægge en ny 2-timers fejl oveni.
     7 steder bruger den. Den er dog DST-skrøbelig: kompensationen bruger
     offsettet **nu**, ikke offsettet **da stemplet blev skrevet**, så et stempel
     sat før 2026-10-25 03:00 og læst efter er 1 time galt → B127.

  **Status: huset er RYDDET.** B121 (de 29 ødelagte sites i 20 filer) + B127 (de
  7 DST-skrøbelige `- now().utcoffset()`-varianter) er begge lukket ⇒ **nul
  kendte tilfælde tilbage**. Finder du ét, er det nyt og indført efter
  oprydningen — `state_attr(x, 'timestamp')` er det ENESTE idiom der skal
  skrives, og et nyt hit er derfor en regression, ikke en rest.
- **En urørt `input_text` står på `'unknown'`, som er truthy** —
  `| default('', true)` redder den ikke; test eksplicit for sentinel.
- **`last_triggered` sættes FØR action-body'en fejler** → frisk `last_triggered`
  + nul side-effekter = action'en aborterer (permanent diagnostik).
  **Konsekvens: `last_triggered` duer heller ikke som dedupe-kilde INDE i
  automationens egen `choose:`.** Stemplet er allerede sat af det kørende run i
  det øjeblik action-body'en evalueres, så en gren der spørger *"er der gået
  N minutter siden sidst?"* læser **sit eget stempel** og er derfor altid
  0 sekunder gammel = dedupen fyrer hver gang, eller aldrig, afhængigt af
  operatorens retning — men den måler under alle omstændigheder ikke det den
  tror. **Signatur: en dedupe der opfører sig identisk uanset hvilken værdi du
  sætter intervallet til.** → Dedupen hører i automationens `condition:`-blok
  (som ligger før action-body'en, hvor stemplet stadig er forrige kørsels), eller
  — mere robust — på et **skrevet** stempel (`input_datetime`/`input_text`) du
  selv kontrollerer, præcis som `last_changed`-bulletten foreskriver.
- **`/api/template` bruger den fulde HA-template-env** → gyldigt orakel for
  "findes dette filter/denne funktion?".
- **Legacy `light: - platform: group` refresher kun ved RESTART**, ikke reload.
- **Lovelace-`visibility` har INGEN `template`-betingelse** — kun `state`,
  `numeric_state`, `screen`, `user`, `location`, `time` + `and`/`or`/`not`. En
  ukendt condition-type afvises **tavst og lukket**: kortet er væk for altid,
  uden logfejl, rødt kort eller advarsel ved reload. Skal en beregnet værdi gate
  et kort, læg tallet i sensorens **state** og brug `numeric_state` (kostede
  alle otte opskrift-kort på Mad-siden 2026-08-17). Virker et kort ikke, så
  mistænk condition-TYPEN før dens indhold — en korrekt template i en
  ikke-eksisterende type ser ud præcis som en template der returnerer false.
  **`attribute:` findes heller ikke** i `state`/`numeric_state` her (kun
  `entity` + `state`/`state_not`/`above`/`below`) — modsat entity-RÆKKER, hvor
  `type: attribute` er helt normalt, så mønstret ser bekendt ud og fejler tavst.
  Skal N ting gates hver for sig, skal der være N entities med tallet i deres
  **state**; en beregnet liste splittes altså i én sensor pr. gate-akse (fx én
  pr. person), ikke i attributter på én sensor (kostede alle 16 stem-knapper
  2026-08-20).
- **Samme tavshed rammer et tile-FEATURE som entiteten ikke bærer feature-bittet
  til.** Lovelace tegner `features:` ud fra entitetens `supported_features`, så
  et feature entiteten ikke understøtter droppes uden fejl — kortet ser helt
  normalt ud, blot uden knappen. **Signatur: en knap du netop har copy-pastet fra
  en søster-entity i SAMME domæne er væk, og YAML'en er identisk.** De tre
  Somfy-gardiner stod på `supported_features: 11` (OPEN\|CLOSE\|STOP) mod
  soveværelsets **15** (+SET_POSITION), så et kopieret `cover-position` var
  blevet usynligt (2026-09-20). → slå `supported_features` op i `/api/states` på
  BEGGE entities før du kopierer en knap; mangler bittet, er opgaven at bygge
  kapaciteten, ikke at rette dashboardet.
  **Og det gælder ikke kun UI: også SERVICE-kald.** HA springer tavst en
  service-feature over som entiteten ikke understøtter — `winter_defense.yaml`
  kaldte `cover.set_cover_position` på præcis de tre gardiner, og
  `continue_on_error: true` slugte resten af sporet, så vinter-forsvaret aldrig
  rørte open-plan-gardinerne i månedsvis uden en eneste fejllinje. **Signatur: en
  automation der "kører fint" (frisk `last_triggered`, ingen fejl) mens den
  fysiske effekt aldrig er observeret.** → verificér en gate/handling på
  entitetens feature-bit, ikke på at kaldet ikke fejlede (jf. fejlklasse #22's
  spejlbillede: her er det kaldet, ikke automationen, der er stumt).
- **Lovelace kan IKKE rulle til et kort på samme side** — kortene lever i shadow
  DOM, så et `#anker` finder aldrig sit mål, og der findes ingen scroll-action.
  "Tryk her og kom hen til X" bygges som link til en `subview: true`-view
  (`back_path` gør tilbage-pilen forudsigelig). Skal listen have templated tekst,
  er markdown-kortet eneste mulighed — det har ingen `tap_action`, så linkene
  skal være markdown-links (`[tekst](/dash-url/path)`).
- **`statistics-graph` tegner serier SIDE OM SIDE, ikke stablet — så en
  DELMÆNGDE ligner en KONKURRENT.** Bar-serier stakkes ikke i denne frontend
  (20260325.5, verificeret i `statistics-chart.ts`: `getGraphColorByIndex` pr.
  serie, og `color:` pr. entity understøttes ikke) — hver serie får sin egen
  palette-farve og sin egen søjle ved siden af naboens. En serie der er en DEL af
  nabosøjlen ser derfor ud som noget der skal LÆGGES TIL den.

  **Grafen kan ikke tegne relationen, så NAVNET skal bære den.** Husets tilfælde:
  spøgelses-forbruget (pærer der har tabt radioen mens de lyste og derfor står
  `unavailable` = 0 W i HA, men lyser fysisk videre) er en delmængde af
  lys-forbruget. Serien hedder derfor **`👻 heraf uden radio`** — ordet *"heraf"*
  gør delmængde-relationen læsbar i legenden — og markdown'en under grafen siger
  det eksplicit én gang til (`dashboards/forbrug.yaml:526-533`:
  *"Den søjle er en **delmængde** af lys-søjlen ved siden af — ikke noget der skal
  lægges til"*).

  **Og en ny serie skal ind i ALLE periode-varianter af kortet, ikke kun den ene
  du kiggede på.** `dashboards/forbrug.yaml` har kortet i fire betingede
  varianter (uge/måned/kvartal/år); spøgelses-serien måtte tilføjes i alle fire
  (i dag linje 442/461/480/498). **Signatur: et kort der ser korrekt ud lige
  indtil user skifter periode** — og så er serien væk, uden fejl. Grep altid
  serie-navnet og tæl hits mod antallet af varianter før du kalder det færdigt
  (fejlklasse #16).
- **`/api/history/period/{start}` defaulter `end_time` til start + 1 DØGN** —
  længere forespørgsler trunkeres TAVST uden `&end_time=`.
- **HA-slugify:** ø→o (`rengøring` → `rengoring`), og produktnavne staves som
  producenten (VALLHORN → `vallhorn`, dobbelt L).
- Jinja: **`repeat.index0` findes ikke** (kun `repeat.index`, 1-baseret);
  `{# #}` kan ikke ligge inde i `{{ }}`; ukendte attributter bliver Undefined
  og maskeres af forbrugerens `| int(0)`.

<!-- flyttet fra CLAUDE.md 2026-09-12 under linje-budget-oprydningen -->
- **`template.reload` er IKKE en gratis deploy — den sender HVER template-entity
  gennem `unavailable`, og uden `from:` er `unavailable → off` en gyldig
  state-flanke** der fyrer sluk-veje (målt 28/8: lyskæden slukket midt i
  madlavning). **Signatur:** en handling i præcis samme sekund som et reload. →
  Eksplicit `from:` på ENHVER `to:`-state-trigger (samme fysik som
  Matter-ekkoet, modsat retning); `automation.reload` når kun automations er
  rørt. Rammer også ægte availability-blips, ikke kun deploys. Sweep: B103.
  **MEN sweepet har undtagelser, og de er usynlige for et mekanisk patch:** en
  automation hvis FORMÅL er at handle på `unavailable → off` bliver en garanteret
  no-op af et indsat `from:` (målt 9/10: `from: "on"` i
  `airbnb_dormant_resweep_efter_blind_kanal` gjorde dens egen "kom kanalen
  tilbage fra blind?"-condition usand for evigt = fredningen blev permanent).
  Undtagelser står i `ALLOWLIST` i `scripts/b103_scan.py` — spørg altid "er
  flanken artefaktet eller BEVISET?" før du indsætter et `from:`. **Siden
  2026-10-07 blokerer pre-commit** en ny sårbar trigger (scanneren kører med
  libyaml på ~1 s; `sove_voksen_afgang_sweep` blev allowlistet samme dag —
  dens falske retur rydder kun et stempel, den sikre retning).
  **Og `from:` redder IKKE en `delay_on`-sensor:** reloadet skriver en ÆGTE
  `off`, og står udtrykket stadig sandt, kommer `off → on` præcis `delay_on`
  senere (målt 1/10: deploy 06:27:36 → brusebad-signaturen `on` 06:28:06 →
  session armeret og lyset TÆNDT i et tomt bad, fordi fugt-latchen huskede et
  bad fra 06:02). → condition på off-fasens længde
  (`to_state.last_changed - from_state.last_changed > delay_on + luft`,
  `badevaerelse_brusebad_arm`), og deploy `automation.reload` FØR
  `template.reload`, så guarden er på plads når flanken kommer.
- **En `platform: time`-trigger på en timestamp-sensor bygget af `sun.sun`s
  `next_setting` fyrer ALDRIG:** attributten hopper til I MORGEN i samme sekund
  solen går ned, så den armerede tid rykkes en dag frem hver dag før den nås.
  Sun-triggerens `offset:` kan heller ikke templates → et slider-styret offset
  kræver et VINDUE-flag. Dagens solnedgang udledes uden en `last_setting`: er
  næste solnedgang > 12 t væk, er dagens passeret og lå ~24 t før den næste
  (fejl = ét døgns ændring i solnedgangstid, maks ~3,5 min i DK). Mønster:
  `binary_sensor.sove_gardin_aftenluk_vindue`.
- **`initial:` RESTORER IKKE — den PÅTVINGER** ved hver HA-start. Skal en værdi
  overleve, så udelad `initial:` helt. Og **`input_boolean.reload`
  gen-påtvinger ALLE `initial:` i hele huset** — kør den aldrig for at aktivere
  én ny helper.
  **`input_text.reload` er husets ENESTE gratis helper-reload** (målt 9/9):
  nul `input_text` har `initial:`, mens `input_boolean` har **41** og
  `input_datetime` har 2 der er ægte divergente — `parent_a_gps_sidst_rapport` +
  `parent_b_gps_sidst_rapport` ville falde til `2000-01-01` og dermed lyve om
  GPS-friskhed. Skal en ny helper bære tilstand og deployes uden restart, så
  vælg `input_text` og kod værdien som en streng (fx `<fase>:<epoch>`).
  Mønster: `packages/airbnb_checkin_prep.yaml`.
  **`input_datetime.reload` er OGSÅ gratis** (målt 2026-10-28, B256): de to
  GPS-stempler MED `initial: 2000-01-01` stod urørte efter reloadet — 9/9-
  påstanden ovenfor var en slutning, ikke en måling. Kilden er den samme som
  for input_number: `async_update_config` sætter kun config, aldrig værdien.
  **`input_number.reload` er OGSÅ gratis** (målt 2026-10-05: før/efter-diff
  af alle 778 input_numbers = 0 ændret). HA's `async_update_config` bevarer
  den aktuelle værdi og klemmer den kun ind i min/max; en NY slider oprettes
  på `min` (ingen restore) → API-set den bagefter. De 16 med `initial:`
  (styrbar-indekser, `styrbar_ct_kelvin_sove`, `entre_mode_idx`,
  `scene_spread_level`) stod alle på deres `initial` — tjek
  `attributes.initial == state` i /api/states før reload, og at ingen står
  uden for min/max. Første brug: `global_putte_loft_kelvin`.
- **`delay_on` + `delay_off` på SAMME template-udtryk bevogter kun ÅBNINGEN.**
  Et 1-samples blip renderer templaten True et øjeblik og annullerer det
  ventende `delay_off` — uden at opfylde `delay_on`. Holdet re-armes altså af
  præcis det blip der ikke må kunne åbne det, og en 6-min hold kan stå on i
  timer. **Signatur:** en sensor hvis `last_changed` er mange gange ældre end
  dens `delay_off`, mens dens state-template renderer False. → Split i to
  sensorer: én BEVIS-sensor med `delay_on` (og intet `delay_off`), og én
  HOLD-sensor med `delay_off` der læser beviset.
  **NB — et templated `delay_off` skal være SEKUNDER som bar skalar.**
  `minutes:`/`seconds:`-undernøglerne kræver en **statisk float**; kun
  skalarformen må indeholde en template. Skriver du
  `delay_off:\n  minutes: "{{ ... }}"`, vælter det ikke bare den ene sensor —
  det dræber HELE `template:`-nøglen i filen (se alt-eller-intet-bulletten), mens
  filens `automation:`/`input_*:` loader som om intet var galt. Målt 2026-09-12c
  i `packages/regn_nu.yaml`: husets øvrige **27** templatede `delay_off` brugte
  alle skalarformen, denne ene gjorde ikke, og prisen var to sensorer der aldrig
  havde eksisteret i 15 dage. Ret til sekunder × 60.
- **Recorderens `context_user_id`-kolonne er TOM** — brugeren står i
  **`context_user_id_bin`**. Samme for `context_id`/`context_parent_id` → brug
  `*_bin` + `hex()`. Læser du den gamle kolonne, ligner hvert fingertryk en
  automation.
- **"Blev state-skift B forårsaget af skift A?" besvares af `parent_id`, ALDRIG
  af `context.id` — og et HA-context-ID er en ULID, hvis første ~10 hex-tegn er
  et millisekund-stempel.** Et forælder-barn-par fødes i samme millisekund og
  deler derfor præfikset ALTID, mens de fulde ID'er er forskellige. Sammenligner
  du afkortede ID'er (et debug-print, et `[:10]`), får du en falsk match;
  sammenligner du fulde `context.id`, får du en gate der aldrig er sand = en
  no-op der ligner et fix. Korrekt: `B.context.parent_id == A.context.id` (målt
  9/9: `house_mode` → AirBnB `id=…C872…` og det tvungne `house_state` → Active
  `parent=…C872…`, men `id=…EDF9…`). **Signatur:** et replay der siger "din nye
  regel gør ingenting" — mistænk reglen før replayet.
- **HA-slugify:** ø→o (`rengøring` → `rengoring`); produktnavne staves som
  producenten (VALLHORN → `vallhorn`). **Entity_id'et afledes af `name:`, ALDRIG
  af `unique_id:`** — "Open-plan mørk indedag" bliver
  `open_plan_mork_indedag`. Rammer du forkert, fejler intet: sensoren findes,
  forbrugeren læser tomt, og dens egen guard returnerer false for evigt. Og
  unique_id'et kan ikke bare rettes bagefter — det gamle object_id er optaget, så
  entity'en får `_2`. Slå sluggen op i `/api/states` efter første restart.
- **Jinja:** `repeat.index0` findes ikke (kun `repeat.index`, 1-baseret);
  `{# #}` kan ikke ligge inde i `{{ }}`; ukendte attributter bliver Undefined og
  maskeres af forbrugerens `| int(0)`; der findes **ingen `exp()`**, men
  konstanten `e` og `**` virker — skriv `e ** x` (brugt i Magnus-Tetens).

<!-- flyttet fra CLAUDE.md 2026-09-17 under linje-budget-oprydningen -->
- **En `template:`-blok er ALT-ELLER-INTET pr. fil: én ugyldig sensor dræber
  HELE `template:`-nøglen i den fil** — mens filens `automation:`, `input_*:`,
  `rest_command:` osv. loader helt normalt. Der er ingen delvis load, og der er
  ingen advarsel ved commit, deploy eller reload.

  **Signatur: en fil der ser HALVT rask ud, og entities der hverken er
  `unavailable` eller findes i entity-registry — altså FULDSTÆNDIG fraværende.**
  Den skelnen er hele diagnosen: en `unavailable` entity er en stale reference
  (integration nede, device væk, registry-orphan), mens en entity der slet ikke
  er i registry aldrig er blevet født = configen blev afvist. Se altid efter
  hvilken af de to det er, før du leder efter en død enhed.

  **Log-grep-opskriften er kontraintuitiv: grep på `template|package` +
  `error|invalid`, IKKE på entity-navnet.** Fejlen hedder
  `Invalid config for 'template'` og nævner **ikke** den sensor der er skyld i
  den, så et grep på entity_id'et giver nul hits og bekræfter fejlagtigt at
  "der står intet i loggen". (Fundet 2026-09-12c: grep'et fandt først svaret da
  det blev udvidet fra `regn_nu` til `template|package`.)

  **To kendte udløsere, begge ren YAML-syntaks:**
  1. **`time_pattern` tager `*`, ét heltal eller `/N` — en komma-liste er
     ugyldig.** `minutes: "4,14,24,34,44,54"` vælter hele blokken; skriv seks
     separate triggers. (`/10` ville være kortere, men flytter tikket til :00 og
     lander oven i `dmi_weather`s :12 og varsel-sensorernes :25/:55 — offsettet
     er bevidst.)
  2. **Et templated `delay_off` skal være SEKUNDER som bar skalar** —
     `minutes:`-undernøglen kræver en statisk float. Se `delay_on`/`delay_off`-
     bulletten ovenfor.

  **Prisen, målt:** `binary_sensor.regn_nu_observeret` + `sensor.regn_nu` i
  `packages/regn_nu.yaml` havde aldrig eksisteret. `terrasse_plug.yaml:174`
  læser den første som sin **kilde 1, "regn MÅLT lige nu"** — netop den kilde der
  blev bygget fordi begge prognose-kilder missede en byge — og den havde stået
  konstant false i **15 dage**, uden ét rødt flag nogen steder.

- **Lokale add-ons deployes fra `/addons/<slug>/`, IKKE fra git-kopien i
  `/config/addons/<slug>/`.** Det er **to uafhængige filtræer** — en almindelig
  `cp -r`-kopi, ikke et symlink, ikke et bind-mount — og **Supervisor kigger kun
  på det første**. Redigerer du kun git-kopien (som er den der ligger i repoet og
  derfor den du naturligt åbner), deployer du ingenting.

  **Signatur — og den er ondskabsfuld, fordi ALT ser rigtigt ud:** `rebuild`
  svarer `{"result":"ok"}`, add-on'et genstarter faktisk, loggen ser sund ud, og
  symptomet forsvinder ofte i et par minutter fordi genstarten i sig selv healer
  en hængende proces. Men `info` melder stadig den **GAMLE `version`**. Et
  samtidigt restart-heal ligner altså et verificeret fix. **Verificér ALTID på
  `version`-feltet i `/addons/<slug>/info` — aldrig på at logget ser sundt ud.**

  **Sekvensen der virker:**
  1. `cp` filerne til `/addons/<slug>/` **FØRST** (ellers er resten støj).
  2. `POST /store/reload` — Supervisor genindlæser det lokale add-on-repo, så den
     opdager den nye `version:` i `config.yaml`.
  3. `POST /addons/<slug>/update` **UDEN body**.

  **Hvorfor ikke `rebuild`, og hvorfor ingen body:**
  - `rebuild` afvises med **`app_rebuild_version_changed_error`** når `version:`
    i `config.yaml` er bumpet. `rebuild` er til "byg samme version igen"; en
    versions-ændring er pr. definition en *update*.
  - `update` afviser **`{"version": ...}`** i body'en med **"extra keys not
    allowed"**. Versionen tages fra `config.yaml`, ikke fra kaldet — derfor er
    `/store/reload` i skridt 2 ikke valgfri.

  Husets eneste lokale add-on er `gesture_frame_shim` (mappe-slug
  `gesture_frame_shim`, **Supervisor-slug `local_gesture_frame_shim`** — brug
  det sidste i API-kald). Begge træer stod på `0.8.4` ved kontrollen 2026-09-17,
  og `/addons/local_gesture_frame_shim/info` gav
  `version: 0.8.4, version_latest: 0.8.4, state: started` = deployet og i sync.

- **Et add-on's host-port (`ports:` / `network` i `/addons/<slug>/info`) er en
  dør UDEN HA-login — på LAN'et OG tailnettet.** Ingress beskytter kun vejen
  gennem HA's UI; den samme container-port mappet ud på værten (`8099/tcp: 8099`)
  svarer enhver der kan nå `192.0.2.151` eller `198.51.100.101`. Add-ons der
  taler sammen gør det over Docker-nettet (`core-mosquitto:1883`,
  `http://local-gesture-frame-shim:8090`), og ingress går direkte til
  container-IP'en — ingen af dem bruger host-porten.

  **Målt 2026-10-25 (B251):** `hand_recognition` (8099) udleverede `/api/config`
  inkl. MQTT-passwordet for `gestus` og `/api/snapshots` (dengang 100 køkken-billeder, nu 10 — B273),
  og `gesture_frame_shim` (8090) udleverede køkkenkameraets aktuelle billede
  (`/api/koekken/latest.jpg`, 200 `image/jpeg`) — alt uden login. Mosquitto
  havde 1883/1884/8883/8884 åbne på værten, så det lækkede password kunne
  publicere falske gestus på `hand-recognition/koekken`. Broker-loggen 17/9-25/10
  havde KUN klienter fra `172.30.32.1` (HA) og Docker-nettet. Alle tre mappinger
  sat til `null` via `POST /addons/<slug>/options {"network": {...: null}}` +
  restart; kæden HA → `house/gesture/scan` → snapshot → svar verificeret bagefter.

  **Signatur:** en `ports:`-linje i et add-on som ingen LAN-enhed forbinder til.
  → `null`, medmindre en enhed UDEN FOR NUC'en skal ind (Volumio henter
  `spotify_bro`'s stream på 8098; MA's afspiller-protokoller). Tjek fladen:
  `ss -tlnH` i SSH-add-on'et (host-net) + `curl http://192.0.2.151:<port>/`.
  Et nyt LAN-MQTT-device (Shelly, Tasmota …) kræver 1883 åbnet igen.

- **Supervisor nægter ETHVERT add-on adgang til systemdisken** (målt 28/10, B272):
  et lokalt add-on med `devices: [/dev/sda]` + `privileged: [SYS_RAWIO]` bygger
  og starter, men device-mappingen bliver tom, og Supervisor-loggen siger
  `App <navn> tried to access blocked device sda!`. SSH-add-on'et har `smartctl`
  men får "Operation not permitted" på `/dev/sda`. **HA Core-containeren er
  derimod privilegeret** (`docker inspect homeassistant` → Privileged=true): den
  kan åbne `/dev/sda`, læse `/sys/block`, `/sys/class/hwmon` og `dmesg`. Derfor
  kører `scripts/nuc_smart.py` som command_line-sensor i HA selv og taler ATA
  gennem SG_IO (ATA PASS-THROUGH 16, kun SMART READ DATA/THRESHOLDS/LOG + RETURN
  STATUS) — facit identisk med `smartctl -x`. **Signatur:** et add-on der
  starter og dør med exit 2 uden fejl i sit eget log.

- **Skrive-bytes pr. add-on måles på Docker-socket'en, og en fil der slettes
  inden 30 s når aldrig disken** (målt 28/10, B273). `curl --unix-socket
  /var/run/docker.sock http://localhost/containers/<navn>/stats?stream=false&one-shot=true`
  → `blkio_stats.io_service_bytes_recursive` (op `write`) er containerens præcise
  bytes til disken; Supervisor-API'ets `blk_write` er 0 for alle, og `docker stats`
  runder for groft til et 10-min-vindue. Hostens journald og ext4-journalen (jbd2)
  står i ingen container (≈ 6,5 GB/døgn 28/10) → **`python3 scripts/nuc_skrivere.py`**
  læser `wbytes` fra hver `io.stat` i HOSTENS cgroup-træ via en kortlivet
  `--cgroupns=host`-container (summen = sda): journald 4,9 GB/døgn, ~50× sin
  tekst-mængde (14.800 linjer/t, 78 % fra hand_recognitions 2 INFO-linjer pr. billede). Kernen skriver beskidte sider
  efter `vm.dirty_expire_centisecs` = 3000: hand_recognition gemte hvert billede
  som jpg i et galleri på 100 (~72 s levetid ved 1,4 billeder/s) = 15 GB/døgn;
  ved 10 (~7 s) slettes filen før write-back, og containeren skrev 0,49 GB/døgn —
  selvom processens `/proc/<pid>/io` `write_bytes` stadig viser ~16 GB/døgn
  (de annullerede bytes tæller med dér). **Signatur:** et add-on hvis blkio står
  i et fast forhold til en fil-rotation.

- **Music Assistant-add-on'en (`d5369777_music_assistant`, 2.10.5, installeret
  2026-10-09 til B204 "Spotify via HA") kræver login på sit API.** Admin-brugeren
  blev oprettet via `POST :8095/setup`; navn + password står i secrets.yaml
  (`music_assistant_*`, gitignored). Al konfiguration går over websocket'en
  (`/ws`, `auth` med token fra `POST /auth/login`) → **`scripts/ma_api.py`**
  (kør i HA-containeren; add-on'en skal køre). Konfigurationen lever i add-on'ens
  data og overlever stop/start.

  **Boot står på `manual`, og `input_boolean.hoejttaler_spotify_via_ha` ejer
  start/stop** (automationen `hoejttaler_spotify_metode`). Off stopper add-on'en.
  Siden 09/10 står knappen ON permanent: myair OG "Højttaler via HA" side om side,
  og HA spiller sange via `script.hoejttaler_spil_sang` (B205).
  En manuel start fra UI'et mens knappen står off får lov at køre videre.

  **Streams-`bind_ip` SKAL være LAN-IP'en (192.0.2.151).** Uden den
  annoncerede MA's Spotify Connect-plugin (go-librespot) sig på ALLE NUC'ens
  adresser, med Tailscale-adressen 198.51.100.101 FØRST. go-librespots
  `zeroconf_interfaces_to_advertise` afledes af bind_ip. **Signatur: telefonen
  ser "Højttaler via HA", men den forbinder aldrig.**

  **Pause i Spotify-appen på enheden "Music Assistant Playback" når IKKE
  højttaleren** (B207, 09/10 18:37). Spiller MA selv et Spotify-nummer, kører det
  i soloist-motoren, som er en Connect-enhed på kontoen. Appens pause pauser kun
  motoren, mens MA's kø og DLNA spiller videre på en tom strøm. Efter ~20 s
  melder MA "Source stalled … aborted by a stream error - skipping" og SPRINGER
  TIL NÆSTE NUMMER. **Signatur: pause i appen → ~25 s senere spiller det næste
  nummer.** Og **go-librespots dealer hænger og kommer aldrig selv igen**
  ("did not receive last pong from dealer, Ns passed" hvert 30. s, målt op til
  8490 s); `config/providers/reload spotify_connect` kurerer det på 1 s.
  → daemonen **`scripts/ma_watch.py`** (SSH-add-on'ens init_commands) læser MA's
  log: soloist `paused <track>` → `player_queues/pause` på køen med nummeret;
  dealer ≥ 90 s → reload (max 1×/30 min, aldrig mens en kø spiller).
  Kill-switch `input_boolean.hoejttaler_spotify_vagt_enabled`. Begge signaler er
  DEBUG-linjer: sættes MA's log til INFO, er vagten blind.
  **Soloisten lukker ~20-25 s efter pausen** (`shutting down`, målt
  18:38:09→18:38:33), og så er "Music Assistant Playback" væk fra appen → appens
  play kan kun genoptage højttaleren inden for det vindue (soloist `playing`
  samme nummer efter vores pause → `player_queues/play`); senere er Lys-sidens
  play vejen (Volumio-overriden genoptager MA-køen fra flow-URL'ens queue_id).
  **MA's kø-objekt har intet `current_item.uri`** — nummeret står i
  `current_item.media_item.uri` / `streamdetails.item_id` (det tavse hul der
  gjorde B207's første app-pause-match til et no-op).

  **Under DLNA-afspilning lyver Volumio om KILDEN:** getState følger MPD's
  play/stop, men uri/service/titel bliver stående på det sidst spillede (målt
  09/10: viste P4, mens MPD spillede MA's strøm). Kilden læses i MPD selv
  (port 6600, `currentsong` → fil på `:8097/`) — `kilde=ha` i
  `sensor.hoejttaler_spotify`.
  **Og den bliver STALE på `play` når MA's strøm er slut** (målt 09/10 16:46:
  Volumio play, MPD stop) → "spiller der noget?" afgøres af MPD når den siger
  stop/pause, ikke af `media_player.hoejttaler` alene.

  **Et shell_command-svar med JSON-booleans native-parses IKKE** (HA's native
  types er Python-literal; `true` ≠ `True`) → variablen forbliver en streng, og
  `svar is mapping` er falsk. `{"url": …, "sekunder": 11}` slipper igennem, så
  fejlen ses først når svaret får et `ok: true`. → `| from_json` (B205: en sang
  der spillede blev stoppet som "fejlet" efter 4 s).


**Radio / hardware**
- **Et `light.turn_on` med N pærer returnerer først når den LANGSOMSTE har svaret — en hurtig effekt der
  sender ét gruppe-kald pr. frame, går i takt med husets dårligste radio-link.** Målt 23/9 på et festlys-police
  (trace): `spisestue_loft` (ZHA) hang 5,4-5,6 s hvert 6.-8. kald (APS-retry), Matter-spotsene 1,5-2,4 s; en 4 s
  effekt kørte 52 s, og hele showet frøs i hvert hæng. Normale kald p50: ZHA 117-165 ms, Matter ~190 ms.
  **Signatur:** en effekt der varer mange gange sin designede tid, og som fryser i ~5 s ad gangen på ALLE pærer.
  → Én løkke pr. pære på et fælles ur (`script.dance_event_bulb`): hver udregner sin frame af uret og venter kun
  på sig selv, så en hængende pære misser slag og falder i takt igen. Takten pr. pære skal ligge over den målte
  p50 (police 0,25 s, ikke 0,1 s).
- **Matter-pærerne deler ÉN flaskehals, og et farvet `turn_on` er TO Matter-kommandoer** (`moveToHueAndSaturation`
  + `onOff.on`/`moveToLevelWithOnOff`, i serie). Målt 11/10 (festlys chase, begge stue-spots, matter-server-loggen):
  ~5,6 kommandoer/s i alt, p50 193 ms / p90 297 ms pr. kommando (solo ~95 ms) ⇒ ~0,1-0,15 s × antal Matter-pærer
  pr. kommando. 2,4 % gensendes (`1↔2+1` i loggen) og hænger hver ~5,2 s — samme rate som husets normale døgn
  (0-3 %/time), så det er ikke et sygt net, bare synligt ved 5+ kommandoer/s. Før fixet nåede spotsene 42 % af
  chase-ticks i tilfældig rækkefølge ("ustabile events"). **Signatur:** Matter-pærer der hakker/kommer ud af takt
  i en hurtig effekt, mens en ZHA-pære ved siden af holder takten (p50 114 ms). → `dance_event_bulb` får `inv`
  (s pr. kommando, 0 for ZHA) og spiller kun hvert mm'te tick på det fælles ur. Åbent: eventets FØRSTE kald hænger
  33 % af gangene mod 2,4 % for resten (B222). **Afløst 25/10 (B260):** `inv` holdt hver pære i takt, men ikke
  HUSETS sum under RCP'ens grænse — Thread-pærerne er nu helt ude af koreografien (næste afsnit om festlys' gitter).
- **Et FARVET `light.turn_on` er TO zigbee-frames pr. pære; et `turn_off` er én.**
  Zigbee har ingen kommando der sætter farve og niveau samtidig, så ZHA sender
  color-cluster + level-cluster hver for sig. Målt 30/8 over 3 døgn på husets tre
  varsel-pærer der faktisk er på nettet (`spisestue_loft`, `stue_laesehygge`,
  `koekken_lyskaede`), som tid fra første til sidste pære i samme service-kald:

  | bølge | p50 | p90 | max |
  |---|---|---|---|
  | ON (farve + brightness) | 101 ms | 275 ms | 554 ms |
  | OFF (bart turn_off) | 58 ms | 85 ms | 112 ms |

  Præcis 2:1 = farve-framen. Målt på hele bølgen med 2 s clustering (179 bølger)
  var vejr-varslets gamle blink-løkke, der gen-sendte farven ved HVERT blink:
  p50 124 ms, **p90 2314 ms**, max 2789 ms — hver tiende blink havde en pære mere
  end 2,3 s bagud. Det ligner et overloadet net og er det ikke: `spisestue_loft`
  blev målt **5,2 s** bagud på ét enkelt `move_to_color`, mens dens rene on/off
  lå på 30-70 ms. **Grebet:** sæt farven ÉN gang før løkken, lad blink 2..n være
  rene niveau-kald — zigbee-pærer beholder sidst-aktive farve hen over et sluk.
  Efter (`script.vejr_varsel_blink`): p50 76 ms, **p90 100 ms**, max 314 ms.
  **Trade-off:** taber en pære netop den første, farve-bærende frame, blinker den
  resten af blokken i forkert farve i stedet for at selv-hele.
  **Følgeregel:** et blink hvis ON-fase er KORTERE end bølgen kan aldrig se
  synkront ud — sne-varslets 120 ms betød at sidste pære typisk tændte efter at
  slukket var sendt. Gulv var derfor 250 ms (≈ 3× målt p90) indtil grupperne kom.

- **ZHA-GRUPPER: husets eneste to er `light.zbt_2_vejrvarsel_morgen` (zigbee.db
  `groups_v15` id 2) og `light.zbt_2_vejrvarsel_aften` (id 3).** Oprettet 30/8
  som den strukturelle løsning på ovenstående (user-valg: *"byg den nu med de 3
  levende"*). Medlemmer, alle endpoint 1:
**2026-09-23:** køkken-lyskæden er fjernet fra begge grupper (user-spec: vejr-
varsler må ikke bruge den). Group 3 har nu kun spisestue_loft, og ZHA laver
ingen gruppe-entity under 2 medlemmer → `light.zbt_2_vejrvarsel_aften` findes
ikke længere; aften-blinket går unicast til `light.spisestue_loft`. Medlemskab
ændres over websocket (`zha/group/members/add|remove`), ikke via en service.

  | gruppe | medlemmer |
  |---|---|
  | morgen (2) | spisestue_loft, stue_laesehygge, koekken_lyskaede |
  | aften (3) | spisestue_loft, koekken_lyskaede |

  To grupper og ikke én, fordi aften-rosteret **bevidst** er uden
  `stue_laesehygge` (user-valg 2026-07-02) — ét groupcast kan ikke ramme to
  forskellige sæt. De tre B91-pærer (`stue_sofa_lampe`, `_2`,
  `stue_hjoernelampe`) er strømløse og kan derfor ikke få skrevet en
  group-binding; de står stadig i automationens `lamps`-liste, men den bruges nu
  KUN til `scene.create`-snapshot og restore. **Blink går til `blink_lamps` =
  gruppe-entity'en.** Kommer pærerne tilbage, skal de tilføjes GRUPPEN — at stå i
  `lamps` giver dem snapshot og restore, men ikke blink.

  **Oprettelse/ændring findes kun på WebSocket-API'et** (`zha/group/add`,
  `zha/group/remove` med `{"ieee": ..., "endpoint_id": 1}`); der er intet
  REST-endpoint. `python3` har `websockets` installeret, `aiohttp` og
  `websocket-client` har ikke. Medlemskabet skrives i pærens NVRAM, så det
  overlever ikke en re-pair og findes ikke i git — kun i `zigbee.db`.

  **Trade-off:** et gruppe-frame er broadcast, altså **ingen APS-ACK pr. pære**.
  Misser en pære frame'et, er der ingen retry (unicast havde en). Accepteret med
  samme argument som farve-grebet: hver effekt-blok sætter forfra, og bookends
  re-asserter.

  **Fælde 1 — gruppe-detektion:** en ZHA-gruppe eksponerer sine medlemmer i
  attributten **`group_entities`**, mens HA's egne lysgrupper (`alle_lys`,
  `*_all`, …) bruger `entity_id`. `light_watchdog`'s "sluk ALDRIG en gruppe"-guard
  testede kun `entity_id` og så derfor ikke de nye grupper — et watchdog-sluk
  ville være blevet et groupcast til alle tre pærer. Guarden tester nu begge
  markører; nye gruppe-typer tilføjes dér, ikke som en entity-navne-liste.

  **Fælde 2 — måling:** ZHA skriver **antaget** state på medlemmerne efter et
  gruppe-kald, så deres recorder-rækker ligger < 3 ms fra hinanden uanset hvad
  radioen faktisk gjorde (målt 30/8: 0,4-3 ms spredning på tre pærer, hvilket er
  fysisk umuligt over luften). Recorderen kan altså ikke længere bevise et
  gruppe-blinks synkronitet. Kun pærernes **egne** attribut-reports er ægte
  målinger — de kom 358 ms fra hinanden på bookend-kaldet i samme kørsel, og de
  beviser at pærerne modtog og udførte gruppe-kommandoen. NB recorder-semantik:
  `last_changed_ts IS NULL` = ægte state-skift (last_changed == last_updated);
  `IS NOT NULL` = kun-attribut-opdatering.

  Med bølgen væk faldt ON-gulvet fra 250 til **120 ms**, sneens designværdi.
  Pærernes egen `on_off_transition_time` er 0, så de smører ikke selv kanten ud.
  Gulvet forudsætter at målet ER en gruppe: kaldes `script.vejr_varsel_blink`
  med en LISTE, er bølgen tilbage og kalderen skal selv sende `on_ms >= 250`.
- **Apollo MSR-2'ens onboard SK6812-RGB lyser ind i sin EGEN LTR390** (+400-490 lx
  ved brightness 204). Adfærds-logik læser `sensor.<rum>_lux_reel`, **aldrig**
  `sensor.<rum>_apollo_lux`. ESPHome gamma-korrigerer både kanal og master
  (γ ≈ 2,9) — en lineær model rammer 75 % forkert.
- **En presence-sensors NAVN er et rum, dens FELT er en radius.** Apolloens
  still-rækkevidde er **6 m** — køkkenets ser sofaen 3,1 m væk, og køkkenet er
  selv kun 2-3 m dybt, så afstand kan ikke skille de to rum ad. Overlapper to
  rum i feltet, skal du skelne på en akse feltet ikke deler, og den akse er
  **rum-specifik**: kravet om et MOVING-target hører i køkkenet, aldrig i stuen
  hvor det at sidde stille ER tilstedeværelsen. Samme grund til at et filter
  ikke kan kopieres mellem rum uden at dets diskriminator gentænkes (08-20d).
- **En LEVENDE krop flytter `still_distance` konstant; et møbel holder værdien
  identisk til decimalen.** Vejrtrækning alene rykker still-targetets range-bin.
  Målt 2026-08-20 (213 samples, 1 Hz): hvert frys ≥10 s hvor occupancy stod ON
  varede max **22,5 s**, mens frys på 122 s og 231 s begge lå i rum der allerede
  var meldt tomme. Det er husets eneste maskine/menneske-diskriminator der er
  **uafhængig af afstand, rum og hvor Apolloen peger** — modsat køkkenets
  `< 75 cm`-gate og stuens varigheds-krav, som begge er rum-specifikke. Lever i
  `packages/apollo_frossen_ghost.yaml` (`binary_sensor.<rum>_apollo_frossen_ghost`).
  Skal du måle det: pollingen SKAL sammenligne på decimalen — kvantisér til
  gates, og en levende krop ligner et møbel.
- **Apollo gate-tærskler har TO lag, og SLIDEREN er autoriteten.**
  `input_number.<rum>_g<N>_<move|still>` (rum-slug `sove`/`boern`, ikke
  entity-slug) skrives af decay + jagt og pushes derfra til ESPHome-NVRAM
  `number.<rum>_apollo_g<N>_<move|still>_threshold`. Per-gate-skriverne ser KUN
  sliderens flanker (og aldrig fra `unknown`, så en restore skriver intet) — en
  direkte `number.`-rettelse blev derfor IKKE rullet tilbage (decayen rører kun
  den gate den sænker): børneværelsets g3 stod på move 50 / still 23 fra en
  direkte skrivning 5/10 til 23/10 (sliderne 15/18), og et sovende barns bursts
  (14-28) nåede ikke over → 0-30 min belægning på børnenætterne 12-17/10 og Child A
  usynlig for people count 22/10. Soveværelsets g3 still stod samtidig på 25 med
  slideren på 21 (slideren rettet til chippen, ikke omvendt). Siden 23/10
  skriver `automation.apollo_daglig_gate_sync_chip_slider` kl. 09:05 slideren til hver gate
  hvor chippen afviger (kun ved afvigelse; engineering mode = skip) — en direkte
  chip-skrivning lever altså højst til næste morgen. Skriv sliderne, vent ~5 s, og verificér BEGGE lag —
  hænger en skrivning i debounce-køen, skub med
  `script.<rum>_apollo_apply_all_gates`. At de to lag er enige beviser i øvrigt
  intet om værdien: 08-23 var de enige om 23 på gates der skulle være 100.
- **LD2410'eren leverer INGEN still-energi på gate 0 og 1 — de to tærskler er
  døde knapper.** Målt 08-24 på køkkenet (engineering mode, 193 samples i træk):
  `g0_still_energy` og `g1_still_energy` = 0,0 hele vejen, mens g2-g4 toppede på
  75/100/100. Et still-flap kan derfor ALDRIG være krydset i 0-1,50 m, og at
  hæve `g0/g1_still` (selv til 100) ændrer intet — det er ikke "nærfeltet er
  pinnet", det er "knappen er ikke tilsluttet". Move-kanalen er upåvirket og
  lever fint i g0/g1. **Følgefælde:** `sensor.<rum>_apollo_radar_still_distance`
  **hviler på ~66-67 cm** (ikke 0, ikke `unknown`) når der intet mål er, så en
  attribution der regner `gate = int(cm/75)` lander på gate 0 hver gang radaren
  ikke ser noget. Jagten guarder nu begge dele (`gate_dead`), og decay springer
  still g0/g1 over så de ikke koster NVRAM-writes.

  **MEN "død knap" betyder ikke "ufikserbart artefakt" — knappen sidder bare et
  andet sted.** Et still-udslag på g0 kan ikke tændes eller slukkes på
  still-tærsklen (den er ikke tilsluttet), men selve udslaget kommer af at
  radaren rapporterer et **sub-sekund MOVE-blip som et STILL-mål bagefter**.
  Det betyder at artefaktet er fikserbart på **MOVE-kanalen, én gate længere
  ude** end der hvor det viser sig. **Signatur: et still-mål der ligger på
  hvile-afstanden (~66-67 cm) med still-energi under ALLE rummets aktive
  still-tærskler** — ægte nærophold har energi i g2-g4-klassen (målt 59-87 mod
  ghostens 8-10), et ekko har ikke. Hæv MOVE-gaten et trin ude i stedet for at
  skrue på den døde still-knap.
  **Og giv altid den hævede gate et GULV i `input_text.<rum>_gate_floors`** —
  ellers walker `apollo_gate_decay` den stille tilbage til udgangspunktet, og
  artefaktet er tilbage om et døgn uden at nogen har rørt noget. Gulvene er
  18-slot-kodede strenge, én pr. rum (live 2026-09-17: `koekken_gate_floors`
  bærer `99`+`50`, `stue_gate_floors` `20`/`44`/`25`/`36`, `sove_gate_floors`
  `25`/`38`/`24`). Gulvet er en spærhage: decay går aldrig under det, og eneste
  vej ned er den manuelle ♻️-knap på dashboardet.
- **Et occupancy-udslag der varer PRÆCIS `number.<rum>_apollo_radar_timeout` er
  ét radar-blip uden gentagelse = maskine, ikke menneske.** Et menneske
  gen-detekteres inden timeouten udløber og forlænger udslaget; en kompressor,
  en ventilator eller et gardin giver ét enkelt hit og så stilhed. Timeouts:
  køkken/spisestue/stue/børneværelse **5 s**, soveværelse **15 s** (læst live
  08-21; noten her påstod 900 s for børneværelset og var forkert).
  **Regelen gælder ikke i soveværelset:** Apolloen taber en liggende krop og
  gen-detekterer den, så en ægte sovende giver også 14-15 s udslag. Dér er
  diskriminatoren HOLD-varighed, ikke blip-længde (08-21b).
  Målt 08-19 over 14 døgn: 48 af 63 køkken-g0-still-udslag lå på præcis 5,0 s
  (~hver 27. min = køleskabet), spisestue 973 af 1045. Filtreringen hører i HA
  (`delay_on` der kræver at detektionen overlever timeouten), ikke i gate-
  tærsklerne — de stod allerede på 100. Mistænker du spøgelser: tæl
  udslags-VARIGHEDER først, det er billigere og mere entydigt end at tune gates.
- **Soveværelsets Apollo fantom-fyrer i eftermiddagssolen** — målt 08-15: 9
  korte occupancy-udslag 12:42-16:11 UTC i et beviseligt tomt hus (robot dokket,
  gardin urørt på 100), ophørende netop som solen forlader det sydvendte vindue.
  Det gør `binary_sensor.physical_presence_recent` ubrugelig som "huset er
  tomt"-vidne om dagen, fordi hvert udslag frisker `last_physical_activity`s
  3t-vindue. Skal du bevise et tomt hus, brug **bredde** (en fantom rører ét
  rum, et menneske rører flere) — ikke stilhed. `apollo_latch_detect.yaml`
  fanger den ikke: den toggler pænt on/off og er derfor ikke en latch. → B73.
- **Børneværelsets Apollo-lux er upålidelig** (ting stilles foran sensoren, ensidet
  fejl) → `sensor.boernevaerelse_lux_reel` afledes af open-plan × 35 %.
- **Sove-Apolloen taber en person der LIGGER STILLE i 5-15 min ad gangen** (målt
  natten til 2026-08-11: "tomt" 04:20:30→04:35:30 med en sovende i sengen). Et
  "tomt rum" i soveværelset er derfor IKKE bevis for fravær — mindst af alt i
  vække-vinduet, hvor rampen pr. definition lyser på en krop der ligger helt
  stille. Auto-sluk dér skal gates på `binary_sensor.sove_alarm_morgen_vindue`.
  **Og omvendt: at rummet bliver optaget IGEN beviser ikke at nogen er STÅET
  OP.** Occupancy er still ELLER moving, så en sovende der gen-detekteres på
  vejrtrækningen har samme signatur som en der rejser sig. Ingen tids-tærskel
  kan skille dem: målt 08-25 gav en sovende Parent B off-huller på 8,3 · 10,7 ·
  11,3 min (17,1 min 08-22c), mens "ægte anden krop"-båndet er 13,6-38,9 —
  bandene OVERLAPPER. Et 8-min-krav gjorde derfor et 8 min 18 s hul til "to
  personer oppe" og rullede gardinet op over en sovende. Skal du bevise at nogen
  er OPPE, kræv `binary_sensor.<rum>_apollo_radar_moving_target` — samme akse
  som børneværelsets morgenlys.
  NB `*_apollo_radar_still_target`/`_moving_target` er UDE af recorderen (kun
  `*_apollo_occupancy` kan graves i historikken).
- **Soveværelsets Apollo sidder LIGE VED DØREN til entréen, så `moving_distance`
  er husets eneste RETNINGS-signal** (målt 08-25 med 1 Hz-polling): på vej ud
  falder den mod sensoren (151 → 87 → 47 cm), på vej ind stiger den (100 → 147
  → 240 cm), og sengen ligger på 229-240 cm. Kløften er bred — dørzonen skiller
  "på vej ud" fra "vendte sig i sengen", og det er dét krav der bærer både
  **to-oppe-detektionen OG voksen-afgangs-sweepet** HELT ALENE.

  **Tærsklen er `input_number.sove_morgen_2p_doerzone_cm`, og SLIDEREN er
  autoriteten — ikke et tal i en note.** Denne bullet påstod **120 cm**; den
  live-værdi er **140,0 cm** (aflæst 2026-09-17 via `/api/states`). Rettet her,
  men gentag aflæsningen før du regner på den: en note er et tidsstemplet gæt,
  slideren er facit (📏-reglen).

  **Retningen aflæses på `trigger.from_state`, ikke på slutværdien.** En
  `below`-crossing af dørzonen hvis `trigger.from_state` er et **TAL over
  dørzonen** er en ÆGTE udgående sweep (nogen bevægede sig fra sengesiden mod
  døren). Er `from_state` derimod `unknown` — fx `unknown → 50` — er det nogen
  der KOMMER IND ad døren og dukker op i feltet tæt på sensoren; samme
  slutafstand, modsat betydning.
  **Et "A og derefter B"-krav over to rum duer ikke som bevis:** på testturen
  sås `entre_valhorn_occupancy` ON ét sekund FØR radarens moving target, fordi
  en tredje krop stod i entréen — og VALLHORN'en er desuden blind 10,2 % af
  tiden. Rækkefølge-kravet er fjernet 08-26 (user-spec). Lad afstanden bære
  beviset alene. **NB: distance-sensorerne er `unknown` uden mål — ikke 0 — og
  det er selve retnings-diskriminatoren.** `| float(0)` oversætter "intet mål"
  til **0 cm = tætteste mulige afstand**, altså det stærkest tænkelige "nogen
  står lige ved døren"-bevis, hver eneste gang radaren ikke ser noget. Brug
  `| float(-1)` og test eksplicit for den negative sentinel. (Samme default-fælde
  fabrikerede 5 af husets 7 Apollo-gate-gulve — se LD2410-bulletten.)
- **Husets Thread-routere er de tre KAJPLATS-spots i badet (node 75/206/234) —
  plus entré-loftet (node 461) siden 2026-08-21.** Falder badets tre, kaskaderer
  halvdelen af Matter-nettet — det ligner et OTBR-kollaps og er det ikke. Entré-
  pæren blev valgt netop for at bryde den enkelt-punkts-afhængighed, og at den
  FAKTISK router er nu verificeret (`read_attribute 0/53/1` = 5 = Router, målt
  08-21 kort efter parring) — men den er på en VÆGKONTAKT: slukkes den fysisk,
  forsvinder routeren. Gen-verificér mod noden, ikke med `ot-ctl router table`:
  den viser kun extended MAC, og den skifter ved hver gen-parring, så den kan
  ikke mappes til et node-id.
  **⚠️ Node-id'erne ovenfor er DECIMAL, men matter-server-add-on'ets log skriver
  dem i HEX** — de tre spots er `@1:4b`, `@1:ce`, `@1:ea` og entré-loftet
  `@1:1cd`. **Signatur: du greper `@1:75` i loggen under en OTA og får nul hits,
  selvom transferen beviseligt kører** (`update_percentage` tæller op), og
  konkluderer fejlagtigt at der ikke sker noget. Greper du efter en node, så
  konvertér først: `printf '@1:%x\n' 75`. Loggens tidsstempler er desuden
  **lokal tid**, i modsætning til `/api/history` og `last_changed`, der er UTC
  (fejlklasse #18) — bland dem ikke i samme tidslinje.
- **NUC'en har TO BLE-adaptere, og indekserne er omvendt af hvad man gætter:
  `hci0` = USB-donglen `FB:69:F4:31:2E:61` (virker), `hci1` = Intel
  `52:AF:C5:8A:62:27` (duer IKKE til commissioning — user-spec — og HA's egen
  bluetooth-integration deler den).** Matter-addon'ets `bluetooth_adapter_id`
  SKAL være `0`. Står den på `1`, er signaturen ikke "ingen BLE": scanningen
  finder enheden, PASE lykkes, og parringen dør så konsekvent på
  `SendPAICertificateRequest` med timeout, fordi PAI-certifikatet er den første
  besked der skal fragmenteres over BTP. Det ligner en pære der ikke er i
  parringstilstand — og et fabriksreset er da netop den forkerte konklusion.
  `bluetoothctl list` viser kun MAC, ikke hci-nummeret; D-Bus-opskrift +
  resten af parringsfælderne i
  [docs/matter_pairing_playbook.md](matter_pairing_playbook.md) — læs DEN
  FØRST, den havde begge dagens rodårsager beskrevet i forvejen.
- **IKEA GRILLPLATS (Thread-plug, VID 4476 / PID 4096) kan IKKE commissiones
  over BLE fra NUC'en.** Målt 2026-09-23 over ~20 forsøg på to eksemplarer:
  BLE-connect lykkes (typisk efter ét `0x3e`-retry), GATT + MTU 247 +
  BTP-håndtryk lykkes (svar `656c04f10005`: v4, MTU 241, vindue 5), og så
  svarer pluggen ALDRIG på den første PASE-besked (PBKDFParamRequest, ~105 B).
  Identisk i matter.js (noble/HCI, `Acknowledgement for the sent sequence number
  was not received`) OG i CHIP-SDK'en (python-matter-server i en midlertidig
  container via BlueZ, `PASESession timed out … Expected message type was
  33`), på BÅDE CSR-donglen (BT 4.0) og Intel (DLE) — så det er hverken
  matter.js, adapteren, afstanden (< 1 m), DLE eller HA's BT-integration
  (slået fra: samme fejl). Factory reset og frisk strøm ændrer intet. KAJPLATS-
  spots parrede samme dag på første forsøg med samme opsætning. Upstream:
  [matterjs-server #929](https://github.com/matter-js/matterjs-server/issues/929)
  (åben, "probably-vendor-issue"); community-løsningen er HA-appens
  Android-flow (telefonens BLE-stak) — og den VIRKEDE (plug 2, 2026-09-23,
  `switch.grillplats_plug`), men først efter nedenstående netværks-fix.
- **Telefon-commissioning (Android/Google Play Services) fejlede i huset af en
  NETVÆRKS-grund, ikke en URL- eller cache-grund.** Målt 2026-09-23: første
  telefon-forsøg nåede Thread (plug registrerede sig i OTBR's SRP på Googles
  fabric `A360F32F0753488A`, lease 7149/7200 s = sekunder gammel), endte i
  "Unable to connect", og Matter-serveren + HA-core så NUL kald — heller ikke
  efter "Linkede apps → Home Assistant" fra Android-indstillingerne (dér
  tilføjede Google blot en 2. node-id på sin egen fabric, intet `_matterc`).
  Årsag: husets router leverer ingen IPv6; OTBR'en er den ENESTE RA-kilde
  (`br onlinkprefix` Local = Favored = `fd38:c90:a5e3:1520::/64`, ruten til
  Thread er `fd6d:ac87:0485:1::/64`), og med `backbone_interface: enp0s25`
  nåede RA'erne ingen Wi-Fi-klient: PC'en havde kun link-local, NUC'ens EGEN
  `wlp2s0` fik heller ikke præfikset, og en RA fanget ud af `enp0s25` kl.
  17:19:10 (efter OTBR-restart) gav stadig intet på PC'en. Unicast IPv6
  kabel↔Wi-Fi virker (link-local ping 2-5 ms) — det er RA/multicast der ikke
  krydser. Efter `backbone_interface: wlp2s0` + OTBR-restart: PC fik
  `fda4:`-adresser, rute til `fdb8::/64` via NUC'ens Wi-Fi link-local, og
  pingede en Thread-node (~550 ms). Næste telefon-forsøg lykkedes. Backbone
  stod på `wlp2s0` fra start, men blev flyttet til `enp0s25` 2026-06-07 fordi
  Wi-Fi'en var nede efter flytning — det lukkede telefonvejen. NB: tcpdump
  findes på HOSTEN, ikke i OTBR-containeren (`docker exec … tcpdump` fejler,
  og et `| grep` skjuler fejlen — kostede to blinde optagelser).
  Trick undervejs: QR-koden (`MT:…`) giver den LANGE discriminator, så man kan
  se hvilken fysisk plug der annoncerer (`D:1220` i matter.js' scan-log).
- **Presence-instrumenterne er IKKE lige pålidelige, og forskellen er stor nok
  til at ændre konklusioner:** målt over 14 døgn er de 5 netdrevne Apolloer
  online **100,0 %** af tiden, mens de batteridrevne Matter/Thread-enheder er
  blinde 10-18 % (terrassedør 17,6 %, hoveddør 10,5 %, entré-VALLHORN 10,2 %;
  længste enkeltudfald 59,2 t). Da `unavailable` læses som `off` i al
  presence-logik (#9), **svarer en død kanal "her er tomt" med fuld
  selvsikkerhed** — der varsles bevidst IKKE om blindhed, fordi blinde kanaler
  er NORMALT for batteridrevne Matter/Thread-enheder. **Kør derfor
  `./scripts/ha_health.sh blind` FØR du forklarer presence-adfærd** — ellers
  bygger du en forklaring oven på et hul.
  **I AirBnB er blindheden desuden menneskeskabt:** gæster slukker
  **vægkontakter**, og en vægkontakt tager både rummets Apollo OG dets pærer —
  så rummet bliver samtidig mørkt og usynligt, uden at noget er i stykker.

  **⚠️ RETTET 2026-09-17 — denne bullet anbefalede tidligere at gate på
  `binary_sensor.activity_state_confident` / `sensor.presence_signal_confidence`.
  Det er FORKERT og modsiges af CLAUDE.md.** De to er **HUS-tal**: de aggregerer
  alle rum, så tvivl om ÉT rums kanal gates husdækkende, og en feature i
  soveværelset holdes nede fordi en dørsensor i entréen er blind. **Tvivl om ét
  rum må aldrig gates husdækkende.** Gate i stedet nye features på **rummets EGEN
  kanal** (fx `binary_sensor.<rum>_apollo_occupancy_filtered` for det rum
  featuren handler om). `presence_sensors_available` duer heller ikke: den er ON
  hvis bare ÉN sensor i huset er online, og er kun bygget som **pre-flyt-gate**
  (må vi overhovedet flytte presence-tilstand nu?), ikke som et kvalitetsmål.
  Fejlklasse #26 (hus-bred gate på rum-scopet tilstand) er præcis denne fejl.
- **En `unavailable` automation med `restored: true` er en registry-orphan, ikke
  en valideringsfejl** (huset har 61 af dem). `id`-attributten duer IKKE som
  skillelinje — orphans bærer den også. Ægte fejl = `restored` mangler, og står
  som "could not be validated" i core-loggen (#22).
- **`brightness: 1` via ZHA er et SLUK på Innr og Hue.** ZHA sender
  move_to_level_with_on_off, og når niveauet rammer pærens min-niveau, slukker
  pæren efter ZCL og melder `off`. Ramt 24/10 af halloween-stemningens udfald
  (niveau 1): depotets Hue LWE007 12:25, spisestue- og sove-loftet (Innr RB 282 C
  / RF 271 T) 18:39-18:40 og stue-læselampen 18:59 — og stemningens "kun hvis den
  stadig lyser"-guard sprang gendannelsen over, så spisestuen stod slukket i
  10 min. min_level-attributten (cluster 8, attr 2) kan ikke læses på nogen af
  dem (None / "Unknown error"), så grænsen er målt ved udfald, ikke slået op.
  → dæmp aldrig under 3, og lad en guard der vogter "stadig tændt" også godtage
  et `off` hvis context er dit eget kald.
- **`IKEA TRADFRI bulb E27 WS globe 1055lm` lander på 2 % hvis ét `light.turn_on`
  indeholder brightness + color_temp + transition > 0 samtidig.** Målt live
  08-18: 5/255 hver gang, mens de samme tre uden `transition` (eller uden
  `color_temp`) giver de bestilte 204. Det er FYSISK, ikke en falsk rapport —
  kommentaren fra 05-28 der påstod det modsatte var forkert, og entré-loftet
  lyste derfor 2 % i knap tre måneder. Husets ENESTE pære med modellen er nu
  `light.depot_loft_ikea` (entréen blev Matter/KAJPLATS 08-21 og må IKKE sendes
  gennem fixet — den kan farve og har ikke quirken). Direkte kald splittes i to
  (ct+bri 1 % snap, så bri med transition); gruppe-kald der ikke kan splittes
  efterfølges af `script.tradfri_ws_bri_fix` (packages/light_groups.yaml).
- **En RGBW-strip kan ikke crossfade mellem RGB-motoren og sin hvide kanal.**
  Sender du `color_temp_kelvin` til `light.boernevaerelse_hygge_strip` (ZHA, innr
  FL 230 C) mens den står i `xy`, skifter `color_mode`, og farven SNAPPER til
  hvid — også med en lang `transition`, for kun brightness ramper. Skal en
  farvet strip fade blødt, så bliv i ÉT color_mode: oversæt kelvin til RGB
  (`script.boern_natlys_set` gør det for natlyset). Gælder enhver blød overgang,
  ikke kun putning.
- **En pære med `power_on_behavior = Off` er usynligt død fra vægkontakten** —
  den kommer aldrig tilbage tændt efter strøm, uanset hvad automationerne tror.
  Attributten bor i pærens NVRAM (ikke i git) og overlever ikke re-pair.
  **Diagnostisk signatur:** history viser masser af `off→on`, men **nul
  `unavailable→on`**. Sove-loftet (`light.spisestue_pendel`) stod sådan indtil
  2026-08-16, med to steder i koden der antog det modsatte.
- **Stuen havde (2026-09-17) KUN to fysiske lys, og tre af rosterets fem
  entities er pærer i et skab.** Fastslået af user: *"jeg tror sofa lampen er
  gammelt skrald og en pære der ligger i et skab. stuen har kun to lys, luksus
  lampen på 40w og læselampen"*. De to ægte var `light.stue_plug` ("Stue
  Hyggelampe" — 40 W, effektmålt via `sensor.stue_plug_power`) og
  `light.stue_laesehygge`. De tre døde er `light.stue_sofa_lampe`,
  `light.stue_sofa_lampe_2` og `light.stue_hjoernelampe`. **2026-09-23 kom to
  IKEA KAJPLATS Thread-spots til** (`light.stue_spot_1`/`_2`) — stuen har nu
  FIRE fysiske lys, ikke to.

  **De bliver liggende — det er user's eget valg** (*"bare lad dem være og gør
  det til et permanent fact"*), så ryd dem IKKE ud af `sofa_lights`-rosteret,
  `light.stue_all` (7 medlemmer) eller `light.stue_room` (5 medlemmer). Se B132.
  De koster nul radiotid: HA springer selv `unavailable` entities over i
  service-kald.

  **Måledata (14 døgn, recorder, 2026-09-17), unavailable-andel:**

  | Entity | Unavailable | Flanker | Status |
  |---|---|---|---|
  | `light.stue_sofa_lampe` | **100 %** (333,8 t) | 28 | i et skab |
  | `light.stue_sofa_lampe_2` | 100 % | — | i et skab |
  | `light.stue_hjoernelampe` | 100 % | — | i et skab |
  | `light.stue_laesehygge` | 26,5 % (88,5 t) | 11 | **rask** — vægkontakt |
  | `light.stue_plug` | 0,0 % | 0 | rask |

  Læselampens 26,5 % er **ikke** en fejl: den sidder på en vægkontakt user selv
  slukker (afklaret med ham 2026-09-17). Den er derfor heller ikke en kandidat
  til noget der kræver konstant tilstedeværelse.

  **Den generaliserbare lærdom — en permanent død entity er ubrugelig som
  BEVIS.** `packages/genstart_rapport.yaml` valgte `light.stue_sofa_lampe` som
  én af sine tre Zigbee-kanariefugle. Rapportens `alt_ok` krævede at ingen
  kanariefugl var nede, og da den ene aldrig kan være oppe, var `alt_ok`
  **strukturelt uopnåelig**: rapporten kunne kun nogensinde melde fejl, og den
  fejl var altid den samme falske. Det udløste en falsk alarm efter
  HAOS-rebooten 17.1 → 18.2 den 2026-09-17, hvor alt i virkeligheden var sundt
  (alle fire Thread-routere, alle fem Apolloer, nul fejlede automations, og
  SSH-add-on'et havde opdateret sig selv).

  **Signatur: en test der kun kan fejle, og som melder det samme hver gang.**
  Metoden er at MÅLE unavailable-andelen over 14 døgn før du vælger en
  kanariefugl, en "kom alt op"-test eller en gate-kilde — ikke at vælge den
  entity der lyder rigtigst. Afløseren blev fundet sådan:
  `light.boernevaerelse_loft` (0,0 %), mens det nærliggende stue-valg
  `stue_laesehygge` (26,5 %) ville have givet falsk alarm ved hver fjerde reboot.
- **En firmware-OTA slutter med en device-reboot, og enheden kommer tilbage
  TÆNDT — også hvis den var slukket før.** Opdaget 2026-09-16 kl. 22:14 på den
  værst tænkelige måde: user havde trykket godnat kl. 22:07, børnene sov, og
  midt i det skrev han *"turn the lights off please. sleeping."* — børneværelsets
  plug-lampe var tændt af sig selv. Årsagen var min egen ZHA-OTA.

  Målingen er utvetydig og ramte **begge** plugs, ikke kun den ene:

  | Enhed | Før flash | Flash slut | Efter reboot |
  |---|---|---|---|
  | `switch.stue_plug` | `off` | 22:04 | **`on`** |
  | `switch.sove_plug` | `off` | 22:14 | **`on`** |

  **Mekanismen er `power_on_behavior`, og den er derfor FORUDSIGELIG.** Da jeg
  dagen efter (2026-09-17) læste `select.<device>_power_on_behavior` på tværs af
  huset, passede den perfekt:

  | Enhed | `power_on_behavior` | Post-OTA |
  |---|---|---|
  | `stue_plug`, `sove_plug` | `On` | tænder ✅ observeret |
  | `badevaerelse_spot_1/2/3` | `on` | tænder — derfor udsat til vågen tid |
  | `third_reality_...3RSPE01044BZ` | `Off` | harmløs |
  | `ikea_of_sweden_tretakt`, `innr_osp_240`, `ullo_u2101001` | `PreviousValue` | harmløs |

  OTA'en afbryder enhedens strøm internt, og ved genstart anvender den sin
  power-on-default i stedet for sin sidste state. HA's `off` var korrekt lige
  indtil rebooten og forkert straks efter — der er ingen fejl at se i loggen,
  kun et lys der tænder.

  **Derfor: læs selecten FØR du flasher.** Er den `Off` eller `PreviousValue`,
  er enheden harmløs uanset tidspunkt. Er den `On`, er flashningen en
  lys-tændende handling. Bemærk at `On` ofte er det RIGTIGE valg for enheden
  (en loftspot på en vægkontakt skal lyse når kontakten slås til igen) — så
  løsningen er at vælge tidspunktet, ikke at skrive NVRAM om.

  **Konsekvensen for planlægning af opdateringer:** en OTA på noget der styrer
  lys ER en lys-tændende handling og hører til i vågen tid. Det gælder
  bad-spottene (der oven i købet er husets Thread-routere), plugs og pærer.
  Batteridrevne sensorer uden lysudgang (`parasoll_*`, `badevaerelse_inde_*`)
  har ikke problemet — de må gerne flashes om natten, men gør rummets
  presence-kanal blind imens.

  **Og ryd op på switch-laget, ikke på wrapperen:** `light.stue_plug` /
  `light.boernevaerelse_hyggelys` er template-lys der står i
  `automations/manual_override.yaml`s rum-map, så et `light.turn_off` udsender
  et `call_service`-event der stempler rummet Manual (#11). Et
  `switch.turn_off` på `switch.stue_plug` rammer ikke mappen. Verificeret:
  `input_select.room_mode_stue` stod stadig `Auto` med uændret `last_changed`
  efter oprydningen. Selve firmware-tændingen tripper derimod INTET — den er en
  device-rapporteret state-ændring uden `call_service`.
- **En pære der falder af radionettet MENS den lyser, bliver stående fysisk
  tændt — og `unavailable` gør den usynlig for hver eneste sluk-vej** (godnat,
  force-instant, super-watchdog'en, der kræver `state == 'on'`). Målt 08-12:
  `depot_strip` lyste 15 t uden at noget i huset kunne se det. Enhver
  "alt-lyset-er-slukket"-påstand skal derfor tælle de uopnåelige lys med;
  **Terrassens pærelyskæde er den kendte undtagelse** (user 2026-09-28: "det
  er bare mig der manuelt slukker stikkontakten") — 43 % unavailable over 14
  døgn, fx `on` 27/9 19:20 → `unavailable` 21:21. Den har INGEN netdreven
  nabo-node at bruge som vidne (`sensor.lys_kontakt_slukkede` målte 0/10
  kobling), så den tælles bevidst stadig som spøgelse; spild ikke tid på at
  jagte den.
  se `input_text.godnat_uopnaaelige_lys` + `lys_offline_sluk_ved_retur`.
  Døgnet rundt holdes de i `sensor.lys_spoegelser` (latch på flanken `on →
  unavailable`), som lys-KPI'erne, rummenes `*_lys_on_effektiv` og
  watt-estimatet lægger oveni — læs DEN, ikke entity'ens rå state, hvis du skal
  svare på "hvor meget lys brænder der". Tvetydigt pr. konstruktion: strøm
  slukket ved kontakten ser præcis ens ud, og en pære der vender tilbage som
  `on` beviser intet.
- **De tre open-plan-gardiners position er en ANTAGELSE, ikke en måling.** Stue
  syd/vest + spisestue vest er template-covers over Somfy RTS via Broadlink RF —
  **envejs, nul feedback** — og antagelsen restaureres ikke: efter hver
  HA-restart står alle tre `unknown`/pos=None (målt 2026-08-17). Sove-gardinet
  er IKKE ramt. Konsekvens: gates på position/`open`/`closed` er stumme efter en
  restart (#9), og forensik kan kun bevise "HA kommanderede det ikke" — aldrig
  "det bevægede sig ikke". → B76.
- **Terrassedøren har INTET gardin; stue vest må højst 85 % ned** (user
  2026-10-07). B198 byggede en "terrassedør-spærre" på `cover.gardin_stue_vest_1`
  ud fra april-specens løfte (§6.1) og en udelukkelse (spisestue vest er et
  vindue med 55 cm brystning) — user: "døren har intet gardin, så dør bør ikke
  spærre for gardin. men rigtigt at vest stue kun skal 85% ned". Spærren blev
  fjernet igen samme dag. 85 %-grænsen ("der står nogle ting", user 2026-06-11)
  er implementeret som NED → `gardin_vest_ned_sekunder` (målt top→85 %) →
  My-stop; den antager start fra TOP, så et 2. luk uden en åbning imellem kører
  forbi grænsen og ned i inventaret. 14 døgns historik (23/9-7/10): vest kun
  lukket én gang (RODRET), intet dobbelt-luk set — men en ny luk-vej skal enten
  re-home (som `script.gardin_film_luk`) eller være flag-gated til ét luk.
- **2026-10-04 (B123): ankeret har nu TO lister — `held` (ÅBN-blokliste, med
  AirBnB-tæppet) og `held_luk` (LUK-blokliste, uden tæppet).** Teksten herunder
  forklarer hvorfor `held` aldrig må læses på en luk-vej; det skete alligevel i
  fire luk-veje (aftenluk, vinter ×2, putte-glare), og i september sov en gæst
  6½ nat med sove-gardinet 100 % oppe, mens aftenluk blev sprunget over 7 aftener
  (målt i backup-DB'en). Luk-vejene læser nu `held_luk`; at vinter-forsvaret og
  putte-glare stadig IKKE kører i AirBnB er deres egen eksplicitte mode-gate
  (user-valg 4/10: kun sove-aftenluk lukker for gæster).
- **`sensor.gardiner_manual_hold`s `held`-attribut er en auto-ÅBN-blokliste, ikke
  et "rør-mig-ikke"-flag.** Ni automations læser den før de ÅBNER et gardin; den
  siger derfor "dette gardin må ikke auto-åbnes lige nu", ikke "hold fingrene
  væk". Og i AirBnB ligger **alle fire** gardiner permanent i listen (user-spec
  2026-09-02: gæsten styrer selv sine gardiner). Fælden opstod 2026-09-23 under
  mosbillede-beskyttelsen: skabelonen `packages/putte_vest_glare.yaml` tjekker
  `held` FØR den rører gardinet, og et copy-paste ville have gjort den nye
  LUK-vej ude af stand til at lukke for en gæst — præcis det modsatte af
  user-spec'en. Løsningen inverterer forholdet: ejer-flaget
  `input_boolean.mosbillede_gardin_ned` lægges IND i ankerets `state` OG `held`
  (begge renderinger — de er divergeret før, #2), så alle ni auto-åbnere arver
  blokeringen gratis (#1/#16), mens luk-vejen hviler på sine EGNE grunde
  (sleepover, manuelt hold, AirBnB-Dormant-gaten).
- **Sol-indtrængnings-geometri: dybden ind i rummet er
  `((brystning + vindueshøjde) / tan(elevation)) × cos(azimut − vinduesnormal)`.**
  `H` måles til vinduets ØVERSTE kant (spisestue-vest: 55 + 220 = 275 cm), fordi
  den dybeste stråle kommer ind derfra; vinduets BREDDE (180 cm) spreder pletten
  sideværts og påvirker ikke dybden. **Formlen alene lyver ved strøjflys:** når
  solen står næsten parallelt med glasset går `1/tan(elev)` mod ∞ mens `cos(Δ)`
  går mod 0, og produktet bliver et plausibelt mellemstort tal uden målbart lys
  i det. Målt live 2026-09-23 før idriftsættelse: **357 cm** ved elevation 1,9°,
  azimut 147,4° (Δ = −87,6°, indfaldsfaktor 0,042) — nok til at rulle gardinet
  ned i morgensol fra SSØ der aldrig rører facaden. Guarden er fysik, ikke en
  dybde-tærskel: `cos(indfald) = cos(elev)·cos(Δ) ≥ 0,25` (indfaldsvinkel < 75°),
  placeret **inde i dybde-sensoren** så gate og dashboard ikke kan blive uenige
  (#2). **Men få rummets MÅL før du modellerer.** Spisestue-vest vender 333°
  (NV, user-målt og satellit-bekræftet); mosbilledet hænger på den PARALLELLE
  væg 245 cm inde, 10-85 cm nord for vinduets nordkant. Direkte sol kan kun
  ramme det fra azimut ~286-331° = sommeraftener maj-aug. 2026-09-24 gik tre
  modeller galt på én dag, alle fordi jeg gættede rummet i stedet for at få
  målene: normal 235° fra lux-toppe, 243° fittet til en observation (sol på
  billedet 17:02 ved az 243,8°), og en sidevæg der ikke findes — hvis gættede
  mål kørte gardinet næsten helt ned. Observationen 17:02 blev dengang
  forklaret som en refleks ("89° strejflys, 170 m sidelæns forskydning") —
  **AFKRÆFTET 2026-09-26:** user så igen sol på billedets nederste 20 % ved
  az 247,5° / elev 13,0° og siger at solen kommer ind "fra siden" gennem
  spisestue-vest. To observationer ved samme sol-position to dage i træk er
  direkte sol, og modellen har et forkert mål (hvilket er uafklaret, BACKLOG).
  Samme dag sluttede jeg "stue syd" fra et manuel-stempel på det gardin — også
  forkert. Samme aften gav user rummet: to parallelle NORD-SYD-vægge ~250 cm
  fra hinanden, vinduet i vestvæggen, billedets sydkant i flugt med vinduets
  nordkant → jeg sluttede **270°** (FORKERT, se 30/9 nedenfor). Med 270°
  rammer modellen begge observationer, og en kortvarig empirisk strejflys-boks
  blev fjernet igen. Gardinet går aldrig under 50 % åben (user-spec). Modellen
  overvurderede plettens højde med ~45 cm, fordi glassets overkant er 228 cm,
  ikke 55 + 220 = 275 (user-målt; model-top 166 cm mod observeret ~165 cm ved
  gardin helt oppe 17:18). Kanterne er nu sliders. **Signatur: en
  observation modellen ikke kan forklare med users mål → et MÅL er forkert
  (ikke en refleks). Fit ALDRIG en vinkel til den, og gæt heller ikke vinduet
  — spørg.**
  30/9: users foto (repo-roden `mosbillede`) bekræfter geometrien perspektiv-
  målt — væg-afstand 252 cm, billedets sydkant i flugt med lysningen. Og
  **270° var FORKERT: user har målt 333° med professionelt kompas** ("source
  of truth"). "Nord-syd-vægge"/"vestvæggen"/"altandøren vender mod nord" var
  omtrentlige ord; jeg byggede 270° på dem og holdt fast mod users tal, fordi
  observationerne passede. De to observationer (24/9 + 26/9, az 244-248°) er
  stadig ægte sol som 333° ikke kan forklare → dækket af en EMPIRISK
  strejflys-boks (az 224-270°, vej 273 cm kalibreret til "nederste 20 %";
  fra = 240° siden 18/10: user så pletten nå billedets kant ved az 241,3°),
  som reproducerer den målte 27/9-regulering. Lysvejen er uafklaret.
- **En Matter/Thread SLEEPY END DEVICE der mister sin forælder mens den melder
  `on`, sender aldrig sin `off`** — HA står `on` i op mod 40 min
  (`occupancy_stuck_on_minutes` = 18 maskerer det ved kilden).
- **En Matter-node der kommer tilbage genopstår med sin SIDSTE kendte værdi** →
  `unavailable → on` er et ekko, ikke bevægelse. Tænd-triggers kræver `from: "off"`.
- **HA's state er IKKE et referat af hvad du sendte til en Matter-enhed.** Noden
  rapporterer ~1 gang/sek, så hurtige skrivninger coalescer: 15 farveskift blev
  til 4 observerede (målt 08-21). Level og Color rapporteres desuden UAFHÆNGIGT,
  så et brightness-dyk kan overskrives af næste skridt før det nogensinde ses.
  Skal du bevise at N hurtige kald landede, så tæl ikke state-skift — gør hver
  skrivning **identificerbar** (fx gyldne-vinkel-farver: 137,5°-skridt er
  entydige mod 360, så hver observeret hue afslører sit skridt-nummer). Gælder
  al verifikation af hurtige sekvenser, ikke kun lys.
- **CHIP Error 0x00000032 (Timeout) aborterer HELE automation-scriptet** på det
  trin → `continue_on_error: true` på Matter-lys-kald. Det gælder også et kald
  til en lysgruppe med et Matter-medlem (gruppen kalder medlemmerne blokerende).
  Reglen stod kun som tekst, og 2026-10-07 manglede 11 kald den — bl.a. begge
  røgalarmens fuldt-lys-kald på `light.alle_lys` i kvitterings- og
  timeout-vejen (et timeout ville have sprunget `script.tradfri_ws_bri_fix`
  over og efterladt depotet på 2 %). Nu blokerer
  `ha_validate.py --check matter` i pre-commit (registry + lysgrupper,
  transitivt; templatede mål kan ikke afgøres offline).
- **Sonoff-donglens RCP kan hard-hænge** → self-heal-daemon i SSH-addon'et;
  RCP-reset kurerer KUN et wedged addon (`state: error`), aldrig en pære der er
  faldet af mesh'et — og på et raskt net gør den skade (ny ensom partition,
  se partition-split-bulleten).
- **RCP-resets skalerer med Matter-kald-raten til stue-spotsene** (målt
  2026-10-13, otbr-loggen under ild-flimmer-testen): ~1 % af kommandoerne til
  `light.stue_spot_1/2` giver `radio tx timeout → RCP failure detected →
  Trying to recover (1/2) → recovery done`, og hver reset stopper ALT
  Thread-trafik ~5 s (alle Matter-kald hænger samtidig). Pr. time: baseline
  0-4, langsom ild 18-35, flimmer 400 ms (~2,3 kald/s) 72-120. To node-
  adresser stod for næsten alle (114 + 95). Pærens firmware interpolerer selv
  transitions, så ms-flimmer via nettet er hverken nødvendigt eller muligt —
  men selv ~2 kald/s er for meget for denne RCP. B232.
  **Trappe-test 17/10 (B239, MoveToLevel på tændte spots, 4 min pr. trin):**
  0,2 og 0,5 kald/s = 0 resets på 168 kald (svartid 0,05 s); 1 kald/s = 4
  resets inden for 21 s efter 2:43 (p95 2,3 s, max 8 s) → trappen afbrudt.
  Alle 4 + de 6 under morgenens OTA af de to spots (7 min hver) var
  `radio tx timeout` på en frame TIL en spot. Forenelig med ~1 % pr. kald,
  men burst-mønstret ved 1/s peger på en rate-tærskel (serial-overløb).
  Ild ved default-takt ≈ 0,03 kald/s ligger langt under.
  **Årsag (13/10):** samme signatur som home-assistant/addons#4856 —
  `Extended Reset info: 0x401 (HV)`, tabte bytes på USB-serial ved 460800 baud
  uden HW flow control. ZBDongle-E har ingen flow-control-linjer (darkxst
  README), og alle darkxst-RCP-builds til den er `no_flow_460800` (2.5.3 og
  2.7.0). ZBT-2'en (ZHA) kører `flow_control: hardware`.
- **Festlys' Thread-gitter: budgettér HUSETS sum af Matter-kommandoer, ikke pr. pære (25/10, B260, user: "det går
  ikke at events lægger thread ned hver gang … vær mere nænsom").** Halloween-eventet (v2/v3) sendte ~22 kommandoer
  på 33 s pr. Matter-pære ≈ 0,67/s pr. stk, ≈ 2/s for entré-loftet + de to stue-spots, plus deres rapporter — 4×
  over trappe-testens rene trin. 24/10: fem test-løb à ~36 s kostede hver 3-5 RCP-resets. 25/10: et låst løb startet
  06:20:08, slukket 06:21:38 (2 løb); OTBR'en hard-hang 06:21:44, og ALLE Thread-enheder var `unavailable` ~3 min.
  Baggrunds-disko'en (`dance_single_bulb`, farvet skrivning hvert ~4,5 s pr. pære ved hastighed 50) lå med 3 Matter-
  pærer på ~1,3 kommandoer/s — ikke bevist som udløser (17/10 07:02-07:09 uden reset-spring), men over 1/s-trinnet.
  **Design:** `custom_templates/festlys.jinja` — ét absolut unix-ur, én Thread-skrivning hvert 60/N s i HELE huset
  (`input_number.festlys_thread_skrivninger` = N, default 8 → 7,5 s), pærerne på skift (Matter-pære m ejer skridt j
  hvor j % antal == m, i `sensor.dance_active_bulbs`' rækkefølge). Events, disko-loopet og løb der følger tæt på
  hinanden deler gitteret, så summen holder uanset hvad der kører. Én skrivning ≤ 2 kommandoer (farve + niveau, uden
  `transition` i events — den koster 2 RemainingTime-rapporter), og der skrives kun når pæren ikke allerede står i
  eventets look (hue ± 5°, sat ± 8, niveau ± 3 %). Hurtige blink-events (strobe, lyn, sparkle, comet, jump, heartbeat,
  halloween) = Thread-pærerne mørke; police/pulse/split/cascade = ét statisk look; chase = langsom regnbue; ild =
  glød 15-45 %. Gruppe-events (blackout, warm, breathe, ildens udbrænding) er kun ZHA. Thread-pausen
  (`binary_sensor.stue_spots_ild_thread_pause`: router nede, spot/entré væk, resets/t over loftet eller 30 min efter
  en byge) = de sidder helt over. **Pris:** med 3 Thread-pærer skifter hver højst hvert 22,5 s og kan komme op til
  22,5 s for sent ind i et event. Worst case 16 kommandoer/min ≈ 0,27/s (trappens rene trin: 0,5/s).
  **Målt 25/10 07:06-07:18** (2 låste chase-løb, 7 min): skrivningerne 0,01-0,07 s efter pladsen, 15-16
  kommandoer/min, 1 enkelt RCP-reset uden klynge — mod 3-5 pr. 36-s løb før. Baggrunden uden fest er ~1,8
  reset-episoder/t (B232), så én reset i et løb er ikke et festlys-tegn; en KLYNGE (3+ inden for 30 s) er.
  **Med-ejer fundet samme dag (#1):** `entre_motion_off`'s /2-backstop startede `script.entre_fade_ud` midt i
  festen (entréen er tom, og motion_off læser ikke `room_mode_entre`) → 9 dæmpe-trin à 4,5 s mod festens farve.
  Scriptet springer nu over mens entréen danser (`dance_mode`/`dance_event_manual_active` + entre_loft i
  `sensor.dance_active_bulbs`).
- **Entré-loftet + stue-spotsene er det skrøbeligste Thread-led (15/10, user-spec
  "meget forsigtige med at belaste entre loft og stue spots").** Stuen hænger
  (indtil 15/10 18:51) kun på OTBR'en via entré-loftet (node 461) — derefter
  også via køkken-routeren (GRILLPLATS node 499, LQ 3 til OTBR + stue spot 1 +
  Stue Plug, meshdiag 15/10 19:19); meshdiag 15/10 viste 74-92 %
  frame-fejl på stue→entré, mens spot↔spot er fin. Stue-spot 1 stod 15/10 fra
  13:32 i `router table` (Age frisk, ping OK) men unavailable i HA: Matter-
  subscriptionens priming-rapport kom ikke igennem broen (backoff 8→17→32→60
  min). Belastnings-opgørelse (matter-serverens Invoke-log, kommandoer/døgn):
  stue-spots 12/10 ~7600 (ild i Auto) → 13/10 ~6200 → 14/10 ~2100 → 15/10
  ~1700; entré-loftets EGNE 116-368/døgn, næsten alt `entre_fade_ud`
  (31 kommandoer pr. fade, 8-24 fades/dag, uændret i 3 uger). Claude-skyld
  fundet: (1) ilden 12-13/10 → RCP-resets 13/10 16:50, 20:13, 14/10 10:22;
  (2) `thread_zombie_kick.py` releaserouterid'ede ENTRÉ-loftet 13/10 19:55;
  (3) Thread-kortets meshdiag hvert 2. min fra 15/10 13:30 (spot 1 væk 13:32).
  Fix 15/10: meshdiag ≤ hvert 30. min (samme aften → slider, 4 min: RCP-
  resets/t p50 3 både ved 2 og 30 min, og stue-klyngen faldt også ud med
  30 min — (3) var tidsfølge, ikke målt årsag), `BRO_NODER = {"461"}` i zombie-kicket,
  entré-faden 10 trin á ~4,5 s med `wait_template` på bevægelse (flaren er
  nu øjeblikkelig). Frikendt: party mode (ikke tændt siden 25/9), dance,
  stedfortræder-pakken (0 Thread-kald), ild-pausen, read-polling, højttaleren.
- **En Matter-pære svarer på hver kommando med subscription-rapporter — de er
  det meste af trafikken (målt 15/10 16:32-16:35 på entré-loftet, matter-
  serverens websocket `start_listening`, stue-spots trukket ud).** Tænd
  1→200 over 10 s: OnOff + CurrentLevel 1, 3, 53, 103, 155, 199 (hvert ~2,5 s)
  + RemainingTime 99 ved start og 0 ved slut. Samme 1→200 over 25 s: level-
  rapporter hvert ~6,3 s = STADIG 4 mellemrapporter → pæren rapporterer pr.
  ~50 trin ÆNDRING, ikke pr. tid. 200→20 over 10 s: 197, 147, 97, 47, 21 + 2×
  RemainingTime. Øjeblikkelig (transition 0) 200→60: ÉN rapport. Regnestykke:
  blødt skift ≈ 1 kommando + 2 RemainingTime + 1 pr. 50 trin + slut ≈ 4-5
  udvekslinger. Gammel entré-fade (31 trin) ≈ 125 udvekslinger, ny (10 trin)
  ≈ 45; B234-ilden ~360 kommandoer/t ≈ 1600 udvekslinger/t, ny ild (60 s)
  ≈ 120 kommandoer ≈ 550 udvekslinger/t — alt sammen gennem entré-loftet.
- **Thread-forsvaret efter B234 (14/10) — fire lag i daemonen + HA:**
  (1) `txhold` i `scripts/otbr_selfheal.sh`: OTBR-add-on'et sætter RCP'ens
  sendestyrke til 6 dBm ved HVER start; daemonen holder den på 17 dBm (før kun
  stigens trin 1, dvs. efter et nedbrud). Daemonens egen RCP-recovery
  13/10 20:13 starter add-on'et → 6 dBm, og stue-spotsene (path cost 4-5 via
  badet) var væk natten over til 06:41 (sammenhængen er IKKE bevist — den
  overnattende TX-værdi blev ikke logget; txhold logger nu hver hævning). (2) `scripts/otbr_rcp_stats.py` → `sensor.otbr_rcp_resets_1t`
  (resets/t + `resets_10m`, `split_peer`/`split_minutter`, `offline_noder` med
  HA-navne) hvert 2. min. (3) Ild-budget: `binary_sensor.stue_spots_ild_thread_pause`
  (≥ `input_number.stue_spots_ild_rcp_loft`/t, af under det halve; 17/10 også
  byge-bremsen: `resets_10m` ≥ `stue_spots_ild_rcp_byge` → pause til
  `input_datetime.stue_spots_ild_rcp_byge_til`, default 3 → 30 min — OTBR-crashet
  17/10 07:53 kom efter 11 resets på 11 min, timeloftet nåede 7 20 s før; bygen
  stod på 3 i 10-min-vinduet 07:50. ≥ 3 på 10 min målt ≈ 5×/døgn 14-17/10) + én
  Matter-kommando pr. ild-skift, gulv 5 s pr. spot. (4) `binary_sensor.thread_enheder_vaek`
  (30 min) → push med HVILKEN enhed og kuren (split = genplug).
  **Split-signaturen:** otbr-loggen `Different partition (peer:X, local:Y)`
  hvert ~par min + NoAck på OTBR'ens rammer til noden; 13-14/10 sad begge
  GRILLPLATS ~14 t i peer 870840965. Hverken OTBR-restart eller RCP-reset
  fletter det (nyt ensomt net), kun et genplug af enheden.
  **Men et genplug af ÉN ø-router er ikke nok, hvis øens andre medlemmer
  stadig kører** (B234, 14-15/10): en genstartet router gendanner sin gamle
  partition og finder sine gamle naboer — ø B (entré, stue-spots, sove-
  lyskæden) genopstod efter hver enkelt-genstart. Opløst først da alle fire
  havde været strømløse natten over og blev tændt én ad gangen 15/10 morgen;
  den sidst tændte (stue-spotsene, gammel partition 1440515826) VANDT
  sammenligningen, og OTBR'en flyttede selv med (`BetterPartition`, 07:18:47)
  — en harmløs fletning, 8/8 routere 07:22. En alene-tændt router (entré)
  kan derimod sidde i sin egen singleton i ~1 t før den fletter.
  **Leder-vagten (15/10):** partitioner sammenlignes på leader weight FØR
  størrelse og partition-ID (`Mle::ComparePartitions`), og alle andre noder
  har 64-65. 15/10 vandt stue-spotsenes ø igen; stue spot 2 blev leder og var
  døv (ingen link til nogen): sove-lyskæden kunne ikke få router-ID (hang som
  barn), stue spot 1 blev stående som halvdød router, og zombie-kicket
  (`releaserouterid`) kræver OTBR'en som leder. Fjernet ved at tage stue spot
  1 ud (14:00; spot 3 blev leder). Nu holder `scripts/thread_zombie_kick.py`
  OTBR'ens `leaderweight` på 128 hvert tick (nulstilles ved add-on-start) og
  kører `state leader` når OTBR'en har været router i ≥ 6 min med ≥ 2 links
  LQ 3/3 (1 pr. 6 t). Målt 14:14:24: 7 routere i OTBR'ens nye partition på
  45 s. Entré-loftet kan IKKE gøres til leder — Matter-pærer har ingen
  leader-weight-indstilling, og det sidder på en vægkontakt.
  **Matter-serveren genabonnerer selv** når en node bliver nåbar igen
  (14/10 06:41, "address is unreachable" indtil da) → ingen auto-restart af
  matter-serveren; det ville bare tabe alle subscriptions.
- **Kun to lys er effektMÅLT, resten er estimat (max-watt × dæmpning):**
  `light.stue_plug` (39 W glødepære) og sove-lyskædens plug
  (`sensor.sove_lyskaede_power`, ~2,5 W; Innr SP 240 fra 15/10, før GRILLPLATS) — watt-kortets `maalt` i
  `packages/energy_estimate.yaml`.
  Effekt-plugs er **delta-rapporterede**: et sample-hul betyder "uændret", aldrig
  "nul", og de hænger på sidste værdi ~15-20 s efter sluk.
- **De to cykelbatterier er ens (504 Wh), men LADERNE er ikke:** hans plateau
  er 171-181 W, Parent B's 72-73 W (målt over 10 døgn). Effekt-niveauet på
  `sensor.entre_cykel_lader_effekt` fortæller altså HVIS batteri der sidder på
  den fælles plug — og hvorfor ét fast timetal aldrig kan passe begge.
  **Fra 2026-10-05 er den rå sensor ekskluderet fra recorderen** (målerens
  nulpunkt svinger 0,2-1,7 W med slukket relæ = ~6.100 rækker/døgn); historik
  til plateau-analyser ligger i `sensor.cykel_lader_effekt_ren` (0 når pluggen
  er slukket eller < 3 W, ændringer ≥ 2 W). Live-værdien er uændret for alle.
- **En lang `transition` på ét `light.turn_on` køres i PÆRENS firmware, ikke af
  HA** — det er ét Zigbee `MoveToLevel` med `TransitionTime`, og HA rører aldrig
  pæren igen. Det ser rigtigt ud i history og ER rigtigt i timing, men kvaliteten
  af rampen er 100 % pærens.
  **Incident 2026-09-05:** user meldte *"kan du lave godnat knap fade down mere
  smooth i soveværelset? det hakker lidt."* `script.godnat_fuld` sendte ét
  `turn_on brightness_pct: 2, transition: 60`. Historikken for
  `light.spisestue_pendel` (soveværelsets pære — innr **RF 271 T**, CCT-only)
  over hele godnat-vinduet indeholdt **præcis to rækker**: `on` ved vinduets
  start og `off` ved +61,6 s fra script-start = nøjagtig den skriptede
  `delay: 60`. **Nul mellemtrin fra HA, og intet andet skrev til pæren** — så
  hverken timing eller interferens kunne forklare hakket. Tilbage stod pærens
  egen kvantisering: ~3 niveau-trin/s hen over 184 → 5 raw.
  **Hvorfor det hakker i den MØRKE ende og ikke i den lyse:** lysopfattelse er
  logaritmisk, så et trin på fx 4 raw-niveauer er umærkeligt ved 180 og et stort
  spring ved 12. En LINEÆR ramp (som `MoveToLevel` kører) har derfor pr.
  konstruktion accelererende opfattet fald.
  **Signatur:** en fade der "hakker mod slutningen" — og en history hvor der kun
  findes to rækker for hele fade-varigheden.
  **Fix-mønstret er en GEOMETRISK ramp drevet af HA:** `lvl_i = start · (slut/
  start)^(i/steps)` giver konstant OPFATTET faldrate. To detaljer der gør den
  ren: (a) hvert trin må kun targete de pærer der lige nu er **lysere** end
  trinnet (`selectattr('attributes.brightness','gt', lvl*2.54)`), så sættet
  krymper monotont og ingen pære kan rampe OP; (b) giv hvert trin en
  `transition` ~1,2× intervallet, så pæren stadig er i bevægelse når næste
  kommando overtager — ellers står den stille i halen af hvert trin og du har
  bare flyttet hakket. On/off-pærer falder automatisk ud (ingen
  `brightness`-attribut) og skal slukkes af det afsluttende rene `turn_off`.
  Kostede 12 service-kald i st.f. 1 ved fade_s = 60 (≈ 2-3 kald/s mod husets
  loft på 5-10/s). Kode: `script_pkg/house_routines.yaml` → `godnat_fuld`.

<!-- flyttet fra CLAUDE.md 2026-09-12 under linje-budget-oprydningen -->
- **RUMMETS EGNE LAMPER lyser også ind i Apolloens LTR390 — en lux-gate der kan
  evalueres mens vores eget lys er tændt, måler sig selv.** Målt 27/8:
  køkken-lyskæden = **+73..79 lx** (spots ≈ 0). En sluk-ved-høj-lux-gate blev
  derfor selvopfyldende (kæden slukkede sig selv ~2 min efter hver tænding).
  Enhver "er der lyst nok?"-gate læser `sensor.koekken_dagslys_lx`, aldrig
  `sensor.koekken_lux_effektiv`. **Og `sensor.open_plan_lux` er SELV sådan en
  gate-kilde — den må kun bygges af kanaler hvor vores eget lys ikke kan lyse
  ind.** Målt 3/9 06:28 med lyskæden tændt og mørke ude: snittet stod på
  **66,4 lx** mens den immune entré-VALLHORN sagde **3,0**; det blokerede stuens
  tænd-gate OG fyrede dagslys-sluk samtidig. Kryds-tjek altid mod
  `sensor.entre_lux_reel` før du tror på et lux-tal — den er immun over for
  OPEN-PLANNETS lys, **men ikke over for sit eget**: VALLHORN'en sidder under
  `light.entre_loft` og målte +19..46 lx af det (4/9), og fordi den kun
  rapporterer ca. hvert 2. minut hang den kontaminerede værdi i **op til 11 min
  efter** slukket og spærrede entréens egen tænd-gate (39 missede tændinger på
  14 dage). Den bruger nu samme fastholdt-rent-sample-model som open-plan
  (`binary_sensor.entre_lys_rent` → `sensor.entre_dagslys_sample`); tjek
  attributten `kilde` før du bruger tallet som facit.

  **⚠️ Og entréen duer som RETNING, ikke som NIVEAU** (målt 2026-09-13c).
  Immun er ikke det samme som repræsentativ: VALLHORN'en måler et ANDET RUM,
  uden direkte dagslys, på en anden skala. Kalibrering over **182 paired
  10-min buckets / 21 døgn, kl. 08-18**, hvor både entréen og begge
  dagslys-samples var friske:

  | percentil | ratio open-plan / entré |
  |---|---|
  | p10 | 1,20 |
  | p25 | **1,76** |
  | p50 | **2,26** |
  | p75 | 2,93 |
  | p90 | 3,50 |

  Entré-gennemsnit **100,1 lx** mod open-plan **206,2 lx**; kun **14 af 182**
  buckets har entréen lysest. Fallback-grenen i `sensor.open_plan_lux` skaleres
  derfor med `input_number.open_plan_entre_fallback_faktor` (**live 1,75 = p25**,
  aflæst 2026-09-17). De to andre fallback-led (`sovevaerelse_lux_reel`,
  `stue_lux_reel`) er ægte rum-målere og skaleres med 1,0.
  **p25 og ikke medianen, fordi fejlretningen er asymmetrisk:** under-vurdering
  = "her er mørkere end det er" → et unødigt tændt lys, synligt og
  selvkorrigerende. Over-vurdering = "her er lysere end det er" → huset bliver
  blindt for et reelt mørkt rum og undlader at tænde (præcis den klage user rejste
  2026-09-04). p25 betyder at vi i 75 % af tilfældene stadig under-vurderer.
  **Hændelsen der afslørede det (09-13c):** lyset havde været tændt siden 07:21,
  så `open_plan_lys_rent` kunne aldrig blive sand, samplene aldrede ud kl. 08:06
  (07:21 + 45 min hold), og fallbacken skrev entréens **rå 25 lx** ind som
  open-plannets niveau. Kl. 09:45:57 tændte huset derfor open-plan-lys i ~**170 lx
  ægte dagslys** (sol 24,8° elevation). Slukket manuelt sprang `open_plan_lux` til
  **130,3 lx** = 3,7× det fallbacken påstod. **Selvforstærkende: lyset huset selv
  tændte garanterer at et rent sample aldrig kan tages igen.**
  **Den generelle regel: et fallback-led skal vurderes på om det måler det
  SAMME, ikke kun på om det SVARER.** En kilde der svarer prompte med et tal fra
  et andet rum lyver med fuld selvsikkerhed — og ingen availability-tjek fanger
  den, fordi der ikke er noget i stykker.

  **SVARET er et FASTHOLDT RENT SAMPLE, ikke et fradrag** (3/9, user-design):
  `open_plan_lux` + `spisestue_dagslys_lx` bruger den værdi Apolloen målte sidst
  hele open-plannet var mørkt (`binary_sensor.open_plan_lys_rent`), gyldig i
  `input_number.open_plan_dagslys_hold_minutter` — ellers entré. Vælg den model
  hver gang du fristes til at bygge et nyt fradrag: de tre punkter herunder
  (farve-regime, over-fradrag, fade-kurve) er alle frihedsgrader et fradrag skal
  ramme rigtigt samtidig, og et gemt sample skal ramme nul af dem.
  **Men et gemt sample er et LOFT, ikke et facit** (4/9): vores eget lys kan kun
  lægge lux TIL, så en rå aflæsning UNDER samplet beviser at samplet er forældet.
  **Og loftet svigter når NABO-rummets lys er tændt** (27/9): køkken-lyskæden
  tændte ved hjemkomst 18:24, spisestue-samplet frøs på 43,9 lx, den rå
  spisestue-Apollo så kæden (~56) → `min()` holdt 43,9 i hele 45-min-holdet
  mens solen gik ned (tærskel 25) = dødbånd; derefter faldt kanalen til
  `open_plan_lux`-fallbacken = kontamineret `spisestue_lux_reel × 0,65` = **42
  lx med solen på −12°**. **Om AFTENEN er retningen kendt** — dagslyset kan kun
  falde — så et aften-sample fremskrives ad SOLHØJDEN (målt 14 døgn rene
  spisestue-samples): under 3° falder lyset **×e^−0,59…−0,85 pr. grad i ALLE
  199 par** (k = 0,55 = langsommere end alle = konservativt); over 4° kan det
  stige (skyer/direkte sol) → ingen fremskrivning dér. Plus sol-loftet
  `10·e^(elev+1)`: nul aften-samples ≥ 25 lx hvor loftet sagde < 25.
  **Men fremskrivningen er kun SIKKER for en gate hvor "for mørkt" er den
  harmløse fejl** (lys-tænd). **For en SOLBESKYTTELSE er det modsat** (2/10):
  køkkenlyset tændte 17:50:54 og frøs samplet på 65 lx, solen brød gennem 88 %
  meldt skydække, og `spisestue_dagslys_lx` faldt 58,9 → 53,3 mod mosbilledets
  tærskel 79 — mens den rå Apollo målte 224 lx og solen stod midt på billedet
  (foto). En beskyttelse skal læse en kanal hvis fejl går OPAD: rå minus et
  målt lampelys-loft (`sensor.mosbillede_lux_maalt` = max(dagslys, reel − 60);
  lampelys på spisestue-sensoren i mørke 18/9-2/10: p90 34, max 50 lx).
  **Signatur: en beskyttelse der ikke reagerer kort efter at et lys tændte i
  samme rum eller et nabo-rum, mens solen står lavt og bryder gennem skyer.**
  **2026-09-30b:** `open_plan_lux` har nu samme fremskrivning i sit sample-led
  (samme bånd-tabel + k_idag; spisestue-samplets sol_elev gælder også køkken-
  samplet, taget i samme minut) — men KUN under 11° sol, fordi kanalen også
  fodrer gardin-forsvarenes 200/500 lx-gates om eftermiddagen, hvor den ikke er
  valideret. Valideret på 137.412 rene sample-par 16-30/9: 0 × falsk mørke i
  dagtimerne, median fremskrevet/målt 0,84. `koekken_dagslys_lx` og
  `entre_lux_reel` arver den via `open_plan_lux` (B167 lukket).
  Alle tre hold-sensorer tager derfor `min(sample, rå *_apollo_lux)` — hold-tiden
  er kalibreret efter hvor længe lyset kan lyse, ikke efter hvor hurtigt
  aftensolen kan falde (målt: 556 → 112 lx på 30 min i vestvendt spisestue, mens
  samplet stod på 217,9). **Rå = `*_apollo_lux`, ALDRIG `*_lux_reel`** — den har
  LED-fradrag og kan klampe til 0,0.
  **Og et fradrag er ALTID for smalt i et åbent rum: en Apollo ser HELE
  open-plannet, ikke kun sit eget rums lamper** (4/9: `light.stue_all` slukket
  trak køkkenets "dagslys" 65,3 → 34,6, og `koekken_dagslys_lx` — som kun
  fradrager lyskæden — stod på 213 lx kl. 19:30 mod entréens 1,0). **Signatur:
  time-medianer HØJERE om aftenen end midt på dagen.** Løsningen er ikke et
  bredere fradrag, men et **loft af `sensor.open_plan_lux`** (den eneste kanal
  der pr. konstruktion er immun) — `min` kan kun gøre rummet mørkere = fejle mod
  "bliv tændt".
  **MEN de 78 lx gælder kun HVID: en RGBW-strip
  i mættet farve lyser næsten intet ind i LTR390'en** (målt 28/8, begge på
  bri 254: hvid +78 lx, orange sat 99 **+1 lx**) — fradraget skal derfor ganges
  med den hvide kanals andel (`1 - sat/100`), ikke kun med brightness.
  **Og over-fradrag er ikke gratis:** 78 lx trukket fra en rå værdi på 28
  klampede sensoren på 0,0 en hel dag, så begge dagslys-sluk krævede 128/143 lx
  ægte dagslys og var reelt blinde. Vælg stadig over- frem for under-fradrag,
  men kun inden for ét og samme farve-regime.
  **Og KLAMPNINGEN SELV er information man smider væk** (2026-09-20, user-bug
  "køkkenlyset har hængt i dag"): et fradrag større end den rå måling er ikke
  0 lux — det er *beviset* på at modellen er for stor, for en lampe kan fysisk
  ikke bidrage med mere lys end sensoren ser i alt. `max(…, 0)` forvandler det
  bevis til en selvsikker påstand om kulsort, og `min`-loftet mod
  `open_plan_lux` kan kun gøre tallet mørkere og kan derfor ikke redde den.
  Målt live: `raa=76,4`, fradrag `78,0` (hvid, bri 254) → `dagslys_lx = 0,0`,
  mens entré-VALLHORN stod på 54 og spisestue-Apolloen på 131. Fordi ENHVER
  "er der lyst nok?"-gate i open-plannet læser netop `koekken_dagslys_lx`, var
  hele rummets dagslys-sluk blindt, og kæden brændte 07:00 → 08:30 i fuldt
  dagslys. **Signatur: en dagslys-sensor klistret på præcis 0,0 mens den rå
  kanal måler 70-noget.** → detektér klampningen og forlad modellen
  (`min(open_plan_lux, raa)`) i stedet for at lade `max()` skjule den.

  **Og det RIGTIGE svar var hverken en bedre model eller en anden tærskel — det
  var en anden KILDE, fordi kontaminationen er selv-korrigerende** (2026-09-23,
  B135). Begge lux-gates flyttede til spisestue-Apolloen, som sidder tæt ved
  vinduet; overførslen køkken→spisestue blev **målt til 3,37×** over 129 rene par
  på 4 døgn (p10 2,08 · p25 2,76 · p75 3,74 · p90 3,96), og båndet sat til
  **tænd under 40 lx / sluk over 110 lx**. Argumentet der bærer det: TÆND-gaten
  evalueres altid mens lampen er SLUKKET (kanalen er ren), SLUK-gaten altid mens
  den LYSER (kanalen er biased OPAD) — og "opad" peger mod at slukke kunstigt
  lys, altså den sikre retning. En fejl i den retning koster et sluk der sker
  lidt for tidligt, ikke et lys der brænder en formiddag. Derfor kræves der ingen
  fradrags-model, kun et bånd **bredere end den målte kontamination** (parret skal
  være ≥ 56 lx). `bright`-tærsklen faldt helt væk, og morgen-rampen flyttede med.
  Commit `d6a0cf2`.

  **Et rent sample kræver mørke LÆNGE nok — og det gør probe-designet skrøbeligt
  på en måde der ligner en bug, men ikke er det** (2026-09-20).
  `sensor.koekken_dagslys_sample` opdateres kun mens
  `binary_sensor.open_plan_lys_rent` er `on`, og den har **`delay_on: 6
  minutes`** (sat efter lyskædens 300 s fade). Kæde-enforceren tænder igen efter
  **~27 s**. `automation.open_plan_dagslys_probe` kan derfor **aldrig** nå de 6
  minutter: dens betingelse 3 ("begge samples er forældede") bliver aldrig
  falsk. **Konsekvens: probens 45-minutters cooldown er BÆRENDE, ikke en bug.**
  Fjerner man den — fordi den "brændte" på et forsøg der blev klobret — fyrer
  proben hvert 5. minut for evigt og får open-plannet til at flimre off/on hele
  dagen. Det er værre end symptomet. Skal proben kunne virke, skal den enten
  suppressere enforceren i ≥ 6 min (mærkbart mørke for familien) eller selv læse
  de RÅ Apolloer efter ~30 s og skrive samplet — ikke få cooldownen fjernet.
  **Fælde ved kalibreringen:** hvert spots-skifte skifter OGSÅ kædens farve
  (spots on = cooking = hvid), så et 72-lx trin ved en spots-flanke tilhører
  kæden, ikke spots. Isolér altid den ene lampe ad gangen.
  **Og et fradrag må ikke stoppe ved entity'ens `off`:** HA sætter state til
  `off` i SAMME sekund et transition-sluk sendes, så lampen lyser videre i op
  mod hele fade-varigheden (køkken: 300 s). Skeln med attributten
  `off_with_transition` + `off_brightness`, og lad fradraget følge fade-kurven
  — målt kvadratisk, `(1 - t/fade)^2`, ikke lineær. Samme fælde omvendt ved
  TÆND: `brightness` melder målet med det samme, længe før lyset er der.
  **Og en slukket lampe har INGEN farve-attributter** (`color_mode`/`hs_color`
  er `None`), så en fade-gren der læser farven i sluk-faden gætter "hvid" —
  målt 15/9 16:09-16:21: en ORANGE kæde (~1 lx) trukket fra som hvid (~78 lx),
  sensoren 83,9 → 9,0 i sluk-sekundet, lux_ok åbnede, presence tændte igen,
  'bright' slukkede igen: fire cyklusser på 12 min. Bær farven fra sidste
  TÆNDTE render (`this.attributes`), og brug den transition kaldet faktisk
  sendte (`sensor.koekken_lyskaede_sluk_fade`, fanget fra `call_service`) —
  ikke den længste der findes (2026-09-29).
  **Og en lux-gates off→on-flanke er derfor oftest vores EGEN sluk, ikke
  tusmørke** — duer ikke som re-arm. Målt 2026-10-16 på
  `binary_sensor.koekken_lyskaede_lux_ok` over 14 døgn: 33 af 74 flanker kom
  < 60 s efter at kæden slukkede (den lyser +56 lx ind i vindues-kanalen), og
  alle 8 hvor en "tænd når det bliver mørkt"-re-arm kunne have fyret, var
  kædens egen sluk 8-54 s før → den ville gen-tænde kæden i ring. Ægte tusmørke
  med nogen i et mørkt open plan: 0 gange. Næste bevægelse er re-armen.
- **Soveværelsets Apollo fantom-fyrer i eftermiddagssolen** → `binary_sensor.
  physical_presence_recent` er ubrugelig som "huset er tomt"-vidne om dagen.
  Skal du bevise et tomt hus, brug **bredde** (en fantom rører ét rum, et
  menneske flere) — ikke stilhed. `apollo_latch_detect.yaml` fanger den ikke.
  → B73.
- **Et Thread partition-split heler IKKE altid sig selv (rettet 2026-10-09;
  før stod her "heler sig selv efter ~20-30 min").** 2026-09-03 var det
  rigtigt: 21 min efter en OTBR-restart begyndte routerne at joine i et 76 s-
  vindue, med entré-loftet som kingmaker (den er fysisk adskilt fra KAJPLATS-
  klyngen og joinede først). Men 08/10 ~21:35 → 09/10 06:27 sad OTBR'en som
  **ensom leder (`routerCount` 1) i 9 timer**: mesh'et (KAJPLATS + entré-loft +
  stue-spots) dannede sin egen partition uden om den, OTBR-loggen viste
  `Different partition` og NoAck/LinkMarginLow, og hver OTBR-restart og hvert
  RTS/DTR-pin-reset (`Reset info: 0x301 (PIN)`) lavede bare en NY ensom
  partition. Først et fysisk genplug af donglen (power-on-reset) kl. 06:27
  flettede nettet (8 routere 06:34). Lære: (a) tålmodighed er IKKE en kur i
  sig selv, (b) "chippen svarer" ≠ "mesh'et er samlet" — mål `routerCount` fra
  OTBR REST `/node` (`sensor.otbr_routere`), (c) en chip-kur på et raskt net
  (`routerCount` > 1) er skadelig. Stigen i `packages/thread_otbr_watchdog.yaml`
  roterer TX-boost (addon'et tvinger 6 dBm ved hver start) → chip-reset →
  USB-genplug (sysfs `usbN-portM/disable`) så længe border-routeren er afskåret.
  **Hård grænse:** NUC'ens xHCI-root-hub har `wHubCharacteristics=0x000a` =
  ingen port-strømstyring, så `disable` er en LOGISK frakobling — VBUS bliver
  tændt og EFR32'en får intet power-on-reset (`scripts/otbr_usb_replug.py`
  melder selv hvilken slags den fik). User køber ikke en hub (9/10).
  **Udløseren 08/10 var IKKE donglen:** stue-spotsene blev trukket ud 20:38,
  badets spots mistede dermed broen (20:56), og den gamle pære-baserede vagt
  pin-resettede OTBR'en 21:34 → ensom partition. Stue-spotsene er bro-routere
  mellem OTBR'en og badet.
- **Zombie-router: en Thread-pære kan sende MLE-advertisements (står i
  OTBR'ens `router table` med Age < 30 s) og alligevel være døv for al unicast**
  — Matter-ping og ICMP til dens RLOC fejler, HA viser `unavailable`, og den
  bliver stående i sin sidste fysiske tilstand (bad-spot_2 09/10, lyste i > 1 t;
  dens sleepy barn TIMMERFLOTTE 434 forsvandt med den). **Kur uden strøm:**
  `ot-ctl releaserouterid <id>` på lederen → gen-attach på ~80 s.
  Automatiseret i `scripts/thread_zombie_kick.py` (daemon-loopet).
- **Huset har ÉN slags ægte ZHA-grupper, og de er husets eneste (`zigbee.db` →
  `groups_v15`): `light.zbt_2_vejrvarsel_morgen` (group 2) og `_aften` (3).**
  Ét groupcast-frame rammer alle medlemmer samtidig ⇒ ingen bølge, men også
  **ingen APS-ACK pr. pære: misser en pære frame'et, er der ingen retry.**
  Oprettes/ændres kun via WebSocket (`zha/group/add|remove`) — der er intet
  REST-endpoint, og medlemskabet skrives i pærens NVRAM, ikke i git. **To
  fælder:** (a) en ZHA-gruppe markerer sig med attributten **`group_entities`**,
  ikke `entity_id` som HA's egne lysgrupper — en "er det en gruppe?"-guard der
  kun tester `entity_id` ser den ikke og kan komme til at groupcast'e et sluk
  (ramte `light_watchdog`); (b) **ZHA skriver ANTAGET state på medlemmerne efter
  et gruppe-kald**, så recorder-rækkerne ligger < 3 ms fra hinanden uanset hvad
  radioen gjorde — recorderen kan ikke bevise et gruppe-blinks synkronitet.
- **Recorderen gemmer INGEN lys-attributter ud over `friendly_name`** (+
  `off_with_transition`/`off_brightness` på ZHA) — det er HA's egen
  domæne-filtrering, ikke vores `exclude`. **History kan derfor ALDRIG bevise
  hvilken farve eller lysstyrke en pære havde**; kun live-polling af
  `/api/states` kan. Og polling har sin egen fælde: en Matter-pære rapporterer
  **1,21 s efter et `turn_on` fra slukket, men 0,19 s når den allerede lyser**
  (målt 12/9 på `light.entre_loft`, KAJPLATS) — et for kort vindue får huset til
  at se defekt ud. **Signatur:** "pæren blev ikke rød", hvor dit eget
  måle-interval er kortere end koldstarten.
- **HA's Matter-light videregiver ALDRIG `transition` til `turn_off`** — den
  sender et bart `OnOff.Off()`, så en Matter-pære går sort med det samme uanset
  hvad du beder om. ZHA-pærer honorerer det og fader i hele transitionen.
  **Konsekvens: en lysgruppe med BEGGE radioer slukker i to tempi**, og det kan
  ikke rettes fra sluk-vejene — de sætter kun `transition` på gruppen.
  **Signatur:** "nogle pærer først og så andre", hvor state-rækkerne ligger
  inden for 0,2 s (så det ligner korrekt gruppe-adfærd i history), og de sene
  pærer har `off_with_transition: true` + `off_brightness` sat. Fix ÉT sted, på
  gruppens `→ off`-flanke: re-send `turn_off` med `transition: 1` til
  ZHA-medlemmerne (bad: `badevaerelse_spots_confirm_off`). Gør de LANGSOMME
  hurtige — en Matter-softfade kræver pre-dim i hver eneste sluk-vej (#2).
  Roster: `light.badevaerelse_all` = spot_1/2/3 Matter (KAJPLATS), spot_4/5 ZHA
  (innr RS 242 C).

**Integrationer**
- **DMI lever på ÉN host med TO versioner:** prognose =
  `opendataapi.dmi.dk/v1/forecastedr` (**keyless**), observationer =
  `opendataapi.dmi.dk/v2/metObs/collections/observation/items` (**keyless**).
  **Rettet 2026-09-17 — denne bullet påstod tidligere "keyed, samme
  `dmi_api_key`", og det var forkert.** Begge endpoints er NØGLE-LØSE; DMI
  afskaffede brugerregistrering + API-nøgler ved platform-opdateringen ultimo
  2025 (`packages/dmi_weather.yaml:9`). Verificeret ved at læse de fire
  `rest_command`-definitioner der faktisk kalder DMI —
  `dmi_harmonie_precip` + `dmi_metobs_now` (`packages/dmi_weather.yaml:22-47`),
  `packages/regn_rapport.yaml:44-46` og `packages/regn_nu.yaml:65-76`: **ingen af
  dem har en `headers:`-blok**, og der findes ingen DMI-nøgle i `secrets.yaml`.
  Der er altså intet credential at fejlsøge når et DMI-kald fejler — mistænk
  host/version/rate-limit, aldrig en nøgle.
  Versionsnummeret hører til PRODUKTET, ikke til en generation —
  `/v1/metObs` svarer 404, og `/v2/forecastedr` findes ikke. Så "modernisér
  versionen så de matcher" er stadig forkert; det er kun HOSTEN der er skiftet.

  **Historik:** frem til 2026-09-09 lå observationerne på den keyless legacy-host
  `dmigw.govcloud.dk/v2/metObs`, og denne bullet advarede eksplicit mod at
  "modernisere" URL'en. DMI DNS-nedlagde hosten uden varsel: opslaget giver nu
  NXDOMAIN ("DNS server returned answer with no data", bekræftet mod 8.8.8.8),
  hvilket i praksis ligner en sandbox-blokade — `curl` returnerer **HTTP 000 på
  ~0,9 ms**, altså for hurtigt til at være en netværks-timeout. Disambiguér altid
  med et kontrol-curl mod en kendt host + `curl -sv` for at se resolver-fejlen,
  før du konkluderer at værktøjet er spærret.

  **Fejlen var usynlig i 16 timer, og det er den vigtige lærdom:** husets
  DMI-REST-sensorer har en `this.state`-fallback, så de holder sidste kendte værdi
  når hentningen fejler i stedet for at gå `unavailable`. `sensor.dmi_udefugt`
  stod derfor blank-fladt på 77,6 % (sand værdi 81,4 %) uden ét eneste rødt flag
  nogen steder — ingen `unavailable`, ingen logfejl i HA's UI, intet i
  `ha_health.sh`. **Signatur: en vejrsensor hvis `last_changed` er timer gammel
  mens vejret udenfor beviseligt har ændret sig.** Verificér ALTID en REST-sensor
  på `last_attempt_ok` + `observed`-tidsstemplet i attributterne, aldrig på state
  alene — en hold-last-value-fallback konverterer "død kilde" til "meget stabil
  måling". Fix 2026-09-10: host-swap i `packages/dmi_weather.yaml` +
  `rest_command.reload` (rører ingen template-entities = ingen B103-risiko).
- **met.no's `cloud_coverage` er systematisk for HØJ om natten** (+25 point i snit
  mod DMI-observation, **+43 på nætter hvor himlen faktisk er klar**, −7 når det
  virkelig er overskyet — målt over 181 nat-samples). Bias'en er ENSIDET og
  rammer præcis udstrålings-nætterne. Korrigér ved INPUTTET
  (`dug_metno_sky_bias_pct`), ikke i den fysik der forbruger tallet. Samme
  mønster som RH-bias'en: met.no melder 6,05 RH-point tørrere end DMI om natten.
- **`.env` findes IKKE i denne checkout** (kun `.env.example`) → `$HA_TOKEN` er
  tom og giver 401. Vi kører PÅ HA-hosten (`/homeassistant` == `/config`), så
  brug `$SUPERVISOR_TOKEN` mod `http://supervisor/core/api/...`.
- **Energi Data Service' `raw_today[].price` er allerede inkl. nettarif + afgifter**
  (ex moms) — læg aldrig tariffer til igen.
- **`sensor.phone_a_next_alarm` (Android) melder UTC**; Parent B's melder lokal offset.
  `unavailable` = "ingen alarm sat", ikke en defekt sensor.
- **2026-10-04 (B149): den native timer er UDE af køkken-timeren.** User
  bekræftede 4/10 at timeren "fortsætter ufortrødent" efter hver dismiss-variant
  — OnePlus' Ur implementerer reelt ikke `DISMISS_TIMER`. Lyden er nu en HA-ejet
  TTS-løkke (`message: TTS`, `media_stream: alarm_stream`, engelsk tekst — telefonens TTS-motor kan ikke dansk, gentaget hvert 10. s
  så længe lysalarmen varer — en version der ringede til kvittering talte i
  2½ min, fordi kvitteringen ikke kom igennem; stop med
  `message: command_stop_tts`). Prisen: lyden kræver forbindelse i udløbs-
  øjeblikket, som den native timer ikke gjorde. Teksten herunder er historik.
- **HA kan sætte en NATIV timer i Android-telefonens Ur-app** — husets eneste
  lydkanal i køkkenet, siden kamera-højttaleren er uopnåelig (B146). Kanalen er
  `notify.mobile_app_phone_a` med `message: "command_activity"`. Målt på PHONE_A
  2026-09-16, hele sekvensen verificeret på selve telefonen:

  - **Start:** `intent_action: android.intent.action.SET_TIMER` med
    `intent_extras: android.intent.extra.alarm.LENGTH:<sek>:int,android.intent.extra.alarm.SKIP_UI:true:boolean,android.intent.extra.alarm.MESSAGE:<label>:String`.
    `SKIP_UI` holder Ur-appen ude af forgrunden.
  - **Fjern:** `intent_action: android.intent.action.DISMISS_TIMER` med
    `intent_extras: android.intent.extra.alarm.SEARCH_MODE:android.label,android.intent.extra.alarm.MESSAGE:<label>:String`.

  **Tre fælder, alle målt — ikke gættet:**

  1. **Der findes INGEN kvittering fra HA's side.** `sensor.phone_a_next_alarm`
     rørte sig ikke ét sekund mens en timer beviseligt kørte på skærmen: en
     timer tæller ikke som "næste alarm". Og `HTTP 200` på service-kaldet
     betyder kun at FCM tog imod pakken — intet om hvad telefonen gjorde.
     **Verifikation kræver et menneske der kigger på telefonen.** Derfor er den
     rigtige test at bede om præcis to observationer: "kom den?" og "forsvandt
     den igen?".
  2. **Et type-suffiks på `SEARCH_MODE` dræber dismiss'en TAVST.**
     `SEARCH_MODE:android.label:String` gjorde ingenting (test-timeren overlevede
     og ringede en time senere); nøjagtig samme kald uden `:String` fjernede
     timeren med det samme. Nøglen skal have værdien bar. **Signatur: en dismiss
     der svarer 200 og efterlader timeren.**
  3. **`SEARCH_MODE:android.all` virker ikke** på denne Ur-app — kun
     `android.label`. Det er heldigt: en dismiss-all ville også dræbe en timer
     brugeren selv har sat, og det tab ville være tavst. Match derfor altid på
     en label du selv har skrevet, og hold labelen ét sted i koden, da den
     bruges BÅDE ved SET og ved DISMISS.

  **Labelen skal være ren ASCII.** Værdien løber gennem en
  `key:value:type`-parser hvor `,` og `:` er delimitere; et `ø` der ikke
  overlever kodningen ville tavst gøre dismiss'en til en no-op og efterlade en
  timer der ringer. Huset bruger `Koekkentimer`.

  **Og dismiss'en holdt ikke i drift (målt 2026-09-17).** Dagen efter at fælde
  2 var kalibreret — bar `android.label` fjernede timeren med det samme —
  overlevede **tre** annullerede køkken-timere **fire** forskellige
  dismiss-varianter i træk (label bar, label `:String`, `android.all`,
  `android.time` med `LENGTH:120`). Alle fire svarede HTTP 200, og user
  rapporterede tre gange at nedtællingen kørte videre på telefonen. Hvad der
  skiller den vellykkede test fra de tre fejlede, kunne ikke afgøres — og det er
  hele pointen: **en kanal uden kvittering kan ikke fejlsøges, kun undgås.**

  **Designreglen der følger:** sæt aldrig en telefon-timer du kan komme til at
  fortryde. Lad HA eje nedtællingen (`timer.koekken_gestus`) og sæt først
  telefonens timer **når tiden ER gået**, på ét sekund (user-spec 2026-09-17).
  Så findes der aldrig en telefon-timer under nedtællingen, og en annullering
  har ingenting at rydde op i. Dismiss'en lever kun ét sted bagefter — i
  `koekken_gestus_alarm_stop`, hvor telefonen faktisk ringer, og hvor en
  mislykket dismiss højst koster at man selv skubber den væk. Bonus: ét sekund
  er et fingeraftryk intet menneske sætter, så `SEARCH_MODE:android.time` med
  `LENGTH:1` kan bruges som ekstra forsøg uden at kunne ramme en timer brugeren
  selv har sat.

  **Hvorfor en native timer og ikke bare en push med lyd:** den ringer videre
  til den afvises, den går uden om lydløs/DND, og den er uafhængig af at HA,
  wifi og FCM lever i selve udløbs-øjeblikket — kun STARTEN kræver forbindelse.
  En push fejler præcis omvendt. Mønster:
  `script.koekken_gestus_telefon_timer` i `packages/koekken_gestus_timer.yaml`.
- **`input_boolean.<person>_home` er en GPS-FRISKHEDS-degraderet proxy**, ikke
  "er personen hjemme" — en stille iPhone er tavs i op til 17 t. Gates der skal
  overleve natten må også læse trackerens sidst kendte zone.
- **En iOS Companion-app uden `Authorized Always` kan ALDRIG melde et zone-skift.**
  Falder `sensor.phone_b_location_permission` til "Authorized when in
  use" (iOS gør det selv, fx efter en opdatering), fryser `device_tracker`'en på
  sin sidste zone, og `presence_*_leave` — der ejer afgangen — får aldrig sin
  flanke. Trackeren er da ikke *langsom*, den er **strukturelt ude af stand**:
  tavsheden har nul informationsindhold, så en staleness-tærskel er kun en
  forsinket løgn. Permission-sensoren er husets eneste vidne om det, og den kan
  ikke flappe. Læs `binary_sensor.parent_b_gps_baggrund_ok`, ikke sensoren rå.
  Android (`phone_a`) rapporterer ingen tilsvarende sensor = blind vinkel.
  **Pr. 2026-08-15 er Parent B's presence flyttet HELT væk fra GPS:** to
  iOS-Genveje trykker på `input_boolean.parent_b_hjemme_ios` (begge verificeret
  live), `parent_b_ios_geofence_enabled` er ON, og app-tilladelsen er med vilje
  sat ned → trackeren er permanent frossen = **nul evidens** om hende. Spørg
  iOS-kontakten, aldrig `device_tracker.phone_b`. Afgangs-kaldet
  sendes pr. definition efter hun er af hjemme-wifi → det hænger på Tailscale;
  svigter det, hænger kontakten ON, og `parent_b_ios_geofence_stille_hus`
  varsler (rydder ikke — en sovende krop ligner stilhed).
- **Kun `zone.home` giver tracker-state `'home'`** (#17).
- **Notifikations-KNAPSVAR kræver netværk til HA** (hjemme-wifi eller Tailscale) —
  leveringen går via FCM/APNS og virker overalt, men svaret er et HTTP-kald
  tilbage. Manglende svar ≠ brugeren ignorerede spørgsmålet.
- **Roborock sug + mop er ÉN tilstand, ikke to knapper** (målt live 08-16):
  `fan_speed: max_plus` nulstiller `mop_intensity` til `off`, `mop_mode:
  deep_plus` nulstiller `fan_speed` til `off`, og `deep` afvises → `standard`.
  Enhver mop-skrivning sætter desuden sugestyrken ned til `balanced`, så sug
  skal skrives SIDST. Kraftigste kombination der holder samtidig: **`max` +
  `extreme` + `standard`**. En "grundig" clean der kun mopper = dette.
- **Roborock:** statussen kommer fra deres SKY og lander 18-155 s EFTER robottens
  egen start; `vacuum.s8_maxv_ultra` kollapser alle varianter til `cleaning` —
  kun `sensor.s8_maxv_ultra_status` skelner. Session-flagene ryddes KUN ved en ren
  afslutning (en fejlet kørsel lader dem hænge i timevis). **Robotten ER den
  bevægelse Apollo'erne ser** og ligner en person der sidder stille →
  `binary_sensor.roborock_zone_maskering` (pre-roll 180 s pga. sky-forsinkelsen,
  `delay_off` 20 min pga. Apollo-latchen) gør at en zone der tændte MENS den
  kørte ikke tæller som EKSTRA person — men den kan kun trække estimatet til 1,
  aldrig til 0. `roborock_blokerer_lys` duer IKKE som anker: den kræver Dormant
  og er OFF i præcis det scenarie der snyder.
- **Roborock ser KUN forhindringer mens den gør rent — `app_goto_target` og
  fjernstyring (`app_rc_*`) registrerer intet og tager ingen fotos** (målt live
  2026-10-22, foto-optagelse slået til i appen: `cameraStatus` 421 → 3493, bit 10
  = map-object-foto). Goto kørte lige ind i et par sko; en `app_zoned_clean` over
  samme felt fandt dem straks (86 %, foto `002aSNI2zGRUF942`). En "rundtur uden
  at støvsuge" kan derfor ikke bygges på goto/RC — kun på en rigtig rengøring
  (evt. med sug/mop skruet ned). Under RC opdateres kortets robot-position ikke;
  negativ `omega` = drej til HØJRE, `velocity` ≤ 0,3 m/s. `avoid_count` nulstilles
  pr. clean. Fotoet hentes med python-roborocks `ObstaclePhotoTrait.get_photo(
  photo_name)` (navnet fra `map_data.obstacles_with_photo[].details.photo_name`)
  inde i `homeassistant`-containeren — HA eksponerer det ikke.
  **`get_collision_avoid_status` = `{'status': 2}` efter at user slog forsigtig
  kørsel til i appen** (var 1; 0 = fra; 2 er udokumenteret) → appens valg er
  facit, `script.roborock_apply_forsigtig` skriver 2.
- **I SmartPlan afviser robotten løse profil-skrivninger** (målt 2026-10-24):
  efter en Styrbar-SmartPlan-tur stod sug/vand/mop-rute alle på `smart_mode`, og
  `select.select_option` på `select.s8_maxv_ultra_mop_mode` → `standard` fejlede
  med "Error while calling SET_MOP_MODE" — hvert 2. min i 10 min, indtil
  afleveringen (`roborock_smartplan_aflever`, venter 10 min efter turen) kom ud
  med det atomiske `set_clean_motor_mode` (102/200/300, landede på 3 s). Rum-
  køens grundig-gren havde ingen `continue_on_error`, så 6 bestilte rum hang
  ("den ignorerer sin kø!"). Fix: `script.roborock_forlad_smartplan` kaldes
  først af hver profil-vej; no-op uden SmartPlan.

<!-- flyttet fra CLAUDE.md 2026-09-12 under linje-budget-oprydningen -->
- **HA Core's shell_command-subproces har en `SUPERVISOR_TOKEN`, men supervisor-proxyen
  afviser den med 401 for `/core/api`** (2026-10-03, B182). `scripts/apollo_kalib_capture.py`
  prøvede den først; fra SSH-add-on'et virker begge veje (200), fra HA Core kun
  secrets-tokenet. Automationen `apollo_kalib_nat_baseline` fyrede 01:00 3/10 (bestillingen
  ryddet, `logbook.log` skrevet), men der kom aldrig en outputfil — barnet døde i første
  template-kald, FØR engineering mode blev slået til, og `--detach` sendte stderr i
  /dev/null. Rettet: secrets-token + loopback først, `<raw_dir>/capture.log` med
  traceback; bevidnet 3/10 21:16 ved at starte den via HA's egen `shell_command`.
  (Tokenet hed `plant_notify_token` til 20/10; nu `ha_api_token`, og alle scripts læser
  secrets.yaml gennem `scripts/ha_secrets.py` — kontrakten er `secrets.example.yaml`,
  håndhævet af `scripts/secrets_contract.py`. Ti kopierede parsere var sådan en
  nøgle-omdøbning blev overset.)
- **DMI lever på ÉN host, `opendataapi.dmi.dk`, med TO versioner:** prognose =
  `/v1/forecastedr`, observationer = `/v2/metObs` (**begge keyless** — rettet
  2026-09-17; ingen `headers:` i noget DMI-`rest_command`). Versionen hører
  til PRODUKTET — `/v1/metObs` er 404. Legacy-hosten `dmigw.govcloud.dk` er
  **DNS-nedlagt 9/9 2026**; NXDOMAIN giver `curl` HTTP 000 på ~1 ms, hvilket
  ligner en sandbox-blokade → disambiguér med et kontrol-curl + `curl -sv`.
- **En REST-sensor med `this.state`-fallback bliver ALDRIG `unavailable` — den
  fryser på sidste værdi og lyver med fuld selvsikkerhed.** `dmi_udefugt` stod
  16 t på 77,6 % (sandhed 81,4 %) uden ét rødt flag. **Signatur: `last_changed`
  er timer gammel mens virkeligheden beviseligt har ændret sig.** Verificér på
  attributterne `last_attempt_ok` + `observed`, aldrig på state alene.
  **Fælden har ramt huset TO gange, ikke én** — og anden gang var i en anden fil,
  af nøjagtig samme årsag (fejlklasse #2): `sensor.regn_faldet` i
  `packages/regn_rapport.yaml` pegede stadig på den DNS-nedlagte
  `dmigw.govcloud.dk`, som blev ryddet i `dmi_weather.yaml` 10/9 men ikke her.
  Den stod derfor på en fuldstændig plausibel **0,3 mm**, båret videre af
  `this.state`-fallbacken uden ét rødt flag, indtil den blev fundet 12/9. Efter
  host-fixet + reload: 0,3 → **0,0** med `last_attempt_ok: True`. **Lærdom: en
  hold-last-value-fallback gør en død kilde til husets mest stabile sensor, så
  når du finder ÉN, skal du grep'e hele huset for den samme URL/host — ikke kun
  rette den fil du kiggede i.**
- **Nemligs søgning er IKKE ascii-foldende — søgeord skal staves med danske
  bogstaver.** Målt 1/9: `soedmaelk`/`sodmaelk` gav score 0,00 med «Coca-Cola»
  som bedste bud, `sødmælk` gav 1,15 mod «Sødmælk 3,5%». Resten af koden
  normaliserer ø→oe internt (parringsnøgler), men det der SENDES til dem skal
  være dansk. Signatur: et helt almindeligt ord finder kun sodavand.
- **Nemligs søgesvar bærer et VARETRÆ i tre niveauer — og BLADET er varearten.**
  Hvert produkt har `ProductMainGroupName › ProductCategoryGroupName ›
  ProductSubGroupName` («Frugt og grønt › Grønt › Svampe» for Portobello,
  «Tørvarer › Ris › Løse ris» for Basmatiris, «Dyremad og tilbehør › Hund ›
  Hundegodbidder» for et produkt der bare hedder "Andebryst"). Matcheren læste
  i 5 iterationer kun midten ("Grønt") og kunne derfor ikke vide at Portobello
  er en svamp, at «Pizza pepperoni» er en pizza, eller at «Oregano» i
  Tørvarer › Krydderier ER tørret oregano. Fra 1/10 læser `nemlig_api.taksonomi()`
  midten + bladet + hele stien (FORM-ord). Tre beslægtede API-fakta målt samme
  dag: (1) `Favorite` = "har købt varen før" og dækker næsten alle varianter
  (huset har købt brune, basmati-, jasmin-, risotto- og grødris) — det er en
  smags-præference, ikke evidens for VAREN, og den slog i 99 af 465 råvarer en
  billigere tilsvarende vare (værst 5,2× for 1 dl madlavningsvin). (2) En
  multipak prissættes PR. STYK: «Zealy Sauvignon Blanc — 6 x 0,75 l» står til
  54,95 kr./Stk. men koster 329,70 kr, og "2 x 75 g" pancetta er ÉN pakke på
  150 g. (3) Midten for sodavand hedder "Sodavand, vand og læskedrikke", ikke
  "…læsk". **Signatur på at en matcher-ændring ikke er målt: tallet for
  "auto-parret" stiger, men ingen har set på om VARERNE er rigtige** — mål med
  `nemlig_selftest.py --offline --diff` (samme søgesvar før/efter) og lad en
  semantisk audit (agent + din egen verifikation) se de ændrede valg.

- **hand_recognition-add-on'ets `three_fingers` er TOMMEL + pege + lang — ikke
  pege + lang + ring, som README'en påstår.** Tabellen i `hand_recognizer.py`
  (v0.3.27) har intet mønster for pege+lang+ring, og nærmeste-match-reglen
  (flest enige fingre) giver `four_fingers` (1 finger fra) frem for
  `three_fingers` (2 fingre fra) — deterministisk, typisk over score-tærsklen.
  Målt 24/9: to "3"-forsøg, ét læst 3 og ét læst 4 i alle frames. **Signatur: et
  fingertal der er konsekvent forkert med én, ikke flimrende** — hold-kravet
  beskytter kun mod flimmer. Fuld analyse: `docs/gesture_recognition.md`
  ("`3` er IKKE et vinkel-problem").

- **Afstanden til en hånd kan kun gates på dens MÅLTE størrelse — hverken
  hold-kravet eller shimmens billed-skala kan det.** 2026-10-05 fyrede tre
  4-min-timere 15:02-15:06 fra én venstre hånd ved køkkenbordet (~1,5 m, user:
  utilsigtet; træner-svar `utilsigtet`). Add-on-loggen: 15:02:03-04 og
  15:03:30-32 `four_fingers` med ryggen mod linsen (rotation −35…−58°), og
  ec:09:9b-6a:c0:11 SEKS frames i træk med håndfladen mod linsen, score
  0,90-0,94 — et hold på 6 havde stadig fyret. Skalaen (24/9: 65 %) fjernede
  krukke-grebene, men 28/9 krævede en knytnæve på 50 cm fuldt billede (sweep
  70 % 0/14 … 100 % 3/14): palme-detektoren finder åbne hænder langt bedre end
  knytnæver, så en global skala skærer knytnæven væk før den fjerne åbne hånd.
  Fix (shim 0.16.0, `PalmGate`): add-on'ets egen palme-detektor
  (`palm_detection_full.tflite`, byte-identisk med mediapipe 0.10.14's) måler
  palme-boksen — 1,07-1,12 × håndled→langfinger-knoe for åben hånd og
  knytnæve — og MediaPipes hånd-ROI om enhver palme under
  `input_number.gestus_min_haand_px` fjernes før add-on'et ser billedet —
  siden 0.16.2 ved at add-on'et KUN får de nære hænders ROI (resten gråt):
  sort maske (0.16.0) og sløring (0.16.1) lækkede begge `four_fingers`, B235.
  **opencv_zoo's palme-ONNX er LITE-modellen** og missede halvdelen af de
  palmer < 50 px som add-on'ets FULL fandt — tjek sha256 mod det add-on'et
  kører, ikke modelnavnet. Fejler åben (ingen model/fejl = uændret billede).
  Offline-bevis med add-on'ets kode som orakel: 0 små hænder overlever
  maskeringen, 0 store tabes (209 hænder, 4 tærskler). Hver palme logges til
  `/share/gesture_frame_shim/palms.jsonl` (live: shimmens `/haand`). **Signatur
  på afstands-falske: lange stabile striber med høj score, ofte venstre/højre
  konsekvent, og de flytter sig ikke når holdet hæves.**

- **Speech-to-Phrase forveksler -teen/-ty på køkken-mikrofonen — akustisk og
  deterministisk, ikke et klip-problem.** Kalibreret 2026-09-28 (shim 0.14.0's
  `/kalibrer`-tilstand, 16 ytringer i fast rækkefølge): twenty 5/5, eleven 2/2,
  twenty five 2/2, thirty 2/2 — men **fifteen → fifty** (1/3) og **sixteen →
  sixty** (1/2); et tidligere 'fifteen' svingede 16/18 ved replay. Alle 16 klip
  genafspillet med 0,4 s stilhed foran/bagved og peak-normaliseret til −3 dBFS
  (`scripts/stemme_replay.py`): INTET tal ændrede sig. Kameraets 8 kHz A-law
  taber netop '-n'et der skiller -teen fra -ty. **Signatur: et timertal der er
  ×10-ish for højt og ellers en perfekt sætning.** Afbødning (user-valgt):
  timeren starter som hørt, men kvitteringen er et DOBBELT vink ved 13-19 og
  30/40/50/60 (`script.koekken_stemme_kvittering`, `advarsel`). Armerede klip
  gemmes i `/share/gesture_frame_shim/clips` (ring på 80) — start dér næste gang
  en stemme-kommando "hørte noget andet".

- **Køkken-kameraet hænger ~30 cm over users hoved — øjenkontakt kræver et
  vippet hoved, og blik-modellen læser det bevidste kig HØJT og ustabilt**
  (user 2026-10-03). Målt samme dag tæt på (ansigt 111-142 px, score 0,85-0,93,
  frontal ≤ 0,2 = alle andre krav bestået): 3-frames-medianer 29,4 / 27,6 /
  24,3 / 26,1 / 23,9 / 25,8 / 18,5 / 25,5 før én 14,5 armerede — fem ytringer
  droppet som `unarmed` på to minutter. 01/10 målte samme slags kig 6-10°.
  Ambient-ansigter der består score/frontal: 32,1-58,1 (23/9-3/10). **Signatur:
  `heard`-linjer mangler, `/motion` → `voice.afvist` viser `unarmed`-ytringer
  på 1,2-1,9 s, og `gaze cal` står i 18-30 mens `gaze face` har score ≥ 0,85.**
  At sænke ansigts-sikkerheden hjælper IKKE (ansigtet der armerede: 0,91), og
  den lukker 5× flere ambient-ansigter ind (2,8 % → 13,5 % af face-samples ved
  80 → 60). Svaret (shim 0.15.0): et blik der falder SAMMEN med ytringen armerer
  med løsere vinkel (`input_number.koekken_blik_tale_taerskel_grader`, 26°, ≥ 2
  billeder fra 2 s før første ord) — `GazeWatcher.heard_while_looking`.

<!-- flyttet fra CLAUDE.md 2026-09-17 under linje-budget-oprydningen -->
- **Køkken-kameraets (Tapo C210) KONTROL-API er DØD — kun RTSP virker. Og
  højttaleren findes KUN bag kontrol-API'en.** Fastslået 2026-09-16, B146 lukket
  som UMULIG på user-beslutning (*"ok luk b146 som umulig"*).

  **Årsagen er FIRMWAREN, ikke vores credentials.** TP-Link ændrede med firmware
  fra **~midten af 2026** login-handshaket på den lokale kontrol-API til et
  nonce-baseret "secure login" (`encrypt_type: 3` + `cnonce`). **`pytapo`
  implementerer det ikke**, så kameraet svarer `error_code -40211`, som
  `tapo_control` oversætter til præcis *"Invalid authentication data"*. Den tekst
  er kameraets eget nej, ikke et catch-all: `invalid_auth_cloud` sættes **kun**
  når exception-teksten er ordret den streng (`config_flow.py:691`). Vi ved
  altså at kameraet svarer og forstår protokollen — det afviser credentialet.

  **FEM kombinationer målt afvist**, alle med ægte `invalid_auth_cloud`: tre
  passwords × brugernavnet `admin`, emailen × det nulstillede password, og
  **camera account'en fra `secrets.yaml`** — den der samtidig autentificerer
  **RTSP fejlfrit** (`DESCRIBE` → `200 OK`, verificeret efter password-skiftet).
  **Det er den skarpeste mulige bekræftelse: samme brugernavn og password, to
  protokoller, ét ja og ét nej.** Netværk, port og protokol er dermed udelukket.

  **Højttaleren kan heller ikke nås udenom via go2rtc/RTSP** — tre uafhængige
  målinger 2026-09-16:
  - RTSP `DESCRIBE` med `Require: www.onvif.org/ver20/backchannel` på
    `/stream1` og `/stream2`: `200 OK`, men **nøjagtig samme SDP** som uden
    headeren (ingen `a=sendonly`). Headeren blev tavst ignoreret = et nej.
  - ONVIF **`GetAudioOutputs`** (enheden svarer på port **2020**,
    `/onvif/device_service`): **tom liste**.
  - ONVIF `GetProfiles` over `profile_1/2/3`: **6 `AudioEncoderConfiguration`
    (mikrofon = kameraet SENDER) og 0 `AudioDecoderConfiguration`
    (højttaler = kameraet MODTAGER)**.

  **MIKROFONEN kan derimod nås** — den ligger i den almindelige RTSP-lydtrack
  (PCMA/8000, verificeret dekodet) og kræver **hverken `tapo_control` eller
  go2rtc**. Tovejslyden i Tapo-appen kører over den proprietære kontrol-API,
  altså præcis den firmwaren har brudt.

  **Reglen at tage med: spørg ALTID hvilken RETNING lyden løber.** RTSP er en
  **hente**-protokol; at sende lyd TIL en enhed kræver ONVIF backchannel. "Kamera
  + lyd" er to helt forskellige opgaver alt efter retning, og den ene er gratis
  mens den anden er umulig på denne hardware.

  **Mikrofonen som "spiller højttaleren?"-orakel (målt 2026-10-09, B202):**
  NIVEAUET skiller ikke — radio (P4, volumen 25) og stoppet højttaler målte
  begge ~−57 dB middel i `volumedetect`; køleskab, emhætte og stemmer dominerer.
  Det der skiller er **krydskorrelation af 50 Hz log-envelopes** (diff(x),
  8 kHz mono) mellem kamera-lyden og Volumios egen stream-URI optaget samtidig:
  spiller 5/5 på 0,23-0,48 (senere 0,69) ved lag **0,3-0,8 s** (kamera bagud);
  stoppet 0,075-0,12 ved tilfældigt lag. Søg kun lag −0,5…2 s — et ±15 s-vindue
  finder tilfældige toppe på samme højde som signalet (første regel gav falsk
  "ikke hørbar"). Dom: `≥ 0,15` OG `> gulv + 0,08`, gulv = samme søgning mod
  den tidsvendte reference. Værktøj: `scripts/hoejttaler_lyttetest.py [sek]`
  (i HA-containeren; læser RTSP-URL'en fra secrets uden at printe den).

  **Installér ikke `tapo_control` igen.** Opgradering hjælper ikke (pytapo
  3.4.19 + integration 7.1.27 er nyeste, ingen af changelogsene nævner auth),
  2FA er en blindgyde, og gen-onboarding/Third-Party-Compatibility-toggle er
  prøvet og virker ikke. Kameraet spærrer desuden aggressivt: **to fejlede
  forsøg giver `Temporary Suspension: Try again in 1799 seconds`**, og config
  flowets ip-step brænder **selv** et forsøg (`registerController(host, port,
  "invalid", "")`, `config_flow.py:882`) ⇒ du får højst ÉT ægte
  credential-forsøg pr. spærringsvindue. Fuld bevisføring + den eneste
  dokumenterede genåbnings-vej (bloker kameraets internetadgang → gen-onboard
  offline → slå auto-update fra → lokal Camera Account):
  `grep -n "B146" BACKLOG.md`.

## `light.spisestue_pendel` er sove-loftet (2026-09-27)
Pendlen (CCT-only) blev flyttet fysisk til soveværelset 2026-06-05 og spiller
sove-loft; entity-navnet blev IKKE ændret (kode repointet i stedet, se
`packages/light_groups.yaml` "Soveværelse all"). 27/9 tog gæste-RODRET'en den med
i sit "open-plan + entré"-kald ud fra navnet → forældrenes loft slukkede/tændte på
gæstens tryk, og sove-lyskæden fulgte loftet. Tjek gruppe-medlemskab
(`light.*_all`) før du stoler på et rum-navn i en entity_id.

## HA segfaulter under nedlukning — restore-state skrives ikke (2026-09-28)
Målt 28/9: user satte `global_light_aggressiveness` 58 → 70 kl. 19:21:59, Claude
satte måltids-sliderne 40/2700 kl. ~19:20; genstart 19:29 → alle tre tilbage
(58, 1, 2200) uden context. `home-assistant.log.fault` (mtime 19:28): `Fatal
Python error: Segmentation fault`, øverste tråd i `pychromecast/socket_client.py
initialize_connection`. `core.restore_state` blev først skrevet igen 17:29:32Z
(efter boot). Ændringer sat > 15 min før en restart overlevede (periodisk dump),
fx `koekken_kamera_krop_enabled` sat 18:38. Workaround: `POST
/api/services/homeassistant/save_persistent_states` før hver restart — verificér
med `last_seen` i `.storage/core.restore_state`. **Siden 2026-10-07 håndhævet:**
`scripts/ha_restart.sh` gemmer og genstarter (også fra `ha.sh`/`ha_deploy.sh`),
og PreToolUse-hooken `scripts/restart_guard.py` afviser en bar genstart i
Claude-sessioner. Rodårsag (Cast + 3.14) er ikke
løst; `config_snapshots/helper_values.yaml` + `helpers_restore.py` er nødplanen.

## `sun.sun` opdaterer kun hvert 4. minut (2026-09-30)

`sun.sun`s `azimuth`/`elevation` skrives hvert 4. min mens solen står over
~10° og hvert 2. min under (målt i history 29-30/9: 16:40:46, 16:44:46, … og
17:51:34, 17:53:34, …). En template der læser dem ser altså en op til 4 min
gammel sol, og en minut-tick + et reguleringsinterval lægger mere oveni. Ved
lav eftermiddagssol falder solhøjden ~0,13°/min i KBH, og en solplet 2,7 m
inde kravler ~0,7 cm/min. Mosbilledet havde 30/9 kun ~40 s margin af den
grund. Løsning: fremskriv solhøjden, `dh/dt = 0,2507°/min · cos(bredde) ·
|sin(az)|` (gælder eftermiddag, az > 180), i stedet for at stramme intervallet
(`sensor.mosbillede_solindfald_cm`). Recorderen gemmer heller ikke sun.sun's
attributter → historiske solpositioner skal REGNES (NOAA-formlen rammer
sun.sun ±0,2°).

## `statistics`-vinduer mister bunden over en ændrings-rapporterende sensor (2026-10-01)

Badets TIMMERFLOTTE (Matter) rapporterer kun når værdien ændrer sig (målte
huller er multipla af ≈ 58,6 s: 117/175/234/293/586 — hvile-rapporten kommer
hver 293 s, og ser ud til at blive sprunget over når værdien står helt stille). `statistics` med `max_age` ser kun samples der
LIGGER i vinduet — rapporteres der intet i hvilen, er vinduet tomt når
hændelsen starter, og `value_min` bliver hændelsens eget første sample.
Målt 1/10: temperaturen stod på 25,05 fra 05:37:30; ved badets start 06:01 var
20-min-vinduet tomt, og temp-stigningen målte +0,18 °C kl. 06:05:49 mod reelt
+0,27. Fugten (293 s takt mod et 300-s burst-vindue) havde 7 s margen og mistede
bunden 25/9 (586 s hul → første bad-sample målte burst 0). (`keep_last_sample`
er ikke afprøvet — den beholder kun det SENESTE sample, så den hjælper næppe.)
Løsning: bær forrige sample med fra en trigger-template på `trigger.from_state`
(`sensor.badevaerelse_fugt_forrige`) og tag min(vindue, forrige). Det dækker et
SPRING (fugt-burst), ikke en stigning over flere samples (temp — B174).

## `history_stats` med `start:` på en flanke er STALE i flankens sekund (2026-10-02)

`sensor.sove_lyskaede_presence_siden_loft` tæller presence siden
`light.spisestue_pendel.last_changed`. history_stats genberegnes på kilde-
entitetens skift og ved et minut-tick — IKKE når start-templatens entity
skifter. Når loftet tændte 2/10 05:53:38, stod tælleren stadig på 6,01 t
(presence fra loftets SLUKKEDE periode = nattesøvn) og faldt først til 0,01 t
ved næste tick 05:54:21. Kæde-reglen, der triggede på selve loft-flanken, læste
6 t ≥ 3 min og tændte kæden 0,13 s efter loftet. 20 af 45 kæde-tænd 23/9-2/10
kom < 5 s efter loftet (3-min-reglen sprunget over, fx vækningens fase 1).
Løsning: læg det loft tallet aldrig kan overstige ind i conditionen —
tiden siden flanken (`now() - last_changed ≥ N`). Ved genberegningen er
tallet altid ≤ tiden siden start, så ingen trigger tabes.

### `!include` vs. `!include_dir_named` når filen mangler eller er ugyldig (2026-10-04)

Målt i HA 2026.9.2's egen loader (`homeassistant.config.load_yaml_config_file`):
`!include` af en manglende fil giver "Unable to read file" og en ugyldig fil (fx
merge-konflikt-markører eller en `\x` i en dobbelt-citeret streng) en
`HomeAssistantError` — begge ender i `bootstrap` som "Failed to parse
configuration.yaml … Activating recovery mode", altså ALLE automations nede.
`!include_dir_named <mappe>` på en manglende mappe giver derimod `{}` uden fejl
(en ugyldig fil I mappen fejler stadig). Derfor: en fil HA læser ved hver start,
men som et script skriver (P1: init_user_preferences ← helpers_export), skal være
afledt, kun indeholde tal, skrives atomisk (tmp + `os.replace`) og have
`merge=binary` i `.gitattributes` — målt: både `git merge` og `git stash pop`
efterlader så vores version uden markører (merge holder stien i konflikt).
Pre-commit `helpers_export.py --check-derived` fanger en fil der ikke passer.
Fundet af adversarial review af P1, docs/konsolidering.md §6.

## Apollo-LTR390'en er delta-rapporteret (~20 lx) — tusmørkets sidste trin hænger (2026-10-04)

`sensor.<rum>_apollo_lux` sender kun en ny værdi når den har flyttet sig ≥ ~20 lx
(målt på soveværelset 4/10: mindste trin 20,5 lx på alle niveauer — 87,7 → 59,3 →
38,5 → 18,0 — og derefter INGEN rapport fra 18:08 til en HA-restart 20:41, der
genmeldte præcis `18.0083332061768`). Det er firmwarens filter, ikke en død chip.
Konsekvens: i skumringen stopper kanalen på et tilfældigt sted i [0, 20) lx og står
dér hele aftenen. Lander det over en gate på ~17 lx, er rummet "lyst" til næste
morgen. Målt 24/9-4/10: 1 af 11 aftener ramt for soveværelset (de andre endte på
0-12,8 lx). Symptomet 4/10: sove-pre-lyset (5 %) blev aldrig opgraderet til START,
og pærelyskæden (kræver loftet ≥ `sove_lyskaede_min_loft_pct`) tændte aldrig.
Fix i begge sove-tænd-veje (`presence_sovevaerelse.yaml` + `presence_lights.yaml`
`presence_lux_sovevaerelse_on`, #2): efter kl. 12 og sol < −6° tæller en aflæsning
< gate + 20 som mørke. Andre rum med Apollo-lux-gates under ~20 lx har samme
blinde vinkel — vurdér dem med samme måling (sidste rapport efter solnedgang pr.
aften vs. gaten), før du kopierer reglen.

## Børne-Apolloen ser folk ved spisebordet gennem væggen (2026-10-05)

Siden 23/9 må frisk radar-BEVÆGELSE tænde børneværelsets loft når børnene ikke er
hjemme (user-bug 22/9: en voksen i rummet fik intet lys). Replay af 14 døgn
(recorderen; distance/energi er ekskluderet, så kun occupancy-flanker): vejen
tændte 26 gange uden børn hjemme. 24/26 startede inden for ±10 s af spisestuens
rå radar, 21/26 var radar-ophold på 13-42 s, og de klumpede sig om måltiderne
(07-09 og 18-20). Loftet brændte derefter 6-75 min. "Solo-tid" — børneværelset
optaget MENS spisestuens radar er stille — i de første 180 s: 0 s i 14 af 23. Den
ægte voksen-sag fra 22/9 19:17 havde 51 s solo, første efter 9 s. B163-målingen
24/9 ("user står/går i spisestuen ved væggen": move ≤ 11 mod tærskel 15) var et
POSERET negativ-sæt: måltidernes kontinuum (rejse sig, flytte stole) ligger over.
Et "spisestuen skal være stille"-krav (solo-bevis) blev bygget og afvist samme
dag: spisestuens 5-s radar-timeout gør det til ~10-15 s ventetid på lys, og user
kræver max 3 s. Inden for 3 s skiller INTET signal: 8 af de 14 nul-solo-
hændelser lignede "nogen kom lige forbi" (spisestuen tændt 1,5-17 s før) præcis
som en ægte indgang, og afstandene ved +2 s (apollo_udslag-loggen) overlapper
(120-222 cm). Fix på SLUK-siden: uden børn hjemme (familie-mode, ikke Manual)
slukker `presence_light_boernevaerelse_off` efter
`input_number.boernevaerelse_uden_boern_sluk_sekunder` (90 s) tomt rum i stedet
for 300 s × global-faktor ≈ 22 min — en tid sat til sovende børn. 90 s er valgt
over radarens huller midt i ophold (14 døgn: 69 af 298 under 60 s, 26 i 60-120 s).
Med børn hjemme var begge veje uændrede — og SAMME AFTEN viste det sig at være
dagens egentlige sag: Child B var hjemme, loftet brændte 5,3 t, 160 min i tomt rum
(fejlklasse #12: beskyttelsen kom kun på den ene søster-gren). → med børn hjemme
06 → børnenes sengetid slukker det efter
`input_number.boernevaerelse_med_boern_sluk_sekunder` (300 s); efter sengetid
gælder 22-min-reglen (sovende børn). Søster-vejen
`presence_light_boernevaerelse_adult_wakeup` har samme fysik, men fyrede 0 gange
på de 14 døgn.

**People count (2026-10-07, user: "4 i går, vi var kun 2"):** samme fysik
ramte børne-tællingen. 6/10 tændte `people_boern_set` flaget "børn set siden
dør" på to blips gennem væggen (18:08:20, 21:15:32; spisestuens rå radar on
i samme sekund) mens `kids_home_manual` stod tvangs-on fra 5/10 → people_gulv
låste 2 voksne + 2 børn = 4 fra 21:15 til 07:45. Natten efter: 0,0 t i
værelset. Det kl. 21:15 var et 13-s blip, men 900-s-natte-timeouten holdt
værelset optaget i 15 min — så både "flanke" og "holdt 60 s" fyrede, og
`boern_occupancy_4h` talte 15 min ≥ 3. Uden latens-krav skiller ALENE-TIDEN:
replay 23/9-7/10, børnefri dage: 86 af 90 ophold havde ≤ 20 s alene-tid ud over
5-s-timeouten, 331-455 s under 900-s-timeouten; de sidste 4 (67-158 s) var
voksne INDE i værelset. Ægte børne-ophold: 61/176 ≥ 60 s. →
`binary_sensor.boernevaerelse_solo_bevis` (delay_on = timeout +
`input_number.people_boern_solo_sekunder` 60) bærer både flaget, dør-
nulstillingerne og `sensor.people_boern` (via `sensor.boern_solo_bevis_4h`).
Pris: børne-aftenerne fanges 16:25-19:47 i stedet for 14:35-17:13 — alle før
20:00-facit.

## Køkken-kameraets "krop" er BEVÆGELSE, ikke tilstedeværelse (2026-10-05)

`binary_sensor.koekken_kamera_krop` (gesture-shimmens hot cells) svarer "bevæger
nogen sig kraftigt i billedet lige nu", ikke "står der nogen" (allerede målt 15/9:
on 19 % af tiden mens familien var i køkkenet). Barne-reglen "radaren ser en
passage, kameraet er tavst ⇒ for lav til billedet" hviler på at tavshed betyder
fravær af voksne — og det gør den ikke: user 5/10 "når vi står og laver mad kan
tapo ikke se os men det kan apollo køkken". Naturlig kontrol-gruppe samme morgen:
06:13-07:23 kun voksne hjemme → 24 "lave passager" (kameraet tavst 269-1733 s
ad gangen); fra 08:13 med Child B → 14 på 3,5 t. Raten var højest UDEN barn.
User-svar på "Børn hjemme?" med kilde lav_krop (19-21/9): 1 ja, 3 nej, 1
ubesvaret. User valgte at slå featuren helt fra (ikke en person-detektor):
`input_boolean.koekken_lav_krop_boern_enabled` (default fra) gater både tælleren
og børn-hjemme-vejen. En brugbar version ville kræve et TILSTEDEVÆRELSES-signal
fra kameraet (person-detektor), ikke en strammere tavsheds-tærskel.

## Højttaleren spiller videre på batteriet når pluggen slukker (2026-10-10)

**Pluggen var i skuffen 10-14/10 (B212 droppet); siden 14/10 er den Thread-router
i depotet 1 m fra donglen (B234)** — `PASSIVE_NODER` i `scripts/otbr_rcp_stats.py`
er derfor tom igen (15/10), så den meldes væk som alle andre routere.

Kort form: `.claude/rules/energi.md`. AxiomAir N3 (brugt, 5-10 år gammelt
batterimodul; spec 9 t/18 t afhængigt af modul — axiomaudio.com) sidder på
GRILLPLATS-plug 2 (`switch.hoejttaler_plug`, node 0x1F2 — siden 15/10 `switch.thread_router_depot`). Målt 10/10: plug slukket
i 90 s → `binary_sensor.hoejttaler_online` og Volumio forblev oppe, afspilningen
fortsatte. Ved gen-tænd: top 56 W, under 12 W efter ~45 s. Hvile med fuldt
batteri ≈ 10-11 W, spiller ved lav volumen ≈ 11-11,7 W. Konsekvens: pluggens
watt er ladeeffekt; "fuldt" = effekt < hvile + 1,5 W i 10 min
(`binary_sensor.hoejttaler_lader_ikke`). Går den offline, er det IKKE bevist
tomt: N3-manualen (axiomaudio.com/manuals/N3_R1.11.pdf) kender ingen auto-standby,
men LED'en skelner — fast rød = batteri skal lades, blå/rød blink = egen WiFi-
hotspot (slår selv til når hjemmenettet tabes), grøn uden netværk = hængt (hold
knappen). HA kan ikke vække den: 10/10 11:46 offline efter 1,79 t på batteri
(0 t spillet), plug-cyklus 12:00 → ingen ping i 90 s. Ladeeffekten 13 min efter
gen-tænd var stadig 39 W (mod < 12 W efter 45 s ved en 90-s-aflading), så
batteriet var reelt afladet. User så INGEN LED (= helt slukket, hverken hotspot
eller hængt); ét tryk → grøn, online 12:06:30. Genopladning ~13 Wh (plug-tæller
0,010 → 0,023 kWh, 1 Wh opløsning) på ~17 min — langt under de ~19 Wh 1,79 t
hvile ved 10,5 W skulle koste, så enten bruger den mindre på batteri end på
pluggen, eller også slukker den af en anden grund end en tom celle. Afgøres af
en test MED afspilning (en evt. inaktivitets-timer kan ikke fyre) — test 2
gav 1,51 t, så batteriet er reelt degenereret (se nedenfor).
**Pluggen fjernet 10/10 (B212 droppet):** højttaleren kører på konstant strøm.
Målt forbrug inden: fuldt batteri 10,45 W tids-vægtet (p50 10,4 / p75 10,7),
afspilning ~11-11,7 W, ~3 t afspilning/døgn ⇒ ~10,6 W døgn-snit ≈ 93 kWh/år ≈
180 kr/år ved 7-døgns-snittet 1,96 kr/kWh all-in. Tæller i setup-kosten via
`input_number.cost_hoejttaler_watt`; målepakken (`energy_hoejttaler.yaml`) er
slettet — hent den i git (7134427a) hvis pluggen kommer tilbage.
**Batteritilstanden kan IKKE aflæses (undersøgt via SSH 10/10):** Pi 3B med
Raspbian 9; ingen `/sys/class/power_supply`, I2C-1 har kun RTC'en pcf2127 (0x51,
"low voltage" i dmesg hvert ~11,6 min = RTC'ens knapcelle, ikke hovedbatteriet),
`axiom_ledsetup.sh` styrer kun den blå LED (GPIO 26) + et rødt netværks-blink
(MCP23017-pin 508 — den chip findes ikke på N3), og Volumio har hverken
sleep-timer eller alarmer aktive. Den røde "lad op"-LED kommer altså fra
batteriets eget ladekort. Eneste kandidater: Pi'ens undervolt-flag
(`vcgencmd get_throttled`, 0x0 med fuldt batteri) og input-GPIO 4 (pull-up)/17/
27/22/13/23 — logget under test 2 (`/media/axiomair_n3_backup/batteritest2_signaler.log`):
throttled forblev 0x0 til døden, men **GPIO 17 gik 0 → 1 ~3 min før batteriet
døde** (14:21 → 14:24:13; 0 i 48 forudgående samples) og var 0 igen efter genstart
under opladning — én aflading, ikke bekræftet. Ingen LED ved døden (heller ikke rød).
Test 2 MED musik døde efter 1,51 t (test 1 uden: 1,79 t) → ingen skjult
inaktivitets-sluk; batteriet holder reelt ~1,5-1,8 t.
SSH slås til på `http://192.0.2.42/dev/` (socket.io `callMethod`
system_controller/system enableSSH, `data:'false'` slår fra; overlever genstart),
login volumio/volumio — slået FRA igen 10/10. Smart-ladning droppet: user kører den
på konstant strøm (B212). Et GPIO 17 → webhook-varsel blev bygget og rullet tilbage
(9e8aa02c), hvis det nogensinde skal genopstå. Fuld SD-backup
(p1+p2 rå, p3-overlay, config) i `/media/axiomair_n3_backup/2026-10-10/` med README.

## `parallel:`-grene deler variabel-scope (2026-10-12)

B227's første ild-løkke kørte én `repeat` pr. spot i en `parallel:`, hver gren
startede med `variables: {spot: light.stue_spot_N}`. Live: spot 1 frøs efter
11 s. Scriptets trace viste 324 trin i hver gren — men ALLE `light.turn_on`
havde `entity_id: light.stue_spot_2`. Grenene deler scope (HA 2026.9.2), så
gren 2's `spot` (og `dt`/`t0`/`roll`) overskrev gren 1's. Fix: én løkke der
skifter spot pr. iteration (`repeat.index % 2`) med en halv pause.

## Trigger-template-sensorer på `unknown` gendanner ikke attributter (2026-10-12)

`homeassistant/components/template/entity.py` `async_restore_last_state`:
`last_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)` → return, FØR
attributterne restores. `sensor.genvex_effekt` renderede `none` indtil første
sample på det aktuelle trin (3 t efter hvert trin-skift) — en restart i det
vindue havde slettet ugers A/B-akkumulator (`acc`). Fix: state falder tilbage
til 0 (genvex_effekt, bad_torretid).

## Sofa-spots + stue-grupperne er udelukket fra recorderen (2026-10-12)

B227's ild fader spotsene konstant; Matter-pærerne melder mellemværdier hvert
~0,5 s under en transition. Målt under live-testen 12/10 (3,5 min,
`significant_changes_only=0`): spot 1 2.366/t, spot 2 9.909/t, `light.stue_room`
og `light.stue_all` 12.086/t HVER (gruppen skriver ved hver medlems-ændring).
User valgte "b": spots ikke i historikken. Grupperne kom med, fordi de ellers
gemte ilden dobbelt; ingen history_stats/statistics læser dem (lys-KPI'en tæller
på `binary_sensor.stue_lys_on_effektiv`). Konsekvens: `hq.py hist|who|flanks`
og logbogen er tomme for de fire. Fortrydes ved at fjerne linjerne i
`configuration.yaml` → `recorder: exclude: entity_globs`.

## Lejligheden har TO fugt-instrumenter — depotets Broadlink er reserve (2026-10-15)

(Også TO temperatur-instrumenter — se punktet **Temperatur** nederst.)

Køkkenets TIMMERFLOTTE (Matter node 434, sleepy) var IKKE "eneste fugt-kilde":
Broadlink RM4 Pro i depotet har temp+RH fra samme instrument. User 15/10:
"hvis den har fugt måler så skal den med overalt vi måler fugt". TIMMERFLOTTE
var væk ~40 af 75 t 13-15/10 (Thread-øen, B234), og alt der læste den stod
stille (genvex-forsøget, badets tørretid, fugt-varslet).
- **Absolut fugt:** depot = køkken + 0,52 g/m³ (1153 kvarterer 1-15/10, sd 0,27,
  døgnmidler 0,38-0,66). **Depotet får bad-dampen** (+0,5-3,4 g/m³ i 10-20 min
  efter hvert bad) → reserven er `sensor.depot_absolut_fugt_30_min` − 0,52.
  Som stue-reference for badets tørretid på 23 bade: median-forskel 0 min mod
  TIMMERFLOTTE (rå depot −5 min, 60-min-minimum +21 min).
- **%RH:** depotet står ~26 °C, så dets RH er lav → `indoor_humidity_resilient`
  regner RH ud af den absolutte fugt ved køkkenets temperatur fra
  `indoor_temperature_resilient`. Fejl ±1-1,5 %RH.
- **Depot-temperaturen er NUC-opvarmet** (Broadlink'en sidder højt oppe lige
  ved NUC'en, user 15/10) → ALDRIG med i et temperatur-middel eller som
  rumtemperatur; kun som reserve for køkkenet. Absolut fugt er upåvirket
  (temp+RH i samme probe) → depotet ER med i fugt-middelet
  (`packages/lejlighed_klima.yaml`).
- **Temperatur:** depot = køkken + 3,14 °C (1532 kvarterer 27/9-15/10, sd 0,26,
  p5-p95 2,80-3,66, max-fejl 0,93; 3,18 efter fyringen 12/10; døgnprofil 3,03
  om natten → 3,44 kl. 7). Depotet manglede 0 kvarterer, køkkenet 215. →
  `sensor.indoor_temperature_resilient` = TIMMERFLOTTE, ellers Broadlink − 3,15;
  summer_defense, climate_control, security kulde-dør og radiator-effekt køkken
  læser den. Apollo-temperaturen er stadig udelukket — IKKE pga. støj eller
  ESP-varme (målt 22/10: σ 0,06 °C, gain 1,0 mod køkkenet, sove-offset
  uafhængigt af ESP-temp), men pga. placering (køleskab, radiatorskjuler/træk),
  ukendt nulpunkt og døde DPS310 i børne + spisestue. Mod køkkenet kan den ikke
  kalibreres: sove − køkken driver −2,5 (jun) → −4,6 °C (okt) med årstiden (B247).
- Alle tre sensorer har attributten `kilde` (køkken/depot).

