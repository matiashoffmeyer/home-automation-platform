"""Gødnings-kvittering (user-spec 2026-10-05): ✅ på pushen, ellers igen i morgen.

python3 -m unittest discover -s scripts/tests -p "test_plant*.py"
"""

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import plant_notify as pn  # noqa: E402

COLS = {
    pn.COL_ID: "ID",
    pn.COL_NAVN: "Kaldenavn",
    pn.COL_PLACERING: "Placering",
    pn.COL_NOTIF: None,
    pn.COL_BESKED: None,
    **{c: c for c in pn.COL_FREQ.values()},
}


def row(pid, navn, plac, efteraar):
    return {
        "ID": pid,
        "Kaldenavn": navn,
        "Placering": plac,
        pn.COL_FREQ["efterår"]: str(efteraar),
        pn.COL_FREQ["sommer"]: "0",
        pn.COL_FREQ["forår"]: "0",
        pn.COL_FREQ["vinter"]: "0",
    }


ROWS = [
    row("4", "Monstera", "Stue", 2),
    row("22", "Fikus", "Køkken", 1),
    row("99", "Kaktus", "Stue", 0),
]
D0 = date(2026, 10, 5)


class Sender:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    def __call__(self, title, msg, payload=None):
        self.sent.append((title, msg, payload))
        return self.ok


class GoedningsKvittering(unittest.TestCase):
    def setUp(self):
        # Begge forfaldne i dag, kaktussen har ingen efterårs-gødning.
        self.state = {"fert_next:4": D0.isoformat(), "fert_next:22": D0.isoformat()}

    def run_day(self, day, ok=True):
        s = Sender(ok)
        pn.process_fertilizer(ROWS, COLS, self.state, day, s)
        return s.sent

    def test_push_baerer_done_og_flytter_ikke_datoen(self):
        sent = self.run_day(D0)
        self.assertEqual(len(sent), 1)
        acts = [a["action"] for a in sent[0][2]["actions"]]
        self.assertEqual(acts, ["PLANT_FERT_DONE", "PLANT_FERT_SNOOZE7"])
        self.assertEqual(self.state["fert_next:4"], D0.isoformat())
        self.assertEqual(self.state["_fert_last"]["status"], "afventer")
        self.assertEqual({p["id"] for p in self.state["_fert_last"]["planter"]}, {"4", "22"})

    def test_genstart_samme_dag_gentager_ikke(self):
        self.run_day(D0)
        self.assertEqual(self.run_day(D0), [])

    def test_ukvitteret_kommer_igen_naeste_dag(self):
        self.run_day(D0)
        sent = self.run_day(D0 + timedelta(days=1))
        self.assertEqual(len(sent), 1)
        self.assertIn("Stadig ikke gødet", sent[0][0])
        self.assertIn("Venter siden 5/10", sent[0][1])
        self.assertEqual(self.state["_fert_last"]["antal"], 2)
        self.assertEqual(self.state["_fert_last"]["foerst"], D0.isoformat())

    def test_ikke_leveret_push_er_ikke_sendt(self):
        self.run_day(D0, ok=False)
        self.assertNotIn("_fert_last", self.state)
        self.assertEqual(len(self.run_day(D0)), 1)

    def test_done_laegger_interval_fra_kvitteringsdagen(self):
        self.run_day(D0)
        dag3 = D0 + timedelta(days=2)
        rc, st = pn.apply_fert_action("done", today=dag3, state=self.state)
        self.assertEqual(rc, 0)
        self.assertEqual(st["fert_next:4"], (dag3 + timedelta(days=15)).isoformat())  # 2×/md
        self.assertEqual(st["fert_next:22"], (dag3 + timedelta(days=30)).isoformat())  # 1×/md
        self.assertEqual(st["fert_sidst:4"], dag3.isoformat())
        self.assertEqual(st["_fert_last"]["status"], "gødet")
        # Listen ligger der stadig til siden ("in case jeg glemmer det").
        self.assertEqual(len(st["_fert_last"]["planter"]), 2)
        self.assertEqual(self.run_day(dag3 + timedelta(days=1)), [])

    def test_snooze_en_uge_og_saa_igen(self):
        self.run_day(D0)
        pn.apply_fert_action("snooze7", today=D0, state=self.state)
        self.assertEqual(self.state["fert_next:4"], (D0 + timedelta(days=7)).isoformat())
        self.assertEqual(self.run_day(D0 + timedelta(days=6)), [])
        sent = self.run_day(D0 + timedelta(days=7))
        self.assertEqual(len(sent), 1)
        self.assertIn("Venter siden 5/10", sent[0][1])

    def test_lukket_batch_fra_tidligere_dag_roeres_ikke(self):
        self.run_day(D0)
        pn.apply_fert_action("done", today=D0, state=self.state)
        foer = dict(self.state)
        pn.apply_fert_action("done", today=D0 + timedelta(days=4), state=self.state)
        self.assertEqual(self.state["fert_next:4"], foer["fert_next:4"])

    def test_samme_dag_maa_man_ombestemme_sig(self):
        self.run_day(D0)
        pn.apply_fert_action("snooze7", today=D0, state=self.state)
        pn.apply_fert_action("done", today=D0, state=self.state)
        self.assertEqual(self.state["_fert_last"]["status"], "gødet")
        self.assertEqual(self.state["fert_next:4"], (D0 + timedelta(days=15)).isoformat())

    def test_ukendt_act_afvises(self):
        rc, _ = pn.apply_fert_action("rm -rf", today=D0, state=self.state)
        self.assertEqual(rc, 1)

    def test_migrering_af_gammel_push(self):
        st = {
            "_fert_sent_date": "2026-10-02",
            "_fert_sent_ids": ["4", "22", "slettet"],
            "fert_next:4": "2026-10-17",
            "fert_next:22": "2026-11-01",
        }
        pn.migrate_legacy_batch(st, ROWS, COLS)
        self.assertNotIn("_fert_sent_ids", st)
        self.assertEqual(st["_fert_last"]["status"], "afventer")
        self.assertEqual(st["fert_next:4"], "2026-10-02")
        self.assertEqual([p["id"] for p in st["_fert_last"]["planter"]], ["4", "22"])
        self.state = st
        sent = self.run_day(D0)
        self.assertIn("Venter siden 2/10", sent[0][1])

    def test_sidens_tekst(self):
        self.assertEqual(pn.sidste_goedning({}, D0)["status_tekst"], "")
        self.run_day(D0)
        self.assertIn("Venter på ✅", pn.sidste_goedning(self.state, D0)["status_tekst"])
        self.run_day(D0 + timedelta(days=1))
        self.assertIn("2× i alt", pn.sidste_goedning(self.state, D0)["status_tekst"])
        pn.apply_fert_action("done", today=D0 + timedelta(days=1), state=self.state)
        self.assertEqual(pn.sidste_goedning(self.state, D0)["status_tekst"], "✅ Gødet 6/10")


if __name__ == "__main__":
    unittest.main()
