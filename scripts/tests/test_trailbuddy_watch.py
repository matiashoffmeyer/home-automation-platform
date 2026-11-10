"""Trail Buddy-vagten: bevægelse, 24 t-alarmen for hele gruppen og tidsplanen.

python3 -m unittest discover -s scripts/tests -p "test_trailbuddy_watch*.py"
"""

import os
import sys
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import trailbuddy_watch as tw  # noqa: E402

PLAN = [
    {"day": 1, "date": date(2026, 11, 8), "km_end": 24.0},
    {"day": 2, "date": date(2026, 11, 9), "km_end": 48.0},
    {"day": 3, "date": date(2026, 11, 10), "km_end": 72.0},
]
H = 3600_000
LAT, LON = 36.55, 29.12  # Lykien


def ms(y, mo, d, h=12, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=tw.TRIP_TZ).timestamp() * 1000


def fix(name, t, dlat=0.0, **kw):
    return {
        "name": name,
        "lat": LAT + dlat,
        "lon": LON,
        "time": t,
        "accuracy": 10,
        "offRoute": 20,
        **kw,
    }


class Watch(unittest.TestCase):
    def run_fixes(self, *batches):
        state = {"members": {}}
        for b in batches:
            tw.update_members(state, b, 250)
        return state

    def test_walking_is_moving(self):
        t = ms(2026, 11, 9, 10)
        s = self.run_fixes(
            [fix("A", t - 10 * 60_000)], [fix("A", t, dlat=0.005, along=30000, toGo=42000)]
        )
        out = tw.evaluate(s, PLAN, t + 60_000, 24, True)
        self.assertTrue(out["bevaeger_sig"])
        self.assertEqual(out["state"], "Går")
        self.assertIn("Følger planen", out["tidsplan"])

    def test_renamed_hiker_is_pruned(self):
        t = ms(2026, 11, 9, 10)
        s = self.run_fixes([fix("Old", t - H), fix("B", t - H)], [fix("New", t), fix("B", t)])
        self.assertEqual(sorted(s["members"]), ["b", "new"])

    def test_empty_fetch_prunes_nothing(self):
        t = ms(2026, 11, 9, 10)
        s = self.run_fixes([fix("A", t)], [])
        self.assertEqual(list(s["members"]), ["a"])

    def test_jitter_is_not_movement(self):
        t = ms(2026, 11, 9, 10)
        s = self.run_fixes([fix("A", t - 3 * H)], [fix("A", t, dlat=0.001)])  # ~110 m
        out = tw.evaluate(s, PLAN, t + 60_000, 24, True)
        self.assertFalse(out["bevaeger_sig"])
        self.assertEqual(out["state"], "Pause")
        self.assertEqual(out["sidst_bevaeget"], tw.iso(t - 3 * H))

    def test_whole_group_still_24h_alarms(self):
        t = ms(2026, 11, 9, 10)
        s = self.run_fixes([fix("A", t), fix("B", t)], [fix("A", t + 20 * H), fix("B", t + 23 * H)])
        out = tw.evaluate(s, PLAN, t + 25 * H, 24, True)
        self.assertTrue(out["stille"])
        self.assertEqual(out["stille_grund"], "stillestående")

    def test_one_member_moving_holds_alarm(self):
        t = ms(2026, 11, 9, 10)
        s = self.run_fixes([fix("A", t), fix("B", t)], [fix("B", t + 20 * H, dlat=0.01)])
        self.assertFalse(tw.evaluate(s, PLAN, t + 25 * H, 24, True)["stille"])

    def test_no_signal_alarms(self):
        t = ms(2026, 11, 9, 10)
        s = self.run_fixes([fix("A", t)])
        out = tw.evaluate(s, PLAN, t + 24 * H + 1, 24, False)
        self.assertTrue(out["stille"])
        self.assertEqual(out["stille_grund"], "intet signal")

    def test_home_positions_before_trip_do_not_alarm_on_day_one(self):
        s = self.run_fixes([fix("A", ms(2026, 11, 5))])
        self.assertFalse(tw.evaluate(s, PLAN, ms(2026, 11, 8, 20), 24, True)["stille"])
        self.assertTrue(tw.evaluate(s, PLAN, ms(2026, 11, 9, 1), 24, True)["stille"])

    def test_someone_at_home_is_not_a_hiker(self):
        t = ms(2026, 11, 9, 10)
        home = {"name": "C", "lat": 55.7, "lon": 12.5, "time": t + 24 * H, "offRoute": 2_500_000}
        s = self.run_fixes([fix("A", t), home])
        out = tw.evaluate(s, PLAN, t + 25 * H, 24, True)
        self.assertTrue(out["stille"])
        self.assertEqual([v["navn"] for v in out["vandrere"]], ["A"])

    def test_pasted_pin_is_not_movement(self):
        t = ms(2026, 11, 9, 10)
        s = self.run_fixes([fix("A", t)], [fix("A", t + 23 * H, dlat=0.05, manual=True)])
        self.assertTrue(tw.evaluate(s, PLAN, t + 25 * H, 24, True)["stille"])

    def test_inactive_after_trip(self):
        s = self.run_fixes([fix("A", ms(2026, 11, 10))])
        out = tw.evaluate(s, PLAN, ms(2026, 11, 14, 12), 24, True)
        self.assertFalse(out["aktiv"])
        self.assertFalse(out["stille"])
        self.assertEqual(out["state"], "Turen er slut")

    def test_schedule_behind_and_ahead(self):
        today = date(2026, 11, 10)
        self.assertEqual(tw.schedule(PLAN, 40.0, None, today)["tidsplan"], "Bagud (8.0 km)")
        self.assertEqual(tw.schedule(PLAN, 75.0, None, today)["tidsplan"], "Foran planen (3.0 km)")
        self.assertEqual(tw.schedule(PLAN, 71.8, None, today)["tidsplan"], "Dagens etape er gået")
        # Ruten er 10 % længere end planen: dagens lejr flytter med.
        self.assertEqual(tw.schedule(PLAN, 75.0, 79.2, today)["plan_km_slut"], 79.2)

    def test_real_plan_parses(self):
        if os.path.exists(tw.PLAN_FILE):
            plan = tw.load_plan()
            self.assertEqual(plan[0]["date"], date(2026, 11, 8))
            self.assertEqual([d["km_end"] for d in plan][:2], [24.0, 48.0])


if __name__ == "__main__":
    unittest.main()
