# Standing instructions — den lange version

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Auto-loades IKKE.** CLAUDE.md bærer selve reglerne (de SKAL være i context for
at blive fulgt); denne fil bærer begrundelserne, incident-forløbene og de
konkrete opskrifter der kun bruges når man faktisk står i situationen.

**Læs den når:** du skal bruge en recovery-procedure, et kode-eksempel eller
grunden bag en regel — `grep -n "<nøgleord>" docs/standing_instructions.md`.

Ændrer en user-spec sig, skal BEGGE lag rettes: reglen i CLAUDE.md og afsnittet
her.

---

## Standing instructions

### 🔄 Tjek status FØR du koder (per 2026-07-29, user-spec)

**Første handling i enhver kode-opgave** — før du læser filer:

```bash
git fetch origin && git status && git rev-list --left-right --count origin/main...HEAD
```

Bagud → `git merge --ff-only origin/main` FØR du rører noget, og genlæs derefter
CLAUDE.md + relevante pakker fra det friske træ. **Hvorfor:** checkouten er
rutinemæssigt 30-200 commits bagud; arbejde mod en stale base skal laves om, og
deployes det, ruller det stille nyere features tilbage. Værst er at CLAUDE.md
selv er stale i context, så konventioner overses.

Er skaden sket: `git diff > backup.patch` → `git checkout -- <filer>` → ff →
genanvend i hånden. Utrackede NYE filer overlever en fast-forward.

(Dette er noget andet end Multi-Claude-sync nedenfor, som handler om NUC'ens
commits ved deploy.)

### 💰 Token-økonomi — en simpel ændring skal koste som en simpel ændring (per 2026-08-08, user-spec)

Filosofien er uændret (**langsomt + grundigt frem for hurtigt**) — pengene skal
bruges på **diagnose og verifikation**, ikke på at læse ting du ikke skal bruge.

**Klassificér opgaven FØRST:**

| | **SIMPEL ændring** | **UNDERSØGELSE / ny feature** |
|---|---|---|
| Kendetegn | User peger på en konkret ting: en slider, en tærskel, en tekst | "hvorfor gjorde huset X?", "byg Y", kalibrering, bug-hunt |
| Budget | **< 10 tool-calls, ingen fuld fil-Read** | Så meget diagnose som der skal til |
| Metode | grep på det user nævnte → `Read(f, offset=hit-25, limit=60)` → Edit → billigst mulige deploy → én samlet push | 🔍-reglen: historik + real-world data |

I tvivl: start som SIMPEL og eskalér. Det omvendte — fuld udgravning til en
tekstrettelse — er det dyre.

**Filer der ALDRIG Read'es helt** (`wc -l` før du Read'er noget ukendt):
`dashboards/settings.yaml` (8100), `automations/init_user_preferences.yaml`
(1350; var 6230 før P1), `scripts/mad_planner.py` (2054), `BACKLOG.md`, `docs/sprint_log.md`.
**API-svar filtreres ved kilden** — `curl /api/states` er ~1 MB; pipe altid
gennem `python3 -c` der trækker de 2-3 felter du skal bruge.

**Anti-mønstre — stop hvis du er ved at gøre et af disse:**

- Læse en fil "for at få kontekst" uden en konkret søgestreng i hovedet.
- Re-Read'e en fil du selv lige har rettet (Edit/Write tracker filens tilstand).
- Køre 4 grep-varianter fordi den første var upræcis — brug én god regex og `-l`.
- Spawne en subagent til noget ét grep kan svare på.
- Dumpe rå output (`git log -p`, fulde restart-logs, `ls -R`, `/api/states`)
  når `--oneline -5`, `| tail -20` eller en `GROUP BY count(*)` gør det.
- TaskCreate på en 2-trins opgave, eller et langt afsnit i chatten om hvad du
  er ved at gøre. Kort update, så handling.
- Gentage user's problem tilbage til ham før du går i gang.

**Vedligeholdelses-budget (håndhæv aktivt):** CLAUDE.md **≤ ~500 linjer**.
Ny sprint-note = 3-5 linjer i sprint-indexet + fuld note i arkivet, samme
commit. Nyt permanent faktum = ÉN bullet i "Permanente fakta". En ny regel med
en lang begrundelse: reglen her, begrundelsen i docs/. Er du over budget efter
dit sprint, arkivér — det er ikke valgfrit.

**Spar ALDRIG på:** logs/history-graving ved en bug, kalibrering mod ægte data,
verifikation efter deploy, eller de grep-sweeps fejlklasse #1/#2/#16 kræver.

### 🚀 Fix + commit + push FØRST — spørg opklarende BAGEFTER (per 2026-07-27, user-spec)

Når user beder om et fix: **lav ændringen, commit og push FØRST**, og stil
derefter evt. opklarende spørgsmål. Spørg IKKE først og vent, **med mindre user
eksplicit skriver at han er til stede og kan svare nu**. Begrundelse: blokerer
du på et spørgsmål user ikke ser (asynkron/telefon), går arbejdet tabt — en
shippet best-effort kan itereres, et ubesvaret spørgsmål giver nul værdi.

Konkret: (1) vælg den mest sandsynlige, laveste-risiko fortolkning ud fra logs;
(2) implementér + commit + push + deploy + notificér; (3) SÅ spørg, tydeligt
markeret ("shippet X med default Y — bekræft/justér:"). Dette **modificerer**
🤔-reglen: stop-og-spørg gælder kun når user kan svare, eller når ændringen er
ægte irreversibel/destruktiv.

### 📏 MÅL altid selv — stil ALDRIG en værdi efter en sprint-note (per 2026-08-29, user-spec)

<!-- flyttet fra CLAUDE.md 2026-09-12 under linje-budget-oprydningen -->

**"ALTID måle det, ALDRIG stil blindt på sprint noter — for så kan vi nedarve
fejl og de kan vokse."** Sprint-noter og kode-kommentarer er *hypoteser med
tidsstempel*, ikke måledata. Skal du sætte, hæve eller sænke en tærskel, en
timing eller en offset: **træk fordelingen af den kanal gaten faktisk læser**
(percentiler + "hvor mange samples ligger over/under?") over 2-3 døgn, FØR du
skriver tallet. Er dine tal uenige med noten, er det noten der er forældet — ret
den i samme commit.

**Hvorfor:** en not-baseret justering arver præmissen i den forrige. Målt
29/8: `koekken_spots_lux_threshold` blev hævet 45 → **250** ud fra en note om
"539/837 samples > 45 lx" fra ét døgn. Den faktiske 3-døgns fordeling på
`koekken_dagslys_lx` var p50 = 29 lx, p90 = 139, og **kun 5,3 % over 250** —
gaten stod altså åben 95 % af tiden, og spots' on-tid gik fra 53-104 min/døgn
til 253-560. Fejlen var usynlig fordi hvert lag kun læste laget før sig.

**Signatur:** en tærskel der er en ensom outlier blandt sine søskende på SAMME
måleskala (her: husets øvrige køkken-lux-grænser lå alle på 45-65).

Fuld incident: `grep -n "2026-08-29b" docs/sprint_log.md`.

### 🔍 Løs opgaver ud fra faktisk adfærd + real-world data (per 2026-07-23, user-spec)

Opgaver løses ved at undersøge **faktisk adfærd de seneste 2-3 døgn** — ikke ud
fra antagelser om hvordan setuppet "burde" opføre sig.

1. **Træk historikken** for de involverede entities (logbook, recorder-DB,
   `/api/history`, ai_feedback-JSONL'erne, `./scripts/ha_health.sh noisy`).
2. **Lad de rigtige tal drive parametre** — kalibrér tærskler/timings mod
   observeret data, ikke mod gæt.
3. **Verificér mod virkeligheden til sidst** (#6/#14): "live-testet" betyder
   ægte device-events + bevis i history, ikke syntetiske events.

Brugeren fodrer løbende systemet med facit (ai_feedback-trænere, korrektioner) —
brug det som ground truth. Undtagelser: triviel syntaks/docs, eller når
brugeren eksplicit dikterer adfærden.

### 🤔 I tvivl om ØNSKET ADFÆRD → spørg. I tvivl om teknik → slå op

**Behavior-spørgsmål (SPØRG, med konkrete a/b/c-options i prosa):** "hvad skal
ske hvis X timeouter?", "skal Y fyre i Dormant også?", "hvor lyst = subjektivt".
**Tech-spørgsmål (bare gør det):** syntaks, entity_id, versioner — slå op/test.
I tvivl om hvilken slags: spørg alligevel. Se dog 🚀-reglen: kan user ikke
svare lige nu, så ship den mest sandsynlige fortolkning og spørg bagefter.

### 📲 Notificér brugeren ved ændringer (per 2026-06-27, user-spec)

Efter **deployede ændringer**: send én kort, punktvis push pr. arbejds-batch
(ikke pr. fil) der siger hvad der er live nu + evt. manuelt skridt der mangler.
Skip kun ved ren research uden deploy.

```bash
curl -s -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"✅ Deployed","message":"• Bad: godnat=5% natlys\n• Ny børne-slider"}' \
  "http://supervisor/core/api/services/notify/mobile_app_phone_a"
```

**⚠️ UNDTAGELSE — AirBnB-mode = SILENT (per 2026-07-13, user-spec):** er
`input_select.house_mode` == `AirBnB`, send INGEN push (heller ikke
deploy-opsummeringen) — telefonen kan være i gæstens hænder. **Tjek mode FØR du
pusher.** Kode/dashboards/reloads er fine; det er kun notifikationerne der
undertrykkes. Nævn i din tekst-opsummering at pushen blev sprunget over.

**↪ Én bevidst UNDER-undtagelse: `packages/kamera_airbnb_vagt.yaml` SKAL pushe i
AirBnB** (user-spec 2026-09-11). Kamera-vagten varsler om at køkken-kameraet
(gestus-stakken) stadig står fremme når AirBnB slås til — et lovkrav, ikke en
præference.

**Hvorfor netop den ene bryder SILENT-reglen:** SILENT findes fordi telefonen
kan være i gæstens hænder. Vagtens `kamera_airbnb_vagt_ved_entry` fyrer på
flanken `input_select.house_mode → AirBnB` — altså i **det sekund user selv
flipper mode**, mens han står med telefonen og forbereder lejligheden. Gæsten er
pr. konstruktion ikke ankommet endnu. Præmissen bag SILENT er dermed ikke
opfyldt for præcis denne trigger.

**Og alternativet findes ikke:** kravet er "hevet ud af stikket OG pakket væk".
Et netværks-tjek kan kun bevise det første — et strømløst kamera på køkkenbordet
er usynligt for enhver ping, og det er netop den tilstand der skal fanges.
Ankeret er derfor et menneskeligt "ja" (`input_text.kamera_airbnb_status`,
`pakket_vaek`-prefix), og uden pushen er der ingen kanal til at bede om det.

**Rør ikke featuren for at "rette" den:** filens egen header siger det direkte —
sætter du en `house_mode`-gate på dens automations, slår du hele featuren fra.
Backstop-automationen gentager varslet (op til 15 min forsinket), entry-flanken
findes for at reaktionen er øjeblikkelig. NB triggeren har eksplicit
`not_from: [unknown, unavailable]`, så et `template.reload` ikke fyrer varslet.

**↪ Anden UNDER-undtagelse: `packages/airbnb_udtjekning.yaml` (user-spec
2026-10-28):** "når airbnb starter skal der laves en udtjekningsdato, default 6
dage senere, giv mig push om at rette det". Samme præmis som kamera-vagten:
pushen fyrer KUN på flanken ind i AirBnB (ingen backstop, ingen gentagelse), så
den rammer user mens han selv står med telefonen. Datoen er B256's grænse for
hvor længe gæster antages at bo i huset.

**↪ Tredje UNDER-undtagelse: velkomstbesked-påmindelsen i
`packages/airbnb_velkomst.yaml` (user-spec 2026-10-29):** "når jeg slår airbnb
til skal jeg påmindes om at skrive en tekst eller slette en gammel tekst".
Samme præmis: kun på flanken ind i AirBnB, én push med "Slet beskeden"-knap;
knappens bekræftelse er svar på hans eget tryk.

### 🧪 Test fysisk + mål når nyt går live (per 2026-05-03)

Har ændringen **observerbar fysisk effekt** (lys, gardiner, lyd, timing):

1. Deploy + verificér at HA reelt er klar (state opdateret, ikke kun "Command completed").
2. **Mål faktisk adfærd** før du erklærer succes — tidsstempl events via REST,
   læs `state_attr('light.X','hs_color')` post-action, tjek brightness (0-254 raw).
3. Matcher observation ikke design-intent: itererér med målinger. **Stop ikke
   ved første "ser ud til at virke".**
4. **HA's reelle throughput: ~5-10 light-kald/sek max.** Loop-designs der
   antager >10/sek fejler silently (kører, bare langsommere). Målt 2026-05-03:
   et "40 ticks/sek"-design leverede 7,5.

### ✋ Live-test og genstart kræver ja via push FØRST (per 2026-10-28, user-spec)

User 2026-10-28: *"hvis der skal testes live med lys eller noget jeg kan høre
eller der genstartes så skal jeg spørges med action knapper før. du må gøre det
så jeg kan godkende eller afvise eller sige om 20min"*. Skærper "ingen live
tests uden lov" (25/10 + 26/10: ét bestilt løb = ét; gen-test efter et fix
kræver et nyt ja).

**Hvad kræver et ja:** ethvert kald huset kan se eller høre — `light`, `switch`,
`scene`, `script`, `media_player`, `tts`, `cover`, `siren`, `remote`, `button`,
`fan`, `vacuum`, `automation.trigger`, `homeassistant.turn_on/off/toggle` — og
enhver genstart (`ha_restart.sh`, `ha core restart/stop/rebuild/update`, host
reboot, add-on restart/stop/update). **Kræver intet:** reloads, notifikationer,
helper-skrivninger (`input_*`), læsninger og passivt bevis i history.

**Sådan:**

1. `python3 scripts/live_godkend.py spørg "<hvad der skal ske, kort dansk>"
   [--genstart] [--minutter N] [--frist M]` med `run_in_background` — ventetiden
   kan være lang.
2. Pushen (tag `claude_godkend`) har knapperne **Godkend / Afvis / Om 20 min**.
   Scriptet abonnerer på `mobile_app_notification_action` FØR pushen sendes;
   knappernes action-id bærer et tilfældigt runde-id, så et tryk på en gammel
   push aldrig tæller.
3. Exit-koder: **0** godkendt (`.cache/live_godkendelse.json` skrives, gyldig 15
   min / 10 min ved genstart, fra trykket) · **1** afvist · **2** intet svar
   inden fristen (default 30 min) eller udsat 6 gange = nej · **3** AirBnB ·
   **4** fejl. **Om 20 min** = spørg igen om 20 min (samme knapper).
4. Efter testen: `live_godkend.py slut` — et ja gælder den test der blev spurgt
   om, ikke det næste kvarters eksperimenter.
5. Svar logges i `.cache/live_godkendelse.log` og i HA's logbog
   ("Claude-godkendelse").

**AirBnB:** ingen push (telefonen kan være hos gæsten) → exit 3; spørg i
chatten, og registrér brugerens ja med `live_godkend.py chat "<brugerens ord>"
[--genstart]` (afvises uden for AirBnB).

**Håndhævelse:** `scripts/live_guard.py` (PreToolUse på Bash, ADR 0006) afviser
kommandoen med exit 2 uden et gyldigt ja af rette slags. Kommandoer der kun
NÆVNER et mønster (grep, git, en heredoc til cat/git) passerer; afgøres pr.
simpel kommando, så `grep … && <kald>` stadig fanges. En heredoc til python
regnes som kode — skal du blot skrive TEKST der nævner `ha_restart.sh`, så brug
Edit/Write. En genstart slippes igennem når HA ikke svarer (ingen at spørge,
intet at forstyrre). Kun user må slå vagten fra (`.claude/live_guard_off`,
git-ignoreret). Omgå den aldrig.

### 🎛️ Tjek eksisterende slidere FØR du bygger nyt (per 2026-05-17)

Skal en parameter justeres (timing, brightness, tærskel, varighed), så grep
FØRST i `packages/global_tuning.yaml`, `packages/constants.yaml` og
dashboards' Global Tuning-sektion. **Findes der allerede en slider → sig det
til brugeren før du ændrer noget:** "det kan du tune via slider X (værdi N
betyder Y) — vil du justere den, eller skal jeg ændre baseline?"

Er det nyt territorium: byg slider + factor-sensor + dashboard-tile +
snapshot-export i ÉN commit. Hardcodede magic numbers skal helst være tunable.
(Siden P1 2026-10-04 er snapshottet fresh-install-defaulten: init gendanner
input_numbers fra den AFLEDTE `config_snapshots/fresh_install/input_number.yaml`
— ingen ny init-blok.)
(Aktuel slider-liste: `grep -n "input_number" packages/global_tuning.yaml`.)

**Scope skal beskrives (per 2026-07-02, user-spec):** rammer en slider ikke
alle pærer — eller ikke alle i det rum den nævner — SKAL undtagelsen stå under
tilen som ÉN kort linje ("Gælder ikke: køkken-lyskæde, bad, soveværelset").
Siden 2026-09-29 er det den ENESTE forklarende tekst en slider må have (se
tekst-reglen under 📊). Ændrer du en sliders scope, opdatér ALLE berørte
beskrivelser i samme commit (grep `dashboards/settings.yaml` for rummet/
lampen). Scope-påstande verificeres i koden, ikke gættes (#1/#3).

**Værdier snapshottes til git (per 2026-06-17):** sliders lever i `.storage`,
ikke i git → ved tab gendanner init dem fra snapshottet (P1 2026-10-04;
før faldt de til håndskrevne init-defaults). `python3
scripts/helpers_export.py` → commit **`config_snapshots/`** (begge filer: exporten
skriver også den afledte fresh-install-fil; pre-commit afviser et par der ikke
passer i det STAGEDE. Håndrettet snapshot → `helpers_export.py --derive`).
`helpers_restore.py [--apply]` gendanner. Ændrer du en default bevidst: kør
export + commit, så git matcher virkeligheden.

**⚠️ Export'en kører på en ALLOWLIST — en ny konfig-helper snapshottes TAVST
ikke.** `scripts/helpers_export.py` skelner KONFIG fra runtime-state (learning,
cursors, timestamps, `room_mode`, `visit_stage`, `house_mode`), så filen er
stabil i git og kun ændrer sig når en faktisk indstilling ændres. Prisen er at
inklusion er **eksplicit**, og reglen er forskellig pr. domæne:

| Domæne | Hvordan en helper kommer med |
|---|---|
| `input_number` | alle, MINUS en denylist (`adaptive_*`, `*_idx`/`*cursor*`, `scene_spread_level`, `airbnb_gaeste_antal`, `people_gulv`/`people_ekstra_gulv`, `user_prefs_version` + `RUNTIME_NUMBERS`: robot-akkumulator, sengetæller, nattens alarm-udskydelse, fødselsdags-epoch, de tre antagne gardin-positioner). **Siden P1 er denne liste også fresh-install-reglen** — det der står her, gendannes IKKE af init |
| `input_boolean` | **mønster**: `*_enabled` eller `notif_*`, + navngivne prefixer (`roborock_styrbar_*`, `nemlig_foretraek_*`, `voice_cmd_*`) |
| `input_datetime` | **navngivet i `DATETIME_CONFIG`** (linje ~31) eller `notif_*` |
| `input_select` | **navngivet i `SELECT_CONFIG`** (linje ~66) — default er IKKE med |
| `input_text` | **navngivet i `TEXT_CONFIG`** |

Bygger du en ny konfig-`input_datetime` eller `input_select`, skal navnet
(uden domæne-prefix) tilføjes i det tilsvarende sæt inde i scriptet — ellers
fejler intet, exporten kører grønt, og helperen er bare **fraværende** i
snapshottet indtil et `.storage`-tab afslører det.

**Signatur:** en helper user beviseligt har tunet står ikke i
`config_snapshots/helper_values.yaml` — verificér med et grep på navnet efter
din export, ikke på at scriptet returnerede 0.

**Fælden er kendt og har ramt to gange, begge fordi NAVNET blev læst som
garanti:** `nemlig_foretraek_oeko`/`_tilbud` (fanget 2026-08-31) kunne ikke
gendannes efter et `.storage`-tab, fordi boolean-allowlisten kun så på suffikset
`_enabled` — de hed noget andet. Samme fælde ramte `voice_cmd_*`-afbryderne fra
`tapo_tuning.yaml`. Begge er nu eksplicitte prefix-undtagelser i scriptet med en
kommentar der siger hvorfor. **Et navn er ikke en garanti for at være med i
backuppen.**

Omvendt er nogle udeladelser BEVIDSTE og skal blive der:
`mad_indkoeb_sprunget_dato` (kvittering for ét svar, ikke en indstilling) og
`input_number.user_prefs_version` — init-gate-markøren MÅ ikke restores, for et
`.storage`-tab skal give 0 → fresh init kan køre (B39). Og `TEXT_CONFIG` er
bevidst smal: kun de fem `*_gate_floors`, fordi gate-gulvene er husets dyrest
opnåede kalibrering (hvert ciffer er et målt flap-forløb) og eneste spærre mod
at gate-decay walker en tærskel tilbage under det niveau der beviseligt stoppede
et spøgelse. Fjerner eller tilføjer du noget i allowlisten, skriv grunden ved
siden af — scriptet er selv-dokumenterende af netop den grund.

### 🚀 Deploy + Multi-Claude sync — aldrig blind `reset --hard`

Claude har fuld adgang (SSH + REST) og udfører **selv** deploy, restart,
state-queries og service-calls fra både PC og telefon. Brugeren bruger kun HA's
UI til det fysiske: parre devices, addons, OAuth.

Arbejder brugeren også fra telefonen, kan `/config` have lokale commits.
`git reset --hard origin/main` wipede phone-Claudes arbejde 2026-05-18. Sikker
sekvens: commit lokalt → fetch → inspicér `git log --oneline @{u}.. -5` →
`pull --ff-only` (fejler ved divergens = tving manuel review) → `ha core
restart` (skip restart ved docs-only). Fuld procedure:
[docs/commit_workflow.md](commit_workflow.md).

**Commit ALTID selv — spørg ALDRIG "skal jeg committe?"** (per 2026-06-16,
user-spec). Skip `ha core check` — helperen er buggy i HAOS 2026.4.0; restart
validerer selv.

**Efter hver deploy: `./scripts/ha_health.sh deploy`** — fanger automations der
er valideringsfejlet og dermed fuldstændig stumme (#22).

#### ⚠️ `git stash && git pull && git stash pop` er en FÆLDE på /config

Idiomet er sikkert på en normal checkout og farligt her, fordi **`/config` bærer
en FÆLLES stash-stak på tværs af sessioner** (PC-Claude, telefon-Claude,
SSH-add-on-sessionen — samme filtræ, samme `.git`).

**Mekanikken, verificeret 2026-09-17 på et rent træ:**

```
$ git stash
No local changes to save
$ echo $?
0
```

`git stash` på et rent træ **opretter ingen entry og returnerer 0**. Et
`&&`-kædet idiom kan derfor ikke se forskel på "jeg gemte mit arbejde" og "der
var intet at gemme" — og `git stash pop` popper så `stash@{0}`, som er en
**FREMMED** stash fra en tidligere session.

**Det er ikke hypotetisk:** samme dag lå der en ubeslægtet
`stash@{0}: WIP on main: 8637586 Nemlig fase 2 live…` fra **2026-08-31
17:09:54** — 6 filer, +34/−2: appends til fem `ai_feedback/*.jsonl` plus en
ændring af `config_snapshots/helper_values.yaml`. Et blindt `pop` ville altså
have (a) injiceret 2½ uge gamle trænings-rækker i ai_feedback-korpusset — det
korpus 🔍-reglen bruger som **ground truth** — og (b) rullet snapshottede
slider-værdier tilbage. Begge dele ville have set ud som *dine* ændringer i
`git status`, og ville være blevet committet uden at nogen opdagede det.

**Signatur:** `git status` viser filer du ikke har rørt, i domæner din opgave
ikke handler om (typisk `ai_feedback/*`, `config_snapshots/*`), umiddelbart
efter en pull.

**Modgiften — vælg én:**

1. **Tjek stakken FØR:** `git stash list` — er den ikke tom, så rør den ikke.
2. **Navngiv din egen:** `git stash push -m "claude-<opgave>"`, og pop KUN hvis
   din egen entry faktisk blev oprettet:
   ```bash
   git stash push -m "claude-fix-b147"
   git stash list | head -1 | grep -q "claude-fix-b147" && git pull --ff-only && git stash pop
   ```
3. **Bedst:** undgå stash helt. Commit lokalt først (🚀/Multi-Claude-sekvensen
   ovenfor gør netop det) — en commit kan rebases og inspiceres, en stash er
   anonym tilstand uden ejer.

Ryd ALDRIG stakken (`git stash drop`/`clear`) for at "gøre den sikker": entryen
kan være en anden sessions eneste kopi af noget.

### 👁️ Monitoring — `./scripts/ha_health.sh`

Ét script dækker det ugentlige helbreds-tjek; det printer tællinger og
afvigelser, ikke dumps. Uden argument køres alle. **Den fulde liste (ground
truth: `case`-blokken i `scripts/ha_health.sh`, ~linje 245):**

| Subkommando | Hvad den svarer på |
|---|---|
| `deploy` | Valideringsfejlede automations (#22) + template-fejl i loggen. **Kør efter HVER deploy.** Kører også `blind`. |
| `blind` | **Blinde presence-kanaler — LÆS FØR du forklarer presence-adfærd.** |
| `kamera` | AirBnB-kamera-compliance: står køkken-kameraet stadig fremme? |
| `flags` | Stuck tilstands-flag |
| `lights` | Lys tændt af automations |
| `noisy` | Mest skiftende entities (recorder-volumen, #24) |
| `zha` | Utilgængelige devices |
| `docs` | Er `docs/auto/` (rooms + dependency_map) stale? |
| `backup` · `sys` | Seneste backups · RAM/disk/uptime |
| `log [n]` | Rå core-log, default 200 linjer |

**`blind` er obligatorisk før enhver forklaring af presence-adfærd.** Begrundelsen
står i scriptets egen kommentar: `unavailable` læses som `off` overalt
(fejlklasse #9), så et dødt instrument svarer **"her er tomt" med fuld
selvsikkerhed**. Årsagen er næsten altid at en vægkontakt er slukket — normal
brug, ikke en fejl, og derfor **varsles der bevidst ikke** om det (09-09f). Den
er lagt ind i `deploy` og i `all` netop for at en session ser den uden at vide at
den skulle spørge. Output: `sensor.presence_signal_confidence` (%) +
`binary_sensor.presence_kanaler_blinde` med `blinde`-listen og en
`forklaret`-attribut. Måling 2026-09-17: konfidens 100 %, 0 blinde kanaler.

En ukendt subkommando printer scriptets eget hoved (`sed -n '2,18p'`) og
exit'er 1 — brug den som opslag hvis tabellen her drifter.

**Git-hooks er installeret** (`.git/hooks/pre-commit` + `pre-push`, kopier af
`scripts/*-hook.sh`): pre-commit kører `ha_validate.py` på staged YAML
(dups/hazards/jinja) og ruff + yamllint på stagede filer, pre-push tjekker
entity-refs mod live HA. De koster nul tokens og fanger #22-klassen før den
bliver stum i prod. Bliver de nogensinde væk (`ls .git/hooks/pre-*`), eller
advarer pre-commit "ruff mangler" (fx efter en opdatering af SSH-add-on'et,
der tager venv'ets python med sig), kør `bash scripts/dev_setup.sh`: den
installerer hooks og bygger de pinnede værktøjer (requirements-dev.txt +
checksum-tjekket gitleaks) i `.cache/dev-venv`. `.cache/` er gitignored og
udeladt af HA's backups (Supervisorens `HOMEASSISTANT_BACKUP_EXCLUDE`), så
venv'ets ~215 MB koster ingen backup-plads. Hooks, Makefile og CI holdes i
trit af `scripts/tests/test_tooling_parity.py` — et nyt tjek i en hook skal
også i en Makefile-target (eller i `NOT_IN_CI` med et hvorfor).

**`docs/auto/*` er GENERERET og bliver stale i tavshed** — 2026-08-15 stod
kataloget 13 dage bagud og manglede 166 entity-referencer, dvs. det svarede
"findes ikke" om entities der findes. Rør ikke filerne i hånden; kør
`python3 scripts/gen_docs.py` og commit resultatet når du har tilføjet
entities.

### 🔥 ESPHome chip-wear — vær paranoid med writes til Apollo MSR-2 (per 2026-05-19)

**2 af 5 Apollos fik bekræftede sensor-chip-failures** inden for 2 uger; den
mistænkte årsag var en automation der skrev ~3600 unødvendige config-writes til
radaren. Fuld incident + kode-eksempel:
[docs/apollo_calibration.md](apollo_calibration.md).

1. **ESPHome NVRAM er persistent** — devices husker config over reboots og
   WiFi-drop. Re-skriv ALDRIG samme værdi ved "device online" eller HA-start.
2. **Triggere kun ved bruger-intent** (slider, knap, scene) — aldrig ved
   device-availability eller HA-lifecycle-events.
3. **Value-comparison ALTID** før `number.set_value`: spring over hvis
   `states(entity) | float(-1) | round(0) | int == target`.
4. **Engineering mode + Bluetooth = ALDRIG ON i drift** (streamer 18
   gate-energies kontinuerligt = konstant varme). Kun under bevidst kalibrering.
5. Nyt ESPHome-config-push: spørg "kan dette fyre periodisk?" (= bad) og
   "kunne brugeren leve med ét manuelt kald?" (= ofte ja) → lav
   `script.X_apply_now` i stedet for auto-triggers.

**Canary:** `sensor.*_apollo_esp_temperature` over ~50 °C steady-state = noget
hamrer for hårdt. Efter ny parring/factory-reset: `script.apollo_radar_apply_now`.

### 🏡 ALT vi bygger skal spille med AirBnB-mode (per 2026-07-28, user-spec)

Gælder **hver eneste ændring**, ikke kun dem der "handler om AirBnB":

1. **`house_mode` har TRE options** — `Normal`, `AirBnB`, `Home Vacation`. En
   `state: "Normal"`-condition udelukker derfor også Home Vacation (familie
   hjemme, bare uden hverdags-rutiner) = næsten altid utilsigtet. Familie-logik
   = `in ['Normal','Home Vacation']`; kun-gæst = `AirBnB`.
2. **Suppressorer/enforcere er farligst.** Holder din feature lys slukket eller
   blokerer en handling uden mode-gate, rammer den også gæsten — som ikke
   kender husets escape-veje. Spørg altid: *hvordan slipper en gæst ud af denne
   tilstand uden at kende systemet?* Der SKAL være en automatisk udgang.
3. **Nye flags:** skal de ryddes ved AirBnB-**entry** (gæst arver ikke
   familiens tilstand) og **exit** (familien arver ikke gæstens)? Se
   flag-clear- og lockdown-listerne i `automations/airbnb_mode.yaml` (+
   mirrors i `automations/light_power_recovery.yaml`). Afslører flaget
   familie-mønstre → med i privacy-purge-globs (#16).
4. **AirBnB har sit eget nat-regime** (`packages/airbnb_natmode.yaml`) der
   sætter godnat-flagene DIREKTE, ikke via `script.godnat` → det rydder IKKE
   cinema/scene-flag. Antag aldrig at Normal-modes oprydnings-kæde kører.
5. **Påtving aldrig familie-rutiner på en gæst** (godnat, vækning, putning) —
   vælg den neutrale handling: SLIP en blokering frem for at tvinge en tilstand.

### 📊 Hold de kuraterede dashboards opdateret

De er hånd-kuraterede og **drifter derfor når koden ændres**. Opdatér i SAMME
sprint som ændringen:

- **Tekst på dashboards (per 2026-09-29, user-spec):** *"Gør ting nemme og
  intuitive at forstå. Sørg for mindre tekst — kun hvad jeg har brug for at
  vide, ikke synlige noter til dig selv."* Indstillinger havde da ~270.000
  tegn markdown (Tapo 17.000), næsten alt skrevet af tidligere sessioner som
  begrundelser, måledata og incident-historik. Reglen:
  - Synligt er KUN: korte danske tile-navne uden emoji (tilen har ikon),
    skrevet så værdien fuldender sætningen ("Sluk efter" → "90 s"); ÉN linje
    scope-undtagelse eller brugs-instruks; live-status-skabeloner.
  - Noter til udviklere (hvorfor defaulten er som den er, målinger, datoer,
    B-numre, entity-/filnavne) → YAML-kommentar over kortet, eller i koden.
  - Live-værdier man bruger mens man justerer → badge i sektionens heading,
    ikke ekstra "→ faktor"/"lige nu"-tiles.
  - Indstillinger har ÉN sektion pr. emne (sektioner flyder i kolonner på
    desktop; én kæmpe-sektion med mellemoverskrifter gør ikke). Ny slider →
    den sektion der passer; 🔍 Søg-fanen (`www/indstillinger-soeg.js`) læser
    dashboardenes config live og finder den uden videre. Ændrer du selve
    kortet: `python3 scripts/lovelace_resources.py` (cache-busting-hash).
  - **Indstillinger er ÉT dashboard med faner (user-spec 2026-09-30: "alle
    indstillinger ind under den side som faner … så kan jeg søge i alt på en
    gang"):** Støvsug, Mad, AirBnB, Tapo og Vandventil er faner der, ikke egne
    sider. Egne sider forbliver KUN Lys, Scener, Festlys og info-siderne
    (Status, Statistik, Forløb, Triggers, Planter, Himmel) — **plus
    KONTROLPANELER** (user-spec 2026-09-30b: "indstillingerne skal være på
    indstillinger siden men kontrolpanelet skal igen ha sin egen side … simple
    kontrol paneler, i stil med lys siden"): Mad (`dashboards/mad.yaml`) og
    Støvsug (`dashboards/stoevsug.yaml`) har ting man TRYKKER på og status,
    ingen sliders; de linker til deres Indstillinger-fane via et badge og
    omvendt. Byg aldrig et nyt indstillings-dashboard — lav en fane. Et emnes
    indstillinger står på emnets fane; andre faner linker dertil i stedet for
    at duplikere.
  **Signatur på overtrædelse:** en markdown under en slider der forklarer
  HVORFOR defaulten er som den er, eller et tile-navn med et forbehold i
  parentes.
- **Nyt/droppet device** → `dashboards/status.yaml` (batterier + sensor
  health), `dashboards/lights.yaml` (tiles, fjern stale placeholders),
  [docs/hardware_shopping.md](hardware_shopping.md). Tjek med et grep på
  det nye entity-navn i begge dashboards — 0 hits = tilføj det.
- **Automation der tænder/slukker/farve-skifter en pære, eller kører et gardin**
  → `dashboards/triggers.yaml` (per 2026-07-03, user-spec). Husdækkende adfærd
  = topsektionen ÉN gang; rum-specifikt = det berørte rum-kort. Verificér med
  `python3 scripts/triggers_scan.py` (ground truth; ON/farve via scripts eller
  templated entity_ids vises som DYNAMISK → kuratér manuelt, jf. #1). Tommelfinger:
  ville brugeren undre sig over at pæren tændte pga. den? → skriv den ind.
- **Alt der kun gælder i AirBnB** (eller en AirBnB-gate i delt logik) →
  🏡 AirBnB-fanen i `dashboards/settings.yaml` (per 2026-07-08, user-spec; eget
  dashboard indtil 2026-09-30), samme commit. `grep AirBnB` for at finde alle
  med-ejere. Tjek særligt: automation flyttet ind/ud
  af lockdown-listen, ny undtagelse/par-kobling, og at tile-entity_ids stadig
  findes (entity_id beholder den GAMLE slug ved alias-rename).

### 🚦 Ingen subagent-flåder — Pro-plan kvote (per 2026-07-02, user-spec)

Delt token-kvote der resetter hver ~5. time. 6 parallelle agenter i én besked
brændte kvoten midtvejs: alle 6 døde UDEN at returnere rapport (~100 tool-calls
spildt) og måtte køres igen = dobbelt pris.

1. **Max 1-2 subagenter ad gangen** — aldrig en parallel flåde.
2. En agent der dør på kvote-loftet mister ALT; kun rapporter der nåede retur
   overlever.
3. Overvej først om hovedsessionen selv kan klare det med grep + targeted Read
   — det er ofte billigere.
4. Store reviews: kør klynger SEKVENTIELT.
5. **Workflow-værktøjet og "ultracode" ophæver IKKE reglen (2026-10-10).** En
   session fik "go ahead and use ultracode" til en død-slider-jagt og skrev et
   workflow med 12 Opus-findere i `pipeline()` + én Opus-skeptiker pr. fund
   (30+ agenter). Workflow-loftet er min(16, nproc−2) = 2 på NUC'en, men det
   bremser kun samtidigheden, ikke det samlede antal eller modellen. Kvoten
   nåede 5 %, mens agenterne stadig regnede, og shard 12 blev aldrig scannet.
   Nu håndhævet af `scripts/agent_guard.py` (PreToolUse på Workflow/Agent +
   SubagentStop-nedtælling): hver `agent()` skal have `model:'sonnet'`, ingen
   `pipeline()`/`while`, `parallel()` kun over `.slice(i, i + 2)`, højst 2
   samtidige Agent-kald, og Opus/fork kun alene. Fund verificeres af
   hovedsessionen selv i historikken, ikke af skeptiker-flåder. Kun brugeren
   må slå hooken fra (`.claude/agent_guard_off`).

**Revideret 2026-10-08 — "deleger rugbrød til Sonnet" (9/21) er droppet.** Måling
over 52 lokale transcripts + 86 subagent-transcripts (usage pr. unik message.id,
vægtet cache-read 0,1 · input 1 · cache-write 2 · output 5):

| | 17-20/9 Opus 5 | 23/9-4/10 Opus 5.5 | 5-8/10 |
|---|---|---|---|
| Kontekst genlæst pr. kald | 108k | 224k | 320k |
| Pris pr. kald | 19k | 35k | 47k |
| Auto-compactions pr. session | 3-6 | 0 | 0 |
| Subagenters andel | 4 % | 13 % | 33 % |

- Hver subagent starter med 50-65k tokens (system + CLAUDE.md + opgave) skrevet
  til 1-t-cache til dobbelt pris. Sonnet-agenter 0,2-1M pr. stk., Opus-agenter
  2-3M. Ultracode-bug-hunten 5-6/10: 27 agenter ≈ 11,7M. 7/10: Sonnet-hoved
  (1,6M) + 3 Opus-subagenter (6,55M) — den dyre model arbejdede i kolde kontekster.
- Den store driver var ikke filstørrelser men kontekst-længden: Opus 5.5's
  1M-vindue compactede aldrig, og ~halvdelen af væksten var bevaret thinking
  (effort xhigh). → `autoCompactWindow: 200000` i `~/.claude/settings.json`
  (Claude Code ≥ 2.1.280; interval 100k-1M, også `/autocompact`).
- CLAUDE.md 61 → 35 KB sparede ~10k tokens/kald (2-4 %); de path-scopede regler
  giver 6-20k tilbage i typiske sessioner.

### Andre standing instructions

- **People count falder KUN efter hoveddøren** (user-spec 2026-07-22, gentaget
  2026-10-01 og 2026-10-21: "again and again it comes back that the people count
  decreases without the main door opening … believe in yourself, guess and then
  stick to that guess until the main door opens (people may or may not leave) or
  change your guess upwards if you're certain you've estimated too low").
  Hvorfor reglen lækkede i tre måneder (undersøgt 21/10, 14 døgn, 113 fald, 51
  uden for et dør-vindue): hver rettelse lagde et gulv på en DEL af formlen
  (v4 ekstra-delen, v5 familie + ekstra), aldrig på det viste tal; "hoveddøren"
  voksede til seks vindue-åbnere (geofence-exit, familie-vækst, eftermiddags-
  børn, "For mange", Dormant, start); Dormant tvang 0 (19 fald); familie-0-grenen
  læste rå zoner (7); manuel-udløb hoppede (3); hukommelses-filen kodede
  undtagelserne som regel; og intet tjek så på tallet selv. v6
  (`packages/people_estimate.yaml`): `sensor.people_estimate` = manuelt tal eller
  `input_number.people_gulv`; modellen er et bud, som tallet følger op når det
  har holdt 150 s og ned kun i `people_afgang_vindue_minutter` efter hoveddøren.
  v6.1 (2026-10-22, user: "hvorfor people count ikke er sat til 0 efter
  dormant"): husets Dormant-dom senest `people_afgang_dom_minutter` (120) efter
  døren er dørens egen konklusion → tallet 0 og ekstra-gulvet ryddet. Målt 30
  døgn: dommen lander 35-104 min efter døren; det tidligste forkerte Dormant
  (nogen hjemme) lå 284 min efter. Et Dormant uden dør foran sænker intet.
  Lovlige veje ned ud over døren: brugerens +/-, "For mange", børn-off-knappen.
  `./scripts/ha_health.sh people` (`scripts/people_invariant.py`) fejler på
  ethvert andet fald.

- **Nye problemer** → [BACKLOG.md](BACKLOG.md) i rette kategori. **Løste** →
  "Done" med dato, eller slet hvis trivielt.
- **Permanent, nyttigt faktum** (hardware-quirk, stabilt miljø-fakta, gentaget
  gotcha) → ÉN kort bullet i "Permanente fakta" ovenfor. Kriterie: ville en
  fremtidig session spilde tid uden at vide det? Task-specifikt hører i memory
  eller BACKLOG, ikke her.
- **`replace_all` på numeriske patterns er farligt:** `transition: 60` matcher
  også prefixet af `transition: 600`. Brød HA boot 2026-04-29. Brug per-sted
  edit eller verificér med line-end-anchored grep.
- **Hardware shopping list** vedligeholdes i
  [docs/hardware_shopping.md](hardware_shopping.md) når devices
  pares/bestilles/droppes.
