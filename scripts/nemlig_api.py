#!/usr/bin/env python3
"""nemlig_api.py — uofficiel Nemlig.com-klient til indkøbslisten.

API-fladen er reverse-engineeret (jf. github.com/schourode/nemlig) og verificeret
live 2026-08-31. Den er LILLE — fire kald bærer hele integrationen:

    POST /webapi/login/login            {Username, Password, ...}  -> sætter .ASPXAUTH
    GET  /webapi/s/0/1/0/Search/Search  ?query=&take=              -> produkter + lager
    GET  /webapi/basket/GetBasket                                  -> nuværende kurv
    POST /webapi/basket/AddToBasket     {productId, quantity}      -> sæt antal

INVARIANT: `quantity` i AddToBasket er ABSOLUT, ikke et delta. quantity=0
FJERNER linjen (verificeret 2026-08-31). Kalder man den to gange med 1, står der
stadig 1 — ikke 2. Al "læg X i kurven"-logik skal derfor sende det ØNSKEDE
slut-antal, ikke tilvæksten. Det gør operationen idempotent, og er grunden til
at en gentaget kørsel af indkøbslisten ikke fordobler kurven.

INVARIANT: lagerstatus koster IKKE et ekstra kald — den ligger allerede i
søgesvaret som `Availability.IsAvailableInStock`. Slå den aldrig op separat.

Secrets i /config/secrets.yaml:
    nemlig_user: "…"
    nemlig_password: "…"

Runtime-filer (uden for git):
    /config/.nemlig_session.json   cookies, så vi ikke logger ind ved hvert kald
    /config/.nemlig_varer.json     vare-navn -> produkt-id (den lærte parring)

CLI:
    --ping                     verificér login
    --search "hakket oksekød"  vis kandidater m. id/pris/lager
    --basket                   vis kurven
    --add ID --antal N         sæt antal (0 = fjern)
    --ryd                      tøm kurven
"""

import argparse
import http.cookiejar
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

import ha_secrets

API_ROOT = "https://www.nemlig.com/webapi"
SESSION_FILE = "/config/.nemlig_session.json"
VARER_FILE = "/config/.nemlig_varer.json"

# Nemlig svarer afvisende på en tom/robot-agtig UA. En almindelig browser-streng
# er ikke et forsøg på at skjule os — det er dét format serveren accepterer.
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Sessionen holder i praksis timer, men udløbet kan ikke aflæses i cookien.
# 6 timer er konservativt: et for tidligt udløb koster kun ét ekstra login.
SESSION_MAX_ALDER = 6 * 3600
RATE_LIMIT_S = 0.7  # schourode brugte 1,0 — vi er lidt hurtigere, stadig høfligt

# Under denne score lægger vi IKKE varen i kurven af os selv. Målt 2026-08-31:
# "pasta" gav 0,00 mod "Penne rigate" — et relevant produkt, men intet i navnet
# bekræfter det, og en forkert vare i kurven opdages først ved leveringen.
# Usikre linjer skal spørges om, ikke gættes.
# Opskriftens ord -> butikkens ord. Ren oversættelse, ikke en præference:
# begge sider betyder nøjagtig samme vare, Nemlig kalder den bare noget andet.
#
# ⚠️ NØGLEN er normaliseret (æøå -> ae/oe/aa, småt, uden tegn) fordi opslaget
# sker på den form. VÆRDIEN skal derimod være RIGTIGT DANSK — den sendes
# direkte til Nemligs søgning, og "flaeskesvaer" giver nul brugbare træf
# (målt: den fandt en alkoholfri øl). Udvid frit; det er billigere end at
# lære matcheren dansk madsprog.
SYNONYMER = {
    "mosede tomater": "hakkede tomater",
    "syltede agurker": "cornichoner",
    "blandet salat": "salatmix",
    "faerdigstegte flaeskesvaer": "flæskesvær",
    # Målt 2026-09-02 over 444 råvarer: i 21 af de 28 "ingen træf" LÅ den
    # rigtige vare i svaret og blev kasseret på stavemåden alene. De er ægte
    # oversættelser (samme vare, andet ord), ikke præferencer — derfor her og
    # ikke som en regel i matcheren, hvor de ville skulle gættes strukturelt.
    "rygeost": "røgeost",
    "tatarsauce": "tartarsauce",
    "pomfritter": "pommes frites",
    "toastbroed": "hvedetoast",
    # Verificeret mod Nemlig 2026-09-02, og to af mine egne bud faldt her:
    # "karry" alene rammer «Karrydressing» med 1,15/hoved=True = auto-køb af
    # en dressing, og "lime" rammer hele frugter til en opskrift der beder om
    # saft. Et synonym skal MÅLES, ikke gættes — det er den korte vej til en
    # forkert vare med selvsikker score.
    # 2026-09-30: "karry krydderi" gav «Grøn karry krydderiblanding» 1,15 og
    # den rigtige «Karry (madras)» 0,50 = usikker. Bare "karry" + FORM-REGLEN
    # (dressingen er ude) rammer «Karry (madras)» 1,15 i Krydderier.
    "karrypulver": "karry",
    "misopasta": "miso",
    "limejuice": "limesaft",
    # Fond og bouillon er samme hylde hos Nemlig; kun ordet skiller.
    "fiskebouillon": "fiskefond",
    "kyllingebouillon": "kyllingefond",
    # «Parmigiano Reggiano» er den beskyttede betegnelse — Nemlig fører ikke
    # ordet "parmesan" på selve osten.
    "parmesan": "parmigiano reggiano",
    # Opslaget sker på HELE navnet, så en frase med et modifikator-ord skal
    # have sin egen linje. Ordet "revet" bliver stående: det blokerer ikke
    # længere (se _TILBEREDNING), men det rangerer den revne variant først.
    "revet parmesan": "revet parmigiano reggiano",
    "fintrevet parmesan": "revet parmigiano reggiano",
    # Runde 4, målt mod Nemlig 2026-09-02 på de 19 der stadig intet fandt.
    # Hver linje er verificeret til score 1,15 + hovedord-træf — altså AUTO-KØB.
    # Derfor er listen kortere end den kunne være: et synonym der skifter
    # RÅVARE (kuller → torsk, pastinak → «rodfrugter», svineslag → stegeflæsk,
    # kalkunschnitzel → kalkunbryst i strimler) ville købe en anden mad UDEN at
    # spørge. De hører i arket, hvor et menneske kan se hvad der byttes —
    # se docs/gemini_ordvalg_prompt.md.
    "svinemoerbrad": "mørbrad af gris",
    "svinekoteletter": "koteletter af gris",
    "vegetarfars": "plantefars",
    "aeggenudler": "ægnudler",
    "tortillapandekage": "tortilla",
    "tunboeffer": "tun steaks",
    "wokgroentsager": "wokblanding",
    "spaede salatblade": "salatmix",
    # Dansk "kaviar" i en opskrift betyder stenbiderrogn, ikke stør.
    "kaviar": "stenbiderrogn",
    # Nemlig fører ikke paella-ris (bomba). Risotto-ris er samme kortkornede
    # type og standard-erstatningen; alternativet var «Snublejuice IPA» til
    # 0,00 — altså at råvaren forsvandt helt ud af kurven.
    "paellaris": "risotto ris",
    # Runde 5, målt 2026-09-02 EFTER Geminis omdøbning af arket. Alle er
    # rene ORD-oversættelser — samme råvare, butikkens stavemåde:
    #   · Nemlig siger "gris", slagteren siger "svin".
    #   · Kategoriordet skal UD når Nemlig ikke bruger det («Penne rigate»,
    #     ikke «Pasta penne») — det talte som et misset søgeord.
    #   · Sammensat i arket, delt hos Nemlig, med varen SIDST.
    "hakket svinekoed": "hakket grisekød",
    "svinekoed i tern": "grisekød i tern",
    "svinekoed i strimler": "grisekød i strimler",
    "hakket svine og kalvekoed": "hakket grise og kalvekød",
    "hakket svine kalvekoed": "hakket grise og kalvekød",
    "pasta penne": "penne",
    "pasta fusilli": "fusilli",
    "shiitake svampe": "shiitake",
    "butternut squash": "butternut",
    "thailandsk basilikum": "thai basilikum",
    "majstortilla": "tortilla majs",
    "fuldkornstortilla": "tortilla fuldkorn",
    "hvide aspargesnitter": "aspargessnitter",
    # Slagterens ord for samme udskæring. «Stegeflæsk i skiver» ER stribet
    # flæsk — modsat svineslag, som er den hele, uskårne brystflæsk.
    "stribet flaesk": "stegeflæsk",
    # Runde 6, målt live 2026-10-01. Samme vare, butikkens ord — hver linje
    # giver auto-køb af den RIGTIGE vare (1,15 + hovedord):
    #   «Mandelflager», «Koriander (hel)», «Kanel (hel)» (en kanelstang er
    #   hel kanel — uden synonymet ramte den en WIENERBRØD-stang), «Hokkaido»
    #   (græskarret hedder bare Hokkaido; uden det: «Græskarsuppe m.
    #   hokkaido»), «Tyttebærsyltetøj», «Peanut sataysauce», «Tofu naturel».
    "mandler i flager": "mandelflager",
    "korianderfroe": "koriander hel",
    "kanelstang": "kanel hel",
    "hokkaido graeskar": "hokkaido",
    "tyttebaermarmelade": "tyttebærsyltetøj",
    "peanut sauce": "satay",
    "fast tofu": "tofu naturel",
    # Målt 2026-10-11: "gulerod" (4 stk) → «Gule ærter» 1,00 — vokalskiftet
    # (rod → rødder) skiller ental fra Nemligs flertal, så de rigtige
    # gulerødder scorede 0, og "gule" + "rod" lignede en bøjning (strammet i
    # `ord_matcher`). Cachen viser samme hul fra den anden side: «Gulerod
    # revet» til en ret der skal bruge hele gulerødder.
    "gulerod": "gulerødder",
    # User-spec 2026-10-11: "ris skal være hvide ris". Nemlig har ingen vare
    # der hedder det; uden synonymet vandt «Brune ris øko.» (præcis navn +
    # favorit). Basmati er hvid OG et tidligere køb. Kun den nøgne "ris" —
    # "brune ris", "jasminris" osv. er andre nøgler.
    "ris": "basmatiris",
    # ⚠️ MÅLT OG FRAVALGT 2026-10-01: "tamarindpasta" → "tamarind" rammer
    # «Sojasauce tamari» som OK — "tamarind" er "tamari" + 2 bogstaver og
    # ligner en bøjning. Og "hel nellike" → "nelliker" finder kun den stødte.
    # ⚠️ MÅLT OG FRAVALGT: "instant nudler" → "nudler" rammer «Risnudler»
    # 1,15 + hovedord = auto-køb af en ANDEN nudel. Samme fælde som "karry"
    # → «Karrydressing» (se SYNONYM_CASES i nemlig_gate_test.py). Begge
    # bliver stående som spørgsmål, hvor et menneske ser byttet.
}


def synonym(navn):
    """→ det ord vi bør SØGE på for `navn` (uændret hvis intet synonym).

    Whitespace kollapses, fordi `normaliser` laver ETHVERT tegn om til et
    mellemrum: "hakket svine- og kalvekød" bliver til nøglen "hakket svine  og
    kalvekoed" med DOBBELT mellemrum. En håndskrevet nøgle rammer aldrig det,
    og synonymet ville tavst aldrig blive brugt.
    """
    return SYNONYMER.get(" ".join(normaliser(navn).split()), navn)


SIKKER_SCORE = 0.99

# Default for `input_number.nemlig_favorit_loft_pct` — se FAVORIT-LOFT i
# `vaelg_produkt`. 100 = en tidligere købt vare må koste det dobbelte pr.
# enhed af den billigste tilsvarende, før den billigste vinder.
FAVORIT_LOFT_PCT = 100.0

# Under denne score er et produkt ikke engang værd at FORESLÅ som knap i et
# spørgsmål. Fallback-søgningen finder ellers rent skrald: "brystflæsk" gav
# "Brystkarameller" og "kullerfileter" gav en chokolade (målt 2026-08-31).
# Et dårligt forslag er værre end ingen: det inviterer til et forkert tryk.
FORSLAG_MIN_SCORE = 0.34
# Mindste fælles begyndelse før to navne overhovedet handler om det samme.
# Bruges KUN til at afgøre om et produkt er værd at FORESLÅ — aldrig til at
# købe. Se `relevant_nok`.
FAELLES_PRAEFIKS_MIN = 4


def log(msg):
    print(f"[nemlig] {msg}", file=sys.stderr)


class NemligFejl(Exception):
    pass


# =============================================================================
# HTTP-klient
# =============================================================================
class Nemlig:
    def __init__(self, bruger=None, kode=None, dry=False):
        self.bruger = bruger or ha_secrets.get("nemlig_user")
        self.kode = kode or ha_secrets.get("nemlig_password")
        self.dry = dry
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self._logget_ind = False
        self._genindlaes_session()

    # -- session-persistens --------------------------------------------------
    def _genindlaes_session(self):
        """Cookies fra disk. En for gammel session er værre end ingen: den kan
        give 200 med tomt indhold i stedet for en ærlig 401 — derfor tids-boks."""
        try:
            with open(SESSION_FILE, encoding="utf-8") as f:
                gemt = json.load(f)
        except FileNotFoundError, json.JSONDecodeError, OSError:
            return
        if time.time() - gemt.get("tid", 0) > SESSION_MAX_ALDER:
            return
        for c in gemt.get("cookies", []):
            self.cj.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=c["name"],
                    value=c["value"],
                    port=None,
                    port_specified=False,
                    domain=c["domain"],
                    domain_specified=True,
                    domain_initial_dot=c["domain"].startswith("."),
                    path=c["path"],
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=False,
                    comment=None,
                    comment_url=None,
                    rest={},
                )
            )
        self._logget_ind = any(c.name == ".ASPXAUTH" for c in self.cj)

    def _gem_session(self):
        data = {
            "tid": time.time(),
            "cookies": [
                {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                for c in self.cj
            ],
        }
        tmp = f"{SESSION_FILE}.tmp.{os.getpid()}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.chmod(tmp, 0o600)  # en cookie-fil ER adgang til kontoen
            os.replace(tmp, SESSION_FILE)
        except OSError as e:
            log(f"kunne ikke gemme session: {e}")
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _xsrf(self):
        return next((c.value for c in self.cj if c.name == "XSRF-TOKEN"), None)

    def _kald(self, metode, sti, body=None, params=None, _retry=True):
        time.sleep(RATE_LIMIT_S)
        url = API_ROOT + sti
        if params:
            url += "?" + urllib.parse.urlencode(params)
        h = {"User-Agent": UA, "Accept": "application/json"}
        tok = self._xsrf()
        if tok:
            h["X-XSRF-TOKEN"] = tok
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=h, method=metode)
        try:
            with self.op.open(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            krop = e.read().decode("utf-8", "replace")
            # 401/403 midt i en kørsel = sessionen udløb. Ét gen-login, så op igen.
            if e.code in (401, 403) and _retry and sti != "/login/login":
                log("session udløbet — logger ind igen")
                self._logget_ind = False
                self.cj.clear()
                self.login()
                return self._kald(metode, sti, body, params, _retry=False)
            if e.code == 400:
                try:
                    raise NemligFejl(json.loads(krop).get("ErrorMessage", krop[:200]))
                except json.JSONDecodeError:
                    pass
            raise NemligFejl(f"{metode} {sti} -> HTTP {e.code}: {krop[:200]}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise NemligFejl(f"{metode} {sti} -> {e}") from e

    # -- API -----------------------------------------------------------------
    def login(self, tvungen=False):
        if self._logget_ind and not tvungen:
            return True
        self._kald(
            "POST",
            "/login/login",
            {
                "Username": self.bruger,
                "Password": self.kode,
                "AppInstalled": False,
                "AutoLogin": False,
                "CheckForExistingProducts": True,
                "DoMerge": True,
            },
        )
        self._logget_ind = any(c.name == ".ASPXAUTH" for c in self.cj)
        if not self._logget_ind:
            raise NemligFejl("login gav 200 men ingen .ASPXAUTH-cookie")
        self._gem_session()
        return True

    def search(self, query, take=12):
        """Søgning virker uden login, men et login giver `Favorite`-flaget — og
        en vare brugeren HAR købt før er et stærkere match end navne-lighed."""
        self.login()
        svar = self._kald("GET", "/s/0/1/0/Search/Search", params={"query": query, "take": take})
        return (svar.get("Products") or {}).get("Products") or []

    @staticmethod
    def _kvalitet(traef, query):
        """Hvor godt svarer dette søgesvar på `query`? → (har svar, hovedord, score).

        Sorteres som et par, så et hovedord-træf ALTID slår en høj score uden
        hovedord — samme rangorden som `find_bedste` og som købs-gaten. Det er
        målestokken stigen nedenfor bruger, og den er bevidst STRENGERE end
        `relevant_nok`: sidstnævnte svarer på "er den værd at foreslå", og et
        svar fuldt af foreslåelige-men-forkerte varer skal stadig få os til at
        prøve et smallere søgeord.
        """
        # Første led: HAR vi overhovedet kandidater. Et tomt svar er værre end
        # et forkert — en vare uden kandidater forsvinder HELT (ingen kurv-linje,
        # intet spørgsmål), mens en forkert kandidat er en knap brugeren kan sige
        # nej til. Målt 2026-09-01b: uden dette led beholdt stigen sit tomme
        # førstesvar for "limejuice", "misopasta", "tahindressing" og elleve
        # andre, fordi den bedre-end-testen sammenlignede (0, 0.0) med (0, 0.0).
        # Ikke-mad tæller ikke som et svar: "brun sovs" → «Brun sæbe» skal
        # få stigen til at prøve igen, ikke stoppe den.
        traef = [p for p in traef if er_mad(p)]
        bedst = (1 if traef else 0, 0, 0.0)
        for p in traef:
            navn = p.get("Name") or ""
            kat = taksonomi(p)
            bedst = max(
                bedst, (1, 1 if hoved_traef(query, navn, kat) else 0, lighed(query, navn, kat))
            )
        return bedst

    def search_bredt(self, query, take=12):
        """Som `search`, men prøver smallere varianter når svaret er ubrugeligt.

        To grunde til at ét opslag ikke rækker:

        1. NUL træf. Nemligs søgning matcher ikke lange danske sammensatte ord:
           26 af 495 råvarer gav nul træf, heriblandt "chorizopølse",
           "cantaloupemelon" og "kulmulefileter" — alle med et oplagt produkt i
           butikken. Uden dette forsvandt varen HELT.

        2. TRÆF, men kun skrald (2026-09-01b). Værre end nul, fordi faldback'en
           aldrig blev udløst: en MODIFIKATOR i råvarenavnet kaprede søgningen.
           Målt over 444 råvarer: "frosne fiskepinde" → «Granatæblekerner»,
           "blandede svampe" → «Blandede fyldte bolcher», "mørkt øl" →
           «Mørkt rugbrød», "ristede hasselnødder" → «Ristede løg».

        Stigen prøver SØGEORDETS EGET HOVEDORD først (dansk substantivfrase er
        hoved-final: varen i "blandede svampe" er svampe), derefter det længste
        ord, og til sidst afkortninger fra HØJRE — dansk sammensætning har
        bestemmelsesordet til venstre, så "chorizo" er den del der findes.

        MONOTON: vi beholder kun et nyt svar hvis det er BEDRE end det vi
        allerede har. Uden den regel gør stigen skade — målt i første forsøg
        blev "tatarsauce" flyttet fra «Tartarsauce» til «Sojasauce tamari» og
        "æggenudler" fra «Æggeblommer» til «Parmigiano Reggiano», fordi en
        afkortet søgning gav noget der lige akkurat bestod relevans-testen.

        Hvert ekstra kald koster kun for de ~20 % der ikke rammer plet i
        første forsøg, og vi stopper i samme sekund svaret er købbart.
        """
        bedste = self.search(query, take)
        kval = self._kvalitet(bedste, query)
        if kval[1] and kval[2] >= SIKKER_SCORE:
            return bedste

        proev = []
        h = hovedord(query)
        ord_ = soegord_af(query)
        if h and (len(ord_) > 1 or h != normaliser(query).strip()):
            proev.append(h)
        rest = [o for o in ord_ if o != h]
        if rest:
            laengst = max(rest, key=len)
            if laengst not in proev:
                proev.append(laengst)
        rod = max(ord_, key=len) if ord_ else normaliser(query).strip()
        for skaer in (3, 5, 7):
            kort = rod[: len(rod) - skaer]
            # 4 tegn er nedre grænse: "lime" og "miso" er rigtige råvarer, men
            # 3 tegn rammer for bredt til at betyde noget.
            if len(kort) < 4:
                break
            proev.append(kort)

        for kandidat in proev:
            nyt = self.search(kandidat, take)
            if not nyt:
                continue
            k2 = self._kvalitet(nyt, query)
            if k2 > kval:
                bedste, kval = nyt, k2
            if kval[1] and kval[2] >= SIKKER_SCORE:
                break
        return bedste

    def basket(self):
        self.login()
        return self._kald("GET", "/basket/GetBasket")

    def basket_linjer(self):
        b = self.basket()
        return [
            {
                "id": str(l.get("Id")),
                "navn": l.get("ProductName") or l.get("Name"),
                "antal": l.get("Quantity"),
                "pris": l.get("Price"),
            }
            for l in (b.get("Lines") or [])
        ]

    def add(self, produkt_id, antal=1):
        """ABSOLUT antal — se modulets invariant. antal=0 fjerner linjen."""
        self.login()
        if self.dry:
            log(f"(dry) add {produkt_id} x {antal}")
            return {"dry": True}
        return self._kald(
            "POST", "/basket/AddToBasket", {"productId": str(produkt_id), "quantity": int(antal)}
        )

    def ryd_kurv(self):
        n = 0
        for l in self.basket_linjer():
            self.add(l["id"], 0)
            n += 1
        return n


# =============================================================================
# Navne-matchning
# =============================================================================
# Ord der beskriver en vare uden at identificere den. De fjernes FØR
# sammenligning, så "500 g små kartofler" og "Kartofler" mødes.
_STOPORD = {
    "frisk",
    "friske",
    "oekologisk",
    "oekologiske",
    "oeko",
    "stort",
    "stor",
    "smaa",
    "lille",
    "ca",
    "stk",
    "god",
    "gode",
    "dansk",
    "danske",
    "finthakket",
    "grofthakket",
    # Tilberedningstilstand: beskriver hvad DU gør ved varen, ikke
    # hvilken vare det er. "ukogt quinoa" og "færdig pizzadej" scorede
    # 0,50 mod de rigtige produkter alene på grund af disse ord.
    # NB: "færdigstegt" er IKKE med — en færdigstegt flæskesteg er en
    # anden vare end en rå, og skal have lov at fejle højlydt.
    "ukogt",
    "optoeet",
    "afdryppet",
    "faerdig",
    "faerdige",
    # "fersk" = rå/ikke-frossen, ikke en vare. Uden det matchede
    # "ferske rødspættefileter" ordet "fersken" og foreslog
    # soltørrede figner og en Tuborg Squash Fersken (målt 2026-08-31).
    "fersk",
    "ferske",
}


def normaliser(s):
    """Fold til sammenlignelig form: småt, uden tegn, æøå -> ae/oe/aa.

    NB: HA-slugify laver ø->o, men her vil vi have ø->oe, fordi vi matcher
    DANSKE varenavne mod hinanden — "kød"/"koed" skal mødes, ikke "kod"."""
    s = (s or "").lower().strip()
    s = s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s)


# En parentes betyder to FORSKELLIGE ting på de to sider af matchet, så den
# må kun fjernes på den ene:
#   ARKET: en note til mennesket. "bao buns (frost)", "flæskesteg (i skiver)".
#     Ordet "frost" er et søgeord der aldrig kan matches og trak scoren fra
#     1,00 til 0,67.
#   NEMLIG: en ægte variant-skelnen. «Ærter (fine)», «Fiskefilet (panerede)»,
#     «Pinjekerner (ristede)». Målt 2026-09-01b: da parentesen også blev
#     strippet på produkt-siden, mistede "fine ærter", "panerede fiskefileter"
#     og "ristede pinjekerner" den ENESTE ting der skilte den rigtige variant
#     fra den forkerte — otte match faldt fra ok til usikker.
# Derfor: `ord_af` rører ikke produktnavne; `soegord_af` renser søgeordet.
_PAREN_RE = re.compile(r"\([^)]*\)")


# Nemlig forkorter bindeordet i produktnavne («Mandler m. salt», «Yoghurt u.
# sukker»); arket skriver det fuldt ud. Uden udfoldningen tæller "med" som et
# MISSET søgeord, og "mandler med salt" scorede 0,67 mod «Mandler m. salt» —
# altså den helt rigtige vare, kasseret på en forkortelse. Begge sider foldes,
# så de mødes på samme form. Ordet bærer ingen vare-identitet, så det kan ikke
# alene løfte et forkert produkt: "ravioli med svampe" står stadig 0,67 mod
# «Ravioli m. kylling» og bliver ved med at være et spørgsmål.
_FORKORTELSER = {"m": "med", "u": "uden"}


def ord_af(s):
    return [_FORKORTELSER.get(o, o) for o in normaliser(s).split() if o and o not in _STOPORD]


# Tilberedning DU foretager, ikke en vare butikken fører. Fjernes KUN på
# søge-siden, og kun fra tælleren i `lighed` — se `variant_ord`.
#
# Målt 2026-09-02: 40 af 86 usikre linjer havde den RIGTIGE vareart valgt og
# faldt alene på et sådant ord. "ristede valnødder" mod «Valnødder» scorede
# 0,50, fordi Nemlig ikke sælger dem ristede — det gør man selv.
#
# ⚠️ Tre ord der ligner disse står bevidst UDENFOR:
#   "blandet"  — målt: "blandet salat" rammer «Radicchio salat» 1,15 og ville
#                blive auto-købt. En blanding ER en vare.
#   "tørret"   — tørrede krydderurter er en anden hylde end friske i potte.
#   "kogt"     — kogt skinke er en anden vare end rå skinke.
# Fælles kriterium: fjern ordet KUN hvis butikken umuligt kan føre varen i den
# tilstand. Kan den, er ordet en vare-skelnen og skal blive.
_TILBEREDNING = {
    "revet",
    "friskrevet",
    "fintrevet",
    "ristet",
    "ristede",
    "pillet",
    "pillede",
    "bloed",
    "bloedt",
    "moden",
    "modne",
    "afpudset",
    "afpudsede",
    "skaert",
}


def soegord_af(s):
    """Som `ord_af`, men til den side der kommer fra ARKET."""
    return ord_af(_PAREN_RE.sub(" ", s or ""))


def haardord_af(s):
    """Søgeordets ord UDEN tilberedning — det der skal kunne findes.

    Falder tilbage til alle ordene hvis der ikke er andet: "revet" alene er
    stadig et søgeord, bare et dårligt et."""
    ord_ = soegord_af(s)
    return [o for o in ord_ if o not in _TILBEREDNING] or ord_


def variant_ord(s):
    """Tilberednings-ordene selv. De må ikke BLOKERE et match, men de skal
    stadig kunne skille to varianter: findes både «Parmesan» og «Revet
    parmesan», skal "revet parmesan" vælge den revne."""
    return [o for o in soegord_af(s) if o in _TILBEREDNING]


def hoved_region(navn, soege_side=False):
    """Ordene FØR første præposition = det varen ER, ikke hvad der er i den.

    «Tofu m. citrongræs» er tofu; «Bacon i skiver» er bacon. Bruges på BEGGE
    sider: produktets region afgør hvad varen er, og søgeordets egen region
    afgør hvilket ord der bærer identiteten ("skært oksekød i tern" handler om
    oksekød, ikke om tern).
    """
    ord_ = soegord_af(navn) if soege_side else ord_af(navn)
    region = []
    for i, o in enumerate(ord_):
        if o in _PRAEPOSITIONER:
            # Undtagelse: "i tern"/"i skiver" er en UDSKÆRING af varen selv,
            # ikke et indhold. «Bacon i tern» ER bacontern, og arket skriver
            # det i ét ord. Uden dette stoppede regionen ved "i", limningen
            # gav "bacon" og det helt rigtige produkt scorede 0,50/False.
            # Kun på produkt-siden og kun foran et FORM-ord — "m."/"med" og
            # «Tofu m. citrongræs» er urørt.
            if not soege_side and o == "i" and i + 1 < len(ord_) and ord_[i + 1] in _FORMORD:
                continue
            break
        region.append(o)
    return region or ord_[:1]


def hovedord(soegt):
    """Søgeordets EGEN identitets-bærer = sidste ord i dets hoved-region.

    Dansk substantivfrase er hoved-final: i "revet parmesan", "hakket lammekød"
    og "blandede rodfrugter" står varen sidst og modifikatoren først. Målt
    2026-09-01b over 444 råvarer: uden dette kunne MODIFIKATOREN alene opfylde
    hovedord-gaten — "revet parmesan" bestod på «Rød cheddar (revet) 30%», og
    "hakket lammekød" på «Hakket spinat øko.». Det er den samme fejlklasse som
    fremmed-hovedord, bare fra den anden side af navnet.
    """
    r = hoved_region(soegt, soege_side=True)
    return r[-1] if r else None


# Dansk flertal/bøjning lægger 1-3 bogstaver til: -e, -r, -er, -ne, -ene.
# Mere end det er ikke en bøjning, det er et andet ord.
MAKS_BOEJNING = 3

# Alt fra og med et af disse ord beskriver hvad der er I varen, ikke hvad
# varen ER. "Tofu m. citrongræs" er tofu.
_PRAEPOSITIONER = {"m", "med", "og", "uden", "i", "til"}
# Udskæring/form — beskriver hvordan varen er skåret, ikke hvad der er i den.
_FORMORD = {"tern", "skiver", "strimler", "baade", "stave", "halve"}


def ord_matcher(o, x):
    """Matcher søgeordet `o` produktordet `x`?

    Tre veje, hver med sin begrundelse:
      1. Identiske.
      2. `x` starter med `o` — dansk sammensætning har kerneordet til HØJRE,
         så "kyllingebryst" skal finde "Kyllingebrystfilet".
      3. `o` starter med `x` og er højst MAKS_BOEJNING længere — det er en
         BØJNING ("laksefileter" -> "laksefilet"), ikke en sammensætning.
         Uden længdegrænsen ville "smørkage" matche "smør" og vi ville købe
         smør til en kage. Målt 2026-08-31: uden (3) scorede "laksefileter"
         og "torskefileter" 0,00 mod de helt rigtige produkter.
    """
    if o == x:
        return True
    if len(o) > 3 and x.startswith(o):
        return True
    # Halen skal være en ÆGTE endelse: "gulerod" er ikke en bøjning af
    # "gule" (målt 11/10: → «Gule ærter» 1,00). Katalog-diff: 1/453 skift,
    # usikker → usikker.
    if (
        len(x) > 3
        and o.startswith(x)
        and len(o) - len(x) <= MAKS_BOEJNING
        and o[len(x) :] in _BOEJNING
    ):
        return True
    return False


def lighed(soegt, navn, kategori=None):
    """0-1,15. Andelen af det SØGTE der findes i produktnavnet, med bonus når
    ordene også står sammenhængende.

    Asymmetrisk med vilje: "hakket oksekød" skal matche "Hakket oksekød 8-12%"
    fuldt ud, mens produktets EKSTRA ord (procent, brand) ikke må straffe.
    Et symmetrisk mål ville rangere den korteste titel højest, ikke den rigtige.

    Delvist match kræver PREFIX, ikke vilkårlig delstreng: dansk sammensætning
    gør "løg" til en delstreng af "rødløg", og en ren `in`-test købte derfor
    rødløg til enhver opskrift der bad om løg (målt 2026-08-31). Prefix bevarer
    det vi vil have — "kyllingebryst" -> "Kyllingebrystfilet" — og afviser det
    vi ikke vil have, fordi et sammensat ord har sit kerneord til HØJRE på dansk.
    """
    a, b = haardord_af(soegt), ord_af(navn)
    if not a:
        return 0.0
    sti = _sti_af(kategori)
    # Sammensat i opskriften, delt hos Nemlig: "dijonsennep" mod "Dijon
    # sennep" scorede 0,00. Vi prøver derfor også mod produktnavnet uden
    # mellemrum. Kun for ord over 5 tegn — ellers ville korte ord som "løg"
    # begynde at ramme inde i sammensætninger, hvilket er præcis den fejl
    # prefix-reglen findes for at undgå.
    # Bindeord skal UD før sammenlimningen: "Bacon i tern" limet som
    # "baconitern" indeholder ikke "bacontern", og det korrekte produkt blev
    # kasseret med score 0,00 (målt over alle 495 råvarer). Ord på 1-2 tegn
    # bærer ingen vare-identitet på dansk.
    sammen = "".join(x for x in b if len(x) > 2)
    omvendt = _omvendte(b)
    traef = sum(
        1
        for o in a
        if any(ord_matcher(o, x) for x in b)
        or (len(o) > 5 and o in sammen)
        or any(ord_matcher(o, x) for x in omvendt)
        or form_ord_opfyldt(o, sti)
        or aekvivalent(o, b)
    )
    score = traef / len(a)
    if score >= 1.0 and " ".join(a) in " ".join(b):
        score += 0.15
    score = min(score, 1.15)

    # Tilberednings-ordet må ikke blokere et match (det er derfor det er ude af
    # tælleren ovenfor), men det skal stadig kunne RANGERE: findes både
    # «Parmigiano Reggiano» og «Parmigiano Reggiano revet», skal "revet
    # parmesan" vælge den revne. Fradraget er med vilje bittelille — det må
    # kun bryde uafgjort, aldrig flytte noget over eller under SIKKER_SCORE
    # (0,99). Base-scoren er brøker af små heltal (+0,15) og rammer aldrig
    # intervallet [0,99; 0,995), så grænsen kan ikke krydses af dette.
    varianter = variant_ord(soegt)
    if varianter and not all(any(ord_matcher(v, x) for x in b) for v in varianter):
        score *= 0.995

    # Rammer navnet slet ikke, så prøv produktets KATEGORI. Vin er hele
    # grunden: «P.Maufoux Chardonnay Horizon» siger intet om at det er hvidvin
    # — ordet står kun i Description efter fem skråstreger og i
    # ProductCategoryGroupName. Kategorien er den strukturerede af de to.
    #
    # Kun som fallback ved score 0, så den aldrig kan forringe et navne-match,
    # og med en lille rabat: en kategori er svagere evidens end et navn.
    # `kategori` kan være flere led af varetræet (se `taksonomi`) — det
    # bedste led tæller.
    if score == 0 and kategori:
        led = _led(kategori)
        # Også de to niveauer SAMMEN: "mørk øl" har "øl" i midten og "mørk" i
        # bladet («Brown Ale» → Drikke › Øl › Mørk Ale). Hvert led for sig
        # dækker kun halvdelen, og en IPA i "Lys Ale" scorede det samme.
        samlet = [k for k in led if not isinstance(k, Sti)]
        if len(samlet) > 1:
            led = led + [Blad(" ".join(samlet))]
        score = max(_kategori_score(soegt, k) for k in led)
    return score


def _sti_af(kategori):
    return next((k for k in _led(kategori) if isinstance(k, Sti)), "")


# OMVENDT SAMMENSÆTNING (2026-10-01). Nemlig navngiver ofte med varen FØRST og
# varianten bagefter — «Persille krus», «Kartofler baby», «Rødbeder runde» —
# mens dansk sammensætter omvendt: "kruspersille". Målt: "kruspersille" mod
# «Persille krus øko.» scorede 0,00/-h og endte som et spørgsmål om præcis den
# rigtige vare. Kun ord-PAR inden for samme navn, og kun når det limede ord er
# langt nok til ikke at ramme tilfældigt.
def _omvendte(b):
    return [y + x for x, y in zip(b, b[1:]) if len(x) > 2 and len(y) > 2]


# FORM-ORD (2026-10-01): ord der beskriver varens FORM, og som Nemlig aldrig
# skriver i navnet — det står i varetræet. «Oregano» i Tørvarer › Krydderier
# ER tørret oregano; «Ærter øko.» i Frost › … ER frosne ærter. Målt over 465
# råvarer: "tørret oregano", "tørret timian", "frosne ærter", "syltede
# rødbeder" og "tørrede abrikoser" havde ALLE den rigtige vare valgt, men
# scorede 0,50 og blev spurgt om — og "tørret oregano" valgte endda den
# FRISKE (Grønt › Krydderurter), fordi formen ikke talte. Ordet tæller kun som
# ramt når stien bekræfter det, så "tørret" mod en frisk potte stadig er et
# misset ord, og den tørrede variant vinder.
# (søgeord-præfikser, sti-delstrenge) — begge normaliseret.
FORM_ORD = [
    (("frosne", "frossen", "frosset", "frost"), ("frost",)),
    (("toerret", "toerrede"), ("toervarer", "toerret")),
    (("syltet", "syltede"), ("survarer", "syltet")),
    (("roeget", "roegede"), ("roeget",)),
    (("instant",), ("portionsnudler", "cupnudler")),
]


# ORD-ÆKVIVALENS (2026-10-01): arkets ord ↔ den del af Nemligs varenavn der
# betyder det samme. Ikke synonymer for hele navnet (de skifter vare), kun for
# ÉT ord, og kun hvor betydningen er den samme: «Svampemix» ER blandede svampe,
# «Grøntsagsfrikadeller» ER vegetariske frikadeller. Målt: begge blev spurgt om
# (0,50), og "vegetariske frikadeller" foreslog kød-frikadeller først.
ORD_AEKVIVALENS = [
    (("blandet", "blandede"), ("mix", "blanding")),
    # "brun sovs" (500 ml) → «Sovsejævner (brun)»; «Brun sauce» stod på 0,50.
    (("sovs",), ("sauce", "sovs")),
    (
        ("vegetarisk", "vegetariske", "vegetar", "vegansk", "veganske"),
        ("groentsag", "plante", "vegan", "veggie", "vegetar"),
    ),
]


def aekvivalent(o, b):
    for ord_, del_ in ORD_AEKVIVALENS:
        if o in ord_:
            return any(d in x for x in b for d in del_)
    return False


def form_ord_opfyldt(o, sti):
    if not sti:
        return False
    s = normaliser(sti)
    for ord_, del_ in FORM_ORD:
        if o in ord_:
            return any(d in s for d in del_)
    return False


# Et BLAD med ord søgeordet IKKE nævner, er en UNDERTYPE af det søgte: "pasta"
# mod bladet "Frisk Pasta" (gnocchi, tortelloni). Målt 2026-10-01: da bladet
# kom med i evidensen, slog «Gnocchi (frisk)» «Penne rigate» på pris, fordi
# begge stod på 1,0. En undertype må gerne FORESLÅS, men aldrig købes
# automatisk og aldrig slå et led der dækker hele begrebet ("Pasta").
# Bladets ord læses RÅT (ikke `ord_af`): "frisk" er et stopord i et varenavn,
# men i bladet "Frisk Pasta" er det hele forskellen.
# Det MIDTERSTE niveau beholder sin gamle regel: "mel" → «Hvedemel» via "Mel
# og bageblandinger" og "olie" via "Olier og eddike" var rigtige auto-køb.
UNDERTYPE_LOFT = 0.95


class Blad(str):
    """Et kategori-led der er varetræets BLAD (se `taksonomi`)."""


class Sti(str):
    """Hele varetræ-stien. Ikke et kategori-led — kun til `FORM_ORD`."""


def _kategori_score(soegt, k):
    if isinstance(k, Sti):
        return 0.0
    s = min(lighed(soegt, k) * 0.9, 1.0)
    if s and isinstance(k, Blad):
        hard = haardord_af(soegt)
        if not all(
            any(ord_matcher(o, x) for o in hard) for x in normaliser(k).split() if len(x) > 2
        ):
            s = min(s, UNDERTYPE_LOFT)
    return s


def _led(kategori):
    """str eller liste af kategori-led → liste (tomme led ude)."""
    if isinstance(kategori, str):
        return [kategori] if kategori else []
    return [k for k in (kategori or []) if k]


# Pakningsstørrelse står i `Description` ("1 kg / Danish Crown", "500 g",
# "6 stk. / Hjem-IS"). Vi tager første tal+enhed.
_PAK_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|l|dl|cl|ml|stk|pk|ds)\b", re.I)
_TIL_GRAM = {"kg": 1000.0, "g": 1.0}
_TIL_ML = {"l": 1000.0, "dl": 100.0, "cl": 10.0, "ml": 1.0}
_STYK = ("stk", "pk", "ds")
# "2 stk. / 225-300 g": et interval er en garanti for den NEDRE grænse.
_INTERVAL_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*-\s*\d+(?:[.,]\d+)?\s*(kg|g|l|dl|cl|ml)\b", re.I)


def _familie(enhed):
    e = (enhed or "").lower()
    return "g" if e in _TIL_GRAM else "ml" if e in _TIL_ML else "stk" if e in _STYK else e


def pakning_i(beskr, enhed):
    """→ (mængde, enhed) for ÉN pakke i SAMME enheds-familie som `enhed`, eller
    (None, None). Multipak først, så et interval (nedre grænse), så resten.

    Målt 2026-10-11 (simuleret madplan): «Torskefilet u. skind — 2 stk. / 200
    g» blev læst som "2 stk" (første tal), 400 g torsk blev "enheder matcher
    ikke" → ÉN pakke = 200 g. Halvdelen af middagen manglede. Vægten stod der
    bare længere henne; samme form på kylling og andre kød-/fiskevarer."""
    beskr = beskr or ""
    fam = _familie(enhed)
    m = _MULTI_RE.search(beskr)
    if m and _familie(m.group(3)) == fam:
        return (int(m.group(1)) * float(m.group(2).replace(",", ".")), m.group(3).lower())
    for rx in (_INTERVAL_RE, _PAK_RE):
        for m in rx.finditer(beskr):
            if _familie(m.group(2)) == fam:
                return float(m.group(1).replace(",", ".")), m.group(2).lower()
    return None, None


# "2 x 75 g", "6 x 0,75 l", "24 x 0,33 l": flere enheder i ÉN pakke.
_MULTI_RE = re.compile(r"(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(kg|g|l|dl|cl|ml|stk|pk|ds)\b", re.I)


def pakning(produkt):
    """-> (mængde, enhed) for ÉN pakke, eller (None, None) hvis ulæselig.

    En multipak tæller HELE pakken (2026-10-01): «Pancetta i tern» er "2 x
    75 g", og uden multiplikatoren blev 150 g til 2 pakker = 300 g. Målt i
    søgesvarene: 168 varer har formen, fra bearnaise-breve til vinkasser."""
    beskr = produkt.get("Description") or ""
    m = _MULTI_RE.search(beskr)
    if m:
        return (int(m.group(1)) * float(m.group(2).replace(",", ".")), m.group(3).lower())
    m = _PAK_RE.search(beskr)
    if not m:
        return None, None
    return float(m.group(1).replace(",", ".")), m.group(2).lower()


def er_kasse(x):
    """En kasse/ramme flasker eller dåser prissat PR. STYK: «Zealy Sauvignon
    Blanc — 6 x 0,75 l» står til 54,95 kr./Stk., men koster 329,70 kr. Enheds-
    prisen får den til at ligne en billig flaske, og "1 pakke" er seks."""
    m = _MULTI_RE.search(x.get("beskrivelse") or "")
    return bool(m) and int(m.group(1)) >= 2 and "stk" in (x.get("enhedspris_label") or "").lower()


# STYKVÆGT (2026-09-30, user: "jeg vil heller ikke ha hvidløg og citroner og
# sådan noget enkeltvis, det er billigere i net eller bundter. optimer.").
# Grøntsager/frugt der sælges BÅDE pr. stk og i net/pose. Uden en stykvægt kan
# kr/stk og kr/kg ikke sammenlignes (øko-loftet opgav: "ingen sammenlignelig
# konventionel pris" → enkelt-hvidløg øko til 5,50 kr/stk slog nettet til
# 66,65 kr/kg), og "6 stk citroner" mod et 500 g-net blev "enheder matcher
# ikke" = ÉT net = 4-5 citroner. Typiske vægte (afrundet, madtabel-niveau),
# ikke målt her — de bruges kun til at SAMMENLIGNE priser og DÆKKE behov,
# aldrig til at vælge vareart. Nøglen er normaliseret (ø→oe) og matcher også
# bøjninger ("citroner"). `fed` er den eneste enhed under et helt stykke.
STK_VAEGT_G = {
    "hvidloeg": 50,
    "citron": 110,
    "lime": 70,
    "loeg": 125,
    "roedloeg": 100,
    "skalotteloeg": 30,
    "banan": 180,
    "aeble": 150,
    "appelsin": 200,
    "avocado": 200,
}
_FED_G = 5


# En multipak — eller en pakke af noget der ikke holder sig (`_kort_holdbar`)
# — må højst være så mange gange behovet (i alt); se PAKKE-LOFT i
# `vaelg_produkt`. 2 = "2 x 400 g" til 800 g er fint; "12 x 400 g" er ikke.
MULTIPAK_MAKS_FAKTOR = 2.0


# Så mange gange sit eget rumfang rækker en fond (bladet "Fond") — 0,2 l til
# 1 l. Et skøn efter de koncentrerede fonde (Oscar 1 dl → 1 l); hellere lidt
# for stærk suppe end fem glas.
FOND_DAEKNING = 5


def _kort_holdbar(x):
    """→ "koed" | "mejeri" | "vin" | None. Fersk/frost kød, fjerkræ og fisk,
    mejeri og vin (en åbnet flaske holder ikke) — det der bliver en rest i
    skabet. Målt 11/10: 500 ml rødvin → bag-in-box 3 l til 179 kr, mens en
    75 cl-flaske kostede 114,95."""
    hg, kat = _n(x.get("hovedgruppe")), _n(x.get("kategori"))
    if hg == "koed og fisk" or (
        hg == "frost" and any(k in kat for k in ("koed", "fisk", "fjerkrae"))
    ):
        return "koed"
    return {"mejeri": "mejeri", "vin og spiritus": "vin"}.get(hg)


def for_stor_pakke(x, maengde, enhed):
    """Er `x` langt over behovet: en multipak («12 x 400 g»), eller en pakke
    der ikke holder sig («Kyllingebrystfilet 1 kg» til 300 g)?

    Tørvarer er bevidst UDE (user 11/10: en stor pose peanuts er fin), og det
    samme er grønt, hvor net-før-enkelt er en user-spec.
    Enheder der ikke kan sammenlignes giver False — hellere en pakke for meget
    end et gæt der smider den rigtige ud. Et behov i stk/ds tælles mod
    antallet af enheder i en multipak."""
    if not maengde:
        return False
    beskr = x.get("beskrivelse") or ""
    m = _MULTI_RE.search(beskr)
    multi = bool(m) and int(m.group(1)) >= 2
    if not (multi or _kort_holdbar(x)):
        return False
    be = (enhed or "stk").lower()
    if multi and be in _STYK and _familie(m.group(3)) != "stk":
        return int(m.group(1)) > MULTIPAK_MAKS_FAKTOR * maengde
    pm, pe = pakning_i(beskr, be)
    if not pm:
        return False
    if be in _TIL_GRAM:
        behov, pak = maengde * _TIL_GRAM[be], pm * _TIL_GRAM[pe]
    elif be in _TIL_ML:
        behov, pak = maengde * _TIL_ML[be], pm * _TIL_ML[pe]
    else:
        behov, pak = maengde, pm
    return pak > MULTIPAK_MAKS_FAKTOR * behov


def stk_vaegt(soegt):
    """→ gram pr. stk for råvaren i `soegt`, eller None hvis vi ikke kender den."""
    for o in haardord_af(soegt or ""):
        for k, g in STK_VAEGT_G.items():
            if o == k or (o.startswith(k) and len(o) - len(k) <= MAKS_BOEJNING):
                return g
    return None


def antal_pakker(behov_maengde, behov_enhed, produkt, navn=None):
    """-> (antal, forklaring). Hvor mange pakker dækker behovet?

    Rund ALTID op: en opskrift der mangler 100 g er en fejlet middag, en
    overskydende pakke er bare en rest i køleskabet."""
    pm, pe = pakning(produkt)
    if not pm or not behov_maengde:
        return 1, "ukendt pakning"
    be = (behov_enhed or "stk").lower()
    if _familie(pe) != _familie(be):
        am, ae = pakning_i(produkt.get("Description"), be)
        if am:
            pm, pe = am, ae
    # Stk/fed mod en pakke i vægt: regn om med stykvægten (2026-09-30).
    sg = stk_vaegt(navn)
    if sg and pe in _TIL_GRAM and be in ("stk", "fed"):
        behov_maengde = behov_maengde * (_FED_G if be == "fed" else sg)
        be = "g"
    if be in _TIL_GRAM and pe in _TIL_GRAM:
        behov, pak, vis = behov_maengde * _TIL_GRAM[be], pm * _TIL_GRAM[pe], "g"
    elif be in _TIL_ML and pe in _TIL_ML:
        behov, pak, vis = behov_maengde * _TIL_ML[be], pm * _TIL_ML[pe], "ml"
    elif be == pe or (be in _STYK and pe in _STYK):
        behov, pak, vis = behov_maengde, pm, be
    else:
        # Fx behov i "stk" mod en pakke i "g" — vi kan ikke regne, så 1 pakke
        # og en ærlig markering er bedre end et gæt der køber 8 kg.
        return 1, f"enheder matcher ikke ({be} vs {pe})"
    if pak <= 0:
        return 1, "pakning 0"
    # Fond er et koncentrat: opskriftens "1 l fiskebouillon" er fond + vand,
    # ikke fem glas fond (simuleret madplan 11/10: 5 × 0,2 l = 116 kr, mens
    # hønsebouillon samme dag blev én terning til 5,50).
    if vis == "ml" and produkt.get("ProductSubGroupName") == "Fond":
        pak *= FOND_DAEKNING
    n = max(1, math.ceil(behov / pak - 1e-9))
    return n, f"{behov:g} {vis} / {pak:g} {vis} pr. pk"


def hoved_traef(soegt, navn, kategori=None):
    """Blev PRODUKTETS egen vare bedt om — med SØGEORDETS egen vare?

    To krav, ét fra hver side af matchet:

      1. PRODUKT-SIDEN: matchet skal ligge i produktets hoved-region (før
         første præposition). Alt derefter beskriver hvad der er I varen.
         Målt 2026-08-31: "citrongræs" fik fuld score på «Tofu m. citrongræs»
         og ville være røget i kurven.
      2. SØGE-SIDEN: det ord der matcher, skal være søgeordets EGEN
         identitets-bærer (sidste ord i dets hoved-region) — eller alle
         søgeordets ord skal matche. Målt 2026-09-01b: uden dette bestod
         "revet parmesan" på «Rød cheddar (revet) 30%» og "hakket lammekød"
         på «Hakket spinat øko.», fordi MODIFIKATOREN alene opfyldte gaten.

    Sammenlimning gælder begge veje inden for hoved-regionen: dansk skriver
    "dijonsennep" i ét ord, Nemlig skriver «Dijon sennep». Limningen sker KUN
    over hoved-regionen — over hele navnet ville «Tofu m. citrongræs» blive
    til "tofucitrongraes" og hullet fra 08-31 ville stå åbent igen.
    """
    region = hoved_region(navn)
    sammen = "".join(x for x in region if len(x) > 2)
    ord_soegt = soegord_af(soegt)
    hoved = hovedord(soegt)

    omvendt = _omvendte(region)

    def rammer(o):
        if any(ord_matcher(o, x) for x in omvendt) or aekvivalent(o, region):
            return True
        for x in region:
            if ord_matcher(o, x):
                return True
            # Suffiks: dansk sammensætning har kerneordet til HØJRE, så
            # "fløde" ER hovedordet i "piskefløde".
            if len(o) > 3 and x.endswith(o):
                return True
        return len(o) > 5 and o in sammen

    if _identitets_veto(soegt, region, kategori):
        return False
    if hoved and rammer(hoved):
        return True
    # Alle søgeordets ord ramte = identiteten kan ikke være gået tabt, uanset
    # hvilket af dem der er hoved-final ("ærter og gulerødder").
    if ord_soegt and all(rammer(o) for o in ord_soegt):
        return True
    # Samme kategori-fallback som `lighed`: beder man om "hvidvin", er en vare
    # i kategorien Hvidvin den rigtige vareart, uanset hvad flasken hedder.
    if kategori and hoved:
        for k in _led(kategori):
            if isinstance(k, Sti):
                continue
            for x in ord_af(k):
                if ord_matcher(hoved, x):
                    return True
    return False


# IDENTITETS-VETO (2026-10-01). Nemlig navngiver ofte med varen FØRST:
# «Skyr rabarber- og vaniljesmag» er skyr, «Pizza pepperoni» er en pizza. Dansk
# hoved-final-logik læser dem omvendt, og målt over 465 råvarer blev begge
# AUTO-KØBT ("rabarber" 300 g → skyr; "pepperoni" og "pancetta" → frostpizza).
# Varetræet afgør det: står et ANDET ord fra navnets hoved-region i produktets
# egen kategori, mens søgeordets hovedord ikke gør, så er produktet DEN vare,
# og søgeordet er kun smagen/fyldet. Form-ord ("i skiver", "hakket") er ikke
# en identitet — «Chorizo i skiver» i "Pålæg i Skiver" er stadig chorizo.
_IKKE_IDENTITET = (
    _FORMORD | _PRAEPOSITIONER | _TILBEREDNING | {"hakket", "hakkede", "skiveskaaret", "naturel"}
)


def _identitets_veto(soegt, region, kategori):
    led = [k for k in _led(kategori) if not isinstance(k, Sti)]
    blad = [k for k in led if isinstance(k, Blad)]
    if not blad:
        return False
    h = hovedord(soegt)
    if not h:
        return False

    def i_tax(o, led_):
        tax = {t for k in led_ for t in normaliser(k).split() if len(t) >= 3}
        return any(
            ord_matcher(o, t)
            or ord_matcher(t, o)
            or o.startswith(t)
            or (len(t) >= 4 and o.endswith(t))
            for t in tax
        )

    # Søgeordet i HVILKET SOM HELST niveau = varen er det søgte. Det andet
    # ords identitet skal derimod stå i BLADET: «Fladbrød Roti Paratha» blev
    # vetoet, fordi "fladbrød" ender på midtens "Brød og dej" (målt).
    if i_tax(h, led):
        return False
    hard = haardord_af(soegt)
    for x in region:
        if any(ord_matcher(o, x) or x in o for o in hard):
            # Søgeordet står FØR et eventuelt typeord: «Sriracha chilisauce»
            # er en chilisauce AF typen sriracha = det søgte. Kun typeord der
            # står FORAN søgeordet («Skyr rabarber», «Pizza pepperoni») er en
            # anden vare. Målt: uden rækkefølgen blev «Basilikum Grøn» vetoet,
            # fordi "grøn" ligner midten "Grønt".
            return False
        if x in _IKKE_IDENTITET or len(x) < 4:
            continue
        if i_tax(x, blad):
            return True
    return False


def relevant_nok(soegt, navn, kategori=None):
    """Er produktet værd at FORESLÅ som knap? (Aldrig: værd at købe.)

    Scoren alene duer ikke som relevans-mål. Dansk gør to helt legitime match
    umulige at score: flertal kan elidere et bogstav ("falafel" -> "falafler"),
    og et sammensat råvarenavn kan have produktet som VENSTRE del
    ("chorizopølse" -> «Chorizo extra»). Begge scorer 0,00, og begge er den
    rigtige vare. Strukturelt kan de ikke skelnes fra "smørkage" -> "smør",
    så de må ikke købes automatisk — men de skal foreslås, for et menneske
    kan afgøre dem på et halvt sekund.

    Fælles begyndelse er den billige test der skiller dem fra rent skrald:
    "paellaris" mod «Snublejuice IPA» deler intet.
    """
    if lighed(soegt, navn, kategori) >= FORSLAG_MIN_SCORE:
        return True
    # Dansk sammensætning med kerneordet til HØJRE: «Hvedemel» ER mel, og
    # «Minimælk» ER mælk. Suffiks-vejen er BEVIDST kun her og ikke i `lighed`:
    # den kan strukturelt ikke skelne "hvedemel"→mel fra "rødløg"→løg, så den
    # må foreslå, aldrig købe. Målt 2026-09-01b: 35 af 39 "ingen træf" HAVDE
    # en kandidat — mel, mælk, olie, pasta, hvidvin, svinemørbrad — der blev
    # kasseret her og dermed forsvandt HELT: ingen kurv-linje og intet
    # spørgsmål, så brugeren fik aldrig at vide at varen manglede.
    for o in soegord_af(soegt):
        if len(o) < 3:
            continue
        for x in ord_af(navn):
            if len(x) > len(o) and x.endswith(o):
                return True
    # Pr. ORDPAR, ikke på de sammenlimede strenge: "frosne falafler" mod
    # «Falafel øko.» deler intet fra tegn ét, men ordene falafler/falafel
    # deler fem — og det er dér genkendelsen sidder.
    for o in soegord_af(soegt):
        for x in ord_af(navn):
            n = 0
            for c1, c2 in zip(o, x):
                if c1 != c2:
                    break
                n += 1
            if n >= FAELLES_PRAEFIKS_MIN:
                return True
    return False


def kun_relevante(rangeret, soegt):
    """Behold de kandidater der overhovedet ligner den ønskede vare.

    Bruges FØR `vaelg_produkt`, ikke efter. Testes relevansen først bagefter —
    altså kun på det ENE produkt der blev valgt — smider vi hele søgesvaret væk
    på grund af én dårlig topkandidat, selv om der lå en brugbar vare lige
    under. Målt 2026-09-01b: "blandede svampe" endte på «Portobello øko.» og
    blev derfor rapporteret som "ingen træf", selv om «Svampemix» lå i samme
    svar og er det oplagte bud.

    Er INTET relevant, returneres listen uændret — så beholder kalderen sin
    mulighed for at sige "ikke fundet, bedste bud var X" i stedet for at
    foreslå «Snublejuice IPA» til "paellaris".
    """
    rel = [
        t
        for t in rangeret
        if relevant_nok(soegt, t.get("navn") or "", t.get("taksonomi") or t.get("kategori"))
    ]
    return rel or rangeret


# VARETRÆET (2026-10-01). Hvert søgetræf bærer en sti i tre niveauer,
# ProductMainGroupName › ProductCategoryGroupName › ProductSubGroupName —
# fx «Frugt og grønt › Grønt › Svampe». Matcheren læste kun det MIDTERSTE
# niveau ("Grønt"), som er for groft til at sige hvad varen ER. Bladet er selve
# varearten: «Portobello øko.» ligger i "Svampe", «Basmatiris øko.» i "Løse
# ris", «Kantareller» i "Svampe". Det var B109's klasse 1 ("vareart uden fælles
# bogstaver"): "svampe" kunne ikke finde Portobello, fordi ordet kun stod i
# bladet, og bladet blev aldrig læst.
#
# Bladet tæller KUN når det er ÉT begreb. "Saucer og fond", "Dressing, pesto,
# humus, mayo, mm." og "Balsamico & Vineddike" er SPANDE med flere vare-
# arter, og en "fond"-træffer i spanden kunne ellers være en béarnaise. Første
# komma-led tæller ("Krydderier, glas" → "Krydderier"); et led med og/&/+ er en
# spand og tæller slet ikke.
_SPAND_RE = re.compile(r"\s(og|&|\+)\s|/")


def blad_led(p):
    """→ bladets første komma-led hvis det er ét begreb, ellers ''."""
    blad = (p.get("ProductSubGroupName") or "").split(",")[0].strip()
    return "" if _SPAND_RE.search(blad) else blad


def taksonomi(p):
    """→ kategori-led til `lighed`/`hoved_traef`: midterste niveau + bladet."""
    kat = p.get("ProductCategoryGroupName") or p.get("SubCategory") or ""
    sti = " ".join(
        x for x in (p.get("ProductMainGroupName"), kat, p.get("ProductSubGroupName")) if x
    )
    return [k for k in (kat, Blad(blad_led(p)), Sti(sti)) if k]


# Hovedgrupper der aldrig er en ingrediens. Målt i søgesvarene 2026-10-01:
# "brun sovs" → «Brun sæbe» (Husholdning), "svampe" → «Rengøringssvampe»,
# "kokos" → bodylotion (Pleje), "kylling" → hundegodbidder (Dyremad). Et
# menneske kasserer dem på et halvt sekund; matcheren skal ikke engang se dem,
# heller ikke som knap i et spørgsmål.
IKKE_MAD = {
    "husholdning",
    "pleje",
    "dyremad og tilbehoer",
    "nonfood",
    "baby og boern",
    "blomster",
    "kiosk",
}
# … og kategorier der er mad, men aldrig ÉN ingrediens: "hvidvin" ramte
# «Hvidvins ''BESTSELLER'' kassen» (6 flasker, 699 kr) med 1,15, fordi
# "hvidvins" er en bøjning af søgeordet.
IKKE_INGREDIENS = {
    "vinkasser",
    # Slik i pose: "ferskner" (4 stk) → «Ferskner» VINGUMMI,
    # da dåse-fersknerne var ude som forarbejdede (re-audit
    # 2026-10-01). Chokolade bor i andre midter og er urørt.
    "poseslik",
}


def _n(x):
    return " ".join(normaliser(x or "").split())


def er_mad(p):
    return (
        _n(p.get("ProductMainGroupName")) not in IKKE_MAD
        and _n(p.get("ProductCategoryGroupName")) not in IKKE_INGREDIENS
    )


# Haler der ikke skifter vare: «Bearnaisesauce» ER bearnaise, «Laksefilet» ER
# laks, «Karrypulver» ER karry. Uden dem tabte "bearnaise" til «Bearnaise
# essens» og "laks" til «Koldrøget laks» (målt 2026-10-01).
_GENERISK_HALE = {
    "sauce",
    "filet",
    "fileter",
    "portion",
    "portioner",
    "stykker",
    "tern",
    "skiver",
    "strimler",
    "pulver",
    "bidder",
    "kerner",
    "bryst",
    "brystfilet",
    "mix",
    "blanding",
}


# Ægte danske bøjningsendelser. `ord_matcher` nøjes med "højst 3 bogstaver
# mere", og det tager også "gurkemeje" → «Gurkemejerod» og "tamarind" →
# «tamari» som bøjninger (målt 2026-10-01). Præcisions-reglerne kræver
# derfor at forskellen ER en endelse.
_BOEJNING = {
    "e",
    "r",
    "er",
    "n",
    "en",
    "ne",
    "ene",
    "erne",
    "s",
    "es",
    "et",
    "ede",
    "t",
    "te",
    "re",
    "der",
}


def _boejning(kort, lang):
    return len(kort) > 3 and lang.startswith(kort) and lang[len(kort) :] in _BOEJNING


def _ord_praecis(o, x):
    """Som `ord_matcher`, men skeptisk over for sammensætning:
    · identitet og bøjning (≤ MAKS_BOEJNING) begge veje → ja
    · `x` ENDER på `o` ("blåmuslinger" ~ "muslinger") → ja: på dansk står
      varen sidst, så det er en SLAGS muslinger
    · `x` BEGYNDER med `o` → kun hvis halen er generisk (se _GENERISK_HALE);
      "kanelbullar" er boller, "honningtomater" er tomater."""
    if o == x:
        return True
    kort, lang = (o, x) if len(o) <= len(x) else (x, o)
    if _boejning(kort, lang):
        return True
    if len(o) >= 4 and len(x) > len(o):
        if x.endswith(o):
            return True
        if x.startswith(o):
            hale = x[len(o) :]
            return hale in _GENERISK_HALE or (hale[:1] in ("e", "s") and hale[1:] in _GENERISK_HALE)
    return False


def _limninger(b):
    """Sammenlimning af 2-3 NABO-ord (begge rækkefølger for par)."""
    b = [x for x in b if len(x) > 2]
    ud = set()
    for i in range(len(b)):
        for j in (i + 2, i + 3):
            if j <= len(b):
                ud.add("".join(b[i:j]))
        if i + 1 < len(b):
            ud.add(b[i + 1] + b[i])
    return ud


def praecis(soegt, navn, kategori=None):
    """Rammer HVERT søgeord et helt ord i navnet (eller en bøjning, en limning
    af nabo-ord, eller et FORM-ord stien bekræfter) — ikke bare BEGYNDELSEN af
    et sammensat ord?

    Målt 2026-10-01: "kanel" (1 tsk) → «Kanelbullar» og "honning" (2 spsk) →
    «Honningtomater i kasse». Begge stod på 1,15 side om side med den rigtige
    vare («Kanel (stødt)», «Hverdags honning»), og prisen pr. kg afgjorde det —
    og et krydderi er ALTID dyrere pr. kg end en bolle. På dansk står varen
    sidst i et sammensat ord, så "kanel…" er kun en smag. Bruges KUN til at
    vælge INDEN FOR topfeltet, aldrig til at købe eller kassere.
    """
    a, b = haardord_af(soegt), ord_af(navn)
    if not a or not b:
        return False
    lim = _limninger(b)
    sti = _sti_af(kategori)
    return all(
        any(_ord_praecis(o, x) for x in b)
        or any(_ord_praecis(o, x) for x in lim)
        or form_ord_opfyldt(o, sti)
        or aekvivalent(o, b)
        for o in a
    )


# Ord der står i et varenavn uden at gøre varen til en ANDEN variant.
_NEUTRALE = {
    "naturel",
    "klassisk",
    "classic",
    "original",
    "vaskede",
    "loese",
    "hel",
    "hele",
    "mellem",
    "almindelig",
    "almindelige",
    "ekstra",
    "extra",
    "store",
    "formodnet",
    # Emballage er ikke en variant — "hvidløg" skal stadig vælge
    # «Hvidløg i net» (user-spec 30/9), ikke «Hvidløg Solo».
    "net",
    "pose",
    "bakke",
    "bundt",
    "kasse",
    "boette",
    "spand",
    # Røget er en FORM, og den har sine egne regler (FORM_ORD,
    # «Røget fisk» som forarbejdet). Som ekstra-ord tabte «Røget
    # Hamburgerryg» (stegen) til «Hamburgerryg» i Pålæg i Skiver.
    "roeget",
    "roegede",
}
# Varenavne der siger "pynt, ikke mad" — tæller som FYLD (mest specifikt):
# "græskar" (1 kg) valgte «Halloween græskar stor» frem for et spisegræskar.
_PYNT = {"halloween", "pynt", "dekoration"}


def _er_selve(o, x):
    """Er produktordet `x` det søgte ord `o` selv (identitet, bøjning eller
    generisk hale) — og IKKE en slags `o` med et forled ("blåmuslinger")?"""
    if o == x:
        return True
    kort, lang = (o, x) if len(o) <= len(x) else (x, o)
    if _boejning(kort, lang):
        return True
    if len(o) >= 4 and x.startswith(o):
        hale = x[len(o) :]
        return hale in _GENERISK_HALE or (hale[:1] in ("e", "s") and hale[1:] in _GENERISK_HALE)
    return False


def ekstra_ord(soegt, navn, brand=None):
    """→ (indhold, ekstra): hvor meget MERE SPECIFIK er varen end det søgte?

    `indhold` = ord efter en præposition («Rejer m. ramsløg»: fyld/smag),
    `ekstra` = øvrige ord der ikke er det søgte («Skole agurker», «Kødboller
    (plantebaseret)», «Avocado i tern», og et sammensat forled: «BLÅmuslinger»).
    Tal, brand, størrelse og "naturel"-agtige ord tæller ikke. Sorteres som
    par, så fyld altid er mere specifikt end et ekstra ord. Bruges KUN til at
    vælge inden for topfeltet — se MEST GENERISK i `vaelg_produkt`."""
    a = soegord_af(soegt)
    brand_ord = set(ord_af(brand or ""))
    ord_ = ord_af(navn)
    indhold = ekstra = 0
    efter = False
    for i, x in enumerate(ord_):
        if x in _PRAEPOSITIONER:
            # "i tern"/"i skiver" er en udskæring af varen, ikke et indhold,
            # og "uden sten" TAGER noget væk («Sorte oliven u. sten»).
            if x == "uden":
                break
            if not (
                x == "i"
                and i + 1 < len(ord_)
                and (ord_[i + 1] in _FORMORD or ord_[i + 1] in _NEUTRALE)
            ):
                efter = True
            continue
        if x in _PYNT:
            indhold += 1
            continue
        if len(x) < 3 or any(c.isdigit() for c in x) or x in brand_ord or x in _NEUTRALE:
            continue
        if any(_er_selve(o, x) for o in a):
            continue
        if any(x in o for o in a):
            continue  # en del af et limet søgeord
        if efter:
            indhold += 1
        else:
            ekstra += 1
    return (indhold, ekstra)


def naer_hoved(soegt, navn, min_praefiks=5):
    """Deler produktets hoved-region en STAMME (≥ 5 fælles begyndelsesbogstaver)
    med søgeordets hovedord? Kun til at rangere forslag — aldrig til at købe."""
    h = hovedord(soegt)
    if not h or len(h) < min_praefiks:
        return False
    for x in hoved_region(navn):
        n = 0
        for c1, c2 in zip(h, x):
            if c1 != c2:
                break
            n += 1
        if n >= min_praefiks:
            return True
    return False


def find_bedste(kandidater, soegt):
    """Rangér: eget køb > lighed > hovedord-træf > på lager > pris."""
    ud = []
    for p in kandidater:
        if not er_mad(p):
            continue
        av = p.get("Availability") or {}
        pm, pe = pakning(p)
        kat = p.get("ProductCategoryGroupName") or p.get("SubCategory") or ""
        tax = taksonomi(p)
        ud.append(
            {
                "id": str(p.get("Id")),
                "navn": p.get("Name"),
                "pris": p.get("Price"),
                "enhedspris": p.get("UnitPriceCalc"),
                "enhedspris_label": p.get("UnitPriceLabel"),
                "oeko": er_oeko(p),
                "tilbud": paa_tilbud(p),
                "beskrivelse": p.get("Description"),
                "brand": p.get("Brand"),
                "pakning": (f"{pm:g}{pe}" if pm else None),
                "paa_lager": bool(av.get("IsAvailableInStock")),
                "leverbar": bool(av.get("IsDeliveryAvailable")),
                "favorit": bool(p.get("Favorite")),
                "score": lighed(soegt, p.get("Name") or "", tax),
                "hoved": hoved_traef(soegt, p.get("Name") or "", tax),
                "kategori": kat,
                "undergruppe": p.get("ProductSubGroupName") or "",
                "hovedgruppe": p.get("ProductMainGroupName") or "",
                "taksonomi": tax,
                "naer": naer_hoved(soegt, p.get("Name") or ""),
                "praecis": praecis(soegt, p.get("Name") or "", tax),
                "ekstra": ekstra_ord(soegt, p.get("Name") or "", p.get("Brand")),
                "_raw": p,
            }
        )
    # KORREKTHED FØR LIGHED (2026-09-01b): hovedord-træf sorteres FØRST, ikke
    # som tiebreaker efter score. En kandidat uden hovedord-træf kan aldrig
    # købes automatisk (gaten i nemlig_kurv.parr), så den må heller ikke stå
    # øverst og være det produkt brugeren bliver spurgt om. Målt over 444
    # råvarer: "orzo" rangerede «Laks og orzo m. timiansauce» først med 1,15
    # (sammenhængs-bonussen slog et rigtigt produkt på 1,00), og det samme
    # gjaldt "røde linser" og "teriyakisauce". Samme rækkefølge-princip som
    # vaelg_produkt fik 2026-08-31 fase 6: korrekthed før præference.
    # NÆR-HOVED (2026-10-01) er næste led: uden hovedord-træf skal den vare der
    # deler STAMME med søgeordets hovedord stå før den der kun deler en
    # modifikator. "hakket lammekød" foreslog «Hakket spinat» (0,50 på
    # "hakket") før lammekøllerne (0,00) — et spørgsmål hvis første knap er
    # spinat til en moussaka.
    ud.sort(
        key=lambda x: (
            not x["hoved"],
            not x["naer"],
            -(x["score"] + (0.30 if x["favorit"] else 0)),
            not x["paa_lager"],
            x["enhedspris"] or 9e9,
        )
    )
    return ud


# =============================================================================
# Øko / tilbud (fase 4)
# =============================================================================
# Begge aflæses af `Labels`, som er Nemligs egen mærkning — ikke af navnet.
# Navnet er upålideligt: "Kaffe øko." har ordet, men "Rucola" kan være
# økologisk uden at skrive det i titlen.
_OEKO_MAERKER = ("øko", "oko", "organic")


def er_oeko(produkt):
    for m in produkt.get("Labels") or []:
        if any(t in (m or "").lower() for t in _OEKO_MAERKER):
            return True
    return False


def paa_tilbud(produkt):
    if produkt.get("DiscountItem"):
        return True
    return any(
        (m or "").lower() in ("discount", "tilbud", "prisfald")
        for m in (produkt.get("Labels") or [])
    )


def _sammenlignelig(a, b):
    """Må disse to enhedspriser overhovedet sammenlignes?

    kr/kg mod kr/stk er et meningsløst regnestykke. Uden dette tjek ville en
    kg-vare til 96 kr se "dyrere" ud end en stk-vare til 20 kr, og øko-loftet
    ville afvise på et falsk grundlag.
    """
    return (
        a.get("enhedspris")
        and b.get("enhedspris")
        and a.get("enhedspris_label") == b.get("enhedspris_label")
    )


# FORM-REGLEN (2026-09-30): en vare i en FORARBEJDET kategori er en anden
# vare end råvaren, selv med samme navn og fuld score. Målt i kurven 30/9:
# "karry" (2 spsk) → «Karrydressing» (Fastfood og dressing, 63,82 kr/kg slog
# «Karry (madras)» 66,11 kr/kg på pris), "rødbeder" (500 g) → «Rødbeder» 710 g
# på glas (Survarer), og "citron" har tre «Citronsaft» i sit topfelt. Findes
# der en kandidat UDEN for disse kategorier, er de forarbejdede ude — også når
# råvaren er udsolgt (så bliver linjen "udsolgt", ikke et glas).
# Frost er IKKE med: hakket frost-spinat er en gængs erstatning.
# Drikkene er med fordi "lime" har «Citron & Lime læskedrik» i sit topfelt
# med hovedord-træf (målt 30/9).
FORARBEJDET_KATEGORIER = {
    "survarer",
    "groentkonserves",
    "fastfood og dressing",
    "saft og juice",
    "sodavand  vand og laesk",
    # Målt 2026-10-01: midten hedder faktisk "Sodavand,
    # vand og læskedrikke" — "squash" købte Tuborg Squash.
    "sodavand, vand og laeskedrikke",
    # 2026-10-01 (læses på midten OG bladet): "ferskner"
    # (4 stk) → «Halve ferskner i sukkerlage»,
    # "muslinger" → «Muslinger i vand» på dåse, "laks" →
    # koldrøget, "laksefilet" → indbagt m. spinat (frost).
    "frugtkonserves",
    "fiskekonserves",
    "koedkonserves",
    "marmelade",
    "gele",
    "roeget fisk og fiskevarer",
}
FORARBEJDET_BLAD_START = ("panere",)  # IKKE "upanerede"
# Beder søgeordet selv om den forarbejdede form, gælder reglen ikke. Første
# gruppe kan stå SIDST i et sammensat ord ("hvidløgsdressing",
# "rødbedesaft"), anden kun først ("syltede", "glasset", "dåse").
FORARBEJDET_I_ORD = (
    "sylt",
    "dressing",
    "saft",
    "juice",
    "konserv",
    "roeg",
    "marmelade",
    "gele",
    "suppe",
)
FORARBEJDET_FOERST = ("glas", "daase", "lage", "marinere", "eddike", "panere")
FORARBEJDET_SIDST = ("lage",)  # "sukkerlage", "eddikelage"


def _kat_saet(xs):
    """Sammenlign kategorinavne på `_n`-form (ét mellemrum). Midten «Sodavand,
    vand og læsk» normaliseres til DOBBELT mellemrum ("sodavand  vand …"), og
    en hånd-skrevet nøgle med ét mellemrum ramte den ikke."""
    return {_n(k) for k in xs}


def _forarbejdet(x):
    """FÆRDIGRETTER er også forarbejdet (2026-10-01): "karahi masala" (1 spsk)
    fik «Tikka masala øko.» (Køl › Færdigretter, 149 kr) som første knap, og
    "orzo" «Laks og orzo m. timiansauce». En færdigret er aldrig en ingrediens,
    når en råvare står lige så højt."""
    blad = _n(x.get("undergruppe"))
    saet = _kat_saet(FORARBEJDET_KATEGORIER)
    return (
        _n(x.get("kategori")) in saet
        or blad in saet
        or blad.startswith(FORARBEJDET_BLAD_START)
        or er_faerdigret(x)
    )


def er_faerdigret(x):
    """Bladet er en færdigret, eller midten hedder netop "Færdigretter".
    IKKE "Middagstilbehør og færdigretter" (Frost) som spand: dér bor også
    kødboller, frikadeller og pommes frites, der ER ingredienser — målt:
    "kødboller" blev til «Kødboller (plantebaseret)», da hele spanden var ude."""
    blad = _n((x.get("undergruppe") or "").split(",")[0])
    return (
        "faerdigret" in normaliser(x.get("undergruppe") or "")
        or _n(x.get("kategori")) == "faerdigretter"
        # Supper (frost, brev, færdige) — "hokkaido græskar" (1 kg) købte
        # «Græskarsuppe m. hokkaido». IKKE "Suppeboller".
        or blad in ("supper", "suppe")
    )


def vil_forarbejdet(soegt):
    """Beder søgeordet selv om den forarbejdede form (syltet/glas/dressing …)?"""
    return any(
        any(m in o for m in FORARBEJDET_I_ORD)
        or o.startswith(FORARBEJDET_FOERST)
        or o.endswith(FORARBEJDET_SIDST)
        for o in ord_af(soegt or "")
    )


def form_advarsel(valgt, soegt):
    """→ grund til at SPØRGE frem for at købe, eller None.

    En færdigret er aldrig en ingrediens. FORM-reglen fjerner den når en råvare
    står lige så højt; findes der INGEN råvare (målt: "svinekæber" → braiserede
    kæber i sovs, "hokkaido græskar" → «Græskarsuppe m. hokkaido»), er det et
    spørgsmål, ikke et køb."""
    if not valgt or vil_forarbejdet(soegt):
        return None
    if er_faerdigret(valgt):
        return "færdigret — ingen råvare fundet"
    # Syltetøj og frugt i lage er aldrig en erstatning for frugten selv (målt:
    # "rabarber" → «Rabarber og hindbærmarmelade», da skyr'en var ude).
    if _n(valgt.get("undergruppe")) in ("marmelade", "gele", "frugtkonserves") or _n(
        valgt.get("kategori")
    ) in _kat_saet(SAFT_OG_SODAVAND):
        return "kun forarbejdet form fundet"
    return None


# Drikke-midter: en råvare der KUN findes som saft/sodavand er et spørgsmål
# (målt: "rabarber" → «Rabarber saft», "squash" → «Tuborg Squash»).
SAFT_OG_SODAVAND = {"saft og juice", "sodavand, vand og læsk", "sodavand, vand og læskedrikke"}


# Råvarer hvor opskriften i VÆGT mener glasset og i STK mener råvaren. Målt
# i ret-arket 30/9: "1 glas (500 g) rødkål" (ribbensteg, flæskestegssandwich)
# bliver struct `500|g|rødkål` — ordet "glas" går tabt — mens rødkålssalaten
# skriver "0.5 stk rødkål". Nøglen er normaliseret.
GLAS_VED_VAEGT = {"roedkaal"}


def form_ord(navn, enhed):
    """→ det FORM-reglen skal læse for `navn` (ikke det der søges på)."""
    if (
        " ".join(normaliser(navn or "").split()) in GLAS_VED_VAEGT
        and (enhed or "").lower() != "stk"
    ):
        return f"{navn} på glas"
    return navn


def form_filter(kandidater, soegt, score_slop=0.001):
    """FORM-REGLEN på kandidater med hovedord-træf.

    Uden markør: forarbejdede kategorier er ude, men KUN når en råvare
    matcher LIGE SÅ GODT (topscore). Katalog-diffen 30/9 viste hvorfor: med
    en ren "findes der en råvare"-regel blev "hvide bønner" til «Bønner
    grønne» (0,5) og "grønne linser" til «Røde splitlinser», fordi den ENESTE
    præcise træffer stod på dåse (Grøntkonserves).
    Med markør (syltet/glas/dressing/saft …): den forarbejdede form vinder,
    hvis den er i toppen.
    """
    kand = list(kandidater)
    if not soegt or not kand:
        return kand
    top = max(x["score"] for x in kand)
    toppen = [x for x in kand if x["score"] >= top - score_slop]
    if vil_forarbejdet(soegt):
        if any(_forarbejdet(x) for x in toppen):
            return [x for x in kand if _forarbejdet(x)]
        return kand
    if any(not _forarbejdet(x) for x in toppen):
        return [x for x in kand if not _forarbejdet(x)]
    return kand


# FRAVÆRENDE FORM (2026-10-01) — spejlbilledet af FORM_ORD: siger opskriften
# IKKE "tørret"/"frosne", er den friske GRØNT-vare svaret, når den står i
# feltet. Målt: "basilikum" valgte «Basilikum» i Krydderier (tørret, brev), og
# "rosenkål" frost-posen. Bevidst SMALT — første version læste al Tørvarer som
# "tørret" og smed karrypulver, quinoa og karrypasta ud til fordel for den ene
# vare fra grøntafdelingen («Frisk rød karrypasta», «Quinoa knækbrød»):
#   · tørret krydderi/tørret frugt ud — kun hvis en frisk KRYDDERURT/frugt står
#     i feltet (gurkemeje-pulveret bliver mod en gurkemejerod),
#   · frost ud — kun hvis frisk frugt/grønt står i feltet (bao buns på frost
#     bliver mod en køle-variant).
_TOERRET = ("toerret", "toerrede")
_FROSSEN = ("frosne", "frossen", "frosset", "frost")


def _fravaerende_form(felt, soegt):
    if not felt or not soegt:
        return felt
    ord_ = set(soegord_af(soegt))

    def mid(x):
        return _n(x.get("kategori"))

    def er_frugt_groent(x):
        return _n(x.get("hovedgruppe")) == "frugt og groent"

    if not ord_ & set(_TOERRET):

        def toerret(x):
            return mid(x) == "krydderier" or "toerret" in mid(x)

        frisk = [
            x
            for x in felt
            if not toerret(x)
            and er_frugt_groent(x)
            and (
                _n(x.get("undergruppe")) == "krydderurter"
                or not any(mid(y) == "krydderier" for y in felt)
            )
        ]
        if frisk and any(toerret(x) for x in felt):
            felt = [x for x in felt if not toerret(x)]
    if not ord_ & set(_FROSSEN):

        def frost(x):
            return _n(x.get("hovedgruppe")) == "frost"

        if any(frost(x) for x in felt) and any(er_frugt_groent(x) and not frost(x) for x in felt):
            felt = [x for x in felt if not frost(x)]
    return felt


def _pr_kg(x, stk_g):
    """→ kopi af kandidaten med enhedsprisen i kr/kg, hvis den står i kr/stk
    og vi kender stykvægten. Ellers kandidaten selv."""
    label = (x.get("enhedspris_label") or "").lower()
    if stk_g and x.get("enhedspris") and "stk" in label:
        return {
            **x,
            "enhedspris": round(x["enhedspris"] / stk_g * 1000, 2),
            "enhedspris_label": "kr./Kg.",
        }
    return x


def _enkelt_stk(x):
    return (x.get("pakning") or "").lower() in ("1stk", "1pk")


def _net_pakke(x):
    """Et net/bundt/pose: vægt-pakke eller ≥ 2 stk. Liter er IKKE et net."""
    m = re.match(r"^(\d+(?:\.\d+)?)(g|kg|stk|pk)$", (x.get("pakning") or "").lower())
    return bool(m) and not (m.group(2) in ("stk", "pk") and float(m.group(1)) < 2)


def vaelg_produkt(
    rangeret,
    oeko_loft_pct=None,
    foretraek_tilbud=True,
    score_slop=0.001,
    soegt=None,
    favorit_loft_pct=None,
    behov=None,
):
    """Vælg blandt de BEDST MATCHENDE på lager, efter øko/tilbuds-præferencer.

    Match-kvalitet er ufravigelig og afgøres FØRST: vi vælger kun mellem
    produkter der scorer lige så højt som den bedste. En billigere eller
    grønnere vare der er den forkerte vare, er stadig den forkerte vare.

    `oeko_loft_pct` = hvor meget dyrere øko må være pr. enhed før vi vælger
    konventionelt. 100 = op til dobbelt pris. None = ingen øko-præference.

    → (valgt, begrundelse, reference) hvor `reference` er den billigste
    sammenlignelige ikke-øko (til merpris-regnskabet).

    `soegt` (valgfri) slår FORM-REGLEN og STYKVÆGT/net-før-enkelt til.
    `behov` (valgfri) = (mængde, enhed) slår PAKKE-LOFTET til.
    """
    # FORM før lager: er råvaren udsolgt, må et glas ikke tage dens plads.
    # Kun blandt kandidater med hovedord-træf, ellers kunne en fremmed vare
    # i en ikke-forarbejdet kategori "redde" feltet fra den rigtige dressing.
    med_h = [x for x in rangeret if x.get("hoved")]
    if soegt and med_h:
        form = form_filter(med_h, soegt)
        rangeret = form + [x for x in rangeret if not x.get("hoved")]
    stk_g = stk_vaegt(soegt) if soegt else None
    if stk_g:
        rangeret = [_pr_kg(x, stk_g) for x in rangeret]
    paa_lager = [x for x in rangeret if x["paa_lager"]] or list(rangeret)
    if not paa_lager:
        return None, "ingen kandidater", None
    # KORREKTHED FØR LIGHED (2026-09-01b) — samme rangorden som `find_bedste`.
    # Hovedord-filteret skal ligge FØR top-score-filteret: gør man det omvendt,
    # kan et produkt med høj lighed men FREMMED hovedord lægge beslag på feltet,
    # og den rigtige vareart med lavere score bliver aldrig set. Et produkt uden
    # hovedord-træf kan alligevel aldrig købes automatisk, så det må heller ikke
    # afgøre hvilke kandidater der er i spil.
    med_hoved = [x for x in paa_lager if x.get("hoved")]
    if med_hoved:
        paa_lager = med_hoved
    else:
        # Intet hovedord-træf = det bliver et spørgsmål. Så skal første knap
        # være den rigtige VAREART (se `naer_hoved`), ikke den højeste score.
        naer = [x for x in paa_lager if x.get("naer")]
        if naer:
            paa_lager = naer
    top = max(x["score"] for x in paa_lager)
    felt = [x for x in paa_lager if x["score"] >= top - score_slop] or [paa_lager[0]]

    # PRÆCIS FØR SAMMENSAT (2026-10-01) — se `praecis`. Er intet præcist (rene
    # kategori-træf: "kalvekød" → alt i bladet Kalvekød), så de navne der
    # deler STAMME med søgeordet («Kalvecuvette» frem for «Burger BOOST»).
    navne_traef = [x for x in felt if x.get("praecis")] or [x for x in felt if x.get("naer")]
    if navne_traef:
        felt = navne_traef
    felt = _fravaerende_form(felt, soegt)
    enkelt = [x for x in felt if not er_kasse(x)]
    if enkelt:
        felt = enkelt

    # PAKKE-LOFT (2026-10-11, user-spec "undgå multipacks så langt over").
    # Målt: "hakkede tomater" 800 g → «Hakkede tomater 12 x 400 g» = 4,8 kg.
    # Multipakkens kg-pris (15,31) slog enkeltdåsen (15,93), og som REFERENCE
    # pressede den både favoritten og øko-varen ud over deres lofter. Den
    # fjernes derfor FØR favorit- og øko-reglerne — også fra referencen.
    # Samme loft på kød/fisk, mejeri og vin (simuleret madplan 11/10): 300 g kyllingebryst →
    # favoritten «Kyllingebrystfilet 1 kg» 139,95 kr, mens 550 g kostede 79,95.
    # To vagter, målt i katalog-diffen samme dag. En for stor pakke viger kun
    # for en passende der er MINDST LIGE SÅ GENERISK (`ekstra`): "kalkunbryst"
    # 900 g veg ellers for «Kalkunbryst i strimler», og så vandt pålægget
    # «Kalkunbryst (røget)» på MEST GENERISK. Og kun hvis den passende ikke
    # koster mere I ALT: blåmuslinger 1 kg til 46,95 blev ellers til
    # kammuslinger 2 × 250 g til 149,95 — loftet skal spare spild, ikke penge.
    # Og kun inden for samme vareart: samme blad, eller samme `_kort_holdbar`-
    # gruppe (frost og fersk kyllingeunderlår er to blade) — pålæg er aldrig
    # en erstatning.
    if behov:

        def i_alt(x):
            return antal_pakker(behov[0], behov[1], x.get("_raw") or {}, navn=soegt)[0] * (
                x.get("pris") or 0
            )

        def mindst_lige_generisk(y, x):
            return y.get("ekstra") is None or x.get("ekstra") is None or y["ekstra"] <= x["ekstra"]

        def samme_art(y, x):
            return (
                y.get("undergruppe") == x.get("undergruppe")
                or _kort_holdbar(y) == _kort_holdbar(x) is not None
            )

        passende = [x for x in felt if not for_stor_pakke(x, *behov)]
        felt = [
            x
            for x in felt
            if x in passende
            or not any(
                samme_art(y, x) and mindst_lige_generisk(y, x) and i_alt(y) <= i_alt(x)
                for y in passende
            )
        ]

    # NET FØR ENKELT (2026-09-30, user-spec): for råvarer vi kender stykvægten
    # på, er 1-stk-varen ude når et net/bundt/pose er på lager. FØR favorit-
    # reglen: et tidligere køb af én hvidløg er ikke et ønske om enkeltstyk.
    # Nettet kan godt ligge UNDER topscoren ("citroner" mod "citron" er en
    # bøjning = 1,00 mod 1,15) → det søges blandt alle på lager med hovedord.
    # Nettet skal ligge i SAMME kategori som enkeltstykkerne: "banan" har
    # «Bananchips øko.» 200 g (Tørret frugt) med 1,15 + hovedord (målt 30/9).
    if stk_g and any(_enkelt_stk(x) for x in felt):
        kat = {x.get("kategori") for x in felt if _enkelt_stk(x)}
        net = [
            x
            for x in paa_lager
            if _net_pakke(x) and x.get("kategori") in kat and x["score"] >= SIKKER_SCORE
        ]
        if net:
            felt = net

    # EGET TIDLIGERE KØB VINDER. `Favorite` er Nemligs flag for "denne kunde
    # har haft varen før" — brugerens egen afslørede præference, og dermed
    # stærkere evidens end et par kroners forskel i enhedspris.
    #
    # Fanget 2026-08-31: "burgerboller" endte som «Kinesiske burgerboller»,
    # selv om «Brioche burgerboller» lå øverst med favorit-mærke. find_bedste
    # rangerede korrekt, men denne funktion så kun på score, øko og pris og
    # smed favorit-signalet væk. Samme princip som et lært valg: har mennesket
    # allerede taget stilling, skal en generisk regel ikke overtrumfe det.
    #
    # Øko- og tilbudsreglerne anvendes stadig — bare INDEN FOR favoritterne,
    # hvis der er flere.
    # KORREKTHED FØR PRÆFERENCE: en favorit der er den forkerte VAREART må ikke
    # vinde, fordi den er en favorit. «Smoothie m. jordbær» er også et tidligere
    # køb, men den er ikke jordbær. (Selve hovedord-filteret er rykket op før
    # top-score-udvælgelsen ovenfor.)
    #
    # FAVORIT-LOFT (2026-10-01). Et tidligere køb er en SMAGS-præference, ikke
    # en blankocheck. Målt over 465 råvarer slog en favorit en billigere
    # tilsvarende vare i 99 af dem, og i toppen lå "hvidvin" (1 dl til
    # madlavning) → «P.Maufoux Chardonnay» 149,95 kr mod 29 kr (5,2×) og
    # "olie" → ekstra jomfru olivenolie 5,2×. Huset har købt næsten alle
    # ris-sorter, så flaget skiller heller ikke varianter ad der. En favorit
    # må højst koste `favorit_loft_pct` mere pr. enhed end den billigste
    # sammenlignelige vare i feltet.
    fuldt = list(felt)
    # Vin i en opskrift er MADLAVNINGSvin: en favorit-flaske er et drikke-valg
    # («P.Maufoux Pinot Noir» 209,95 kr til 2 dl sovs, 1,8× den billigste).
    favoritter = [
        x for x in felt if x.get("favorit") and _n(x.get("hovedgruppe")) not in FAVORIT_IKKE_I
    ]
    if favorit_loft_pct is not None:
        favoritter = [x for x in favoritter if _inden_for_loft(x, fuldt, favorit_loft_pct)]
    # … og kun i varens EGEN kategori: findes en vare der hedder præcis det
    # søgte («Quinoa øko.»), er dens blad hjemmet, og en favorit i et andet
    # blad («Quinoa knækbrød») er en anden mad, selv om navnet passer.
    hjem = {x.get("undergruppe") for x in fuldt if x.get("praecis") and x.get("ekstra") == (0, 0)}
    if hjem:
        favoritter = [x for x in favoritter if x.get("undergruppe") in hjem]
    if favoritter:
        felt = favoritter

    # MEST GENERISK (2026-10-01): beder opskriften om "agurk", er «Agurk» det
    # svar, ikke «Skole agurker»; "kødboller" er ikke «Kødboller
    # (plantebaseret)»; "rejer" er ikke «Rejer m. ramsløg». Uden dette afgjorde
    # prisen pr. styk — og et styk snackagurk koster en tredjedel af en agurk.
    # EFTER favoritterne: et tidligere køb («Basilikum Grøn», «Edamame
    # (pillede)») er et ægte signal, "færrest ord" kun en standard. Kun blandt
    # navne-træf: et kategori-træf (vin) har intet navn at være generisk med.
    if navne_traef and all(x.get("ekstra") is not None for x in felt):
        mindst = min(x["ekstra"] for x in felt)
        felt = [x for x in felt if x["ekstra"] == mindst]

    def billigst(xs):
        med = [x for x in xs if x.get("enhedspris")]
        return min(med, key=lambda x: x["enhedspris"]) if med else (xs[0] if xs else None)

    ikke_oeko = [x for x in felt if not x["oeko"]]
    oeko = [x for x in felt if x["oeko"]]
    # Referencen tages fra HELE feltet, ikke kun favoritterne (2026-10-01).
    # Var alle favoritter øko, fandtes der ingen konventionel reference blandt
    # dem, og øko-loftet blev SPRUNGET OVER med begrundelsen "ingen
    # sammenlignelig konventionel pris" — selv om den stod i samme felt. Målt:
    # «Hakket spinat øko.» til 4,4× og «Ærter øko.» til 3,5× brugerens
    # konventionelle alternativ, med loftet sat til 80 %.
    fuldt_ikke_oeko = [x for x in fuldt if not x["oeko"]]
    reference = billigst(ikke_oeko) or billigst(fuldt_ikke_oeko)

    if oeko_loft_pct is not None and oeko:
        kandidat = billigst(oeko)
        if reference is None or not _sammenlignelig(kandidat, reference):
            # Ingen sammenlignelig konventionel pris → loftet kan ikke afgøres.
            # Vi vælger øko, men siger hvorfor prøven ikke blev taget.
            return kandidat, "øko (ingen sammenlignelig konventionel pris)", reference
        loft = reference["enhedspris"] * (1.0 + oeko_loft_pct / 100.0)
        if kandidat["enhedspris"] <= loft:
            merpris = kandidat["enhedspris"] - reference["enhedspris"]
            pct = (merpris / reference["enhedspris"] * 100.0) if reference["enhedspris"] else 0
            return kandidat, f"øko (+{pct:.0f}% pr. enhed, loft {oeko_loft_pct:.0f}%)", reference
        # For dyr → konventionel, men sig hvor meget for dyr.
        pct = (kandidat["enhedspris"] / reference["enhedspris"] - 1) * 100.0
        felt = ikke_oeko or fuldt_ikke_oeko or felt
        valgt = _tilbud_eller_billigst(felt, foretraek_tilbud)
        return valgt, f"konventionel (øko var +{pct:.0f}%, over loft)", reference

    return _tilbud_eller_billigst(felt, foretraek_tilbud), "bedste pris", reference


FAVORIT_IKKE_I = {"vin og spiritus"}


def _inden_for_loft(x, felt, loft_pct):
    """Koster `x` højst loft_pct mere pr. enhed end den billigste
    SAMMENLIGNELIGE vare i feltet? Uden sammenlignelig pris: ja."""
    if not x.get("enhedspris"):
        return True
    andre = [y["enhedspris"] for y in felt if _sammenlignelig(x, y)]
    if not andre:
        return True
    return x["enhedspris"] <= min(andre) * (1.0 + loft_pct / 100.0) + 1e-9


def _tilbud_eller_billigst(felt, foretraek_tilbud):
    """Tilbud vinder — men kun hvis det faktisk er billigere pr. enhed.

    Et "tilbud" på en dyrere vare er stadig det dyre valg; rabatmærket alene
    er ikke en besparelse.
    """
    med_pris = [x for x in felt if x.get("enhedspris")]
    if not med_pris:
        return felt[0]
    billigste = min(med_pris, key=lambda x: x["enhedspris"])
    if foretraek_tilbud:
        tilbud = [x for x in med_pris if x["tilbud"]]
        if tilbud:
            bt = min(tilbud, key=lambda x: x["enhedspris"])
            if bt["enhedspris"] <= billigste["enhedspris"]:
                return bt
    return billigste


# =============================================================================
# Lært parring (vare-navn -> produkt-id)
# =============================================================================
def hent_varer():
    try:
        with open(VARER_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError, json.JSONDecodeError, OSError:
        return {}


def gem_varer(d):
    tmp = f"{VARER_FILE}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, VARER_FILE)


# =============================================================================
# CLI
# =============================================================================
def _linje(x):
    mark = ("*" if x["favorit"] else " ") + ("+" if x["paa_lager"] else "-")
    pak = x["pakning"] or (x["beskrivelse"] or "")[:18]
    return (
        f"{x['score']:.2f} {mark} {x['id']:>9}  "
        f"{(x['navn'] or '')[:40]:40}  {str(x['pris']):>7} kr  [{pak}]"
    )


def main():
    ap = argparse.ArgumentParser(description="Nemlig.com-klient")
    ap.add_argument("--ping", action="store_true", help="verificér login")
    ap.add_argument("--search", metavar="TEKST")
    ap.add_argument("--basket", action="store_true")
    ap.add_argument("--add", metavar="ID")
    ap.add_argument("--antal", type=int, default=1)
    ap.add_argument("--ryd", action="store_true", help="tøm kurven")
    ap.add_argument("--take", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    try:
        n = Nemlig(dry=a.dry)
        if a.ping:
            n.login(tvungen=True)
            b = n.basket()
            print(
                json.dumps(
                    {
                        "ok": True,
                        "kurv_linjer": len(b.get("Lines") or []),
                        "kurv_total": b.get("TotalPrice"),
                        "min_ordre": b.get("MinimumOrderTotal"),
                    },
                    ensure_ascii=False,
                )
            )
        elif a.search:
            r = find_bedste(n.search(a.search, a.take), a.search)
            if a.json:
                print(
                    json.dumps(
                        [{k: v for k, v in x.items() if k != "_raw"} for x in r],
                        ensure_ascii=False,
                        indent=1,
                    )
                )
            else:
                for x in r:
                    print(_linje(x))
        elif a.basket:
            linjer = n.basket_linjer()
            if a.json:
                print(json.dumps(linjer, ensure_ascii=False, indent=1))
            else:
                print(
                    "\n".join(f"{x['antal']:>3} x {x['id']:>9}  {x['navn']}" for x in linjer)
                    or "(tom)"
                )
        elif a.add:
            n.add(a.add, a.antal)
            print(json.dumps({"ok": True, "id": a.add, "antal": a.antal}))
        elif a.ryd:
            print(json.dumps({"ok": True, "fjernet": n.ryd_kurv()}))
        else:
            ap.print_help()
    except (NemligFejl, RuntimeError) as e:
        print(json.dumps({"ok": False, "fejl": str(e)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
