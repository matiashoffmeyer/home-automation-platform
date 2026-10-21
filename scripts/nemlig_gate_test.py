#!/usr/bin/env python3
"""nemlig_gate_test.py — offline regressionstest af matcherens GATES.

Ingen netværk, ingen Nemlig-kald, ingen sheet: kun de rene funktioner der
afgør om et produkt må købes automatisk. Kører på under et sekund, så den kan
køres ved hver ændring i `nemlig_api.py`.

    python3 scripts/nemlig_gate_test.py

Hvorfor den findes: hver eneste gang matcheren er blevet forbedret, er en
TIDLIGERE rettelse blevet rullet tilbage af den nye. 08-31 lukkede
"citrongræs → «Tofu m. citrongræs»", og den skulle nemt kunne åbnes igen af
en sammenlimnings-regel skrevet for "dijonsennep → «Dijon sennep»". Hvert
case herunder er et MÅLT fund fra en selvtest over hele ret-katalogret — ikke
et gæt — og de gamle fund står som vagtposter side om side med de nye.

`nemlig_selftest.py` er stadig den brede test (den kører mod ægte søgesvar og
finder de fejlklasser vi ikke har tænkt på endnu). Denne er den smalle: den
holder fast i det vi ALLEREDE har lært.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nemlig_api as NA  # noqa: E402

# (søgeord, produktnavn, forventet, hvorfor) — forventet=True betyder
# "produktets egen vare blev bedt om", altså kandidat til automatisk køb.
HOVED_CASES = [
    # --- Sammenlimning: dansk skriver i ét ord, Nemlig i to (målt 09-01b) ---
    ("cremefraiche", "Creme fraiche 18% øko.", True),
    ("dijonsennep", "Dijon sennep (stærk)", True),
    ("tacokrydderi", "Taco krydderimix chili - lime", True),
    ("tigerrejer", "Sorte tiger rejer", True),
    ("tortillachips", "Tortilla chips m. salt", True),
    ("romainesalat", "Romaine salat øko", True),
    ("kormasauce", "Korma sauce", True),
    ("cæsardressing", "Caesar dressing", True),
    # --- VAGTPOSTER fra 08-31: alt efter en præposition er INDHOLD, ikke vare.
    # Limningen må aldrig række ud over hoved-regionen, ellers købte vi tofu
    # til en portion citrongræs.
    ("citrongræs", "Tofu m. citrongræs øko.", False),
    ("jordbær", "Smoothie m. jordbær og hindbær", False),
    ("orzo", "Laks og orzo m. timiansauce", False),
    ("teriyakisauce", "Kylling i chili-teriyakisauce", False),
    ("røde linser", "Daal m. røde linser øko.", False),
    # --- VAGTPOST fra 08-31: bøjning ja, sammensætning nej.
    ("smørkage", "Smør 82% øko.", False),
    ("laksefileter", "Laksefilet m. skind", True),
    # --- NYT 09-01b: MODIFIKATOREN må ikke alene opfylde gaten. Dansk
    # substantivfrase er hoved-final, så varen står sidst.
    ("revet parmesan", "Rød cheddar (revet) 30%", False),
    ("revet ingefær", "Rød cheddar (revet) 30%", False),
    ("hakket lammekød", "Hakket spinat øko.", False),
    ("hakket svinekød", "Hakket spinat øko.", False),
    ("blandede rodfrugter", "Blandede fyldte bolcher", False),
    ("blandede svampe", "Blandede fyldte bolcher", False),
    ("brun sovs", "Brun sæbe (flydende)", False),
    ("mørkt øl", "Mørkt rugbrød", False),
    ("mørk øl", "Mørk chokolade 70% øko.", False),
    ("rice cakes", "Rice krispies", False),
    ("ristede hasselnødder", "Ristede løg", False),
    # --- … men de ægte match må ikke ryge med i faldet.
    ("hakket oksekød", "Hakket oksekød 8-12%", True),
    ("ristede løg", "Ristede løg", True),
    ("ristede peanuts", "Peanuts", True),
    ("ristede valnødder", "Valnødder", True),
    ("pillede rejer", "Grønlandske rejer (store)", True),
    ("skært oksekød i tern", "Oksekød i tern", True),
    ("piskefløde", "Piskefløde 38%", True),
    ("fløde", "Piskefløde 38%", True),
]

# relevant_nok = "værd at FORESLÅ som knap", aldrig "værd at købe".
RELEVANT_CASES = [
    # Dansk sammensætning med kerneordet til højre. Alle fem forsvandt HELT
    # før 09-01b: ingen kurv-linje, intet spørgsmål.
    ("mel", "Falke hvedemel øko.", True),
    ("mælk", "Minimælk 0,4% øko.", True),
    ("olie", "Rapsolie", True),
    ("chorizopølse", "Chorizo extra", True),
    ("frosne falafler", "Falafel øko.", True),
    # … men rent skrald skal stadig falde.
    ("paellaris", "Snublejuice IPA", False),
    ("mel", "Coca-Cola", False),
    ("kullerfileter", "COCOHAGEN Cocoa øko.", False),
]

# Parentesen betyder to forskellige ting på de to sider, og må derfor KUN
# fjernes på søge-siden (målt 09-01b: strippet på produkt-siden mistede
# "fine ærter" og "panerede fiskefileter" den eneste variant-skelnen der var).
SOEGORD_CASES = [
    ("bao buns (frost)", ["bao", "buns"]),
    ("ærter og gulerødder (frost)", ["aerter", "og", "guleroedder"]),
    ("flæskesteg (i skiver)", ["flaeskesteg"]),
]

# … mens PRODUKT-siden skal beholde parentesens indhold: den ER skelnen.
PRODUKT_ORD_CASES = [
    ("Ærter (fine)", ["aerter", "fine"]),
    ("Fiskefilet (panerede)", ["fiskefilet", "panerede"]),
    ("Pinjekerner (ristede)", ["pinjekerner", "ristede"]),
    # Nemlig forkorter bindeordet, arket skriver det fuldt ud. Uden
    # udfoldningen tæller arkets "med" som et misset søgeord.
    ("Mandler m. salt", ["mandler", "med", "salt"]),
    ("Svinekam u. ben øko.", ["svinekam", "uden", "ben"]),
]

# Variant-match må ikke falde tilbage til den generiske vare.
VARIANT_CASES = [
    ("fine ærter", "Ærter (fine)", 1.0),
    ("panerede fiskefileter", "Fiskefilet (panerede)", 1.0),
    ("ristede pinjekerner", "Pinjekerner (ristede)", 1.0),
]

# Må produktet lægges i kurven UDEN at spørge? (score >= SIKKER_SCORE OG
# hovedord-gaten passeret). Målt 09-02: 40 af 86 usikre linjer havde den
# rigtige vare valgt og faldt alene på et tilberednings-ord Nemlig umuligt kan
# føre. De fire nederste er vagtposter: de må ALDRIG blive auto-køb.
AUTOKOEB_CASES = [
    ("ristede valnødder", "Valnødder", True),
    ("revet ingefær", "Ingefær", True),
    ("pillede rejer", "Grønlandske rejer", True),
    ("blødt smør", "Smør", True),
    ("ristet rugbrød", "Rugbrød", True),
    # «Bacon i tern» ER bacontern — "i" + formord er en udskæring, ikke indhold.
    ("bacontern", "Bacon i tern", True),
    # "blandet" og "kogt" ligner tilberedning, men ER varer. Ryger de ind i
    # _TILBEREDNING, køber vi radicchio til en blandet salat.
    ("blandet salat", "Radicchio salat", False),
    ("kogt skinke", "Skinke", False),
    # Fund fra 08-31/09-01b der er blevet rullet tilbage før.
    ("revet parmesan", "Rød cheddar (revet) 30%", False),
    ("hakket lammekød", "Hakket spinat øko.", False),
    ("citrongræs", "Tofu m. citrongræs", False),
    ("smørkage", "Smør", False),
    # "m." = "med". De to første ER varen og scorede 0,67 alene på
    # forkortelsen; de to sidste er vagtposter, hvor bindeordet matcher men
    # INDHOLDET er et andet — de skal blive ved med at være spørgsmål.
    ("mandler med salt", "Mandler m. salt", True),
    ("olie med trøffel", "Olie m. hvid trøffel", True),
    ("ravioli med svampe", "Ravioli m. kylling (frisk)", False),
    ("tortellini med ost", "Tortellini m. skinke (frisk)", False),
]

# Tilberednings-ordet er ude af tælleren, men skal stadig RANGERE: den variant
# der faktisk er revet, skal slå den generiske — og begge skal blive over
# SIKKER_SCORE, så fradraget aldrig gør et godt match usikkert.
VARIANT_RANG_CASES = [
    ("revet parmigiano reggiano", "Parmigiano Reggiano revet", "Parmigiano Reggiano øko."),
]

# Verificeret mod Nemlig 09-02. To gæt faldt her ("karry" -> «Karrydressing»
# 1,15/True = auto-køb af dressing; "lime" -> hele frugter til en saft), så
# tabellen står som målte fakta, ikke som oversættelser vi synes er rigtige.
SYNONYM_CASES = [
    # 2026-09-30: "karry krydderi" gav «Grøn karry krydderiblanding» 1,15.
    ("karrypulver", "karry"),
    ("limejuice", "limesaft"),
    ("rygeost", "røgeost"),
    ("parmesan", "parmigiano reggiano"),
    ("revet parmesan", "revet parmigiano reggiano"),
    # Runde 4. Nøglen normaliseres (ø→oe, æ→ae), så et dansk opslag skal
    # stadig ramme — det er dét disse cases holder fast i.
    ("svinemørbrad", "mørbrad af gris"),
    ("æggenudler", "ægnudler"),
    ("tunbøffer", "tun steaks"),
    ("wokgrøntsager", "wokblanding"),
    ("spæde salatblade", "salatmix"),
    ("paellaris", "risotto ris"),
    # Runde 5 (efter Geminis omdøbning). Bindestregen er pointen i den
    # første: `normaliser` gør ETHVERT tegn til et mellemrum, så nøglen får
    # DOBBELT mellemrum og en håndskrevet nøgle rammer den aldrig — med
    # mindre `synonym()` kollapser whitespace. Denne case er vagtposten.
    ("hakket svine- og kalvekød", "hakket grise og kalvekød"),
    ("hakket svine/kalvekød", "hakket grise og kalvekød"),
    ("hakket svinekød", "hakket grisekød"),
    ("pasta penne", "penne"),
    ("majstortilla", "tortilla majs"),
    ("stribet flæsk", "stegeflæsk"),
    # Runde 6 (2026-10-01), målt live: samme vare, butikkens ord.
    ("korianderfrø", "koriander hel"),
    ("kanelstang", "kanel hel"),
    ("hokkaido græskar", "hokkaido"),
    ("mandler i flager", "mandelflager"),
    ("tyttebærmarmelade", "tyttebærsyltetøj"),
    ("fast tofu", "tofu naturel"),
    ("peanut sauce", "satay"),
    # VAGTPOST: "tamarind" rammer «Sojasauce tamari» som en "bøjning".
    ("tamarindpasta", "tamarindpasta"),
    # … og en vagtpost: dem vi BEVIDST lod stå, fordi synonymet ville skifte
    # råvare uden at spørge. Dukker de op i tabellen, er reglen glemt.
    ("kullerfilet", "kullerfilet"),
    ("pastinak", "pastinak"),
    ("kalkunschnitzler", "kalkunschnitzler"),
    ("instant nudler", "instant nudler"),
]


# VALG blandt kandidater (2026-09-30) — FORM-REGLEN og NET FØR ENKELT.
# Kandidaterne er dagens MÅLTE søgesvar (navn, kategori, pakning, enhedspris),
# skåret til felterne vaelg_produkt læser. (søgeord, kandidater, forventet
# navn, forventet på lager).
def _k(navn, kat, pak, pris, label, oeko=False, tilbud=False, lager=True, score=1.15, hoved=True):
    return {
        "id": navn,
        "navn": navn,
        "kategori": kat,
        "pakning": pak,
        "enhedspris": pris,
        "enhedspris_label": label,
        "oeko": oeko,
        "tilbud": tilbud,
        "paa_lager": lager,
        "score": score,
        "hoved": hoved,
        "favorit": False,
    }


_KARRY = [
    _k("Karrydressing", "Fastfood og dressing", "380g", 63.82, "kr./Kg."),
    _k("Karry (madras)", "Krydderier", "90g", 66.11, "kr./Kg.", tilbud=True),
    _k("Rød karrypasta", "Verdensmad", "110g", 108.27, "kr./Kg.", tilbud=True),
    _k("Karry (madras) øko.", "Krydderier", "50g", 343.4, "kr./Kg.", oeko=True),
]
_ROEDBEDER = [
    _k("Rødbeder runde øko.", "Grønt", "1kg", 15.0, "kr./Kg.", oeko=True),
    _k("Rødbeder", "Survarer", "710g", 30.21, "kr./Kg.", tilbud=True),
    _k("Rødbeder lange øko.", "Grønt", "1kg", 20.0, "kr./Kg.", oeko=True),
]
_ROEDBEDER_UDSOLGT = [dict(x, paa_lager=(x["kategori"] == "Survarer")) for x in _ROEDBEDER]
_HVIDLOEG = [
    _k("Hvidløg øko.", "Grønt", "1stk", 5.5, "kr./Stk.", oeko=True, tilbud=True),
    _k("Hvidløg røde/pink", "Grønt", "3stk", 11.67, "kr./Stk."),
    _k("Hvidløg dansk øko.", "Grønt", "1stk", 12.0, "kr./Stk.", oeko=True),
    _k("Hvidløg i net", "Grønt", "200g", 66.65, "kr./Kg.", tilbud=True),
    _k("Hvidløg i chiliolie", "Grøntkonserves", "290g", 98.89, "kr./Kg."),
]
_CITRON = [
    _k("Citron lille øko.", "Frugt og bær", "1stk", 5.0, "kr./Stk.", oeko=True, tilbud=True),
    _k("Citroner øko.", "Frugt og bær", "500g", 36.0, "kr./Kg.", oeko=True, tilbud=True),
    _k("Citron", "Frugt og bær", "1stk", 6.0, "kr./Stk."),
    _k("Citronsaft koncentreret", "Fastfood og dressing", "0.2l", 25.3, "kr./Ltr.", tilbud=True),
]
_LIME = [
    _k("Lime øko.", "Frugt og bær", "1stk", 4.5, "kr./Stk.", oeko=True),
    _k("Limesaft koncentreret", "Fastfood og dressing", "0.2l", 30.25, "kr./Ltr."),
    _k("Citron & Lime læskedrik", "Saft og juice", "0.5l", 41.9, "kr./Ltr."),
]
_BANAN = [
    _k("Banan øko.", "Frugt og bær", "1stk", 4.0, "kr./Stk.", oeko=True),
    _k("Bananer små øko.", "Frugt og bær", "4stk", 18.18, "kr./Kg.", oeko=True),
    _k("Banan", "Frugt og bær", "1stk", 2.5, "kr./Stk."),
    _k("Bananchips øko.", "Tørret frugt, nødder og kerner", "200g", 147.5, "kr./Kg.", oeko=True),
]
_BANAN_UDSOLGT = [dict(x, paa_lager=(x["pakning"] != "4stk")) for x in _BANAN]
VAELG_CASES = [
    ("banan", _BANAN, "Bananer små øko.", True),
    # Bundtet udsolgt → enkeltstyk (øko +60 % er inden for loft 80 %),
    # ALDRIG bananchips fordi de er en vægtpakke.
    ("banan", _BANAN_UDSOLGT, "Banan øko.", True),
    ("karry", _KARRY, "Karry (madras)", True),
    ("karrydressing", _KARRY, "Karrydressing", True),
    ("rødbeder", _ROEDBEDER, "Rødbeder runde øko.", True),
    # Frisk udsolgt → UDSOLGT frisk, ikke et glas i kurven.
    ("rødbeder", _ROEDBEDER_UDSOLGT, "Rødbeder runde øko.", False),
    ("hvidløg", _HVIDLOEG, "Hvidløg i net", True),
    ("citron", _CITRON, "Citroner øko.", True),
    # Intet net → enkeltstyk er fint; en læskedrik er IKKE et net.
    ("lime", _LIME, "Lime øko.", True),
]
# Beder søgeordet selv om den forarbejdede form, må FORM-reglen ikke fjerne
# den. (søgeord, kandidater, antal der skal blive tilbage)
FORM_CASES = [
    ("rødbeder", _ROEDBEDER, 2),
    # Markøren VENDER reglen: glasset vinder når det er i toppen.
    ("syltede rødbeder", _ROEDBEDER, 1),
    ("rødbeder på glas", _ROEDBEDER, 1),
    ("limesaft", _LIME, 2),
    ("lime", _LIME, 1),
    # Katalog-diffen 30/9: den eneste PRÆCISE træffer står på dåse → bliver.
    (
        "hvide bønner",
        [
            _k("Hvide bønner", "Grøntkonserves", "410g", 30.0, "kr./Kg."),
            _k("Bønner grønne øko.", "Grønt", "300g", 60.0, "kr./Kg.", oeko=True, score=0.5),
        ],
        2,
    ),
    (
        "grønne linser",
        [
            _k("Grønne linser øko.", "Grøntkonserves", "400g", 40.0, "kr./Kg.", oeko=True),
            _k(
                "Røde splitlinser øko.",
                "Mos, gryn og bønner",
                "400g",
                45.0,
                "kr./Kg.",
                oeko=True,
                score=0.5,
            ),
        ],
        2,
    ),
]
# Rødkål i gram = glasset, i stk = kålhovedet (ret-arket 30/9).
FORM_ORD_CASES = [
    ("rødkål", "g", "rødkål på glas"),
    ("rødkål", "stk", "rødkål"),
    ("rødbeder", "g", "rødbeder"),
]

# Behov i stk/fed mod en vægt-pakke (stykvægt). (navn, mængde, enhed,
# pakke-beskrivelse, forventet antal)
PAKKE_CASES = [
    # Multipak (2026-10-01): pakken ER 2 × 75 g. Før: 150 g = 2 pakker.
    ("pancetta i tern", 150, "g", "2 x 75 g / Tulip", 1),
    ("rødvin", 200, "ml", "Italien / Veneto / 2022 / 6 x 0,75 l / rødvin", 1),
    ("citroner", 6, "stk", "500 g", 2),
    ("citron", 1, "stk", "500 g", 1),
    ("hvidløg", 2, "fed", "200 g", 1),
    ("hvidløg", 5, "stk", "200 g", 2),
    ("løg", 10, "stk", "1 kg", 2),
    ("bananer", 6, "stk", "4 stk.", 2),
    ("karry", 2, "spsk", "90 g", 1),
]

# Søgeordets egen identitets-bærer (sidste ord før første præposition).
HOVEDORD_CASES = [
    ("revet parmesan", "parmesan"),
    ("skært oksekød i tern", "oksekoed"),
    ("blandede rodfrugter", "rodfrugter"),
    ("bao buns (frost)", "buns"),
]


# =============================================================================
# VARETRÆET (2026-10-01): rå søgesvar-produkter med deres ÆGTE kategori-sti
# (målt i søgecachen samme dag) gennem find_bedste → vaelg_produkt, præcis som
# driften kører dem. Hver case er et fund fra katalog-diffen 1/10.
# =============================================================================
def _p(navn, sti, beskr, pris, label, fav=False, oeko=False, lager=True, brand="", pid=None):
    hoved_, midt, blad = sti.split(" › ")
    return {
        "Id": pid or navn,
        "Name": navn,
        "Description": beskr,
        "Brand": brand,
        "UnitPriceCalc": pris,
        "UnitPriceLabel": label,
        "Price": pris,
        "Favorite": fav,
        "Labels": ["Øko (dansk)"] if oeko else [],
        "Availability": {"IsAvailableInStock": lager},
        "ProductMainGroupName": hoved_,
        "ProductCategoryGroupName": midt,
        "ProductSubGroupName": blad,
    }


_KRYDDERI = "Tørvarer › Krydderier › Krydderier, brev"
_URT = "Frugt og grønt › Grønt › Krydderurter"
TAKSONOMI_CASES = [
    # (søgeord, produkter, forventet Id, hvorfor)
    (
        "kanel",
        [
            _p("Kanelbullar", "Brød › Kager › Specialkager", "300 g", 26.95, "kr./Kg.", fav=True),
            _p("Kanel (stødt)", _KRYDDERI, "40 g", 300.0, "kr./Kg."),
        ],
        "Kanel (stødt)",
        "PRÆCIS: 'kanel…' i et sammensat ord er en smag",
    ),
    (
        "honning",
        [
            _p(
                "Honningtomater i kasse",
                "Frugt og grønt › Grønt › Tomat",
                "1,5 kg",
                70.0,
                "kr./Kg.",
                fav=True,
            ),
            _p(
                "Hverdags honning",
                "Tørvarer › Marmelade, honning og smørepålæg › Honning",
                "450 g",
                56.5,
                "kr./Kg.",
            ),
        ],
        "Hverdags honning",
        "PRÆCIS",
    ),
    (
        "bearnaise",
        [
            _p(
                "Bearnaisesauce",
                "Tørvarer › Saucer og smagsforstærkere › Middagssauce, færdig",
                "250 ml",
                41.3,
                "kr./Kg.",
            ),
            _p(
                "Bearnaise essens",
                "Tørvarer › Saucer og smagsforstærkere › Kryddersauce og essens",
                "30 ml",
                30.0,
                "kr./Kg.",
            ),
            _p(
                "Okse bearnaise",
                "Køl › Færdigretter › Middags- og færdigretter",
                "400 g",
                421.0,
                "kr./Kg.",
            ),
        ],
        "Bearnaisesauce",
        "generisk hale: «-sauce» skifter ikke vare; essens er mere specifik; færdigret ude",
    ),
    (
        "hvidvin",
        [
            _p(
                "P.Maufoux Chardonnay Horizon",
                "Vin og spiritus › Hvidvin › Hvidvin Frankrig",
                "0,75 l",
                149.95,
                "kr./Stk.",
                fav=True,
            ),
            _p(
                "Faina Vinho Blanco",
                "Vin og spiritus › Hvidvin › Hvidvin Portugal",
                "1 l brik",
                29.0,
                "kr./Stk.",
            ),
        ],
        "Faina Vinho Blanco",
        "madlavningsvin: favorit-flasken er et drikke-valg",
    ),
    (
        "rødvin",
        [
            _p(
                "Baron de Lestac Rouge",
                "Vin og spiritus › Rødvin › Rødvin Frankrig",
                "0,75 l",
                114.95,
                "kr./Stk.",
            ),
            _p(
                "Ca del Vallo Ripasso",
                "Vin og spiritus › Rødvin › Rødvin Italien",
                "6 x 0,75 l / rødvin",
                99.95,
                "kr./Stk.",
            ),
        ],
        "Baron de Lestac Rouge",
        "en kasse prissat pr. flaske er ikke én flaske",
    ),
    (
        "hakket spinat",
        [
            _p(
                "Hakket spinat øko.",
                "Frost › Frugt og grønt, frost › Grøntsager, frost",
                "400 g",
                58.13,
                "kr./Kg.",
                fav=True,
                oeko=True,
            ),
            _p(
                "Hakket spinat",
                "Frost › Frugt og grønt, frost › Grøntsager, frost",
                "450 g",
                13.27,
                "kr./Kg.",
            ),
        ],
        "Hakket spinat",
        "øko-loftet (80 %) gælder også en øko-FAVORIT — referencen er hele feltet",
    ),
    (
        "pepperoni",
        [
            _p(
                "Pizza pepperoni",
                "Frost › Middagstilbehør og færdigretter › Pizza, frost",
                "350 g",
                103.2,
                "kr./Kg.",
            ),
            _p("Pepperoni", "Køl › Bacon, pølser og toppings › Toppings", "80 g", 113.7, "kr./Kg."),
        ],
        "Pepperoni",
        "IDENTITETS-VETO: typeordet (pizza) står FØR søgeordet",
    ),
    (
        "muslinger",
        [
            _p(
                "Muslinger i vand",
                "Tørvarer › Fiskekonserves › Fiskekonserves, øvrig",
                "120 g",
                247.8,
                "kr./Kg.",
            ),
            _p(
                "Blåmuslinger",
                "Kød og fisk › Fisk og skaldyr, fersk › Skaldyr, fersk",
                "1 kg",
                46.95,
                "kr./Kg.",
            ),
            _p(
                "Kammuslinger",
                "Kød og fisk › Fisk og skaldyr, fersk › Skaldyr, fersk",
                "250 g",
                599.8,
                "kr./Kg.",
            ),
        ],
        "Blåmuslinger",
        "dåse er forarbejdet; to slags muslinger → billigst",
    ),
    (
        "kødboller",
        [
            _p(
                "Kødboller",
                "Frost › Middagstilbehør og færdigretter › Suppeboller, frost",
                "500 g",
                64.3,
                "kr./Kg.",
            ),
            _p(
                "Kødboller (plantebaseret)",
                "Kød og fisk › Køderstatning › Køderstatning, frost",
                "300 g",
                211.3,
                "kr./Kg.",
            ),
        ],
        "Kødboller",
        "Frost-SPANDEN er ikke en færdigret; plantebaseret er mere specifik",
    ),
    (
        "rejer",
        [
            _p(
                "Grønlandske rejer (store)",
                "Frost › Fisk og skaldyr, frost › Rejer, frost",
                "500 g",
                200.0,
                "kr./Kg.",
            ),
            _p(
                "Rejer m. ramsløg",
                "Frost › Fisk og skaldyr, frost › Rejer, frost",
                "150 g",
                180.0,
                "kr./Kg.",
            ),
        ],
        "Grønlandske rejer (store)",
        "MEST GENERISK: fyld efter «m.» er mere specifikt end et ord",
    ),
    (
        "agurk",
        [
            _p("Agurk", "Frugt og grønt › Grønt › Agurk", "1 stk", 10.0, "kr./Stk."),
            _p("Skole agurker", "Frugt og grønt › Grønt › Agurk", "1 stk", 4.33, "kr./Stk."),
        ],
        "Agurk",
        "MEST GENERISK: kr/stk for en snackagurk er ikke en agurk",
    ),
    (
        "basilikum",
        [
            _p("Basilikum", _KRYDDERI, "10 g", 198.0, "kr./Kg.", pid="tørret"),
            _p("Basilikum", _URT, "1 potte", 500.0, "kr./Kg.", pid="frisk"),
        ],
        "frisk",
        "FRAVÆRENDE FORM: uden 'tørret' er krydderurten svaret",
    ),
    (
        "tørret oregano",
        [
            _p("Oregano", _KRYDDERI, "10 g", 300.0, "kr./Kg.", pid="tørret"),
            _p("Oregano stor øko.", _URT, "1 potte", 40.0, "kr./Stk.", oeko=True, pid="frisk"),
        ],
        "tørret",
        "FORM-ORD: stien bekræfter 'tørret'",
    ),
    (
        "gurkemeje",
        [
            _p(
                "Gurkemeje",
                "Tørvarer › Krydderier › Krydderier, glas",
                "40 g",
                400.0,
                "kr./Kg.",
                pid="pulver",
            ),
            _p(
                "Gurkemejerod øko.",
                "Frugt og grønt › Grønt › Fin grønt",
                "100 g",
                150.0,
                "kr./Kg.",
                oeko=True,
                pid="rod",
            ),
        ],
        "pulver",
        "kun en KRYDDERURT slår det tørrede — ikke en rod",
    ),
    (
        "karry",
        [
            _p(
                "Karry",
                "Tørvarer › Krydderier › Krydderiblandinger, glas",
                "17 g",
                838.0,
                "kr./Kg.",
            ),
            _p(
                "Frisk rød karrypasta (stærk)",
                "Frugt og grønt › Grønt › Fin grønt",
                "50 g",
                400.0,
                "kr./Kg.",
            ),
        ],
        "Karry",
        "VAGTPOST: første FRAVÆRENDE FORM smed al Tørvarer ud",
    ),
    (
        "vegetariske frikadeller",
        [
            _p(
                "Frikadeller",
                "Frost › Middagstilbehør og færdigretter › Frikadeller og kødboller, frost",
                "600 g",
                80.0,
                "kr./Kg.",
            ),
            _p(
                "Grøntsagsfrikadeller",
                "Frost › Middagstilbehør og færdigretter › Frikadeller og kødboller, frost",
                "400 g",
                95.0,
                "kr./Kg.",
            ),
        ],
        "Grøntsagsfrikadeller",
        "ORD-ÆKVIVALENS: vegetarisk ↔ grøntsags-",
    ),
    (
        "andebryst",
        [
            _p(
                "Andebryst",
                "Dyremad og tilbehør › Hund › Hundegodbidder",
                "100 g",
                209.75,
                "kr./Kg.",
            ),
            _p(
                "Confiteret andebryst",
                "Kød og fisk › Fjerkræ, fersk › And, fersk",
                "300 g",
                295.2,
                "kr./Kg.",
            ),
        ],
        "Confiteret andebryst",
        "IKKE MAD: hundegodbidder",
    ),
    # Re-audit 2026-10-01 af de 81 ændrede valg:
    (
        "ferskner",
        [
            _p("Ferskner", "Konfekture › Poseslik › Vingummi", "100 g", 120.0, "kr./Kg."),
            _p(
                "Halve ferskner i sukkerlage",
                "Tørvarer › Frugt og dessert › Frugtkonserves",
                "410 g",
                40.0,
                "kr./Kg.",
            ),
        ],
        "Halve ferskner i sukkerlage",
        "slik i pose er aldrig en ingrediens (dåsen spørges om, se FORM_ADVARSEL)",
    ),
    (
        "hamburgerryg",
        [
            _p(
                "Røget Hamburgerryg",
                "Kød og fisk › Grisekød, fersk › Grisekød røgvarer, fersk",
                "1 kg",
                75.5,
                "kr./Kg.",
            ),
            _p("Hamburgerryg", "Køl › Pålæg › Pålæg i Skiver", "100 g", 159.5, "kr./Kg."),
        ],
        "Røget Hamburgerryg",
        "'røget' er en form, ikke et ekstra ord",
    ),
    (
        "græskar",
        [
            _p(
                "Halloween græskar stor",
                "Frugt og grønt › Grønt › Grov grønt",
                "1 stk",
                15.0,
                "kr./Kg.",
            ),
            _p(
                "Græskar Crown Prince øko.",
                "Frugt og grønt › Grønt › Grov grønt",
                "1 stk",
                25.0,
                "kr./Kg.",
                oeko=True,
            ),
        ],
        "Græskar Crown Prince øko.",
        "pynt-græskar er ikke spisegræskar",
    ),
    (
        "brun sovs",
        [
            _p(
                "Sovsejævner (brun)",
                "Tørvarer › Saucer og smagsforstærkere › Jævner",
                "250 g",
                115.8,
                "kr./Kg.",
            ),
            _p(
                "Brun sauce",
                "Tørvarer › Saucer og smagsforstærkere › Middagssauce, færdig",
                "500 ml",
                41.3,
                "kr./Kg.",
            ),
        ],
        "Brun sauce",
        "ORD-ÆKVIVALENS sovs ↔ sauce — også i hovedord-gaten",
    ),
]

# Spørg frem for at købe: kun en færdigret / et syltetøj / en saft fundet.
FORM_ADVARSEL_CASES = [
    (
        "svinekæber",
        _p(
            "Svinekæber", "Køl › Færdigretter › Middags- og færdigretter", "800 g", 160.0, "kr./Kg."
        ),
        True,
    ),
    (
        "rabarber",
        _p("Rabarber saft", "Drikke › Saft og juice › Saft", "0,5 l", 60.0, "kr./Ltr."),
        True,
    ),
    (
        "græskar",
        _p(
            "Græskarsuppe m. hokkaido",
            "Frost › Middagstilbehør og færdigretter › Supper, frost",
            "500 g",
            80.0,
            "kr./Kg.",
        ),
        True,
    ),
    (
        "hakkede tomater",
        _p(
            "Hakkede tomater",
            "Tørvarer › Grøntkonserves › Tomater, hakkede og flåede",
            "400 g",
            15.9,
            "kr./Kg.",
        ),
        False,
    ),
    (
        "halve ferskner i sukkerlage",
        _p(
            "Halve ferskner i sukkerlage",
            "Tørvarer › Frugt og dessert › Frugtkonserves",
            "410 g",
            40.0,
            "kr./Kg.",
        ),
        False,
    ),
]

# hoved_traef med varetræet: identitets-vetoet og dets undtagelser.
TAKSONOMI_HOVED_CASES = [
    ("rabarber", "Skyr rabarber- og vaniljesmag", "Mejeri › Yoghurt og syrnet › Skyr", False),
    (
        "pepperoni",
        "Pizza pepperoni",
        "Frost › Middagstilbehør og færdigretter › Pizza, frost",
        False,
    ),
    ("sriracha", "Sriracha chilisauce", "Tørvarer › Saucer og smagsforstærkere › Chilisauce", True),
    (
        "roti",
        "Fladbrød Roti Paratha",
        "Frost › Brød og dej, frost › Madbrød og fastfood, frost",
        True,
    ),
    ("basilikum", "Basilikum Grøn øko.", "Frugt og grønt › Grønt › Krydderurter", True),
    ("chorizo", "Chorizo i skiver øko.", "Køl › Pålæg › Pålæg i Skiver", True),
    ("kruspersille", "Persille krus øko.", "Frugt og grønt › Grønt › Krydderurter", True),
]


def main():
    fejl = []

    for soegt, prods, forv, hvorfor in TAKSONOMI_CASES:
        tr = NA.find_bedste(prods, soegt)
        v, grund, _r = NA.vaelg_produkt(
            NA.kun_relevante(tr, soegt),
            80.0,
            True,
            soegt=soegt,
            favorit_loft_pct=NA.FAVORIT_LOFT_PCT,
        )
        if not v or v["id"] != forv:
            fejl.append(
                f"varetræ({soegt!r}) = {v and v['id']!r} ({grund}), forventet {forv!r} — {hvorfor}"
            )
    for soegt, prod, forv in FORM_ADVARSEL_CASES:
        x = NA.find_bedste([prod], soegt)[0]
        f = bool(NA.form_advarsel(x, soegt))
        if f != forv:
            fejl.append(f"form_advarsel({soegt!r}, {prod['Name']!r}) = {f}, forventet {forv}")
    for soegt, navn, sti, forv in TAKSONOMI_HOVED_CASES:
        p = _p(navn, sti, "", 1.0, "kr./Kg.")
        f = NA.hoved_traef(soegt, navn, NA.taksonomi(p))
        if f != forv:
            fejl.append(f"hoved_traef({soegt!r}, {navn!r}, varetræ) = {f}, forventet {forv}")

    for soegt, navn, forv in HOVED_CASES:
        f = NA.hoved_traef(soegt, navn)
        if f != forv:
            fejl.append(f"hoved_traef({soegt!r}, {navn!r}) = {f}, forventet {forv}")

    for soegt, navn, forv in RELEVANT_CASES:
        f = NA.relevant_nok(soegt, navn)
        if f != forv:
            fejl.append(f"relevant_nok({soegt!r}, {navn!r}) = {f}, forventet {forv}")

    for raat, forv in SOEGORD_CASES:
        f = NA.soegord_af(raat)
        if f != forv:
            fejl.append(f"soegord_af({raat!r}) = {f}, forventet {forv}")

    for raat, forv in PRODUKT_ORD_CASES:
        f = NA.ord_af(raat)
        if f != forv:
            fejl.append(f"ord_af({raat!r}) = {f}, forventet {forv}")

    for soegt, navn, mindst in VARIANT_CASES:
        f = NA.lighed(soegt, navn)
        if f < mindst:
            fejl.append(f"lighed({soegt!r}, {navn!r}) = {f:.2f}, forventet >= {mindst}")

    for soegt, navn, forv in AUTOKOEB_CASES:
        f = NA.lighed(soegt, navn) >= NA.SIKKER_SCORE and NA.hoved_traef(soegt, navn)
        if f != forv:
            fejl.append(f"auto-køb({soegt!r}, {navn!r}) = {f}, forventet {forv}")

    for soegt, bedre, ringere in VARIANT_RANG_CASES:
        hb, hr = NA.lighed(soegt, bedre), NA.lighed(soegt, ringere)
        if not (hb > hr >= NA.SIKKER_SCORE):
            fejl.append(
                f"variant-rang({soegt!r}): {bedre!r}={hb:.3f} skal være "
                f"> {ringere!r}={hr:.3f} >= {NA.SIKKER_SCORE}"
            )

    for raat, forv in SYNONYM_CASES:
        f = NA.synonym(raat)
        if f != forv:
            fejl.append(f"synonym({raat!r}) = {f!r}, forventet {forv!r}")

    for raat, forv in HOVEDORD_CASES:
        f = NA.hovedord(raat)
        if f != forv:
            fejl.append(f"hovedord({raat!r}) = {f!r}, forventet {forv!r}")

    for soegt, kand, forv, lager in VAELG_CASES:
        v, grund, _r = NA.vaelg_produkt([dict(x) for x in kand], 80.0, True, soegt=soegt)
        if not v or v["navn"] != forv or v["paa_lager"] != lager:
            fejl.append(
                f"vaelg_produkt({soegt!r}) = {v and v['navn']!r} "
                f"(lager {v and v['paa_lager']}, {grund}), "
                f"forventet {forv!r} (lager {lager})"
            )
    for soegt, kand, forv in FORM_CASES:
        n_tilbage = len(NA.form_filter(kand, soegt))
        if n_tilbage != forv:
            fejl.append(f"form_filter({soegt!r}) beholdt {n_tilbage}, forventet {forv}")
    for navn, enh, forv in FORM_ORD_CASES:
        if NA.form_ord(navn, enh) != forv:
            fejl.append(
                f"form_ord({navn!r}, {enh!r}) = {NA.form_ord(navn, enh)!r}, forventet {forv!r}"
            )
    for navn, m, e, beskr, forv in PAKKE_CASES:
        a, why = NA.antal_pakker(m, e, {"Description": beskr}, navn=navn)
        if a != forv:
            fejl.append(
                f"antal_pakker({navn!r}, {m} {e}, {beskr!r}) = {a} ({why}), forventet {forv}"
            )
    i_alt = (
        len(TAKSONOMI_CASES)
        + len(FORM_ADVARSEL_CASES)
        + len(TAKSONOMI_HOVED_CASES)
        + len(VAELG_CASES)
        + len(PAKKE_CASES)
        + len(FORM_CASES)
        + len(FORM_ORD_CASES)
        + len(HOVED_CASES)
        + len(RELEVANT_CASES)
        + len(SOEGORD_CASES)
        + len(PRODUKT_ORD_CASES)
        + len(VARIANT_CASES)
        + len(HOVEDORD_CASES)
        + len(AUTOKOEB_CASES)
        + len(VARIANT_RANG_CASES)
        + len(SYNONYM_CASES)
    )
    if fejl:
        print(f"FEJL: {len(fejl)} af {i_alt} gate-cases fejlede:")
        for f in fejl:
            print(f"   {f}")
        return 1
    print(f"OK: alle {i_alt} gate-cases bestaar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
