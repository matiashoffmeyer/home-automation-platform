#!/usr/bin/env python3
"""Find live secrets in Claude Code's transcripts, and push which ones to rotate.

Why: everything Claude reads or prints is stored under ``~/.claude`` and sent to
Anthropic. Two leaks happened before this existed: the supervisor token via
``bash -x`` (2026-11-02) and an API key pasted into the chat (2026-11-04).
``scripts/secret_guard.py`` blocks the common ways in; this is the backstop for
everything a guard cannot see (a value inside a tool's output, a paste).

How: collect the house's live secret values (secrets.yaml, ``.storage``
credentials, add-on options, environment, SSH keys, Claude's own login) and
search the transcript files for them as bytes, raw and JSON-/URL-escaped. On top
come generic token patterns (an Anthropic key, a GitHub token, a live HA JWT).
Values live in memory only: output, state and pushes carry a label
(``secrets.yaml:nemlig_password``) and an HMAC fingerprint, never a value.

Modes:
  (none)        scan what is new since the last run, print, queue hits for a push
  --push        the same, then push the queue (held back in AirBnB mode)
  --all         rescan everything, print only (state untouched) - after an incident
  --baseline    mark everything up to now as seen, without scanning
  --inventory   list the live set (label, length) to review it for false positives
  --ignore FP   never report this fingerprint again (a reviewed false positive)
  --context     with a scan: show each hit's surroundings, every secret masked
  hook          SessionEnd hook: read stdin, start ``--push --quiet`` detached
"""

from __future__ import annotations

import base64
import fcntl
import glob
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ha_secrets  # noqa: E402
from secret_guard import SECRETISH  # noqa: E402
from secrets_contract import IDENTIFIERS  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE = os.path.expanduser("~/.claude")
STATE_DIR = os.path.join(REPO, ".cache", "secret_leak_scan")
STORAGE = os.path.join(REPO, ".storage")
CLOUD_DIR = os.path.join(REPO, ".cloud")
LOCAL_CONFIGS = os.path.join(REPO, ".*.local.y*ml")  # git-ignored tool config (a glob)
SSH_DIR = "/data/.ssh"
S6_DIRS = ["/run/s6/container_environment"]
OPTIONS_JSON = "/data/options.json"
CLAUDE_TOKEN_ENV = "/share/claude-token.env"
SUPERVISOR = "http://supervisor"
NOTIFY = "/core/api/services/notify/mobile_app_phone_a"
TZ = ZoneInfo("Europe/Copenhagen")

# Shared by design, so a sighting is not a leak to rotate: the guest WiFi is handed
# to every guest (its own network, B267), and some_password is HA's stock example.
SHARED_OK = {"gaeste_wifi_kode", "gaeste_wifi_ssid", "some_password"}
# Trail Buddy's trip code is a word the whole hiking group shares, and it rides in
# every app URL (addons/trailbuddy/README.md).
SHARED_LABELS = {"addon:local_trailbuddy:trip_code"}
SSH_PUBLIC = {"config", "known_hosts", "known_hosts.old", "authorized_keys"}
KEYRX = re.compile(
    r"token|secret|pass|key$|code$|(^|_)pin($|_)|cookie|session|credential|private|webhook",
    re.I,
)
SKIP_KEY = re.compile(
    r"storage_key|token_type|.*_(at|in)|.*expir.*|.*(country|language|zip)_?code", re.I
)
URL_CRED = re.compile(r"^[a-z][a-z0-9+.-]*://[^:/@\s]+:([^@\s]+)@", re.I)
HEX = re.compile(r"[0-9a-fA-F]+")
SHORT = 16  # below this a value only counts between word boundaries
ESCAPES = (b"\\n", b"\\t", b"\\r")
OVERLAP = 4096  # re-read this much before the stored offset (a value cut at EOF)
MAX_SHOWN = 4

GEN = [
    ("jwt", re.compile(rb"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}")),
    (
        "privat-nøgle",  # three body lines: the first is shared by every OpenSSH key
        re.compile(
            rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----(?:(?:\\[rn]|\s)+[A-Za-z0-9+/=]{40,}){1,3}"
        ),
    ),
    ("github", re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{50,255}")),
    ("anthropic", re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,255}")),
    ("openai", re.compile(rb"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{40,255}")),
    ("google", re.compile(rb"AIza[0-9A-Za-z_-]{35}")),
    ("slack", re.compile(rb"xox[abposr]-[A-Za-z0-9-]{10,255}")),
    ("aws", re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])")),
    ("bearer", re.compile(rb"Bearer\s+[A-Za-z0-9._~+/-]{20,1024}")),
]
RANDOMISH = re.compile(r"[A-Za-z0-9+/=_.~-]{20,}")

HINTS = [
    ("env:SUPERVISOR_TOKEN", "genstart SSH-add-on'et (ny SUPERVISOR_TOKEN)"),
    ("secrets.yaml:", "ny værdi hos tjenesten + i secrets.yaml"),
    ("config_entry:anthropic", "ny nøgle på console.anthropic.com → Anthropic-integrationen"),
    ("config_entry:", "genkonfigurer integrationen med en ny nøgle"),
    ("application_credentials:", "ny client secret hos udbyderen"),
    ("auth_provider:", "skift HA-adgangskoden"),
    ("auth:", "slet tokenet under Profil → Sikkerhed"),
    ("ha-token:", "slet tokenet under Profil → Sikkerhed"),
    ("addon:", "ny værdi i add-on'ets Konfiguration"),
    ("ssh-", "ny deploy-nøgle (GitHub → Deploy keys)"),
    ("claude", "/logout + /login i Claude Code"),
    ("thread:", "ny Thread-netværksnøgle kræver gen-parring — vurder risikoen"),
    ("local:", "ny nøgle i den lokale config-fil — læs filens egen kommentar først"),
    ("env:", "ny værdi for miljøvariablen"),
    ("mønster:anthropic", "tilbagekald nøglen på console.anthropic.com"),
    ("mønster:", "tjek om nøglen er aktiv, og tilbagekald den hos udstederen"),
]


# --- the live set -------------------------------------------------------------


class Live:
    """Secret value -> label, and the byte forms each value can take in a transcript."""

    def __init__(self) -> None:
        self.labels: dict[str, str] = {}
        self.rt_ids: dict[str, str] = {}  # HA refresh-token id -> name (a JWT's iss)
        # Integration domains and add-on slugs. A password equal to one of these names
        # (a vendor default) appears all over the transcripts as the name, so it cannot
        # be scanned for; it is a weak password, not a leak.
        self.public: set[str] = set()

    def add(self, label: str, value: object, minimum: int = 8) -> None:
        if not isinstance(value, str) or label in SHARED_LABELS:
            return
        if "\n" in value.strip():
            self.add_lines(label, value)
            return
        v = value.strip()
        if (
            len(v) < minimum
            or len(set(v)) < 5
            or (v.isdigit() and len(v) < 12)
            or v.lower() in {"true", "false", "none", "null", "bearer"}
        ):
            return
        self.label(v, label)

    def label(self, value: str, label: str) -> None:
        """The first source names a value; a reuse elsewhere is appended (rotate both)."""
        have = self.labels.get(value)
        if have is None:
            self.labels[value] = label
        elif label not in have.split(" = "):
            self.labels[value] = f"{have} = {label}"

    def add_lines(self, label: str, text: str) -> None:
        """A multi-line value (a private key): every long body line is its own needle."""
        lines = [x.strip() for x in text.splitlines()]
        body = [x for x in lines if len(x) >= 40 and not x.startswith("-----")]
        if "OPENSSH PRIVATE KEY" in text:
            body = body[1:]  # the first line is the same in every unencrypted OpenSSH key
        for line in body:
            self.label(line, label)

    def needles(self, key: bytes) -> list[tuple[bytes, str, str, bool]]:
        """(bytes, label, fingerprint, short) for every form of every value."""
        out = []
        for v, label in self.labels.items():
            if v.lower() in self.public:
                continue
            fp = fingerprint(key, v.encode())
            for form in variants(v):
                out.append((form, label, fp, len(v) < SHORT))
        return out


def variants(v: str) -> set[bytes]:
    forms = {v, urllib.parse.quote(v, safe="")}
    once = json.dumps(v, ensure_ascii=False)[1:-1]
    forms |= {once, json.dumps(v)[1:-1], json.dumps(once, ensure_ascii=False)[1:-1]}
    if HEX.fullmatch(v):
        forms |= {v.lower(), v.upper()}
    return {f.encode() for f in forms}


def fingerprint(key: bytes, value: bytes) -> str:
    return hmac.new(key, value, hashlib.sha256).hexdigest()[:10]


def walk(obj: object, path: str = "", hot: bool = False):
    """(keypath, value) for every string under a secret-ish key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            k = str(k)
            hot_k = bool(KEYRX.search(k)) and not SKIP_KEY.fullmatch(k)
            yield from walk(v, f"{path}.{k}" if path else k, hot_k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]", hot)
    elif isinstance(obj, str):
        if hot:
            yield path, obj
        m = URL_CRED.match(obj)
        if m:  # a password inside a URL (an RTSP camera address) counts on its own
            yield f"{path}(kodeord)", urllib.parse.unquote(m.group(1))


def load_json(path: str) -> object:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError, ValueError:
        return None


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def env_lines(text: str):
    for line in text.splitlines():
        name, sep, value = line.removeprefix("export ").partition("=")
        if sep and name.strip():
            yield name.strip(), value.strip().strip("\"'")


def from_secrets_yaml(live: Live) -> None:
    try:
        values = ha_secrets.load()
    except Exception:
        return
    for key, value in values.items():
        if key in IDENTIFIERS or key in SHARED_OK:
            continue
        live.add(f"secrets.yaml:{key}", value, minimum=6)
        for path, inner in walk({key: value}):
            if path != key:
                live.add(f"secrets.yaml:{path}", inner, minimum=6)


def from_storage(live: Live) -> None:
    entries = (load_json(os.path.join(STORAGE, "core.config_entries")) or {}).get("data", {})
    entries = entries.get("entries", [])
    per_domain: dict[str, int] = {}
    for e in entries:
        per_domain[e.get("domain")] = per_domain.get(e.get("domain"), 0) + 1
        live.public.add(str(e.get("domain")).lower())
    for e in entries:
        dom = e.get("domain", "?")
        name = dom if per_domain[dom] == 1 else f"{dom}[{(e.get('title') or '')[:30]}]"
        for part in ("data", "options"):
            for path, value in walk(e.get(part) or {}):
                live.add(f"config_entry:{name}:{path}", value)

    auth = (load_json(os.path.join(STORAGE, "auth")) or {}).get("data", {})
    for rt in auth.get("refresh_tokens", []):
        name = rt.get("client_name") or rt.get("client_id") or rt.get("token_type") or "?"
        if rt.get("id"):
            live.rt_ids[rt["id"]] = name
        for key in ("token", "jwt_key"):
            live.add(f"auth:{name}:{key}", rt.get(key), minimum=16)

    users = (load_json(os.path.join(STORAGE, "auth_provider.homeassistant")) or {}).get("data", {})
    for u in users.get("users", []):
        live.add(f"auth_provider:{u.get('username')}:password-hash", u.get("password"), 16)

    for name in ["application_credentials", "backup", "cloud"] + [
        os.path.basename(p) for p in glob.glob(os.path.join(STORAGE, "auth_module.*"))
    ]:
        stored = load_json(os.path.join(STORAGE, name)) or {}
        for path, value in walk(stored.get("data") or {}):  # not the file's own "key"
            live.add(f"{name}:{path}", value)

    for p in glob.glob(os.path.join(CLOUD_DIR, "*.json")):
        for path, value in walk(load_json(p) or {}):
            live.add(f"cloud:{os.path.basename(p)}:{path}", value)

    datasets = (load_json(os.path.join(STORAGE, "thread.datasets")) or {}).get("data", {})
    for ds in datasets.get("datasets", []):
        tlv = ds.get("tlv") or ""
        fields = parse_tlv(tlv)
        net = fields.get(3, b"").decode("utf-8", "replace") or "?"
        live.add(f"thread:{net}:dataset", tlv, minimum=16)
        for typ, what in ((5, "networkkey"), (4, "pskc")):
            if typ in fields:
                live.add(f"thread:{net}:{what}", fields[typ].hex(), minimum=16)


def parse_tlv(tlv: str) -> dict[int, bytes]:
    try:
        raw = bytes.fromhex(tlv)
    except ValueError:
        return {}
    out, i = {}, 0
    while i + 2 <= len(raw):
        typ, n = raw[i], raw[i + 1]
        out[typ] = raw[i + 2 : i + 2 + n]
        i += 2 + n
    return out


def from_env(live: Live) -> None:
    for name, value in os.environ.items():
        if SECRETISH.search(name):
            live.add(f"env:{name}", value, minimum=16)
    for d in S6_DIRS:
        for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if SECRETISH.search(name):
                live.add(f"env:{name}", read_text(os.path.join(d, name)), minimum=16)


def supervisor_get(path: str, token: str) -> dict:
    req = urllib.request.Request(SUPERVISOR + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def from_addons(live: Live) -> None:
    for path, value in walk(load_json(OPTIONS_JSON) or {}):
        live.add(f"addon:ssh:{path}", value)
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    try:
        addons = supervisor_get("/addons", token).get("data", {}).get("addons", [])
    except Exception:
        return
    deadline = time.monotonic() + 30
    for a in addons:
        if time.monotonic() > deadline:
            break
        slug = a.get("slug", "")
        live.public.update({slug.lower(), slug.split("_", 1)[-1].lower()})
        try:
            options = supervisor_get(f"/addons/{slug}/info", token).get("data", {}).get("options")
        except Exception:
            continue
        for path, value in walk(options or {}):
            live.add(f"addon:{slug}:{path}", value)


def from_files(live: Live) -> None:
    if os.path.isdir(SSH_DIR):
        for name in sorted(os.listdir(SSH_DIR)):
            if name.endswith(".pub") or name in SSH_PUBLIC:
                continue
            text = read_text(os.path.join(SSH_DIR, name))
            if "PRIVATE KEY" in text:
                live.add_lines(f"ssh-key:{name}", text)
            elif name == "environment":
                for var, value in env_lines(text):
                    if SECRETISH.search(var):
                        live.add(f"ssh-env:{var}", value, minimum=16)
    for path, value in walk(load_json(os.path.join(CLAUDE, ".credentials.json")) or {}):
        live.add(f"claude:{path}", value, minimum=16)
    for var, value in env_lines(read_text(CLAUDE_TOKEN_ENV)):
        live.add(f"claude-token.env:{var}", value, minimum=16)
    for path in sorted(glob.glob(LOCAL_CONFIGS)):
        for line in read_text(path).splitlines():
            key, sep, value = line.partition(":")
            if sep and KEYRX.search(key.strip()):
                label = f"local:{os.path.basename(path)}:{key.strip()}"
                live.add(label, value.strip().strip("\"'"), 16)


def build_live() -> Live:
    live = Live()
    for source in (from_secrets_yaml, from_storage, from_env, from_addons, from_files):
        try:
            source(live)
        except Exception as e:  # one broken source must not blind the others
            log_error(f"{source.__name__}: {type(e).__name__}")
    return live


# --- scanning -----------------------------------------------------------------


def targets() -> list[str]:
    found = glob.glob(os.path.join(CLAUDE, "projects", "**", "*"), recursive=True)
    found += [os.path.join(CLAUDE, "history.jsonl")]
    found += glob.glob(os.path.join(CLAUDE, "paste-cache", "*"))
    return sorted(p for p in found if os.path.isfile(p))


def bounded(data: bytes, s: int, e: int) -> bool:
    """A short value must stand alone, not be a slice of a longer word."""

    def word(b: bytes) -> bool:
        return b.isalnum() or b == b"_"

    if word(data[s - 1 : s]) and data[max(0, s - 2) : s] not in ESCAPES:
        return False
    return not word(data[e : e + 1])


def randomish(body: bytes) -> bool:
    text = body.decode("ascii", "replace")
    return (
        len(set(text)) >= 10 and any(c.isdigit() for c in text) and any(c.isalpha() for c in text)
    )


def jwt_label(token: bytes, live: Live) -> str | None:
    """A live HA token is signed by a current refresh token; a dead JWT is no leak."""
    try:
        payload = token.split(b".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + b"=" * (-len(payload) % 4)))
    except ValueError, IndexError:
        return None
    if not isinstance(claims, dict):
        return None
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp < time.time():
        return None
    iss = claims.get("iss")
    if iss in live.rt_ids:
        return f"ha-token:{live.rt_ids[iss]}"
    if set(claims) == {"iss", "iat", "exp"} and HEX.fullmatch(str(iss)):
        return None  # HA's own shape, but its refresh token is deleted: dead
    return "mønster:jwt"


def scan_data(data: bytes, needles, live: Live, key: bytes) -> list[dict]:
    """Every hit in data as {label, fp, s, e, raw}; a hit inside a longer one is dropped."""
    hits = []
    for form, label, fp, short in needles:
        i = data.find(form)
        while i != -1:
            if not short or bounded(data, i, i + len(form)):
                hits.append({"label": label, "fp": fp, "s": i, "e": i + len(form), "raw": form})
            i = data.find(form, i + 1)
    hits.sort(key=lambda h: (h["s"], h["s"] - h["e"]))
    kept, reach = [], -1
    for h in hits:
        if h["e"] <= reach:
            continue  # inside a longer hit (a sheet id inside its URL)
        kept.append(h)
        reach = max(reach, h["e"])
    spans = [(h["s"], h["e"]) for h in kept]
    for kind, rx in GEN:  # a known value already explains the match: no pattern hit on top
        for m in rx.finditer(data):
            s, e = m.span()
            if any(a < e and b > s for a, b in spans):
                continue
            raw = m.group(0)
            token = raw.split()[-1]
            if kind == "privat-nøgle":
                label = "mønster:privat-nøgle"
            elif not randomish(token):
                continue  # a placeholder (sk-ant-XXXX…), not a key
            elif token.startswith(b"eyJ"):
                label = jwt_label(token, live)
                if label is None:
                    continue
            else:
                label = f"mønster:{kind}"
            kept.append({"label": label, "fp": fingerprint(key, raw), "s": s, "e": e, "raw": raw})
            spans.append((s, e))
    return kept


def place(path: str, data: bytes, pos: int, raw: bytes, parsed: dict) -> dict:
    """Where a hit sits: local time, who wrote it, which session."""
    rel = os.path.relpath(path, CLAUDE)
    parts = rel.split(os.sep)
    session = "-"
    if parts[0] == "projects" and len(parts) > 2 and parts[2] != "memory":
        session = parts[2][:8]
    where = {"file": rel, "session": session, "ts": mtime_local(path), "role": role_by_path(parts)}
    if not path.endswith(".jsonl"):
        return where
    start = data.rfind(b"\n", 0, pos) + 1
    if start not in parsed:
        end = data.find(b"\n", pos)
        try:
            parsed[start] = json.loads(data[start : end if end != -1 else len(data)])
        except ValueError:
            parsed[start] = None
    obj = parsed[start]
    if not isinstance(obj, dict):
        return where
    ts = obj.get("timestamp")
    if isinstance(ts, (int, float)):
        where["ts"] = local(datetime.fromtimestamp(ts / 1000, UTC))
    elif isinstance(ts, str):
        try:
            where["ts"] = local(datetime.fromisoformat(ts.replace("Z", "+00:00")))
        except ValueError:
            pass
    if parts[-1] != "history.jsonl":
        prefix = "subagent " if "subagents" in parts else ""
        where["role"] = prefix + role_of(obj, raw.decode("utf-8", "replace"))
    return where


def role_by_path(parts: list[str]) -> str:
    if parts[-1] == "history.jsonl":
        return "prompt-historik"
    if parts[0] == "paste-cache":
        return "indsat tekst"
    if "memory" in parts:
        return "hukommelse"
    if "tool-results" in parts:
        return "værktøjs-output"
    return "transskript"


def role_of(obj: dict, raw: str) -> str:
    kind = obj.get("type")
    content = (obj.get("message") or {}).get("content")
    if kind == "assistant" and isinstance(content, list):
        names = {
            "tool_use": "Claude-kommando",
            "text": "Claude-svar",
            "thinking": "Claude-tænkning",
        }
        for item in content:
            if isinstance(item, dict) and raw in json.dumps(item, ensure_ascii=False):
                return names.get(item.get("type"), "Claude")
        return "Claude"
    if kind == "user":
        if obj.get("isCompactSummary"):
            return "resumé"
        if isinstance(content, list) and any(
            isinstance(x, dict) and x.get("type") == "tool_result" for x in content
        ):
            return "værktøjs-output"
        return "brugerbesked"
    return {
        "attachment": "vedhæftning",
        "last-prompt": "brugerbesked",
        "queue-operation": "brugerbesked",
        "summary": "resumé",
    }.get(kind, str(kind))


def local(t: datetime) -> str:
    return t.astimezone(TZ).strftime("%Y-%m-%d %H:%M")


def mtime_local(path: str) -> str:
    try:
        return local(datetime.fromtimestamp(os.path.getmtime(path), UTC))
    except OSError:
        return "?"


def masked(data: bytes, hit: dict, needles, width: int = 40) -> str:
    """The hit's surroundings with every known value and random-looking run masked.

    Masks are computed on a window 200 bytes wide on each side and cut to `width`
    afterwards, so a token crossing the cut is already masked whole."""
    lo = max(0, hit["s"] - 200)
    window = data[lo : hit["e"] + 200]
    spans = [(hit["s"] - lo, hit["e"] - lo, None)]
    for form, label, _fp, _short in needles:
        i = window.find(form)
        while i != -1:
            spans.append((i, i + len(form), f"‹{label}›"))
            i = window.find(form, i + 1)
    spans.sort(key=lambda x: (x[0], -x[1]))
    out: list[str] = []
    pos, anchor = 0, None

    def plain(b: bytes) -> str:
        text = b.decode("utf-8", "replace")
        return RANDOMISH.sub(
            lambda m: "‹…›" if randomish(m.group(0).encode()) else m.group(0), text
        )

    for s, e, tag in spans:
        if s < pos:
            continue
        out.append(plain(window[pos:s]))
        if tag is None:
            anchor = sum(map(len, out))
            tag = f"‹{hit['label']}›"
        out.append(tag)
        pos = e
    out.append(plain(window[pos:]))
    flat = "".join(out)
    if anchor is None:
        anchor = len(flat) // 2
    snippet = flat[max(0, anchor - width) : anchor + len(hit["label"]) + 2 + width]
    return snippet.replace("\\n", "⏎").replace("\n", "⏎")


def scan(state: dict, full: bool, context: bool) -> tuple[list[dict], dict]:
    """Findings grouped by (label, fp), and the new offsets."""
    key = bytes.fromhex(state["key"])
    live = build_live()
    needles = live.needles(key)
    offsets = {} if full else state.get("offsets", {})
    new_offsets: dict[str, int] = {}
    groups: dict[tuple[str, str], dict] = {}
    for path in targets():
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        off = offsets.get(path, 0)
        if off > size:
            off = 0  # the file was rewritten
        if off == size:
            new_offsets[path] = size
            continue
        start = max(0, off - OVERLAP)
        try:
            with open(path, "rb") as f:
                f.seek(start)
                data = f.read()
        except OSError:
            continue
        new_offsets[path] = start + len(data)
        hits = [h for h in scan_data(data, needles, live, key) if start + h["e"] > off]
        parsed: dict[int, object] = {}
        for h in hits:
            g = groups.setdefault(
                (h["label"], h["fp"]),
                {"label": h["label"], "fp": h["fp"], "count": 0, "where": []},
            )
            g["count"] += 1
            where = place(path, data, h["s"], h["raw"], parsed)
            if context:
                where["context"] = masked(data, h, needles)
            g["where"].append(where)
    findings = sorted(groups.values(), key=lambda g: min(w["ts"] for w in g["where"]))
    for g in findings:
        g["where"].sort(key=lambda w: w["ts"])
        g["first"] = g["where"][0]["ts"]
    return findings, new_offsets


# --- state, output, push ------------------------------------------------------


def load_state() -> dict:
    state = load_json(os.path.join(STATE_DIR, "state.json"))
    if not isinstance(state, dict) or "key" not in state:
        state = {"version": 1, "key": os.urandom(16).hex(), "offsets": {}, "pending": []}
        save_state(state)  # the HMAC key must outlive this run, or fingerprints drift
    state.setdefault("ignore", [])
    return state


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    path = os.path.join(STATE_DIR, "state.json")
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def log_error(msg: str) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "errors.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(TZ):%Y-%m-%d %H:%M} {msg[:300]}\n")
    except OSError:
        pass


def lock():
    os.makedirs(STATE_DIR, exist_ok=True)
    fd = os.open(os.path.join(STATE_DIR, "lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def hint(label: str) -> str:
    return next((h for prefix, h in HINTS if label.startswith(prefix)), "roter værdien")


def merge(pending: list[dict], findings: list[dict]) -> list[dict]:
    by_key = {(p["label"], p["fp"]): p for p in pending}
    for f in findings:
        slim = [{k: w[k] for k in ("file", "ts", "role", "session")} for w in f["where"]]
        p = by_key.setdefault(
            (f["label"], f["fp"]),
            {"label": f["label"], "fp": f["fp"], "count": 0, "first": f["first"], "where": []},
        )
        p["count"] += f["count"]
        p["first"] = min(p["first"], f["first"])
        p["where"] = (p["where"] + slim)[:MAX_SHOWN]
    return list(by_key.values())


def report(findings: list[dict], heading: str) -> None:
    print(f"🔐 {len(findings)} {heading}:")
    for f in findings:
        print(f"- {f['label']}  ×{f['count']}  fp {f['fp']}")
        seen = []
        for w in f["where"]:
            line = f"{w['ts']}  {w['role']}  session {w['session']}  {w['file']}"
            if line not in seen:
                seen.append(line)
        for line in seen[:MAX_SHOWN]:
            print(f"    {line}")
        if len(seen) > MAX_SHOWN:
            print(f"    … +{len(seen) - MAX_SHOWN} steder")
        for w in f["where"][:MAX_SHOWN]:
            if "context" in w:
                print(f"      «{w['context']}»")
        print(f"  → roter: {hint(f['label'])}")


def ha_get(path: str) -> dict | None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    try:
        return supervisor_get(path, token)
    except Exception:
        return None


def push(findings: list[dict]) -> bool:
    """Push labels and rotation hints; False (keep them queued) in AirBnB or on error."""
    mode = (ha_get("/core/api/states/input_select.house_mode") or {}).get("state")
    if mode in (None, "AirBnB", "unavailable", "unknown"):
        return False
    labels = [f["label"] for f in findings]
    shown = ", ".join(labels[:MAX_SHOWN])
    if len(labels) > MAX_SHOWN:
        shown += f" +{len(labels) - MAX_SHOWN}"
    hints = "; ".join(dict.fromkeys(hint(x) for x in labels))
    first = min(f["first"] for f in findings)
    body = {
        "title": "🔐 Hemmelighed i Claude-transskript",
        "message": f"{shown} (første {first}). Roter: {hints}. "
        "Detaljer: python3 scripts/secret_leak_scan.py --all",
    }
    req = urllib.request.Request(
        SUPERVISOR + NOTIFY,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except Exception as e:
        log_error(f"push: {type(e).__name__}")
        return False


def inventory() -> int:
    live = build_live()
    rows = sorted(
        (label, len(v), len(variants(v)), v.lower() in live.public)
        for v, label in live.labels.items()
    )
    for label, n, forms, public in rows:
        note = "  (offentligt navn: scannes ikke)" if public else ""
        note += "  (ord-grænse)" if n < SHORT else ""
        print(f"{label}  len {n}  former {forms}{note}")
    print(f"{len(rows)} værdier, {len(live.rt_ids)} refresh-token-id'er (JWT-tjek)")
    return 0


def hook() -> int:
    try:
        sys.stdin.read()
    except OSError, ValueError:
        pass
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--push", "--quiet"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=REPO,
    )
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["hook"]:
        try:
            return hook()
        except Exception:
            return 0
    flags = set(argv)
    quiet, context = "--quiet" in flags, "--context" in flags
    if "--inventory" in flags:
        return inventory()
    if "--all" in flags:
        state = load_state()
        findings, _ = scan(state, full=True, context=context)
        hidden = [f for f in findings if f["fp"] in state["ignore"]]
        findings = [f for f in findings if f["fp"] not in state["ignore"]]
        if findings:
            report(findings, "hemmeligheder i Claude-transskripter (alt, fuld scan)")
        elif not quiet:
            print("✅ ingen levende hemmeligheder i Claude-transskripterne")
        if hidden:
            print(f"({len(hidden)} ignorerede fingeraftryk ikke vist)")
        return 1 if findings else 0
    fd = lock()
    if fd is None:
        return 0  # another scan runs; it covers the same bytes
    try:
        return locked_main(argv, flags, quiet, context)
    finally:
        os.close(fd)


def locked_main(argv: list[str], flags: set[str], quiet: bool, context: bool) -> int:
    state = load_state()
    if "--ignore" in flags:
        fps = [a for a in argv if not a.startswith("--")]
        state["ignore"] = sorted(set(state["ignore"]) | set(fps))
        state["pending"] = [p for p in state["pending"] if p["fp"] not in fps]
        save_state(state)
        print(f"ignorerer {len(fps)} fingeraftryk ({len(state['ignore'])} i alt)")
        return 0
    if "--baseline" in flags:
        state["offsets"] = {p: os.path.getsize(p) for p in targets() if os.path.exists(p)}
        save_state(state)
        size = sum(state["offsets"].values()) / 1e6
        print(f"baseline: {len(state['offsets'])} filer ({size:.1f} MB) markeret som set")
        return 0
    findings, offsets = scan(state, full=False, context=context)
    findings = [f for f in findings if f["fp"] not in state["ignore"]]
    state["offsets"] = offsets
    state["pending"] = merge(state["pending"], findings)
    if "--push" in flags and state["pending"] and push(state["pending"]):
        state["pending"] = []
    state["last_run"] = datetime.now(TZ).isoformat(timespec="seconds")
    save_state(state)
    if findings:
        report(findings, "nye hemmeligheder i Claude-transskripter")
    elif not quiet:
        queued = f", {len(state['pending'])} i kø til push" if state["pending"] else ""
        print(f"✅ intet nyt{queued}")
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        log_error(f"main: {type(e).__name__}: {e}")
        sys.exit(0 if "--quiet" in sys.argv else 1)
