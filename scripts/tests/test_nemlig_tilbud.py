"""Nemlig-tilbud (2026-11-14): kampagnepris, multikøb og tilbuds-kilden.

python3 -m unittest discover -s scripts/tests -p "test_nemlig*.py"

Rene funktioner + en falsk Nemlig — intet net, ingen konto.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import nemlig_api as NA  # noqa: E402
import nemlig_kurv as NK  # noqa: E402
import nemlig_tilbud as NT  # noqa: E402

OM_EN_UGE = (datetime.now(UTC) + timedelta(days=7)).isoformat().replace("+00:00", "Z")


def produkt(pid="1", pris=12.0, kamp=None, dage=30, gruppe="Kolonial", fav=True, lager=True):
    return {
        "Id": pid,
        "Name": f"Vare {pid}",
        "Price": pris,
        "UnitPriceCalc": pris,
        "UnitPriceLabel": "kr/stk",
        "Campaign": kamp,
        "SaleBeforeLastSalesDate": dage,
        "ProductMainGroupName": gruppe,
        "Favorite": fav,
        "Availability": {"IsAvailableInStock": lager, "IsDeliveryAvailable": lager},
        "Labels": [],
    }


def saet(m, total, slut=OM_EN_UGE, kode="KF", maks=0):
    return {
        "Type": "ProductCampaignMixOffer",
        "MinQuantity": m,
        "TotalPrice": total,
        "MaxQuantity": maks,
        "IntervalEnd": slut,
        "Code": kode,
    }


def rabat(pris, slut=OM_EN_UGE, kode="U"):
    return {
        "Type": "ProductCampaignDiscountPercent",
        "CampaignPrice": pris,
        "MinQuantity": 1,
        "IntervalEnd": slut,
        "Code": kode,
    }


class Kampagne(unittest.TestCase):
    def test_saet_tekst_og_pris(self):
        k = NA.kampagne(produkt(pris=110.0, kamp=saet(2, 206.95)))
        self.assertEqual(k["min_antal"], 2)
        self.assertEqual(k["tekst"], "2 for 206,95 kr (normalt 220)")
        self.assertFalse(k["madspild"])

    def test_rabat_tekst(self):
        k = NA.kampagne(produkt(pris=139.95, kamp=rabat(104.96)))
        self.assertEqual(k["min_antal"], 1)
        self.assertEqual(k["tekst"], "104,96 kr (normalt 139,95)")

    def test_udloebet_og_uden_besparelse_er_ingen_kampagne(self):
        gaar = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        self.assertIsNone(NA.kampagne(produkt(kamp=saet(2, 20, slut=gaar))))
        self.assertIsNone(NA.kampagne(produkt(pris=10.0, kamp=saet(2, 20))))
        self.assertFalse(NA.paa_tilbud(produkt(kamp=saet(2, 20, slut=gaar))))

    def test_madspild_er_um(self):
        self.assertTrue(NA.kampagne(produkt(kamp=rabat(6, kode="UM")))["madspild"])
        self.assertFalse(NA.kampagne(produkt(kamp=rabat(6, kode="US")))["madspild"])


class PrisOgMultikoeb(unittest.TestCase):
    K = {"min_antal": 2, "total": 20.0, "max_antal": 0}

    def test_kun_hele_saet_faar_saetprisen(self):
        self.assertEqual(NA.pris_for(self.K, 12, 3), 32.0)
        self.assertEqual(NA.pris_for(dict(self.K, max_antal=2), 12, 4), 44.0)
        self.assertEqual(NA.pris_for(None, 12, 3), 36.0)

    def test_oprunding(self):
        self.assertEqual(NA.multikoeb(self.K, 12, 1), (2, 8.0, 4.0))
        self.assertIsNone(NA.multikoeb(self.K, 12, 2))
        self.assertIsNone(NA.multikoeb(dict(self.K, max_antal=2), 12, 3))

    def test_gratis_oprunding(self):
        k = {"min_antal": 8, "total": 100.0, "max_antal": 0}
        self.assertEqual(NA.multikoeb(k, 15, 7), (8, -5.0, 20.0))

    def test_holdbar(self):
        self.assertTrue(NA.lager_holdbar(produkt(dage=30)))
        self.assertFalse(NA.lager_holdbar(produkt(dage=3)))
        self.assertTrue(NA.lager_holdbar(produkt(dage=0, gruppe="Husholdning")))
        self.assertFalse(NA.lager_holdbar(produkt(dage=0, gruppe="Frugt & grønt")))
        self.assertFalse(NA.lager_holdbar(produkt(dage=30, kamp=rabat(6, kode="UM"))))


def beslutning(pid, antal=1, pris=12.0, k=None, holdbar=True, favorit=True):
    return {
        "navn": f"vare {pid}",
        "produkt": f"Vare {pid}",
        "id": pid,
        "antal": antal,
        "pris": pris,
        "status": "ok",
        "kampagne": k or {"min_antal": 2, "total": 20.0, "max_antal": 0, "tekst": "2 for 20 kr"},
        "holdbar": holdbar,
        "favorit": favorit,
    }


POLITIK = {"max_kr": 200.0, "min_pct": 15.0}


class Runding(unittest.TestCase):
    def test_runder_holdbar_favorit_op(self):
        r = NK.multikoeb_runding([beslutning("1")], {"1": 1}, {}, POLITIK)
        self.assertEqual(r["1"]["ekstra"], 1)
        self.assertEqual(r["1"]["i_alt"], 2)

    def test_kraever_holdbar_og_favorit_og_rabat(self):
        self.assertEqual(
            NK.multikoeb_runding([beslutning("1", favorit=False)], {"1": 1}, {}, POLITIK), {}
        )
        self.assertEqual(
            NK.multikoeb_runding([beslutning("1", holdbar=False)], {"1": 1}, {}, POLITIK), {}
        )
        self.assertEqual(
            NK.multikoeb_runding([beslutning("1")], {"1": 1}, {}, dict(POLITIK, min_pct=50)), {}
        )
        self.assertEqual(NK.multikoeb_runding([beslutning("1")], {"1": 1}, {}, None), {})

    def test_den_anden_kildes_stk_tæller_med(self):
        self.assertEqual(NK.multikoeb_runding([beslutning("1")], {"1": 1}, {"1": 1}, POLITIK), {})

    def test_budget_og_gratis(self):
        dyr = {"min_antal": 2, "total": 300.0, "max_antal": 0, "tekst": "2 for 300"}
        gratis = {"min_antal": 8, "total": 100.0, "max_antal": 0, "tekst": "8 for 100"}
        b = [
            beslutning("1", pris=200.0, k=dyr),
            beslutning("2", pris=15.0, k=gratis, holdbar=False, favorit=False),
        ]
        r = NK.multikoeb_runding(b, {"1": 1, "2": 7}, {}, dict(POLITIK, max_kr=50))
        self.assertNotIn("1", r)  # 100 kr ekstra > 50 kr
        self.assertEqual(r["2"]["ekstra"], 1)  # billigere end ikke at runde op


class FalskNemlig:
    def __init__(self, kurv=None):
        self.kurv = dict(kurv or {})
        self.kald = []

    def basket_linjer(self):
        return [{"id": k, "antal": v} for k, v in self.kurv.items()]

    def add(self, pid, antal):
        self.kald.append((pid, antal))
        if antal:
            self.kurv[pid] = antal
        else:
            self.kurv.pop(pid, None)


class LaegIKurv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fil = os.path.join(self.tmp, "kurv.json")
        self.p = mock.patch.object(NK, "KOERSEL_FIL", self.fil)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_ekstra_staar_i_antal_og_raekken(self):
        n = FalskNemlig()
        b = [beslutning("1")]
        lagt, _ = NK.laeg_i_kurv(n, b, multikoeb=POLITIK)
        self.assertEqual(n.kald, [("1", 2)])
        self.assertEqual(lagt, [{"id": "1", "antal": 2, "kilde": NK.KILDE_LISTE, "ekstra": 1}])
        self.assertEqual(b[0]["multikoeb"]["ekstra"], 1)
        # Næste kørsel: kurven matcher regnskabet → ingen "rettet i hånden".
        NK.gem_koersel(lagt)
        n2 = FalskNemlig(n.kurv)
        lagt2, _ = NK.laeg_i_kurv(n2, [beslutning("1")], multikoeb=POLITIK)
        self.assertEqual(n2.kald, [("1", 2)])
        self.assertEqual(lagt2, lagt)

    def test_slaaet_fra_runder_ikke(self):
        n = FalskNemlig()
        lagt, _ = NK.laeg_i_kurv(n, [beslutning("1")], multikoeb=None)
        self.assertEqual(n.kald, [("1", 1)])
        self.assertNotIn("ekstra", lagt[0])


class TilbudsKilden(unittest.TestCase):
    def test_filter_og_budget(self):
        faste = {
            "1": {"navn": "kaffe", "gange": 4, "stk": 4},
            "2": {"navn": "kylling", "gange": 5, "stk": 5},
            "3": {"navn": "tun", "gange": 3, "stk": 9},
            "4": {"navn": "engang", "gange": 1, "stk": 1},
            "5": {"navn": "pasta", "gange": 2, "stk": 2},
        }
        varer = [
            produkt("1", pris=240.5, kamp=saet(2, 399)),  # holdbar, 17 %
            produkt("2", pris=60.0, kamp=saet(2, 90), dage=4),  # ikke holdbar
            produkt("3", pris=12.0, kamp=saet(3, 25)),  # 31 %, typisk 3 stk
            produkt("4", pris=12.0, kamp=saet(3, 25)),  # kun købt én gang
            produkt("5", pris=20.0, kamp=saet(2, 30), lager=False),  # udsolgt
        ]
        n = mock.Mock()
        n.tilbud.return_value = varer
        with mock.patch.object(NA, "faste_varer", return_value=faste):
            valgt, over = NK.tilbud_beslutninger(n, 300.0, 15.0)
        self.assertEqual([b["id"] for b in valgt], ["3"])  # mest sparet pr. krone
        self.assertEqual(valgt[0]["antal"], 3)
        self.assertEqual([b["id"] for b in over], ["1"])  # 399 kr > budget

    def test_springer_varer_i_kurven_over_men_ikke_vores_egne(self):
        faste = {"3": {"navn": "tun", "gange": 3, "stk": 9}}
        n = mock.Mock()
        n.tilbud.return_value = [produkt("3", pris=12.0, kamp=saet(3, 25))]
        with mock.patch.object(NA, "faste_varer", return_value=faste):
            self.assertEqual(NK.tilbud_beslutninger(n, 300.0, 15.0, {"3": 1})[0], [])
            igen, _ = NK.tilbud_beslutninger(n, 300.0, 15.0, {"3": 3}, {"3": 3})
        self.assertEqual([b["id"] for b in igen], ["3"])


class SensorRaekker(unittest.TestCase):
    def test_kampagnen_bliver_tekst(self):
        b = beslutning("1")
        b["spar_kr"] = 0.0
        v = NK.til_sensor(b)
        self.assertEqual(v["tilbud_tekst"], "2 for 20 kr")
        for k in ("kampagne", "holdbar", "favorit", "spar_kr"):
            self.assertNotIn(k, v)
        json.dumps(v)


class SoegeLoft(unittest.TestCase):
    """Searchgatewayen når kun de første 100 (målt 15/11) → målrettede søgninger."""

    def _n(self, svar):
        n = NA.Nemlig.__new__(NA.Nemlig)
        n.kald = []

        def gw(params):
            n.kald.append(params["query"])
            ps, found = svar[params["query"]]
            return {"Products": {"Products": ps, "NumFound": found}}

        n._gateway = gw
        return n

    def test_under_loftet_ingen_ekstra_soegning(self):
        n = self._n({"*": ([{"Id": 1}], 1)})
        self.assertEqual(len(n.tilbud(soeg=["kylling"])), 1)
        self.assertEqual(n.kald, ["*"])

    def test_over_loftet_soeger_og_deduperer(self):
        n = self._n({"*": ([{"Id": 1}, {"Id": 2}], 500), "kylling": ([{"Id": 2}, {"Id": 3}], 2)})
        ud = n.tilbud(kun_favoritter=False, soeg=["kylling", "kylling", " "])
        self.assertEqual([p["Id"] for p in ud], [1, 2, 3])
        self.assertEqual(n.kald, ["*", "kylling"])

    def test_faste_soegeord(self):
        f = {"1": {"navn": "Smør, saltet"}, "2": {"navn": "Smør usaltet"}, "3": {"navn": "Æg"}}
        self.assertEqual(NA.faste_soegeord(f), ["smør"])


def tilbud_(navn, vareart, pct, madspild=False):
    return {
        "navn": navn,
        "vareart": vareart,
        "rabat_pct": pct,
        "spar_kr": pct,  # 1 kr pr. % — nok til at teste mætningen ved 40 kr
        "tekst": f"-{pct} %",
        "madspild": madspild,
    }


class MatcherTest(unittest.TestCase):
    CACHE = {
        "kyllingebryst": [
            {"ProductSubGroupName": "Kylling filet, fersk", "ProductMainGroupName": "Kød"}
        ]
    }

    def test_vareart_rammer_enhver_variant(self):
        m = NT.Matcher([tilbud_("Kyllingebrystfilet øko.", "Kylling filet, fersk", 20)], self.CACHE)
        bonus, t = m.ret([(500, "g", "kyllingebryst")])
        self.assertAlmostEqual(bonus, 0.5)
        self.assertEqual(len(t), 1)

    def test_navne_fallback_og_maetning(self):
        m = NT.Matcher(
            [tilbud_("Citroner øko.", "Citrusfrugt", 30), tilbud_("Laksestykke", "Laks", 34)], {}
        )
        bonus, t = m.ret([(1, "stk", "citroner"), (400, "g", "laksestykke")])
        self.assertEqual(bonus, 1.0)
        self.assertEqual(len(t), 2)

    def test_madspild_tæller_ikke_men_korte_navneord(self):
        m = NT.Matcher([tilbud_("Ost", "Ost", 50), tilbud_("Laks", "Laks", 40, madspild=True)], {})
        self.assertEqual(m.ret([(1, "", "laks")])[0], 0.0)  # madspild tæller ikke
        self.assertEqual(m.ret([(1, "", "ost")])[0], 0.5)  # 3-bogstavs navneord duer; loft 20 kr

    def test_fyldord_og_basis(self):
        m = NT.Matcher([tilbud_("Chili rød", "Chili", 30), tilbud_("Peberfrugt", "Peber", 20)], {})
        self.assertEqual(len(m.rammer("rød peberfrugt")), 1)  # kun peberfrugten
        self.assertEqual(m.ret([(1, "", "rød peberfrugt")], frozenset({"rød peberfrugt"}))[0], 0)


if __name__ == "__main__":
    unittest.main()
