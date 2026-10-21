# Prompt til Gemini — ret mad-arkets indkøbsord

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Kopier alt herunder ind til Gemini.

---

Du har skriveadgang til mit mad-ark. Jeg vil have dig til at rette **kun**
kolonnen `Ingredienser_struktureret`, så varerne kan findes i Nemlig.com's
søgning. Formatet er uændret: `mængde|enhed|vare;mængde|enhed|vare;…`

**Rør ALDRIG kolonnen `Ingredienser`.** Den er opskriftens egen tekst og skal
blive ved med at lyde som en opskrift. Du må heller ikke ændre mængder eller
enheder — kun selve varenavnet i tredje felt.

## Opgaven

Nedenfor står 37 varenavne fra arket som Nemligs søgning **ikke** kan finde.
For hvert af dem: skriv det navn Nemlig ville bruge i butikken, og opdater
alle de rækker hvor varen optræder.

Listen er delt i to. **Gruppe A** finder ingenting og forsvinder helt ud af
indkøbslisten — dem betaler det sig mest at få rettet. **Gruppe B** har fået
et bud fra Nemlig med i listen; ofte ER det den rigtige vare, bare med
butikkens stavemåde, så dér skal du mest bekræfte eller justere.

Kan du ikke finde varen på nemlig.com, så **lad den stå uændret**. Et gæt er
værre end at lade den være — systemet spørger mig selv om dem det er i tvivl
om, og det er en fin udgang.

## Reglerne

1. **Butikkens ord, ikke køkkenets.** `mosede tomater` → `hakkede tomater`.
   Nemlig siger **gris**, ikke svin: `svinekød i tern` → `grisekød i tern`.
2. **Drop tilstands-ord der ikke identificerer varen:** frisk, færdig,
   ukogt, optøet, blød, modne, store, små.
   `blødt smør` → `smør`
   **Men BEHOLD `frosne` og `tørret`** (ændret 2026-10-01): systemet læser
   formen i Nemligs kategori (Frost / Tørvarer) og vælger den rigtige variant
   ud fra ordet. `frosne ærter` bliver stående.
3. **BEHOLD ord der ER varen.** Det er den vigtigste regel:
   `hakket` (oksekød), `revet` (ost), `røget`, `syltet`, `tørret`, `ristet`.
   Syltede rødbeder er en anden vare end rødbeder. Fjerner du ordet, skifter
   du mad.
4. **Ental frem for flertal:** `torskefileter` → `torskefilet`
5. **Skriv sammensatte ord som Nemlig gør, og med VAREN SIDST.** De deler
   nogle og limer andre, og rækkefølgen betyder noget:
   `dijonsennep` → `dijon sennep` · `majstortilla` → `tortilla majs` ·
   `cantaloupemelon` → `cantaloupe melon`
6. **Aldrig et generisk ord alene.** `halloumi ost` må IKKE blive `ost`,
   `oksekød i strimler` må IKKE blive `strimler`, `kogte brune linser` må
   IKKE blive `linser`. Varen skal stadig kunne stå som et produktnavn.
7. **Men heller ikke et overflødigt kategori-ord FORAN.** Nemlig kalder den
   «Penne rigate», ikke «Pasta penne» — det ekstra ord tæller som et misset
   søgeord. `pasta penne` → `penne` · `shiitake svampe` → `shiitake`
8. **Aldrig en forkortelse.** `bacontern` → `bacon i tern`, ikke `baco`.
9. **Krydderiblandinger:** Nemlig kalder dem typisk `krydderiblanding <navn>`.
   `cajunkrydderi` → `krydderiblanding cajun`
10. **Brug husets allerede målte ord** (2026-10-01, tabellen
    `ARK_OVERSAETTELSER` i `scripts/nemlig_ordbog.py` — en ny ret med det gamle
    ord oversættes også ved næste kørsel af `--oversaet --apply`):
    `orzo` → `risoni` · `svinekæber` → `grisekæber` · `mørk(t) øl` → `porter` ·
    `lyst brød`/`ristet brød` (skiver) → `toastbrød` · `hvid fisk`/`kuller` →
    `torskefilet` · `griseslag` → `svinebryst` · `wontonpapir` → `gyoza dej` ·
    `soja fars` → `plantefars` · `sweet chilisauce` → `sød chilisauce` ·
    `stjerne anis` → `stjerneanis` · `romainesalat` → `hjertesalat` ·
    `brune linser` → `grønne linser` · `gule linser` → `røde linser`

## Sådan tjekker du

Slå ordet op på nemlig.com. Findes det som et produktnavn, er det rigtigt.
Alt hvad du skriver bliver bagefter verificeret automatisk mod Nemligs API,
og forkerte forslag bliver fanget — men det er hurtigere for os begge hvis du
tjekker undervejs.

## Rapportér til sidst

Giv mig en liste: `gammelt ord → nyt ord` for dem du ændrede, og hvilke du
lod stå fordi du ikke kunne finde varen.

## Varenavnene

Målt mod Nemlig 2026-09-02 over alle 440 råvarer i arket. Listen er
bevidst KORT: de navne der virker er skåret væk, for et "forbedret" navn
på en vare der allerede blev fundet er en ren regression. Navne hvor
spørgsmålet er KORREKT (tørret/syltet/hakket osv.) er også skåret væk — dem
skal systemet blive ved med at spørge om.

### A. Ingen brugbar vare overhovedet (5)

Disse forsvinder i dag HELT ud af indkøbslisten. Højeste værdi.

- `kuller` — søgningen ender på «COCOHAGEN Cocoa øko.», som er noget helt andet
- `pastinak` — søgningen ender på «Rodfrugtmix øko.», som er noget helt andet
- `pastinakker` — søgningen ender på «Rodfrugtmix øko.», som er noget helt andet
- `tamarindpasta` — søgningen ender på «Marinade m. daddel», som er noget helt andet
- `tyttebærmarmelade` — nul svar fra Nemlig

### B. Nemlig har varen, men under et andet navn (32)

Her fandt søgningen faktisk noget, men scoren blev for lav, så
systemet tør ikke købe det. Kolonnen efter pilen er hvad Nemlig
bød ind med — den er tit tæt på og nogle gange præcis den rigtige
vare med butikkens stavemåde. Bekræft eller ret den; du behøver
ikke starte forfra.

- `balsamico glace` → Nemligs bud: «Balsamico»
- `brune linser` → Nemligs bud: «Røde splitlinser øko.»
- `ferskner i tern` → Nemligs bud: «Halve ferskner i sukkerlage»
- `fiskepinde` → Nemligs bud: «Snack fiskefilet (panerede)»
- `instant nudler` → Nemligs bud: «Risnudler»
- `kalkunschnitzel` → Nemligs bud: «Kalkunspegepølse»
- `kalveskank` → Nemligs bud: «Kalvelever i skiver»
- `karrypulver` → Nemligs bud: «Karry (madras)»
- `kecap manis (sød soja)` → Nemligs bud: «Sojasauce ketjap manis»
- `kewpie mayonnaise` → Nemligs bud: «Mayonnaise»
- `krydderiblanding taco` → Nemligs bud: «Tacoskaller»
- `lammeskank` → Nemligs bud: «Lammekølle m. hvidløg»
- `mandler i flager` → Nemligs bud: «Mandler»
- `mørk øl` → Nemligs bud: «Tuborg Classic (dåse)»
- `mørkt øl` → Nemligs bud: «Tuborg Classic (dåse)»
- `oksekød i wokstrimler` → Nemligs bud: «Hakket oksekød 8-12% øko.»
- `paneng karrypasta` → Nemligs bud: «Frisk panang karrypasta (sød)»
- `peanut sauce` → Nemligs bud: «Hoisin sauce»
- `ravioli med svampe` → Nemligs bud: «Ravioli m. kylling (frisk)»
- `ribeye bøffer` → Nemligs bud: «Ribeye steak»
- `rice cakes` → Nemligs bud: «Dumle Corn Cakes»
- `rød dressing` → Nemligs bud: «Creme fraiche dressing»
- `skinkekød i strimler` → Nemligs bud: «Kalkunbryst i strimler»
- `soja fars` → Nemligs bud: «Sojasauce»
- `stjerne anis` → Nemligs bud: «Sojasauce ketjap manis»
- `svinekød i strimler` → Nemligs bud: «Hakket grisekød 8-12%»
- `svineslag med svær` → Nemligs bud: «Flæskesteg m. ridset svær»
- `sweet chili sauce` → Nemligs bud: «Chili sauce m. hvidløg»
- `tom yum pasta` → Nemligs bud: «Cremet Tom Yum kylling»
- `tortellini med ost` → Nemligs bud: «Tortellini m. skinke (frisk)»
- `vildtkød` → Nemligs bud: «Luksus vildfuglefrø»
- `ærter og gulerod` → Nemligs bud: «Ærter og gulerødder»
