"""Tests for scripts/secret_leak_scan.py, the transcript backstop behind secret_guard.

Every secret here is generated at runtime, so neither this file nor gitleaks sees a
value. The scanner's promise under test: it finds a live value in a transcript in
the forms it takes there, it reports each exposure once, and nothing it prints,
stores or pushes ever contains the value itself.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import secrets
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ha_secrets  # noqa: E402
import secret_leak_scan as sls  # noqa: E402


def b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def jwt(claims: dict) -> str:
    return f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64(claims)}.{secrets.token_urlsafe(32)}"


def line(kind: str, text: str, ts: str = "2026-11-05T10:00:00.000Z") -> str:
    if kind == "user":
        obj = {"type": "user", "message": {"role": "user", "content": text}}
    elif kind == "command":
        item = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": text}}
        obj = {"type": "assistant", "message": {"role": "assistant", "content": [item]}}
    else:
        item = {"type": "tool_result", "tool_use_id": "t1", "content": text}
        obj = {"type": "user", "message": {"role": "user", "content": [item]}}
    obj["timestamp"] = ts
    return json.dumps(obj, ensure_ascii=False) + "\n"


class Scan(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.root = root
        self.claude = root / "claude"
        self.transcript = self.claude / "projects" / "-repo" / "0f1e2d3c-aaaa.jsonl"
        self.transcript.parent.mkdir(parents=True)
        storage = root / "storage"
        storage.mkdir()

        self.router = "r" + secrets.token_hex(3) + "Q7"  # 9 chars: needs word boundaries
        self.api = secrets.token_urlsafe(30)
        self.quoted = 'p"' + secrets.token_hex(10)  # JSON-escaped in a transcript
        self.rt_id = secrets.token_hex(16)
        self.rt_token = secrets.token_hex(64)
        self.env_token = secrets.token_hex(28)
        self.shared = "wifi-" + secrets.token_hex(6)
        (root / "fake_secrets.yaml").write_text(
            f"router_admin_password: {self.router}\n"
            f"plant_api_token: {self.api}\n"
            f"plant_notify_token: {self.api}\n"
            f"gaeste_wifi_kode: {self.shared}\n"
            "home_name: Hjemmet\n",
            encoding="utf-8",
        )
        entries = [
            {"domain": "squeezebox", "title": "Højttaler", "data": {"host": "x"}},
            {"domain": "mqtt", "title": "MQTT", "data": {"password": self.quoted}},
            {"domain": "speaker", "title": "S", "data": {"password": "squeezebox"}},
        ]
        self.write(storage / "core.config_entries", {"data": {"entries": entries}})
        rts = [{"id": self.rt_id, "client_name": "SSH", "token": self.rt_token, "jwt_key": "k"}]
        self.write(storage / "auth", {"data": {"refresh_tokens": rts}})
        self.write(
            storage / "application_credentials",
            {"key": "application_credentials", "data": {"items": []}},
        )
        patches = [
            mock.patch.multiple(
                sls,
                CLAUDE=str(self.claude),
                STATE_DIR=str(root / "state"),
                STORAGE=str(storage),
                CLOUD_DIR=str(root / "nocloud"),
                LOCAL_CONFIGS=str(root / ".*.local.yaml"),
                SSH_DIR=str(root / "nossh"),
                S6_DIRS=[],
                OPTIONS_JSON=str(root / "none.json"),
                CLAUDE_TOKEN_ENV=str(root / "none.env"),
            ),
            mock.patch.object(ha_secrets, "SECRETS_FILE", root / "fake_secrets.yaml"),
            mock.patch.dict(os.environ, {"MY_API_TOKEN": self.env_token}, clear=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)

    @staticmethod
    def write(path: Path, obj: dict) -> None:
        path.write_text(json.dumps(obj), encoding="utf-8")

    def append(self, *lines: str) -> None:
        with open(self.transcript, "a", encoding="utf-8") as f:
            f.writelines(lines)

    def run_main(self, *argv: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sls.main(list(argv))
        return out.getvalue()

    def values(self) -> list[str]:
        return [self.router, self.api, self.quoted, self.rt_token, self.env_token]

    def assert_no_values(self, text: str) -> None:
        for v in self.values():
            self.assertNotIn(v, text)
            self.assertNotIn(json.dumps(v)[1:-1], text)

    def test_finds_each_form_and_prints_no_value(self) -> None:
        self.append(
            line("user", f"koden er {self.router}."),
            line("command", f"curl -H 'Authorization: Bearer {self.env_token}' x"),
            line("result", json.dumps({"password": self.quoted})),
            line("result", f"token={self.rt_token}"),
        )
        out = self.run_main()
        for label in (
            "secrets.yaml:router_admin_password",
            "env:MY_API_TOKEN",
            "config_entry:mqtt:password",
            "auth:SSH:token",
        ):
            self.assertIn(label, out)
        self.assertIn("2026-11-05 11:00  brugerbesked  session 0f1e2d3c", out)
        self.assertIn("Claude-kommando", out)
        self.assertIn("værktøjs-output", out)
        self.assert_no_values(out)
        self.assert_no_values((self.root / "state" / "state.json").read_text(encoding="utf-8"))

    def test_each_exposure_is_reported_once(self) -> None:
        self.append(line("user", f"api {self.api}"))
        self.assertIn("plant_api_token", self.run_main())
        self.assertIn("intet nyt", self.run_main())
        self.append(line("result", f"igen {self.api}"))
        self.assertIn("plant_api_token", self.run_main())

    def test_rewritten_file_is_scanned_again(self) -> None:
        self.append(line("user", "intet"), line("user", "intet"), line("user", "intet"))
        self.run_main()
        self.transcript.write_text(line("user", f"api {self.api}"), encoding="utf-8")
        self.assertIn("plant_api_token", self.run_main())

    def test_short_value_counts_only_as_a_word(self) -> None:
        self.append(line("result", f"abc{self.router}def"))
        self.assertNotIn("router_admin_password", self.run_main())
        self.append(line("result", f"første linje\n{self.router}\n"))  # JSON: \\n before it
        self.assertIn("router_admin_password", self.run_main())

    def test_reused_value_carries_both_names(self) -> None:
        self.append(line("user", self.api))
        self.assertIn(
            "secrets.yaml:plant_api_token = secrets.yaml:plant_notify_token", self.run_main()
        )

    def test_shared_identifier_metadata_and_public_names_are_skipped(self) -> None:
        live = sls.build_live()
        self.assertNotIn(self.shared, live.labels)  # guest WiFi: shared by design
        self.assertNotIn("Hjemmet", live.labels)  # IDENTIFIERS
        self.assertNotIn("application_credentials", live.labels)  # storage metadata
        self.assertIn("squeezebox", live.labels)  # collected, but a domain name:
        self.assertNotIn(b"squeezebox", [n[0] for n in live.needles(b"k")])

    def test_local_config_contributes_its_keys_only(self) -> None:
        key = secrets.token_hex(32)
        (self.root / ".tool.local.yaml").write_text(
            f'hmac_key: "{key}"\npseudonyms:\n  "Jane Doe": "Parent A"\n', encoding="utf-8"
        )
        live = sls.build_live()
        self.assertEqual(live.labels.get(key), "local:.tool.local.yaml:hmac_key")
        self.assertNotIn("Parent A", live.labels)  # a name mapping is not a secret

    def test_patterns(self) -> None:
        now = int(time.time())
        key = "sk-ant-" + "api03-" + secrets.token_urlsafe(40)
        placeholder = "sk-ant-" + "X" * 40
        live_jwt = jwt({"iss": self.rt_id, "iat": now, "exp": now + 3600})
        dead_jwt = jwt({"iss": self.rt_id, "iat": now - 7200, "exp": now - 3600})
        orphan = jwt({"iss": secrets.token_hex(16), "iat": now, "exp": now + 3600})
        self.append(
            line("user", f"nøgle {key}"),
            line("result", f"{placeholder} {dead_jwt} {orphan}"),
            line("command", f"curl -H 'Authorization: Bearer {live_jwt}'"),
        )
        out = self.run_main()
        self.assertIn("mønster:anthropic  ×1", out)
        self.assertIn("ha-token:SSH  ×1", out)
        self.assertNotIn("mønster:jwt", out)
        self.assertNotIn("mønster:bearer", out)
        for v in (key, live_jwt):
            self.assertNotIn(v, out)

    def test_all_mode_reports_everything_and_keeps_state(self) -> None:
        self.append(line("user", self.api))
        self.run_main()
        state = (self.root / "state" / "state.json").read_text(encoding="utf-8")
        self.assertIn("plant_api_token", self.run_main("--all"))
        self.assertEqual(state, (self.root / "state" / "state.json").read_text(encoding="utf-8"))

    def test_baseline_and_ignore(self) -> None:
        self.append(line("user", self.api))
        self.run_main("--baseline")
        self.assertIn("intet nyt", self.run_main())
        out = self.run_main("--all")
        fp = out.split("fp ")[1].split()[0]
        self.run_main("--ignore", fp)
        self.assertNotIn("plant_api_token", self.run_main("--all"))

    def test_context_masks_every_value(self) -> None:
        self.append(line("result", f"a={self.api} b={self.env_token} {secrets.token_hex(20)} slut"))
        out = self.run_main("--all", "--context")
        self.assertIn("‹secrets.yaml:plant_api_token", out)
        self.assertIn("slut", out)
        self.assert_no_values(out)

    def test_push_holds_in_airbnb_and_sends_only_labels(self) -> None:
        self.append(line("user", self.api))
        sent = []

        def urlopen(req, timeout=0):
            sent.append(req.data.decode())
            return contextlib.nullcontext()

        with (
            mock.patch.dict(os.environ, {"SUPERVISOR_TOKEN": "t"}),
            mock.patch.object(sls, "ha_get", return_value={"state": "AirBnB"}),
            mock.patch.object(sls.urllib.request, "urlopen", urlopen),
        ):
            self.run_main("--push")
        self.assertEqual(sent, [])
        state = json.loads((self.root / "state" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["pending"]), 1)
        with (
            mock.patch.dict(os.environ, {"SUPERVISOR_TOKEN": "t"}),
            mock.patch.object(sls, "ha_get", return_value={"state": "Normal"}),
            mock.patch.object(sls.urllib.request, "urlopen", urlopen),
        ):
            self.run_main("--push")
        self.assertEqual(len(sent), 1)
        self.assertIn("plant_api_token", sent[0])
        self.assertIn("Roter", sent[0])
        self.assert_no_values(sent[0])
        state = json.loads((self.root / "state" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["pending"], [])

    def test_hook_starts_a_detached_push(self) -> None:
        with (
            mock.patch.object(sls.subprocess, "Popen") as popen,
            mock.patch.object(sys, "stdin", io.StringIO('{"transcript_path": "x"}')),
        ):
            self.assertEqual(sls.main(["hook"]), 0)
        args, kwargs = popen.call_args
        self.assertEqual(args[0][-2:], ["--push", "--quiet"])
        self.assertTrue(kwargs["start_new_session"])


if __name__ == "__main__":
    unittest.main()
