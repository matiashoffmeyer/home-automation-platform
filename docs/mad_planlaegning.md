# Mad-planlægning — ret-afstemninger + indkøbsliste

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Daglig notifikation til Parent A og Parent B med **én ret** og knapperne
**JA! / SUPERJA! / NIX!**. Hver anden tirsdag samles 3–4 godkendte retter til én
indkøbsliste med **summerede mængder**, klar til nemlig.com.

Ret-kataloget lever i Google Sheets, så Gemini kan fylde flere retter på
løbende uden at røre HA.

| Del | Fil |
|---|---|
| Hjernen (udvælgelse, summering, notifikationer) | [`scripts/mad_planner.py`](../scripts/mad_planner.py) |
| Sheets-API (læs/skriv fra HA) | [`scripts/mad_sheet_api.gs`](../scripts/mad_sheet_api.gs) |
| Sliders, kill-switches, shell_commands | [`packages/mad_planlaegning.yaml`](../packages/mad_planlaegning.yaml) |
| Scheduler + stemme-handler | [`automations/mad_planlaegning.yaml`](../automations/mad_planlaegning.yaml) |
| "Mad"-siden (kontrolpanel: Opskrifter · Indkøb · Afstemning · Nemlig · Stats) | [`dashboards/mad.yaml`](../dashboards/mad.yaml) |
| Mad-indstillingerne (alle sliders og til/fra) | [`dashboards/settings.yaml`](../dashboards/settings.yaml), fanen `🥘 Mad` |

---

## Mad-siden (UX-rework 2026-08-17)

> **2026-09-30 (to skridt samme dag):** Mad blev først lagt ind som fanen **🥘 Mad**
> under Indstillinger, og fik så sit KONTROLPANEL tilbage som eget dashboard
> (`/mad-dash/`, user: "indstillingerne skal være på indstillinger siden men
> kontrolpanelet skal igen ha sin egen side"). Mad-siden har fanerne Opskrifter
> (+ undersiderne `opskrift-1..16`), Indkøb, Afstemning, Nemlig og Stats; alle
> sliders og til/fra står under Indstillinger → 🥘 Mad (`/indstillinger-dash/mad`).

Fire faner, så den daglige brug ikke ligger begravet under sliders:

| Fane | Indhold |
|---|---|
| 👩‍🍳 **Opskrifter** (landingsside) | Oversigtsliste over ugens retter + ét kort pr. opskrift med ingredienser og nummererede trin |
| 🛒 **Indkøb** | Retterne på listen, varerne, knappen til `todo.shopping_list`, fjern/udskift, "lav liste nu" |
| 🗳️ **Afstemning** | Godkendt/afventer/afvist, balance, seneste svar, seneste spørgsmål, tabte svar-tryk |
| ⚙️ **Indstillinger** | Alle sliders + hele den lange forklaring |

**Opskrift-kortene er dumme.** Hele markdown-formatet bygges i
`opskrift_md()` og lægges på hver ret som attributten `md` (plus `linje` til
oversigten og `ikon` til kategori-emojien). Dashboardet har otte kort-slots der
kun skriver `r[n].md` ud — så et formatskifte rammer alle otte på én gang i
stedet for at divergere (fejlklasse #2). **Slot 8 viser `[7:]`**, altså resten
samlet, så en lang liste ikke taber opskrifter i tavshed.

**⚠️ Slottene SKAL gates med `numeric_state`.** Derfor er
`sensor.mad_opskrifter`s state et rent **tal** (antallet af opskrifter) med
`unit_of_measurement: "opskrifter"`, så badges stadig læser "5 opskrifter", og
slot *i* står på `above: i` (0-7). Lovelace har **ingen `template`-betingelse**
i card/section-`visibility` — en `condition: template` afvises tavst og skjuler
kortet for altid, uden logfejl. Det kostede alle otte kort 2026-08-17. Ændrer du
sensorens state til noget ikke-numerisk, forsvinder opskrift-kortene igen.

`guide_trin()` deler arkets fritekst-guide i nummererede trin. Et sætningsskift
kræver **både** `.`/`!`/`?` **og** stort begyndelsesbogstav efter — ellers ville
danske forkortelser (`ca. 35 minutter`, `2 stk. squash`) dele et trin midt over.
Er guiden allerede skrevet med linjeskift, respekteres den som den er.

### Afkrydsning i butikken

`script.mad_indkoeb_til_liste` (knap på 🛒 Indkøb) kopierer
`sensor.mad_indkoebsliste`s `varer` over i **`todo.shopping_list`**, hvor de kan
krydses af på telefonen. Scriptet henter først de eksisterende punkter og
tilføjer **kun** det der mangler — det rydder aldrig, så hverken egne linjer
eller allerede afkrydsede varer forsvinder ved et ekstra tryk (verificeret live:
27 varer ind, uændret 27 ved andet tryk).

---

## Regler (user-spec 2026-07-29)

- **Godkendt ret** = begge har svaret **+ ingen NIX + mindst ét JA**.
  To × "Måske" er altså ikke nok, og et enkelt NIX udelukker retten permanent.
- **"Måske" er en TIMEOUT, ikke en knap** (user-spec 2026-08-29). Har man ikke
  svaret inden `input_number.mad_svar_timeout_dage` (7) dage regnet fra det
  **første** spørgsmål om retten, tæller det manglende svar som et Måske:
  retten er færdigbehandlet og bliver ikke genspurgt mere. Fristen måles fra
  første spørgsmål, fordi `mad_genspoerg_dage` ellers ville nulstille uret hver
  gang vagten spurgte igen. 0 = timeout slået fra.
- **SUPERJA!** garanterer retten en plads på den **førstkommende** indkøbsliste,
  uanset hvad den anden svarer — også et NIX. Kvote: **én pr. person pr.
  `input_number.mad_superja_dage`** (7). Bruges den oftere, bliver den lydløst
  til et almindeligt JA, og kvitteringen fortæller hvornår den næste er klar.
  Arkets Apps Script kender kun `JA/NIX/MAASKE`, så et SUPERJA skrives til arket
  som `JA`; "super"-stemplet lever i `/config/.mad_planner_state.json` under
  `superja` (pr. person: ret + dato + `leveret`) og ryddes når retten er landet
  på en liste. Stemplet følger rettens **navn**, ikke dens id — id-kolonnen er
  positionel og forskyder sig når Gemini sletter rækker.
- **Ingen "bestilt"-markering.** Retter kan gentages; vi satser på at puljen er
  lang nok til at tilfældigheden holder.
- **Alle retter er skrevet til 4 personer** (2 voksne + 2 børn) — ingen
  portions-skalering.
- Er der færre godkendte retter end minimum, sendes **ingen** indkøbsliste.

### Balanceret udvælgelse

Spørgsmålet er ikke tilfældigt: dagens ret trækkes fra den kombination
(**børnevenlig × sværhedsgrad**) der er mest underrepræsenteret i den
**godkendte pulje** — så puljen er i balance den dag der skal købes ind.
Retter der er sendt ud men endnu ikke besvaret tæller halvt med, så vi ikke
spørger en hel uge ind i samme hjørne før det første svar lander.
Sværhedsgraderne opdages fra arket, så en fremtidig "Svær" indgår automatisk.

Selve indkøbslisten sammensættes efter samme mål: ~50 % børnevenlige
(slider) og spredt på sværhedsgrad.

### Tema-karantæne (user-spec 2026-08-26)

Balancen ovenfor kender kun to akser (børnevenlig × sværhedsgrad) og ser
derfor ikke at flere retter deler samme **tema**. Parent B klagede over
kartoffelsalat, og arket gav hende ret: der blev spurgt om tre forskellige
kartoffelsalater på fire dage (22., 24. og 25. august 2026). Puljen er ikke
skæv — 6 af 406 retter er kartoffelsalat — men de seks fordeler sig pænt på
begge balance-akser (Lyst kød / Salat / Vegetar / Rødt kød), og alle seks er
`Sommer`, som vejer 3× i august. Klyngen var altså sandsynlig, ikke uheldig.
`naer_dublet` fanger den ikke: den bruges kun når **kurven** fyldes, aldrig når
der spørges.

`RET_TEMA_KARANTAENE` i `scripts/mad_planner.py` er derfor en `{delstreng:
dage}`-tabel — pt. `kartoffelsalat: 30` = "maks ét kartoffelsalat-spørgsmål pr.
måned". Karantænen læses ud af arkets egen `Sidst spurgt`-kolonne (ingen
sidevogns-state), gælder **også** når dagens spørgsmål er tvunget til at være
en salat, og dedupliker desuden inden for samme batch hvis
`mad_spoergsmaal_antal` > 1. Et nyt tema er én linje i tabellen.

---

## Ark-skema

De 6 første kolonner er dem arket havde i forvejen. `setup`-kaldet tilføjer
resten bagerst — eksisterende data røres ikke.

| Kolonne | Indhold |
|---|---|
| `ID` | stabilt løbenummer (tildeles automatisk) — notifikationsknapperne peger på det, så indsatte/sorterede rækker ikke flytter en stemme |
| `Ret` | rettens navn |
| `Kategori` | fx `Aftensmad` |
| `Børnevenlig` | `Ja` / `Nej` |
| `Sværhedsgrad` | `Let` / `Mellem` / `Svær` |
| `Ingredienser` | fri tekst (menneske-læsbar) |
| `Trin-for-trin Guide` | fri tekst |
| `Ingredienser_struktureret` | **maskin-læsbar** — se format nedenfor |
| `Parent A` / `Parent B` | `JA` / `NIX` / `MAASKE` (skrives af HA — et SUPERJA lander her som `JA`) |
| `Sidst spurgt` | `ÅÅÅÅ-MM-DD` (skrives af HA) |

### Format for `Ingredienser_struktureret`

```
mængde|enhed|vare;mængde|enhed|vare;…
```

Eksempel:

```
500|g|hakket oksekød;800|g|hakkede tomater;1|dl|mælk;1|stk|løg;2|stk|gulerødder;500|g|spaghetti
```

Regler:

- **Enheder**: `g`, `kg`, `ml`, `dl`, `l` (kan lægges sammen på tværs af retter)
  eller `stk`, `spsk`, `tsk`, `fed`, `ds`, `pk`, `pose`, `glas`, `bdt`, `brev`,
  `potte`, `bøtte` (summeres i deres egen enhed).
- **Vægt/volumen slår antal**: står der `2 ds (800 g) hakkede tomater`, så skriv
  `800|g|hakkede tomater` — det er den mængde man køber efter.
- **Genbrug varenavne præcist.** `hakket oksekød` i alle retter kan lægges
  sammen; `oksekød, hakket` bliver en selvstændig linje på listen.
- Ingen mængde i navnet, ingen decimalkomma (brug punktum: `0.5`).

Mangler kolonnen for en ret, falder scriptet tilbage til at udlede mængderne
fra fri-tekst-kolonnen. Det virker for ~90 % af linjerne, men den strukturerede
kolonne er den præcise.

---

## Opsætning (engangs)

### 1. Apps Script web-app (giver HA skriveadgang)

1. Åbn arket → **Udvidelser → Apps Script**.
2. Erstat al kode med indholdet af `scripts/mad_sheet_api.gs`.
3. Ret `TOKEN` øverst til en tilfældig streng.
4. **Gem** → **Udrul → Ny udrulning** → vælg type **Webapp**:
   - *Kør som*: **Mig**
   - *Hvem har adgang*: **Alle** (HA kan ikke logge ind — token'et er beskyttelsen)
5. Godkend adgangen, kopiér web-app-URL'en (slutter på `/exec`).

### 2. Secrets på NUC'en

```yaml
# /config/secrets.yaml  (gitignored)
mad_sheet_url: https://script.google.com/macros/s/…/exec
mad_sheet_token: <samme streng som TOKEN i mad_sheet_api.gs>
mad_sheet_id: <arkets id — læs-only CSV-fallback>
```

### 3. Initialisér arket + backfill

```bash
python3 /config/scripts/mad_planner.py --refresh          # tjek forbindelse
python3 /config/scripts/mad_planner.py --sync-local       # løft lokale stemmer op i arket
python3 /config/scripts/mad_planner.py --backfill-struct  # udfyld den strukturerede kolonne
```

(`setup`-kaldet der opretter kolonnerne kaldes af `--sync-local`/API'et første
gang; det kan også køres direkte i browseren:
`<web-app-url>?token=…&action=setup`.)

**Uden trin 1–2 kører alt stadig** — bare i læs-only-tilstand mod den
offentlige CSV-eksport: spørgsmål sendes, og stemmer gemmes lokalt i
`/config/.mad_planner_state.json` i stedet for i arket. `--sync-local` løfter
dem op bagefter.

---

## Instruktion til Gemini

> Når du tilføjer retter til arket, udfyld alle kolonner inkl.
> `Ingredienser_struktureret` i formatet `mængde|enhed|vare;…` (fx
> `500|g|hakket oksekød;1|stk|løg`). Brug g/kg/ml/dl/l hvor der findes en vægt
> eller et rumfang — også når opskriften siger "1 ds": skriv indholdets vægt.
> Ellers stk/spsk/tsk/fed/ds/pk/pose/glas/bdt/brev/potte/bøtte. Genbrug
> varenavne præcist på tværs af retter, så mængder kan lægges sammen. Skriv
> aldrig mængder ind i varenavnet. Lad `ID`, `Parent A`, `Parent B` og
> `Sidst spurgt` stå tomme — de styres af Home Assistant.
> Retterne skal være til 4 personer (2 voksne + 2 børn), og hold gerne
> fordelingen 50/50 mellem `Børnevenlig` Ja/Nej og en jævn spredning på
> `Sværhedsgrad`.

---

## Ret ud af listen: fjern eller udskift

Nederst på Mad-siden vælges en ret i `input_select.mad_vaelg_ret` ("Vælg ret" —
entity_id hedder stadig `mad_fjern_ret`), hvorefter to knapper kan bruges:

| Knap | shell_command | Flag | Hvad sker der |
|---|---|---|---|
| 🗑️ Fjern denne ret | `mad_fjern_ret` | `--fjern-valgt` | Retten slettes, listen genberegnes uden den |
| 🔄 Udskift denne ret | `mad_udskift_ret` | `--udskift-valgt` | Retten erstattes af én ny, godkendt ret **på samme plads** |

Udskiftningen vælger ikke tilfældigt: `vaelg_erstatning()` scorer kandidaterne
mod de retter der **bliver stående** — kategori, sværhedsgrad, andelen af
børnevenlige (samme ~50 %-mål som selve listen) og sundhed — plus et led der
straffer stor afvigelse i kurv-vægt fra den ret der ryger ud, så indkøbet ikke
hopper i størrelse. Retter der allerede står på listen er udelukket. Er der
ingen kandidat, røres listen ikke (logbook + kort push).

Begge veje genpublicerer via `publish_indkoeb`, som er eneste skriver af
indkøbs-state — så selecten, sensorerne og dashboardet følger med i ét hug.

### Fortryd: læg en ret tilbage

```bash
python3 /config/scripts/mad_planner.py --tilfoej-ret "Svinekæber i mørkt øl"
```

Slår op i hele kataloget (ikke kun i den godkendte pulje) og lægger retten
bagerst på den aktuelle liste. `🗑️ Fjern` havde ellers ingen vej tilbage.

### Vi har det allerede hjemme

```bash
python3 /config/scripts/mad_planner.py --har-hjemme "350|g|afpudsede svinekæber"
```

Trækkes fra **summen**, ikke fra opskriften: retten skal stadig laves på sine
800 g, vi skal bare ikke købe dem der står i køleskabet — linjen bliver `450 g`,
og en vare der dækkes helt forsvinder fra listen. Formatet er arkets
(`mængde|enhed|vare`, flere adskilt med `;`), så varenavnet normaliseres præcis
som i opskriften.

Posten hænger på den **liste** den blev sat på (`genereret`-stemplet): næste
indkøbsliste starter forfra. Det er med vilje — en glemt post der overlevede
ville trække fra hver fremtidig liste i tavshed, og at købe 350 g for meget er
en billigere fejl end at mangle dem midt i en gryderet.

---

## Notifikationer

To typer i den centrale notifikations-styring (🔔-fanen på Indstillinger):

| Nid | Vej | Hvorfor |
|---|---|---|
| `mad_indkoeb` | `script.push_notify` | Samme besked til begge → central dispatch, hjemkomst-kø virker |
| | | Pushen er bevidst **kort**: én linje pr. ret + antal varer. Hele listen med mængder står i `sensor.mad_indkoebsliste`s attribut og på Mad-siden — en push man skal scrolle i, læses ikke |
| `mad_spoergsmaal` | direkte fra scriptet | Hver telefon skal have sine egne svar-knapper (personen er kodet i action-id'et `MAD_<person>_<svar>_<id>`), og dispatchen sender samme payload til alle |

⚠️ Fordi ret-spørgsmålet går uden om dispatchen, **spejler**
`mad_planner.py::gate_ok` gate-logikken fra `script.push_notify` (master, type,
AirBnB, tidsvindue, telefon-valg) — præcis som `plant_notify.py::deliverable_now`.
Ændrer du gaten ét sted, skal det andet med.

Begge nids har tidsvindue `00:00–00:00` (= altid) med vilje: tidspunktet ejes af
sliderne på Mad-siden, så der kun er én tids-autoritet. Slår du en af telefonerne
fra på ret-spørgsmålet, kan retter aldrig blive godkendt (begge svar kræves).

## Drift

| Situation | Hvad sker der |
|---|---|
| Notifikations-knap trykkes | `mobile_app_notification_action` → regex-valideret → `shell_command.mad_vote` → stemme i arket + kvittering på telefonen |
| HA genstarter | `sensor.mad_*` er REST-publicerede og forsvinder; refresh-automationen genskaber dem 20 s efter start |
| Slider ændres | samme refresh → "næste indkøbsliste" opdateres med det samme |
| Ingen retter tilbage at spørge om | ingen notifikation, kun en logbook-linje |
| Web-app'en svarer ikke | automatisk fallback til CSV (læs-only) — `sensor.mad_status` viser kilden |

Manuel test:

```bash
python3 /config/scripts/mad_planner.py --ask --dry-run
```

Basisvare-filteret (salt, peber, olie, sukker, mel, tørrede krydderier) står i
`BASISVARER` i `scripts/mad_planner.py` og slås fra/til med
`input_boolean.mad_basisvarer_filter_enabled`.
