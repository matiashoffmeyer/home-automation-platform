"""Offline-tests for scripts/hq.py — ingen HA, intet netværk.

    python3 -m unittest discover -s scripts/tests -p "test_hq*.py"

Dækker fælderne CLI'et findes for: lokal tid over DST (25/10 = den gentagne
time), end_time + døgn-chunking af /api/history, tids-vægtede fordelinger og
`who`'s attribution med FULD context-lighed (præfiks-fælden fra CLAUDE.md).
"""

import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.parse
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import hq  # noqa: E402

with open(os.path.join(HERE, "hq_fixture.json"), encoding="utf-8") as f:
    FIX = json.load(f)


def ts(s):
    return hq.parse_ts(s)


class FakeHA(hq.HA):
    """HA-klient der svarer fra fixturen og logger hvert kald."""

    def __init__(self, responses):
        super().__init__("http://fake", "tok")
        self.responses, self.calls = responses, []

    def req(self, path, params=None, body=None, raw=False):
        self.calls.append((path, dict(params or {})))
        start = urllib.parse.unquote(path.rsplit("/", 1)[1])
        return self.responses.get(start, [[]])


class TestTime(unittest.TestCase):
    def test_dst_points_fallback_rule(self):
        # PC'en har ingen tzdata → EU-reglen skal ramme det samme som zoneinfo
        saved, hq.LOCAL = hq.LOCAL, None
        try:
            for utc_s, want in FIX["dst_points"]:
                self.assertEqual(hq.fmt_t(ts(utc_s)), want, utc_s)
        finally:
            hq.LOCAL = saved

    @unittest.skipIf(hq.LOCAL is None, "ingen tzdata på denne maskine")
    def test_fallback_matches_zoneinfo_hourly_2026_2027(self):
        t = datetime(2026, 1, 1, tzinfo=UTC)
        while t < datetime(2028, 1, 1, tzinfo=UTC):
            self.assertEqual(
                hq.to_local(t).utcoffset(), hq.to_local(t, use_zoneinfo=False).utcoffset(), t
            )
            t += timedelta(minutes=30)

    def test_from_local_ambiguous_and_gap(self):
        f = lambda *a: hq.from_local(datetime(*a), use_zoneinfo=False)  # noqa: E731
        self.assertEqual(
            f(2026, 10, 25, 2, 30), ts("2026-10-25T00:30:00+00:00")
        )  # fold=0 = sommertid
        self.assertEqual(
            f(2026, 3, 29, 2, 30), ts("2026-03-29T01:30:00+00:00")
        )  # findes ikke → vintertid
        self.assertEqual(f(2026, 7, 1, 12, 0), ts("2026-07-01T10:00:00+00:00"))
        self.assertEqual(f(2026, 12, 1, 12, 0), ts("2026-12-01T11:00:00+00:00"))

    def test_parse_when(self):
        ref = ts("2026-10-05T10:00:00+00:00")  # 12:00 lokal
        self.assertEqual(hq.parse_when("3d", ref), ref - timedelta(days=3))
        self.assertEqual(hq.parse_when("90m", ref), ref - timedelta(minutes=90))
        self.assertEqual(hq.parse_when("2t", ref), ref - timedelta(hours=2))
        self.assertEqual(hq.parse_when("11:00", ref), ts("2026-10-05T09:00:00+00:00"))
        self.assertEqual(
            hq.parse_when("13:00", ref), ts("2026-10-04T11:00:00+00:00")
        )  # fremtid → i går
        self.assertEqual(hq.parse_when("2026-10-04 18:00", ref), ts("2026-10-04T16:00:00+00:00"))
        with self.assertRaises(hq.HQError):
            hq.parse_when("igår", ref)

    def test_fmt_dur(self):
        self.assertEqual(
            [hq.fmt_dur(x) for x in (5, 75, 3660, 90000)], ["5s", "1m15s", "1h01m", "1d01h"]
        )

    def test_fnum_keeps_integer_zeros(self):
        # review 10-05: 110.4 blev "11" (rstrip('0') på et tal uden decimalpunktum)
        self.assertEqual(
            [hq.fnum(x) for x in (110.4, 150.5, 2e7, 1203, 45.67, 0.8123, 0.0, -3.5)],
            ["110", "150", "20000000", "1203", "45.7", "0.812", "0", "-3.5"],
        )

    def test_hhmm_uses_local_calendar_on_dst_days(self):
        saved, hq.LOCAL = hq.LOCAL, None
        try:
            ref = ts("2026-10-25T11:00:00+00:00")  # 12:00 CET på vintertids-dagen
            self.assertEqual(
                hq.parse_when("13:00", ref), ts("2026-10-24T11:00:00+00:00")
            )  # i går 13:00 CEST
            self.assertEqual(hq.parse_when("23:30", ref), ts("2026-10-24T21:30:00+00:00"))
            # i den gentagne time vinder den SENESTE forekomst ≤ nu
            ref2 = ts("2026-10-25T01:45:00+00:00")  # 02:45 CET (anden gang)
            self.assertEqual(hq.parse_when("02:30", ref2), ts("2026-10-25T01:30:00+00:00"))
            ref3 = ts("2026-10-25T00:45:00+00:00")  # 02:45 CEST (første gang)
            self.assertEqual(hq.parse_when("02:30", ref3), ts("2026-10-25T00:30:00+00:00"))
            with self.assertRaises(hq.HQError):
                hq.parse_when("24:00", ref)
        finally:
            hq.LOCAL = saved

    def test_local_candidates(self):
        c = lambda *a: hq.local_candidates(datetime(*a), use_zoneinfo=False)  # noqa: E731
        self.assertEqual(len(c(2026, 10, 25, 2, 30)), 2)
        self.assertEqual(len(c(2026, 10, 25, 3, 30)), 1)
        self.assertEqual(c(2026, 3, 29, 2, 30), [ts("2026-03-29T01:30:00+00:00")])


class TestHistory(unittest.TestCase):
    def test_dst_window_rows_and_end_time(self):
        d = FIX["dst_window"]
        ha = FakeHA(d["responses"])
        rows = ha.history(d["entity"], ts(d["since_utc"]), ts(d["until_utc"]))
        self.assertEqual([[hq.fmt_t(t), v] for t, v in rows], d["expected_rows_local"])
        self.assertEqual(len(ha.calls), d["expected_chunks"])
        for path, params in ha.calls:
            self.assertIn(
                "end_time", params, "end_time SKAL med — ellers trunkerer HA tavst til 1 døgn"
            )
            a = ts(urllib.parse.unquote(path.rsplit("/", 1)[1]))
            self.assertLessEqual(ts(params["end_time"]) - a, timedelta(hours=24))
            self.assertIn("minimal_response", params)

    def test_30_day_chunking(self):
        c = FIX["chunking_30d"]
        s, e = ts(c["since_utc"]), ts(c["until_utc"])
        ch = hq.chunks(s, e)
        self.assertEqual(len(ch), c["expected_chunks"])
        self.assertEqual(ch[0][0], s)
        self.assertEqual(ch[-1][1], e)
        for (_a1, b1), (a2, _) in zip(ch, ch[1:]):
            self.assertEqual(b1, a2)  # ingen huller, intet overlap
        self.assertTrue(all(b - a <= timedelta(hours=c["max_chunk_hours"]) for a, b in ch))
        ha = FakeHA({})
        ha.history("sensor.x", s, e)
        self.assertEqual(len(ha.calls), 30)

    def test_attr_not_recorded_is_an_error(self):
        # review 10-05: en attribut recorderen ikke gemmer så ud som "None hele vinduet"
        s, e = ts("2026-10-01T00:00:00+00:00"), ts("2026-10-01T12:00:00+00:00")
        ha = FakeHA(
            {
                s.isoformat(): [
                    [
                        {
                            "entity_id": "light.x",
                            "state": "on",
                            "attributes": {"friendly_name": "X"},
                            "last_changed": s.isoformat(),
                            "last_updated": s.isoformat(),
                        }
                    ]
                ]
            }
        )
        with self.assertRaises(hq.HQError):
            ha.history("light.x", s, e, attr="brightness")
        self.assertEqual(ha.calls[0][1].get("significant_changes_only"), "0")
        self.assertNotIn("minimal_response", ha.calls[0][1])

    def _flanks(self, rows, argv):
        s = ts("2026-10-01T00:00:00+00:00")
        resp = [
            {
                "entity_id": "x.y",
                "state": rows[0][1],
                "last_changed": "2026-09-30T00:00:00+00:00",
                "last_updated": "2026-09-30T00:00:00+00:00",
            }
        ] + [
            {"state": v, "last_changed": (s + timedelta(minutes=m)).isoformat()}
            for m, v in rows[1:]
        ]
        ha = FakeHA({s.isoformat(): [resp]})
        a = hq.build_parser().parse_args(
            [
                "flanks",
                "x.y",
                "--since",
                "2026-10-01T00:00:00+00:00",
                "--until",
                "2026-10-01T06:00:00+00:00",
            ]
            + argv
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            hq.cmd_flanks(a, ha)
        return buf.getvalue()

    def test_min_prev_keeps_clipped_first_flank(self):
        # review 10-05: forrige state startede FØR vinduet → varigheden er kun en nedre grænse
        out = self._flanks([(0, "off"), (2, "on"), (3, "off"), (60, "on")], ["--min-prev", "30m"])
        self.assertIn("≥2m00s i off", out)  # klippet: beholdt
        self.assertIn("57m00s i off", out)  # ægte, ≥ 30m
        self.assertNotIn("1m00s i on", out)  # ægte, < 30m → filtreret

    def test_flank_summary_capped_for_numeric(self):
        rows = [(0, "0")] + [(i, str(i)) for i in range(1, 200)]
        out = self._flanks(rows, [])
        self.assertIn("numerisk entity", out)
        self.assertLess(len(out.splitlines()), hq.CAP + 5)

    def test_collapse_drops_boundary_repeats(self):
        t0 = ts("2026-10-01T00:00:00+00:00")
        rows = [(t0, "on"), (t0 + timedelta(hours=24), "on"), (t0 + timedelta(hours=25), "off")]
        self.assertEqual([v for _, v in hq.collapse(rows)], ["on", "off"])


class TestStats(unittest.TestCase):
    def setUp(self):
        self.t0 = ts("2026-10-01T00:00:00+00:00")

    def test_time_weighted_vs_samples_and_gate(self):
        # 0 i 9 timer, 100 i 1 time, ti korte 50'ere på 1 minut hver
        rows, t = [(self.t0, "0")], self.t0 + timedelta(hours=9)
        rows.append((t, "100"))
        t += timedelta(hours=1)
        for _ in range(10):
            rows += [(t, "50"), (t + timedelta(minutes=1), "0")]
            t += timedelta(minutes=2)
        end = t
        out = hq.stats_lines(rows, end, gate=60)
        self.assertTrue(out[0].startswith("samples\tn 22"), out[0])
        self.assertIn("p50 0", out[1])  # tids-vægtet median = 0, ikke 50
        self.assertIn("over 1h00m", out[2])
        self.assertIn("krydsninger op: 1", out[2])

    def test_unavailable_reported_separately(self):
        rows = [
            (self.t0, "10"),
            (self.t0 + timedelta(hours=1), "unavailable"),
            (self.t0 + timedelta(hours=2), "12"),
        ]
        out = hq.stats_lines(rows, self.t0 + timedelta(hours=3))
        self.assertTrue(any(line.startswith("ikke-tal\tunavailable 1h00m") for line in out), out)

    def test_state_distribution_for_binary(self):
        rows = [
            (self.t0, "off"),
            (self.t0 + timedelta(minutes=50), "on"),
            (self.t0 + timedelta(minutes=60), "off"),
        ]
        out = hq.stats_lines(rows, self.t0 + timedelta(hours=2))
        self.assertEqual(out[0], "state\tn\ttid\tandel\tp50-varighed\tmax")
        self.assertTrue(out[1].startswith("off\t2\t1h50m"), out[1])
        self.assertTrue(out[2].startswith("on\t1\t10m00s"), out[2])

    def test_numeric_decided_by_time_not_count(self):
        # mest unavailable i ANTAL, men tal det meste af TIDEN → stadig tal-fordeling + gate
        rows = [(self.t0, "unavailable")]
        t = self.t0 + timedelta(seconds=5)
        for i in range(5):
            rows += [(t, str(10 + i)), (t + timedelta(hours=1), "unavailable")]
            t += timedelta(hours=1, seconds=5)
        out = hq.stats_lines(rows, t, gate=12)
        self.assertTrue(out[0].startswith("samples"), out)
        self.assertTrue(any(line.startswith("gate 12") for line in out), out)

    def test_gate_on_categorical_says_ignored(self):
        rows = [(self.t0, "off"), (self.t0 + timedelta(minutes=5), "on")]
        out = hq.stats_lines(rows, self.t0 + timedelta(minutes=10), gate=1)
        self.assertTrue(out[0].startswith("# --gate ignoreret"), out)

    def test_tw_pct(self):
        self.assertEqual(hq.tw_pct([(1, 90), (100, 10)], 0.5), 1)
        self.assertEqual(hq.tw_pct([(1, 90), (100, 10)], 0.95), 100)


SCHEMA = """
CREATE TABLE states_meta (metadata_id INTEGER PRIMARY KEY, entity_id TEXT);
CREATE TABLE state_attributes (attributes_id INTEGER PRIMARY KEY, shared_attrs TEXT);
CREATE TABLE states (state_id INTEGER PRIMARY KEY, state TEXT, last_updated_ts REAL, last_changed_ts REAL,
  context_id_bin BLOB, context_user_id_bin BLOB, context_parent_id_bin BLOB, metadata_id INTEGER,
  old_state_id INTEGER, attributes_id INTEGER);
CREATE TABLE event_types (event_type_id INTEGER PRIMARY KEY, event_type TEXT);
CREATE TABLE event_data (data_id INTEGER PRIMARY KEY, shared_data TEXT);
CREATE TABLE events (event_id INTEGER PRIMARY KEY, event_type_id INTEGER, data_id INTEGER, time_fired_ts REAL,
  context_id_bin BLOB, context_user_id_bin BLOB, context_parent_id_bin BLOB);
"""
UID = "0f3c5a2b9e8d4c7f8a1b2c3d4e5f6a7b"
SYSUID = "aa3c5a2b9e8d4c7f8a1b2c3d4e5f6a7b"


def ctx(n):
    # ULID-agtige 16 bytes: FÆLLES 6-byte tids-præfiks, så en præfiks-match ville kollidere
    return bytes.fromhex("0192ab34cd56") + n.to_bytes(10, "big")


class TestWho(unittest.TestCase):
    def setUp(self):
        c = self.c = sqlite3.connect(":memory:")
        c.executescript(SCHEMA)
        c.executemany(
            "INSERT INTO states_meta VALUES (?,?)",
            [
                (1, "light.x"),
                (2, "binary_sensor.motion"),
                (3, "sensor.tmpl_kilde"),
                (4, "light.gruppe"),
            ],
        )
        c.execute(
            "INSERT INTO state_attributes VALUES (1, ?)",
            (json.dumps({"entity_id": ["light.x", "light.y"]}),),
        )
        c.executemany(
            "INSERT INTO event_types VALUES (?,?)",
            [(1, "automation_triggered"), (2, "script_started"), (3, "call_service")],
        )
        c.executemany(
            "INSERT INTO event_data VALUES (?,?)",
            [
                (
                    1,
                    json.dumps(
                        {
                            "name": "Lys: tænd",
                            "entity_id": "automation.lys_taend",
                            "source": "state of binary_sensor.motion",
                        }
                    ),
                ),
                (2, json.dumps({"name": "Fade", "entity_id": "script.fade"})),
                (3, json.dumps({"domain": "light", "service": "turn_off"})),
                (4, json.dumps({"name": "Fremmed", "entity_id": "automation.fremmed"})),
                (5, json.dumps({"name": "Gruppe sluk", "entity_id": "automation.gruppe_sluk"})),
                (
                    6,
                    json.dumps(
                        {
                            "domain": "light",
                            "service": "turn_off",
                            "service_data": {"entity_id": ["light.gruppe"]},
                        }
                    ),
                ),
                (7, json.dumps({"name": "Senere", "entity_id": "script.senere"})),
            ],
        )
        self.base = b = ts("2026-10-25T00:00:00+00:00").timestamp()

        def S(sid, st, dt, cid=None, uid=None, par=None, mid=1, lc=None, old=0, attrs=None):
            c.execute(
                "INSERT INTO states VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, st, b + dt, lc, cid, uid, par, mid, old if old != 0 else sid - 1, attrs),
            )

        def E(eid, typ, data, dt, cid, uid=None):
            c.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?,NULL)", (eid, typ, data, b + dt, cid, uid)
            )

        S(1, "off", -3600)  # før vinduet → forrige state
        S(2, "on", 60, ctx(10), bytes.fromhex(UID))  # bruger via app
        E(1, 3, 3, 60, ctx(10))
        S(3, "off", 120, ctx(20))  # automation + script i samme context
        E(2, 1, 1, 119, ctx(20))
        E(3, 2, 2, 119.5, ctx(20))
        E(8, 2, 7, 125, ctx(20))  # script startet EFTER skiftet: ikke "via"
        E(4, 1, 4, 119, ctx(21))  # nabo-ULID: må IKKE matche
        S(4, "on", 180, ctx(30))  # ingen ophav, intet kald → device
        S(5, "on", 240, ctx(31))  # samme state igen → genskrevet
        S(6, "on", 250, ctx(32), lc=b + 240)  # kun attribut-ændring
        S(7, "sensor-kilde", 299, ctx(40), mid=3)  # en anden entity skiftede FØRST i samme context
        S(8, "off", 300, ctx(40))  # → fulgte
        S(9, "on", 360, ctx(50), par=ctx(60))  # barn af en state-ændring
        S(10, "on", 359, ctx(60), mid=2)
        S(15, "on", 400, ctx(70), mid=4, attrs=1)  # light.gruppe med light.x som medlem
        E(5, 1, 5, 413.9, ctx(81))  # automation kalder gruppen ...
        E(6, 3, 6, 414, ctx(81))
        S(12, "off", 420, ctx(80), old=9)  # ... og pæren melder 6 s senere med frisk context
        S(13, "on", 480, ctx(90), old=None)  # første række efter genstart
        S(14, "off", 540, ctx(95), bytes.fromhex(SYSUID), old=13)  # Supervisor/cron-script
        S(11, "off", 9999, ctx(99))  # efter vinduet
        c.commit()

    def run_who(self, **kw):
        return hq.who_db(
            self.c,
            "light.x",
            datetime.fromtimestamp(self.base, UTC),
            datetime.fromtimestamp(self.base + 3600, UTC),
            users={UID: "Parent A", SYSUID: "api:Supervisor"},
            **kw,
        )

    def test_attribution(self):
        got = [(f, to, who) for _, f, to, who, _ in self.run_who()]
        self.assertEqual(
            got,
            [
                ("off", "on", "user:Parent A"),
                ("on", "off", "automation.lys_taend"),
                ("off", "on", "device"),
                ("on", "on", "genskrevet"),
                ("on", "off", "fulgte:sensor.tmpl_kilde"),
                ("off", "on", "barn:binary_sensor.motion"),
                ("on", "off", "≈automation.gruppe_sluk"),
                ("off", "on", "genstart"),
                ("on", "off", "api:Supervisor"),
            ],
        )

    def test_details_and_no_prefix_match(self):
        rows = self.run_who()
        self.assertEqual(rows[0][4], "light.turn_off")
        self.assertEqual(
            rows[1][4], "via script.fade ← state of binary_sensor.motion"
        )  # ikke script.senere
        self.assertNotIn("fremmed", repr(rows))
        self.assertIn("på light.gruppe 6.0s før", rows[6][4])

    def test_attr_changes_flag(self):
        self.assertEqual(len(self.run_who()), 9)
        rows = self.run_who(attr_changes=True)
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[4][2], "(attr)")

    def test_unknown_entity(self):
        with self.assertRaises(hq.HQError):
            hq.who_db(
                self.c,
                "light.findes_ikke",
                datetime.fromtimestamp(self.base, UTC),
                datetime.fromtimestamp(self.base + 60, UTC),
                users={},
            )


class TestFold(unittest.TestCase):
    def test_house_spelling_matches_danish(self):
        # review 10-05: id'erne staver ø som 'oe' og å som 'aa'
        self.assertEqual(hq.fold("køkken"), hq.fold("koekken"))
        self.assertEqual(hq.fold("børneværelse"), hq.fold("boernevaerelse"))
        self.assertEqual(hq.fold("uopnåelige"), hq.fold("uopnaaelige"))


class TestRepoLookups(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        os.makedirs(os.path.join(r, "automations"))
        os.makedirs(os.path.join(r, "script_pkg"))
        os.makedirs(os.path.join(r, "packages"))
        with open(os.path.join(r, "automations", "a.yaml"), "w", encoding="utf-8") as f:
            f.write(
                "- id: foo\n  alias: Foo\n  triggers:\n    - trigger: state\n      id: bar\n"
                "- id: bar\n  alias: Bar\n"
            )
        with open(os.path.join(r, "script_pkg", "s.yaml"), "w", encoding="utf-8") as f:
            f.write("fade:\n  sequence: []\n")
        with open(os.path.join(r, "packages", "p.yaml"), "w", encoding="utf-8") as f:
            f.write(
                "input_boolean:\n  fade:\n    name: x\nscript:\n  pkg_script:\n    sequence: []\n"
            )
        self.saved, hq.REPO = hq.REPO, r

    def tearDown(self):
        hq.REPO = self.saved
        self.tmp.cleanup()

    def test_automation_id_beats_trigger_id(self):
        self.assertEqual(
            hq.find_automation_lines(["foo", "bar"]),
            {"foo": "automations/a.yaml:1", "bar": "automations/a.yaml:6"},
        )

    def test_script_lines(self):
        self.assertEqual(
            hq.find_script_lines(["fade", "pkg_script"]),
            {"fade": "script_pkg/s.yaml:1", "pkg_script": "packages/p.yaml:5"},
        )


class TestOutput(unittest.TestCase):
    def test_emit_caps(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            hq.emit([str(i) for i in range(100)], tail=True)
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), hq.CAP + 1)
        self.assertTrue(lines[0].startswith("# … 60 ældre"))
        self.assertEqual(lines[-1], "99")

    def test_parser(self):
        a = hq.build_parser().parse_args(["flanks", "light.x", "--to", "on", "--min-prev", "30s"])
        self.assertEqual((a.cmd, a.to, a.min_prev), ("flanks", "on", timedelta(seconds=30)))


if __name__ == "__main__":
    unittest.main()
