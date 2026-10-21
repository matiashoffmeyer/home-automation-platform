#!/usr/bin/env python3
"""nemlig_gemini_prompt.py — byg prompten til Gemini ud fra en MÅLING.

    python3 scripts/nemlig_selftest.py --ud /tmp/r.json
    python3 scripts/nemlig_gemini_prompt.py /tmp/r.json > docs/gemini_ordvalg_prompt.md

Hvorfor et script og ikke en håndskrevet fil: listen skal være KORT og kun
indeholde navne der faktisk fejler lige nu. Gensender man de gamle navne,
beder man Gemini omdøbe det der allerede virker — og et "forbedret" navn på
en vare der blev fundet er en ren regression.

Derfor er udvælgelsen snæver med vilje:
  · `ingen_traef`  — varen forsvinder HELT ud af indkøbslisten. Højeste værdi.
  · `usikker` MEN kun dem hvor buddet ligner en stavemåde-forskel, ikke dem
    hvor spørgsmålet er KORREKT. "tørret oregano" mod «Oregano» SKAL blive
    ved med at spørge — tørrede krydderurter er en anden hylde end friske i
    potte, og et menneske skal se byttet. Sådanne navne må ikke i prompten.
"""

import json
import sys

# Ord der gør et spørgsmål KORREKT: varen findes i flere tilstande, og
# forskellen er en ægte vare-skelnen. Bliver de omdøbt væk, køber vi den
# forkerte variant uden at spørge.
_AEGTE_SKELNEN = {
    "toerret",
    "toerrede",
    "syltet",
    "syltede",
    "roeget",
    "roegede",
    "kogt",
    "kogte",
    "hakket",
    "hakkede",
    "revet",
    "revne",
    "frossen",
    "frosne",
    "vegetarisk",
    "vegetariske",
    "fast",
    "blandet",
    "blandede",
}


def normord(s):
    return (s or "").lower().replace("ø", "oe").replace("æ", "ae").replace("å", "aa")


def vaelg(res):
    """→ (gruppe_a, gruppe_b). A = intet brugbart bud. B = bud, men lav score."""
    a, b = [], []
    for x in res:
        st = x.get("status")
        if st not in ("ingen_traef", "usikker"):
            continue
        if any(o in _AEGTE_SKELNEN for o in normord(x["navn"]).split()):
            continue
        bud, score = x.get("produkt"), x.get("score") or 0.0
        if st == "ingen_traef":
            a.append((x["navn"], bud))
        elif score < 0.7:
            b.append((x["navn"], bud))
    return sorted(a), sorted(b)


HOVED = """\
# Prompt til Gemini — ret mad-arkets indkøbsord

Kopier alt herunder ind til Gemini.

---

Du har skriveadgang til mit mad-ark. Jeg vil have dig til at rette **kun**
kolonnen `Ingredienser_struktureret`, så varerne kan findes i Nemlig.com's
søgning. Formatet er uændret: `mængde|enhed|vare;mængde|enhed|vare;…`

**Rør ALDRIG kolonnen `Ingredienser`.** Den er opskriftens egen tekst og skal
blive ved med at lyde som en opskrift. Du må heller ikke ændre mængder eller
enheder — kun selve varenavnet i tredje felt.

## Opgaven

Nedenfor står {i_alt} varenavne fra arket som Nemligs søgning **ikke** kan finde.
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
2. **Drop tilstands-ord der ikke identificerer varen:** frisk, frosne, færdig,
   ukogt, optøet, blød, modne, store, små.
   `frosne ærter` → `ærter` · `blødt smør` → `smør`
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

## Sådan tjekker du

Slå ordet op på nemlig.com. Findes det som et produktnavn, er det rigtigt.
Alt hvad du skriver bliver bagefter verificeret automatisk mod Nemligs API,
og forkerte forslag bliver fanget — men det er hurtigere for os begge hvis du
tjekker undervejs.

## Rapportér til sidst

Giv mig en liste: `gammelt ord → nyt ord` for dem du ændrede, og hvilke du
lod stå fordi du ikke kunne finde varen.

## Varenavnene

Målt mod Nemlig {dato} over alle {antal_raavarer} råvarer i arket. Listen er
bevidst KORT: de navne der virker er skåret væk, for et "forbedret" navn
på en vare der allerede blev fundet er en ren regression. Navne hvor
spørgsmålet er KORREKT (tørret/syltet/hakket osv.) er også skåret væk — dem
skal systemet blive ved med at spørge om.
"""


def main():
    if len(sys.argv) < 3:
        print("brug: nemlig_gemini_prompt.py <selftest.json> <dato>", file=sys.stderr)
        return 2
    data = json.load(open(sys.argv[1]))
    res = data["resultater"]
    a, b = vaelg(res)

    print(HOVED.format(i_alt=len(a) + len(b), dato=sys.argv[2], antal_raavarer=len(res)))
    print(f"### A. Ingen brugbar vare overhovedet ({len(a)})\n")
    print("Disse forsvinder i dag HELT ud af indkøbslisten. Højeste værdi.\n")
    for navn, bud in a:
        if bud:
            print(f"- `{navn}` — søgningen ender på «{bud}», som er noget helt andet")
        else:
            print(f"- `{navn}` — nul svar fra Nemlig")
    print(f"\n### B. Nemlig har varen, men under et andet navn ({len(b)})\n")
    print(
        "Her fandt søgningen faktisk noget, men scoren blev for lav, så\n"
        "systemet tør ikke købe det. Kolonnen efter pilen er hvad Nemlig\n"
        "bød ind med — den er tit tæt på og nogle gange præcis den rigtige\n"
        "vare med butikkens stavemåde. Bekræft eller ret den; du behøver\n"
        "ikke starte forfra.\n"
    )
    for navn, bud in b:
        print(f"- `{navn}` → Nemligs bud: «{bud}»")
    return 0


if __name__ == "__main__":
    sys.exit(main())
