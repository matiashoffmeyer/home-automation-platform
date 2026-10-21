# Nemlig-kurv — feasibility + eksekveringsplan

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Status 2026-08-31: feasibility afklaret — det er muligt, og fase 1 er live.**
Denne fil er planen for resten. Fuld API-dokumentation står i modulets docstring
(`scripts/nemlig_api.py`); her står *hvorfor* og *hvad mangler*.

---

## 1. Er det muligt?

Ja, og med bedre odds end forventet. Repoet [schourode/nemlig][repo] er fra 2019,
så det reelle spørgsmål var ikke "kan man kode det" men "svarer API'et stadig".
Det blev **målt, ikke antaget** — hele kæden kørt live 2026-08-31:

| Kald | Resultat |
|---|---|
| `POST /webapi/login/login` | 200, sætter `.ASPXAUTH` + `XSRF-TOKEN` |
| `GET /webapi/s/0/1/0/Search/Search` | 200, 149 træf på "hakket oksekød" |
| `GET /webapi/basket/GetBasket` | 200, `Lines[]`, `TotalPrice`, `MinimumOrderTotal` |
| `POST /webapi/basket/AddToBasket` | 200, vare i kurven — og fjernet igen |

Ingen Cloudflare-udfordring, ingen CAPTCHA, ingen 2FA. Der kræves en almindelig
browser-`User-Agent`; en tom UA afvises.

**Testen efterlod ingen spor:** kurven var tom før og er tom efter.

### Gemini-forslaget, korrigeret

Gemini kendte ikke setuppet. Tre ting er overruled:

| Gemini | Her |
|---|---|
| Klon `api/`-mappen ind i `/config` | **Nej.** Fladen er fire HTTP-kald — hele klienten er ét selvstændigt modul uden `requests`-afhængighed. Et vendored tredjeparts-repo ville være mere kode at vedligeholde end at eje. |
| Credentials i Python-filen | **Nej.** `/config/secrets.yaml` (git-ignoreret), samme mønster som `mad_planner.py`. |
| PyScript via HACS | **Unødvendigt.** Huset kalder allerede Python via `shell_command` overalt; en ny runtime for én integration er ikke værd at eje. |
| RESTful Command uden Python | **Umuligt i praksis.** Flowet kræver cookie-session + XSRF-header + søgning + matchning + pakke-matematik. Det er ikke et REST-kald, det er et program. |
| `add_to_basket(session, item_id, quantity=1)` | **Farligt som skrevet.** `quantity` er *absolut*, ikke et delta — se invarianten nedenfor. |

### To invarianter, dyre at genopdage

1. **`AddToBasket.quantity` er ABSOLUT.** `add(id,1)` to gange giver **1**, ikke 2.
   `quantity=0` **fjerner** linjen. Det er godt nyt: kurv-opbygningen bliver
   idempotent, så en gentaget kørsel ikke fordobler indkøbet. Men kode skrevet
   ud fra "læg én til"-antagelsen ville lydløst gøre det forkerte.
2. **Lagerstatus koster ikke et ekstra kald** — `Availability.IsAvailableInStock`
   ligger allerede i søgesvaret. Og den er **volatil**: peberfrugt skiftede fra
   udsolgt til på lager inden for fem minutter under testen. Derfor må status
   aldrig caches i parringsfilen — den skal læses i selve kurv-kørslen.

---

## 2. Skal HA's AI lægge varerne i kurven?

**Nej — ikke i v1, og formentlig aldrig som den primære vej.** Det blev testet
frem for gættet: en deterministisk matcher blev kørt mod 15 ægte
ingrediens-linjer fra indkøbslistens format.

**Resultat: 14 af 15 sikre match.** Den ene usikre (`pasta` → "Penne rigate")
er præcis den slags, et menneske skal afgøre én gang — hvorefter parringen
huskes for altid i `.nemlig_varer.json`.

Argumenterne mod en LLM i sløjfen:

- **Den svære del er ikke sprog.** Det er pakke-matematik (800 g behov mod
  400 g-pakker = 2) og lagerstatus. Begge dele er aritmetik og et boolsk flag.
- **Det skal være auditerbart.** En forkert vare opdages først ved leveringen.
  En score på 0,00 er en forklaring; "modellen mente det" er ikke.
- **Parringen bliver bedre af sig selv.** Hver gang brugeren afgør et usikkert
  match, er det spørgsmål væk permanent. En LLM ville gætte igen hver gang.
- Huset kalder allerede eksterne API'er nok; en model-rundtur pr. vare er
  hverken gratis eller hurtigere end et opslag i en JSON-fil.

**Hvor en LLM *kunne* betale sig senere:** at foreslå en søgeterm når
råvarenavnet slet ikke findes som produkt ("forårsløg" → "bundtløg"). Det er en
lille, afgrænset opgave på restgruppen — ikke på hovedvejen. Udskudt til efter
vi har målt hvor stor restgruppen faktisk er over et par indkøbsrunder.

### Hvorfor prefix-match, ikke delstreng

Første version scorede **"Rødløg" 1,15 på søgningen "løg"**, fordi `loeg` er en
delstreng af `roedloeg` — huset ville have købt rødløg til enhver opskrift der
bad om løg. Rettet til prefix-match: et dansk sammensat ord har sit **kerneord
til højre**, så `kyllingebryst` → `Kyllingebrystfilet` består, mens
`løg` → `rødløg` falder. Efter fixet: "Løg Zittauer". ✓

---

## 3. Hvad er live nu (fase 1 — færdig)

- `scripts/nemlig_api.py` — klient (login m. session-cache, søgning, kurv,
  navne-matcher, pakke-matematik) + CLI: `--ping --search --basket --add --ryd`
- `packages/nemlig_kurv.yaml` — kill-switch, tørkørsels-switch, score-slider,
  `shell_command.nemlig_ping`
- Credentials i NUC'ens `secrets.yaml`; session-cookies `chmod 600`,
  runtime-filer i `.gitignore`
- Verificeret fra NUC'en: `{"ok": true, "kurv_linjer": 0, "min_ordre": 500}`

**Bemærk: minimums-ordre er 500 kr.** En kurv under det kan ikke bestilles —
fase 2 skal rapportere totalen, så det opdages før leveringsdagen.

---

## 4. Eksekveringsplan (fase 2+)

### Fase 2 — kurv fra indkøbslisten ✅ *(live 2026-08-31)*

Summen er skilt ud som data (`mad_planner.indkoebsposter`), med
`byg_indkoebsliste` som en tynd formaterings-skal ovenpå — matcheren parser
ikke strenge vi selv lige har formateret. Pr. vare:

1. Slå op i `.nemlig_varer.json` → kendt produkt-id? brug det.
2. Ellers søg, `find_bedste()`, og accepter kun score ≥ `nemlig_match_min_score`.
3. `antal_pakker()` → ønsket antal.
4. **På lager** → `add(id, antal)` (absolut, idempotent).
5. **Ikke på lager** eller **usikker match** → med i notifikationen, ikke i kurven.

Kørslen skal være **idempotent pr. indkøbsrunde**: samme runde igen = samme
kurv, ikke dobbelt. Det følger gratis af den absolutte `quantity`, forudsat vi
sender slut-antal og aldrig et delta.

**Første ægte kørsel (2026-08-31):** 9 retter · 44 varer → **35 produkter,
1064 kr**. 2 udsolgt, 7 usikre — ingen af dem lagt i kurven. Kurven blev
ryddet igen med `--ryd-vores`; verificeret tom.

Kørslen afslørede én defekt der er rettet: **"jordbær" købte en smoothie.**
"Smoothie m. jordbær og hindbær" scorede fuldt, fordi ordet ganske rigtigt står
i navnet — men som *bestemmelsesord*, ikke som varen. Rangeringen fik en
hovedord-tiebreaker (Nemlig navngiver hovedord-først). Bevidst kun en
tie-breaker, ikke en afvisning: fire korrekte match i samme kørsel havde et
bestemmelsesord forrest ("Grønlandske rejer", "Brioche burgerboller", "Baby
salatmix", "Arborio risottoris"), og en hård regel ville have kasseret dem alle
for at redde én.

**Kendt, ikke en fejl:** 9 af 35 varer gav "enheder matcher ikke" (opskriften
siger `2 stk tomater`, varen sælges pr. kg; `1 fed hvidløg` mod et helt løg;
`2 spsk ketchup` mod en flaske). Der lægges 1 pakke og markeres ærligt. At
gætte en omregning fra stk til kg ville være værre end at sige det højt.

### Fase 3 — notifikation + afklaring ✅ *(live 2026-08-31)*

Én samlet push (gennem `script.push_notify`, nid `nemlig` — **ikke** direkte
`notify.mobile_app_*`, jf. husets dispatch), med tre grupper:

- ✅ lagt i kurven (antal + total, samt advarsel hvis total < 500 kr)
- ⚠️ **udsolgt** — brugerens eksplicitte krav
- ❓ **usikker parring** — knapper til at vælge blandt top-3, og valget skrives
  til `.nemlig_varer.json`, så spørgsmålet aldrig stilles igen

Den sidste gruppe er hele indlæringsmekanismen. Den er grunden til at
integrationen bliver bedre af at blive brugt, uden en model i sløjfen.

**Bygget som:** ét spørgsmål pr. uafklaret vare, kun til Parent A, med to
in-stock-kandidater + "Spring over" som knapper (Android viser 3 pålideligt).
Loft på spørgsmål pr. kørsel (8), fordi ni notifikationer på én gang er en mur.
Kun kandidater **på lager** bliver til knapper — for en udsolgt vare er hele
pointen at finde noget man kan få. Svaret skrives til `.nemlig_varer.json`,
lægges straks i kurven med antal genberegnet mod det VALGTE produkts pakning,
og næste kørsel springer score-tærsklen over for den vare.

Verificeret ende-til-ende med den ægte `mobile_app_notification_action`-event:
spørgsmål → svar → parring skrevet → vare i kurv (2 pk Rucola mod 150 g behov
og 100 g pr. pakke). Testparringen blev slettet igen.

### Fase 5 — selvtest over hele katalogget ✅ *(live 2026-08-31)*

`scripts/nemlig_selftest.py` kører matcheren mod **alle 495 unikke råvarer** i
de 406 retter (read-only mod Nemlig). Rapporten grupperer efter **fejlklasse**,
ikke efter vare — en liste med 495 linjer er ikke en analyse. Den bruger den
STØRSTE mængde set for hver råvare, fordi det er dér pakke-matematikken har
mest at tage fejl af.

| | Før | Efter |
|---|---|---|
| Sikre (købes automatisk) | 67 % | 63 % |
| Spørges der om | 28 % | 27 % |
| Ingen brugbare produkter | 5 % | 10 % |
| **Accepteret på fremmed hovedord** | **48** | **0** |

Faldet i "sikre" er tilsigtet: de 48 farlige er flyttet til spørgsmål.

**Fem defekter fundet og rettet:**

1. **`citrongræs` → «Tofu m. citrongræs» med fuld score.** Vi ville have købt
   tofu. `hoved_traef` ser nu kun på navnet **indtil første præposition** —
   alt efter "m."/"med" beskriver hvad der er I varen — og er blevet en
   **gate** for auto-køb, ikke bare en tie-breaker.
2. **Bøjning.** `laksefileter` scorede 0,00 mod «Laksefilet». Prefix-matchet
   gik kun én vej. Nu også omvendt, men højst 3 tegn — ellers ville
   "smørkage" matche "smør".
3. **Sammensætning.** `dijonsennep` mod «Dijon sennep» scorede 0,00.
   Sammenlignes nu også mod produktnavnet uden mellemrum og uden bindeord
   («Bacon i tern» limet som "baconitern" indeholdt ikke "bacontern").
4. **26 råvarer forsvandt tavst.** Nemligs søgning matcher ikke lange danske
   sammensatte ord — `chorizopølse`, `cantaloupemelon`, `kulmulefileter` gav
   nul træf. Uden træf er der hverken kurv-linje eller kandidater at spørge
   med, så varen forsvandt uden at nogen fik det at vide. `search_bredt()`
   afkorter fra højre ved nul træf.
5. **Relevans ≠ score.** En score på 0,00 betyder "køb den ikke i blinde", ikke
   "nævn den ikke". Dansk gør flere korrekte match uscorbare: flertal kan
   elidere et bogstav (`falafel`→`falafler`), og et sammensat råvarenavn kan
   have produktet som venstre del (`chorizopølse`→«Chorizo»). Strukturelt er
   de ikke til at skelne fra `smørkage`→`smør`, så de må ikke købes
   automatisk — men de skal foreslås. `relevant_nok()` bruger fælles
   begyndelse pr. ordpar.

**Kendt og accepteret:** ~30 råvarer har en enhed pakke-matematikken ikke kan
omregne (`spsk` optræder 338 gange i katalogget, plus `fed`, `bdt`, `knsp`).
De får 1 pakke og en ærlig markering. For krydderier og hvidløg er det
rigtigt; et gæt på omregningen ville ramme forkert i begge retninger.

To fejl blev fundet ved **gennemlæsning**, ikke af testen — den kører kun
matcheren, ikke kurv- og svar-stierne: dublette knapper (det valgte produkt
kunne optræde som sit eget alternativ), og at `besvar()` sendte et absolut
antal og dermed kunne SÆTTE NED i stedet for at lægge til.

### Fase 6 — knapperne virkede aldrig ✅ *(live 2026-08-31)*

**`shell_command` har en hård timeout på 60 sekunder** (`COMMAND_TIMEOUT` i
`homeassistant/components/shell_command`). En fuld kurv-kørsel tager ~95 s.
HA dræbte derfor processen **midt i løkken**: varerne der allerede var lagt i
blev stående, mens køerselsfilen, spørgsmålene og sensoren aldrig blev
skrevet. Knappen så død ud *og* efterlod varer som "Fjern vores varer" ikke
kunne rydde op efter — den fil der skulle huske dem blev jo aldrig skrevet.

De lange kommandoer er nu detachede (`nohup … &`) og scriptet publicerer
"kører … N varer" med det samme, så knappen kvitterer synligt. Verificeret:
returnerer på 0,0 s og gør sig færdig efter ~90 s.

**Favorit-signalet var tabt.** `find_bedste` rangerede «Brioche burgerboller»
øverst med ★ (tidligere køb), men `vaelg_produkt` så kun på score, øko og
pris. Rækkefølgen er nu **korrekthed før præference**: hovedord-filter →
favorit → øko → tilbud. En favorit der er den forkerte vareart må ikke vinde
fordi den er favorit — «Smoothie m. jordbær» er også et tidligere køb.
Sidegevinst: `citrongræs` finder nu «Citrongræs øko.» i stedet for tofuen.

**Forældede valg blev hængende.** Den absolutte `quantity` gør gentagne
kørsler idempotente for varer der forbliver de samme — men når et match
ændrer sig, blev den gamle vare stående for evigt. Kørslen afstemmer nu mod
forrige køersel og fjerner det den ikke længere vil have.

**"Spring over" var for permanent.** Brugeren sprang alle fem spørgsmål over
på ét minut, fordi forslagene var ubrugelige («Soltørrede fersken» til ferske
rødspættefileter — "fersk" er nu stopord, og varen rammer «Rødspættefilet»
med 1,00). Et permanent nej som konsekvens af ét tryk på et dårligt forslag
er en fælde. Spring over er nu tidsboks på 30 dage.

Nemlig har fået **sin egen fane** på Mad-siden.

### Fase 4 — øko + tilbud ✅ *(live 2026-08-31)*

**Øko foretrækkes, men kun når prisen holder.** Sammenligningen sker på
**enhedspris med samme enhed** — kr/kg mod kr/kg. Uden det tjek ville en
kg-vare til 96 kr se dyrere ud end en stk-vare til 20 kr, og loftet ville
afvise på et falsk grundlag. Referencen er den billigste konventionelle vare
der matcher **lige så godt**: match-kvalitet afgøres først, for en grønnere
vare der er den forkerte vare er stadig den forkerte vare.

Målt mod ægte data ved loft 100 %:

| Vare | Øko-merpris | Ved loft 50 | Ved loft 100 |
|---|---|---|---|
| Hakket oksekød | +74 % | konventionel | **øko** |
| Gulerødder | +57 % | konventionel | **øko** |
| Mælk | +23 % | **øko** | **øko** |

**Tilbud vinder kun hvis varen faktisk er billigst pr. enhed.** Et rabatmærke
på en dyrere vare er ikke en besparelse, og en ren "foretræk tilbud"-regel
ville have købt den.

**Besparelse i kroner kan ikke opgøres mod normalprisen.** Det blev undersøgt,
ikke antaget: `Campaign` og `CampaignAttribute` er `null` på alle varer,
produkt-detalje-endpointet har ingen prisfelter, og produktsiden redirecter.
Der findes ingen før-pris i API'et. Det vi *kan* opgøre — og som faktisk siger
noget om vores eget valg — er forskellen mod **det alternativ vi valgte fra**:
`merpris_oeko` (hvad øko-præferencen kostede) og `besparelse_est` (hvad det
billigere valg sparede). Begge står pr. vare i `sensor.nemlig_kurv` med en
begrundelse, og summeret i rapportens 🌱/🏷️-linje. Tallet er mærket som
estimat overalt — det må aldrig læses som "Nemlig gav rabat".

### Fase 4 — dashboard + drift

- Tiles på **Mad**-siden: kurv-total, antal linjer, sidste kørsel, udsolgte
- `sensor.nemlig_kurv` publiceret af scriptet (samme REST-mønster som
  `sensor.mad_indkoebsliste`; forsvinder ved restart → med i refresh-automationen)
- Kobles til `mad_indkoeb`-kørslen (hver 2. tirsdag) — **efter** en runde med
  tørkørsel, så matchene kan læses igennem før kontoen røres

### Bevidst uden for scope

**Der afgives aldrig en ordre.** Integrationen fylder kurven; leveringstid og
betaling vælger et menneske i Nemligs egen app. Der bygges ingen kode-sti til
checkout — en fejl i en matcher skal kunne koste en forkert vare, aldrig en
gennemført handel.

---

## 5. Risici

| Risiko | Håndtering |
|---|---|
| Nemlig ændrer deres uofficielle API | `--ping` er røgtesten; klienten fejler højlydt med JSON-fejl frem for tavst |
| Session udløber midt i en kørsel | 401/403 → ét automatisk gen-login, så videre |
| Forkert vare i kurven | Score-tærskel + tørkørsels-switch + notifikation; aldrig checkout |
| Kurv under 500 kr | Rapporteres i fase 3-notifikationen |
| Konto-låsning ved for mange kald | 0,7 s rate limit + session-cache; en indkøbsrunde er ~20-40 kald hver 14. dag |

[repo]: https://github.com/schourode/nemlig
