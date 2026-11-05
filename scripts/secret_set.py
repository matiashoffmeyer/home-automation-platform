#!/usr/bin/env python3
"""New keys and passwords in secrets.yaml without a NUC keyboard, unseen by Claude.

    secret_set.py generate <key> [--length 32] [--chars alnum|hex|urlsafe] [--replace]
    secret_set.py ask <key> "<what, short Danish>" [--deadline 15] [--replace]
                  [--no-push] [--lan]
    secret_set.py keys

generate  A random value for a machine password (a speaker, an MQTT user, a webhook
          id). It is written and never printed: the output is the key and the length.
ask       For a value only the user has (an API key from a web page). A one-time page
          on the house's tailnet address, behind a random path, takes it from the
          phone's browser. The push carries the link, which is printed for the chat
          too. The page closes after one save, a cancel or the deadline. --lan serves
          it on the home network instead, for a phone without Tailscale switched on.
keys      Key names and lengths: all Claude needs to see.

Exit codes: 0 saved, 1 cancelled, 2 no answer by the deadline, 3 AirBnB (no push:
run again with --no-push and give the link in the chat), 4 error.

Every value goes through ha_secrets.put, which reads it back before it lands and keeps
the previous file as secrets.yaml.prev. Nothing here logs, prints or raises with a
value in it. The only place one is ever shown is the page itself, on the phone, when
the user ticks "Vis".
"""

from __future__ import annotations

import argparse
import html
import http.server
import ipaddress
import json
import os
import secrets
import socket
import socketserver
import string
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import ha_secrets

NOTIFY = "mobile_app_phone_a"
REST = "http://supervisor/core/api"
TAG = "claude_secret_set"
TAILNET = ipaddress.ip_network("100.64.0.0/10")  # Tailscale hands out addresses here
MAX_BODY = 8192
ALPHABETS = {
    "alnum": string.ascii_letters + string.digits,
    "hex": string.digits + "abcdef",
    "urlsafe": string.ascii_letters + string.digits + "-_",
}
SAVED, CANCELLED, NO_ANSWER, AIRBNB, ERROR = 0, 1, 2, 3, 4


def api(path: str, body: dict | None = None, timeout: float = 10) -> object:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN mangler — kør fra SSH-add-on'et")
    req = urllib.request.Request(
        f"{REST}/{path}",
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def logbook(message: str) -> None:
    """Best effort: which key changed, and how, in HA's logbook. Never the value."""
    try:
        api("services/logbook/log", {"name": "Claude-nøgle", "message": message}, timeout=5)
    except OSError, RuntimeError, ValueError:
        pass


def refusal(key: str, path: Path, replace: bool) -> str | None:
    if not ha_secrets.KEY.fullmatch(key):
        return f"{key!r} er ikke et gyldigt nøglenavn"
    n = len(ha_secrets.load(path).get(key) or "")
    if n and not replace:
        return (
            f"{key} findes allerede ({n} tegn) — kør igen med --replace "
            f"(den gamle værdi ligger bagefter i {path.name}.prev)"
        )
    return None


def saved(key: str, n: int, new: bool, path: Path) -> None:
    print(f"GEMT {key} ({n} tegn{', ny nøgle' if new else ''}) i {path}")
    if new:
        print("   Ny nøgle → skriv den i secrets.example.yaml med en pladsholder.")


# ── generate ──────────────────────────────────────────────────────────────────


def make(chars: str, length: int) -> str:
    alphabet = ALPHABETS[chars]
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        # A device that demands mixed classes rejects an all-letter password.
        tests = (str.islower, str.isupper, str.isdigit)
        if chars != "alnum" or all(any(t(c) for c in value) for t in tests):
            return value


def cmd_generate(a: argparse.Namespace) -> int:
    path = ha_secrets.SECRETS_FILE
    why = refusal(a.key, path, a.replace)
    if why:
        print(f"AFVIST: {why}", file=sys.stderr)
        return ERROR
    try:
        new = ha_secrets.put(a.key, make(a.chars, a.length), path)
    except (OSError, ValueError) as e:  # put names the key and the file, never the value
        print(f"FEJL: {e}", file=sys.stderr)
        return ERROR
    saved(a.key, a.length, new, path)
    logbook(f"{a.key}: ny tilfældig værdi ({a.length} tegn)")
    return SAVED


# ── ask ───────────────────────────────────────────────────────────────────────

STYLE = (
    "body{font:18px/1.4 system-ui,sans-serif;max-width:30em;margin:1.5em auto;padding:0 1em}"
    "input,button{font:inherit;width:100%;box-sizing:border-box;padding:.7em;margin:.3em 0}"
    "button{border:0;border-radius:.4em;background:#03a9f4;color:#fff}"
    "button.nej{background:#ddd;color:#000}.lille{color:#666;font-size:.85em}.fejl{color:#c00}"
)
HEADERS = {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
}


def page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="da"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>"
        f"<body><h2>{html.escape(title)}</h2>{body}</body></html>"
    )


GONE = page("Lukket", "<p>Linket er brugt, udløbet eller forkert.</p>")


class Result(NamedTuple):
    outcome: str  # saved | cancelled | error
    length: int = 0
    new: bool = False
    error: str = ""


class Page(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """One form for one key, answered once.

    Threaded because a browser may open a spare connection it never uses, and a
    single-threaded server would sit on it until the socket times out.
    """

    daemon_threads = True
    block_on_close = False  # serve() waits for the one answer that matters
    timeout = 1  # handle_request() comes back every second, so the deadline holds

    def __init__(
        self,
        host: str,
        peers: ipaddress.IPv4Network,
        key: str,
        what: str,
        path: Path,
        until: str,
        bind: str = "0.0.0.0",  # noqa: S104 — verify_request keeps it to `peers`
    ) -> None:
        # Not bound to the tailnet address: traffic to it is rewritten to the LAN
        # address before the socket lookup, so a socket bound there refuses every
        # connection (measured 5/11; HA's own :8123 listens on 0.0.0.0 too).
        super().__init__((bind, 0), Handler)
        self.host, self.peers = host, peers
        self.key, self.what, self.secrets_path, self.until = key, what, path, until
        self.route = "/" + secrets.token_urlsafe(24)
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.closed = False
        self.result: Result | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.server_address[1]}{self.route}"

    def verify_request(self, request, client_address) -> bool:  # noqa: ANN001
        # The sender survives the rewrite: a phone on the tailnet keeps its 100.x address.
        return ipaddress.ip_address(client_address[0]) in self.peers

    def form(self, problem: str = "") -> str:
        note = f'<p class="fejl">{html.escape(problem)}</p>' if problem else ""
        return page(
            self.what,
            f'{note}<form method="post" autocomplete="off">'
            '<input name="v" type="password" autocomplete="off" autocapitalize="off" '
            'autocorrect="off" spellcheck="false" placeholder="Indsæt her" autofocus>'
            '<label class="lille"><input type="checkbox" style="width:auto" '
            "onclick=\"v.type=this.checked?'text':'password'\"> Vis</label>"
            '<button name="a" value="gem">Gem</button>'
            '<button name="a" value="annuller" class="nej">Annuller</button></form>'
            f'<p class="lille">Gemmes som <code>{html.escape(self.key)}</code> i secrets.yaml '
            f"og vises ingen andre steder. Linket virker én gang, til kl. {self.until}.</p>",
        )

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001
        # The default prints a traceback, whose lines may quote what was being parsed.
        print(f"FEJL i en forespørgsel: {sys.exc_info()[0].__name__}", file=sys.stderr)


class Handler(http.server.BaseHTTPRequestHandler):
    server: Page
    server_version = "secret_set"
    sys_version = ""
    timeout = 10

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # the request line carries the route

    def reply(self, code: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        for name, value in HEADERS.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        s = self.server
        if self.path != s.route or s.closed or s.result is not None:
            return self.reply(404, GONE)
        self.reply(200, s.form())

    def do_POST(self) -> None:  # noqa: N802
        s = self.server
        if self.path != s.route:
            return self.reply(404, GONE)
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            n = 0
        if not 0 < n <= MAX_BODY:
            return self.reply(413, s.form("Tom eller for stor — prøv igen."))
        try:
            fields = urllib.parse.parse_qs(
                self.rfile.read(n).decode("utf-8"), keep_blank_values=True, max_num_fields=4
            )
        except UnicodeDecodeError, ValueError:
            return self.reply(400, s.form("Kunne ikke læses — prøv igen."))
        cancel = fields.get("a") == ["annuller"]
        value = (fields.get("v") or [""])[0].strip()
        if not cancel and (not value or not value.isprintable()):
            return self.reply(400, s.form("Tom, eller mere end én linje — prøv igen."))
        with s.lock:
            if s.closed or s.result is not None:
                return self.reply(404, GONE)
            if cancel:
                s.result = Result("cancelled")
            else:
                try:
                    s.result = Result(
                        "saved", len(value), ha_secrets.put(s.key, value, s.secrets_path)
                    )
                except (OSError, ValueError) as e:  # names the key and the file, never the value
                    s.result = Result("error", error=str(e))
        del value
        try:
            r = s.result
            if r.outcome == "saved":
                key = html.escape(s.key)
                self.reply(200, page("Gemt ✓", f"<p>{r.length} tegn i <code>{key}</code>.</p>"))
            elif r.outcome == "cancelled":
                self.reply(200, page("Annulleret", "<p>Intet er gemt.</p>"))
            else:
                self.reply(500, page("Ikke gemt", f"<p>{html.escape(r.error)}</p>"))
        finally:
            s.done.set()  # only now: the phone has its answer before the script may exit


def serve(server: Page, seconds: float) -> Result | None:
    """Answer requests until the page is used or the deadline passes."""
    end = time.monotonic() + seconds
    try:
        while not server.done.is_set() and time.monotonic() < end:
            server.handle_request()
        with server.lock:  # a save in progress at the deadline still counts
            server.closed = True
            result = server.result
        if result is not None:
            server.done.wait(5)
        return result
    finally:
        server.server_close()


def address(lan: bool) -> tuple[str, ipaddress.IPv4Network]:
    """The link's host and the senders it serves: the host of HA's external_url and
    the tailnet, or with --lan the host of internal_url and its /24."""
    field = "internal_url" if lan else "external_url"
    url = (api("config") or {}).get(field) or ""
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        raise RuntimeError(f"HA har ingen {field} at lytte på")
    ip = ipaddress.ip_address(socket.gethostbyname(host))
    if lan:
        ok, net = ip.is_private and not ip.is_loopback and ip not in TAILNET, "hjemmenettet"
        peers = ipaddress.ip_network(f"{ip}/24", strict=False)
    else:
        ok, net, peers = ip in TAILNET, f"tailnettet ({TAILNET})", TAILNET
    if not ok:
        raise RuntimeError(f"{field} peger på {ip}, ikke {net} — siden åbnes ikke dér")
    return str(ip), peers


def house_mode() -> str:
    return api("states/input_select.house_mode")["state"]


def push(url: str, what: str, until: str) -> None:
    # The route rides through the push service and the recorder's call_service row;
    # it can only set this one key, once, from the tailnet, until the deadline.
    api(
        f"services/notify/{NOTIFY}",
        {
            "title": f"Indsæt: {what}",
            "message": f"Tryk og indsæt den på siden (én gang, til kl. {until}). "
            "Claude ser den ikke.",
            "data": {
                "tag": TAG,
                "priority": "high",
                "ttl": 0,
                "clickAction": url,
                "actions": [{"action": "URI", "title": "Åbn siden", "uri": url}],
            },
        },
    )


def cmd_ask(a: argparse.Namespace) -> int:
    path = ha_secrets.SECRETS_FILE
    why = refusal(a.key, path, a.replace)
    if why:
        print(f"AFVIST: {why}", file=sys.stderr)
        return ERROR
    pushing = not a.no_push
    try:
        if pushing and house_mode() == "AirBnB":
            print(
                "AIRBNB: ingen push (telefonen kan være hos gæsten). Er brugeren i chatten: "
                "kør igen med --no-push og giv linket dér."
            )
            return AIRBNB
        until = datetime.fromtimestamp(time.time() + a.deadline * 60).strftime("%H:%M")
        server = Page(*address(a.lan), a.key, a.what, path, until)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as e:
        print(f"FEJL: {e}", file=sys.stderr)
        return ERROR
    print(f"SIDE (én gang, til kl. {until}): {server.url}", flush=True)
    if pushing:
        try:
            push(server.url, a.what, until)
            print("PUSH sendt", flush=True)
        except (OSError, RuntimeError, ValueError) as e:
            print(f"PUSH fejlede ({e}) — giv linket i chatten", flush=True)
    result = serve(server, a.deadline * 60)
    if pushing:
        try:
            api(
                f"services/notify/{NOTIFY}", {"message": "clear_notification", "data": {"tag": TAG}}
            )
        except OSError, RuntimeError, ValueError:
            pass
    if result is None:
        print(f"INTET SVAR inden kl. {until}: {a.key} er uændret")
        return NO_ANSWER
    if result.outcome == "cancelled":
        print(f"ANNULLERET: {a.key} er uændret")
        return CANCELLED
    if result.outcome == "error":
        print(f"FEJL: {result.error}", file=sys.stderr)
        return ERROR
    saved(a.key, result.length, result.new, path)
    logbook(f"{a.key}: ny værdi fra telefonen ({result.length} tegn)")
    return SAVED


# ── keys ──────────────────────────────────────────────────────────────────────


def cmd_keys(_: argparse.Namespace) -> int:
    path = ha_secrets.SECRETS_FILE
    found = ha_secrets.load(path)
    print(f"{path}: {len(found)} nøgler (navn, længde)")
    for key, value in found.items():
        print(f"  {key:<40} {len(value):>4}")
    return SAVED


def length(text: str) -> int:
    n = int(text)
    if not 8 <= n <= 128:
        raise argparse.ArgumentTypeError("mellem 8 og 128 tegn")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="tilfældig maskine-kode, vises aldrig")
    g.add_argument("key")
    g.add_argument("--length", type=length, default=32)
    g.add_argument("--chars", choices=sorted(ALPHABETS), default="alnum")
    g.add_argument("--replace", action="store_true", help="erstat en eksisterende værdi")
    g.set_defaults(run=cmd_generate)
    k = sub.add_parser("ask", help="engangs-side: brugeren indsætter værdien på telefonen")
    k.add_argument("key")
    k.add_argument("what", help='kort dansk tekst til pushen og siden, fx "Anthropic API-nøgle"')
    k.add_argument("--deadline", type=int, default=15, help="minutter siden lever (standard 15)")
    k.add_argument("--replace", action="store_true", help="erstat en eksisterende værdi")
    k.add_argument("--no-push", action="store_true", help="kun linket i chatten (AirBnB)")
    k.add_argument("--lan", action="store_true", help="hjemmenettet i stedet for tailnettet")
    k.set_defaults(run=cmd_ask)
    sub.add_parser("keys", help="nøglenavne og længder").set_defaults(run=cmd_keys)
    a = p.parse_args(argv)
    return a.run(a)


if __name__ == "__main__":
    sys.exit(main())
