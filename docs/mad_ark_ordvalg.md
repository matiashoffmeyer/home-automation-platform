# Ordvalg i mad-arket — så varerne kan findes hos Nemlig

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

**Til den der fylder ret-arket ud (Gemini, eller et menneske).** Reglerne her
handler kun om kolonnen **`Ingredienser_struktureret`** (`mængde|enhed|vare;…`),
som maskinen læser. Kolonnen **`Ingredienser`** er opskriftens egen tekst og
skal blive ved med at lyde som en opskrift — den røres aldrig af disse regler.

Baggrunden er målt, ikke gættet: matcheren blev kørt mod alle 495 unikke
råvarer i de 406 retter, og de mønstre der fejlede står nedenfor.

---

## Den korte version

> Skriv varen som **Nemlig ville kalde den i butikken** — ikke som den lyder i
> en opskrift.

`800|g|hakkede tomater` ✅ &nbsp;&nbsp; `800|g|mosede tomater` ❌

---

## 1. Brug butikkens ord, ikke køkkenets

Samme vare, forskelligt sprog. Disse er set i arket:

| I opskriften | Hos Nemlig |
|---|---|
| mosede tomater | **hakkede tomater** |
| syltede agurker | **cornichoner** |
| blandet salat | **salatmix** |
| færdigstegte flæskesvær | **flæskesvær** |

## 2. Drop tilstands-ord der ikke identificerer varen

`frisk`, `friske`, `frosne`, `færdig`, `ukogt`, `optøet`, `afpudset`,
`store`, `små`, `ferske`.

`400|g|ukogt quinoa` → `400|g|quinoa` &nbsp;·&nbsp;
`1|stk|færdig pizzadej` → `1|stk|pizzadej`

**Undtagelser der SKAL blive stående**, fordi de er en anden vare i butikken:
`hakket` (oksekød), `revet` (ost), `røget`, `syltet`, `tørret`.

## 3. Ental frem for flertal — men kun når Nemlig gør det

⚠️ **Tjek varen først.** Reglen gælder ikke blindt: Nemlig sælger
`kartofler`, `søde kartofler` og `hakkede tomater` i FLERTAL, og en
ental-form dér koster hele matchet (målt: `kartofler` 1,15 → `kartoffel`
0,00, på 73 retter).

Grunden til reglen: dansk flertal kan elidere et bogstav (`falafel` →
`falafler`), og så kan ingen algoritme se at det er samme ord. Men mange
grøntsager sælges netop i flertal, så **slå varen op før du bøjer den**.

`400|g|laksefileter` → `400|g|laksefilet` ✅
&nbsp;&nbsp; `800|g|kartofler` → `800|g|kartoffel` ❌

## 4. Skriv sammensatte ord som butikken gør

Nemlig deler nogle ord og limer andre sammen. Rammer du forkert, findes varen
ikke — søgningen matcher ikke lange danske sammensætninger.

`dijonsennep` → **dijon sennep** &nbsp;·&nbsp;
`chorizopølse` → **chorizo** &nbsp;·&nbsp;
`cantaloupemelon` → **cantaloupe melon**

## 5. Undgå ord der peger på en anden vareart

Det farligste mønster, fordi det giver et match med **fuld score** på den
forkerte vare. Nemlig-navne har formen «vare … m./med tilbehør», og alt efter
præpositionen beskriver hvad der er *i* varen:

- `citrongræs` fandt «Tofu m. citrongræs» → det er **tofu**
- `jordbær` fandt «Smoothie m. jordbær og hindbær» → det er **en smoothie**

Skriv varen så præcist at den kan stå alene som et produktnavn.

## 6. En høj score er ikke et bevis

Det farligste er ikke at ramme forbi — det er at ramme noget forkert med fuld
sikkerhed. Da `cajunkrydderi`, `enchiladakrydderi` og `fajitakrydderi` alle
blev forkortet til `krydderiblanding`, scorede alle tre 1,15 — mod det samme
produkt. Spørg altid: *er den vare jeg fandt stadig den mad jeg skrev?*

## 7. Vin, krydderier og mængder

- **Vin:** skriv `hvidvin` eller `rødvin`. Ordet står ikke i flaskens navn, men
  i Nemligs kategori, og den slår systemet op.
- **Krydderier og fed hvidløg** (`spsk`, `tsk`, `fed`, `knsp`) kan ikke regnes
  om til pakker. Der købes 1 pakke, og det er med vilje — et gæt ville ramme
  forkert i begge retninger. Skriv gerne mængden alligevel; den bruges i
  opskriften.

---

## Hvis du er i tvivl

Slå ordet op på nemlig.com. Findes det som et produktnavn, er det det rigtige
ord til `Ingredienser_struktureret`.

Systemet er bygget til at spørge frem for at gætte: en vare der ikke kan
parres sikkert havner i en notifikation med de faktiske produkter som valg,
og svaret huskes permanent. Reglerne her handler om at gøre den bunke lille —
ikke om at undgå den helt.

**Værktøj:** `python3 scripts/nemlig_ordbog.py` foreslår rettelser ud fra
faktiske Nemlig-opslag og kan skrive dem med `--apply`. Den rører kun råvarer
der beviseligt fejler, og verificerer hvert forslag før det skrives.
