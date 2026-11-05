"""hoejttaler_kode: the speaker's password changes on both sides, or on neither.

python3 -m unittest discover -s scripts/tests -p "test_secret_hoejttaler_kode.py"

ssh is faked: no speaker, no secrets file. All values here are synthetic.
"""

import os
import queue
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import hoejttaler_kode as hk  # noqa: E402

OLD = "gammel-syntetisk-kode-1"
NEW = "NyKode0123456789abcdefABCDEF0123"


class FakeSession:
    """The root session on the speaker: answers SAT=ja, then SLUT=ny on "ok"."""

    def __init__(self, sat="SAT=ja", answers=True):
        self.out = queue.Queue()
        self.written = []
        self.sat, self.answers = sat, answers
        self.stdin = self
        self.stdout = iter(self.out.get, None)

    def write(self, text):
        self.written.append(text)
        if text.endswith(f"{NEW}\n"):
            self.out.put(self.sat + "\n")
            if not self.sat.startswith("SAT="):
                self.out.put(None)
        elif text in ("ok\n", "nej\n"):
            if self.answers:
                self.out.put(("SLUT=ny" if text == "ok\n" else "SLUT=gammel") + "\n")
            self.out.put(None)

    def flush(self):
        pass

    def close(self):
        pass

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.argv = []
        self.session = FakeSession()
        self.logins = {NEW: True, OLD: False}
        for target, fake in (
            ("subprocess.Popen", self.fake_popen),
            ("subprocess.run", self.fake_run),
            ("time.sleep", lambda s: None),
        ):
            p = mock.patch(f"hoejttaler_kode.{target}", side_effect=fake)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(hk.hb, "cache_dir", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def fake_popen(self, argv, **kw):
        self.argv.append(argv)
        self.events.append(("session", kw["env"][hk.ENV]))
        return self.session

    def fake_run(self, argv, **kw):
        self.argv.append(argv)
        kode = kw["input"].strip()
        self.events.append(("login", kode))
        ok = self.logins.get(kode, False)
        return mock.Mock(returncode=0 if ok else 255, stdout="0\n" if ok else "")

    def gem(self, value):
        self.events.append(("gem", value))

    def run_skift(self):
        return hk.skift(OLD, NEW, self.gem)


class HappyPath(Base):
    def test_saved_before_the_speaker_is_told_ok(self):
        ok, _ = self.run_skift()
        self.assertTrue(ok)
        self.assertEqual(self.events, [("session", OLD), ("login", NEW), ("gem", NEW)])
        self.assertEqual(self.session.written[-1], "ok\n")

    def test_values_never_in_argv(self):
        self.run_skift()
        flat = " ".join(" ".join(a) for a in self.argv)
        self.assertNotIn(OLD, flat)
        self.assertNotIn(NEW, flat)
        self.assertNotIn(OLD, hk.enhed_script())
        # sudo eats line one; the script reads the old and the new value after it.
        self.assertEqual(self.session.written[0], f"{OLD}\n{OLD}\n{NEW}\n")


class NeitherChanges(Base):
    def test_new_login_fails_speaker_told_no(self):
        self.logins[NEW] = False
        ok, _ = self.run_skift()
        self.assertFalse(ok)
        self.assertNotIn(("gem", NEW), self.events)
        self.assertEqual(self.session.written[-1], "nej\n")

    def test_store_fails_speaker_told_no(self):
        def broken(value):
            raise ValueError("hoejttaler_ssh_password: read-back mismatch")

        ok, why = hk.skift(OLD, NEW, broken)
        self.assertFalse(ok)
        self.assertNotIn(NEW, why)
        self.assertEqual(self.session.written[-1], "nej\n")

    def test_speaker_refuses_before_setting(self):
        self.session = FakeSession(sat="FEJL=sudoers")
        ok, why = self.run_skift()
        self.assertFalse(ok)
        self.assertIn("FEJL=sudoers", why)
        self.assertEqual([e for e in self.events if e[0] != "session"], [])

    def test_lost_confirmation_old_login_restores_file(self):
        self.session = FakeSession(answers=False)
        calls = iter([True, False, True])  # verify new, then: new fails, old works
        with mock.patch.object(hk, "login_virker", side_effect=lambda d, k: next(calls)):
            ok, _ = self.run_skift()
        self.assertFalse(ok)
        self.assertEqual(self.events[-2:], [("gem", NEW), ("gem", OLD)])

    def test_lost_confirmation_new_login_keeps_file(self):
        self.session = FakeSession(answers=False)
        calls = iter([True, True])
        with mock.patch.object(hk, "login_virker", side_effect=lambda d, k: next(calls)):
            ok, _ = self.run_skift()
        self.assertTrue(ok)
        self.assertEqual(self.events[-1], ("gem", NEW))


class Sudoers(unittest.TestCase):
    def test_sorts_after_volumio_user_and_is_read(self):
        name = os.path.basename(hk.SUDOERS_FIL)
        self.assertGreater(name, "volumio-user")  # last match wins
        self.assertNotIn(".", name)  # sudo skips names with a dot
        self.assertNotRegex(name, "~$")
        hk.SUDOERS.encode("ascii")

    def test_covers_the_four_hardcoded_calls(self):
        for cmd in (
            "/bin/cp -f /usr/bin/mpdsacd /usr/bin/mpd",
            "/bin/cp -f /usr/bin/mpdorig /usr/bin/mpd",
            "/bin/sh /data/plugins/*/install.sh",
            "/bin/sh /data/plugins/*/uninstall.sh",
        ):
            self.assertIn(cmd, hk.SUDOERS)


if __name__ == "__main__":
    unittest.main()
