"""secret_set: values nobody types or sees, and the one-time page for those only the user has.

python3 -m unittest discover -s scripts/tests -p "test_secret_set.py"

Everything runs against a temporary secrets file on 127.0.0.1; HA is never called.
All keys and values here are synthetic.
"""

import contextlib
import io
import ipaddress
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ha_secrets  # noqa: E402
import secret_set  # noqa: E402

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LOOPBACK = ipaddress.ip_network("127.0.0.0/8")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "s.yaml"
        self.path.write_text("existing: old-value\n", encoding="utf-8")
        self.saved, ha_secrets.SECRETS_FILE = ha_secrets.SECRETS_FILE, self.path
        self.calls = []
        self.answers = {"states/input_select.house_mode": {"state": "Normal"}}
        patcher = mock.patch.object(secret_set, "api", side_effect=self.fake_api)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        ha_secrets.SECRETS_FILE = self.saved
        self.tmp.cleanup()

    def fake_api(self, path, body=None, timeout=10):
        self.calls.append(path)
        return self.answers.get(path, {})

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = secret_set.main(list(argv))
        return code, out.getvalue()


class Generate(Base):
    def test_the_value_is_written_and_never_printed(self):
        code, out = self.run_main("generate", "speaker_password", "--length", "24")
        value = ha_secrets.load(self.path)["speaker_password"]
        self.assertEqual(code, 0, out)
        self.assertEqual(len(value), 24)
        self.assertTrue(value.isalnum() and value.lower() != value != value.upper())
        self.assertTrue(any(c.isdigit() for c in value))
        self.assertNotIn(value, out)
        self.assertIn("speaker_password (24 tegn, ny nøgle)", out)
        self.assertIn("services/logbook/log", self.calls)

    def test_an_existing_key_needs_replace(self):
        code, _ = self.run_main("generate", "existing")
        self.assertEqual(code, 4)
        self.assertEqual(ha_secrets.load(self.path)["existing"], "old-value")
        code, out = self.run_main("generate", "existing", "--replace", "--chars", "hex")
        value = ha_secrets.load(self.path)["existing"]
        self.assertEqual(code, 0, out)
        self.assertEqual(len(value), 32)
        self.assertLessEqual(set(value), set("0123456789abcdef"))
        self.assertEqual(
            ha_secrets.load(self.path.with_name("s.yaml.prev"))["existing"], "old-value"
        )

    def test_bad_key_or_length(self):
        self.assertEqual(self.run_main("generate", "bad-key")[0], 4)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            secret_set.main(["generate", "short", "--length", "4"])


class Keys(Base):
    def test_names_and_lengths_only(self):
        code, out = self.run_main("keys")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"existing\s+9\b")
        self.assertNotIn("old-value", out)


class Ask(Base):
    def start(self, seconds=10, peers=LOOPBACK):
        server = secret_set.Page(
            "127.0.0.1", peers, "api_key", "Test-nøgle", self.path, "12:00", bind="127.0.0.1"
        )
        box = {}
        t = threading.Thread(target=lambda: box.setdefault("r", secret_set.serve(server, seconds)))
        t.start()
        self.addCleanup(t.join, 15)
        return server, t, box

    def request(self, url, data=None):
        body = None if data is None else urllib.parse.urlencode(data).encode()
        try:
            with DIRECT.open(url, body, timeout=5) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_only_the_route_answers_and_cancel_saves_nothing(self):
        server, t, box = self.start()
        self.assertEqual(self.request(server.url.rsplit("/", 1)[0] + "/guess")[0], 404)
        code, body = self.request(server.url)
        self.assertEqual(code, 200)
        self.assertIn("<form", body)
        self.assertIn("api_key", body)
        self.assertEqual(self.request(server.url, {"v": "typed", "a": "annuller"})[0], 200)
        t.join(5)
        self.assertEqual(box["r"].outcome, "cancelled")
        self.assertNotIn("api_key", ha_secrets.load(self.path))

    def test_a_save_lands_once_never_printed_and_closes_the_page(self):
        value = "sk-synthetic-0123456789"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            server, t, box = self.start()
            self.assertEqual(self.request(server.url, {"v": "  "})[0], 400)
            self.assertEqual(self.request(server.url, {"v": "two\nlines"})[0], 400)
            code, body = self.request(server.url, {"v": f" {value}\n", "a": "gem"})
            t.join(5)
        self.assertEqual(code, 200)
        self.assertIn("Gemt", body)
        self.assertNotIn(value, body)
        self.assertEqual(box["r"], secret_set.Result("saved", len(value), True))
        self.assertEqual(ha_secrets.load(self.path)["api_key"], value)
        self.assertNotIn(value, out.getvalue())
        with self.assertRaises(OSError):
            self.request(server.url)

    def test_a_sender_outside_the_network_gets_nothing(self):
        server, t, box = self.start(seconds=1.5, peers=secret_set.TAILNET)
        with self.assertRaises(OSError):
            self.request(server.url, {"v": "from-the-wrong-network", "a": "gem"})
        t.join(5)
        self.assertIsNone(box["r"])
        self.assertNotIn("api_key", ha_secrets.load(self.path))

    def test_no_answer_by_the_deadline(self):
        _, t, box = self.start(seconds=1.5)
        t.join(5)
        self.assertIsNone(box["r"])
        self.assertNotIn("api_key", ha_secrets.load(self.path))

    def test_airbnb_sends_no_push(self):
        self.answers["states/input_select.house_mode"] = {"state": "AirBnB"}
        code, out = self.run_main("ask", "api_key", "Test-nøgle")
        self.assertEqual(code, 3)
        self.assertIn("AIRBNB", out)
        self.assertFalse([c for c in self.calls if c.startswith("services/notify")])

    def test_listens_only_on_the_tailnet_or_the_home_network(self):
        self.answers["config"] = {
            "external_url": "http://198.51.100.174:8123",
            "internal_url": "http://192.0.2.36:8123",
        }
        self.assertEqual(secret_set.address(lan=False), ("198.51.100.174", secret_set.TAILNET))
        self.assertEqual(
            secret_set.address(lan=True), ("192.0.2.36", ipaddress.ip_network("192.168.0.0/24"))
        )
        self.answers["config"] = {
            "external_url": "http://203.0.113.7:8123",
            "internal_url": "http://198.51.100.174:8123",
        }
        for lan in (False, True):
            with self.subTest(lan=lan), self.assertRaises(RuntimeError):
                secret_set.address(lan=lan)
        self.answers["config"] = {}
        with self.assertRaises(RuntimeError):
            secret_set.address(lan=False)


if __name__ == "__main__":
    unittest.main()
