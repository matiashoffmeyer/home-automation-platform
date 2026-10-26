#!/usr/bin/env python3
"""gaeste_wifi.py — tænd/sluk routerens gæste-wifi (B267, 2026-10-25).

Kører i HA-core-containeren via shell_command.gaeste_wifi (og fra SSH-add-on'et
til test). Routeren er en Sagemcom F@st 3896; scriptet taler det samme
web-API som dens GUI (afledt af GUI'ens main.js, målt 25/10):

  login   POST /api/v1/login-params (login) → cookies salt + nonce
          POST /api/v1/login (login, auth_key, cnonce), hvor
          auth_key = sha512hex(sha512hex(user:nonce:sha512crypt(kode, salt)[3:])
                     + ":0:" + cnonce)
  bånd    GET/PUT /api/v2/wireless/guest24 og guest5 — en PUT SKAL have `ssid`
          med (ellers 400). `hidden: 1` betyder SYNLIG, så feltet sendes aldrig.
  adgang  PUT /api/v1/wireless/guest/settings guest_access=1 = "kun internet"

Alle kald er form-encoded; firmwaren har ingen CSRF. Navnet sættes fra
`gaeste_wifi_ssid` i secrets.yaml ved hver tænd/sluk. Koden står der også
(`gaeste_wifi_kode`) men skrives aldrig herfra: den sattes én gang i GUI-API'et.

Skriver KUN når routeren afviger fra det ønskede: hver ændring giver hoved-
wifi'en et kort blip (målt 25/10: Apollo'erne < 1 s, højttaleren 5 s).

  python3 gaeste_wifi.py on|off   # gør det, vent på at routeren melder det
  python3 gaeste_wifi.py status   # læs kun

Udskriver én JSON-linje (aldrig koder). Exit 0 = routeren står som ønsket,
1 = den gør ikke efter ventetiden, 2 = login/netværk fejlede.
"""

import hashlib
import http.cookiejar
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import ha_secrets

ROUTER = "http://192.168.0.1"
BAAND = {"24": "/api/v2/wireless/guest24", "5": "/api/v2/wireless/guest5"}
ADGANG = "/api/v1/wireless/guest/settings"
VENT_S = 40  # routeren anvender med forsinkelse (guest_access 25/10); shell_command dør ved 60 s

_ITOA64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
# Byte-rækkefølgen i SHA-crypt's base64 (Drepper, "Unix crypt using SHA-256 and SHA-512").
_ORDEN = [
    (0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4), (47, 5, 26),
    (6, 27, 48), (28, 49, 7), (50, 8, 29), (9, 30, 51), (31, 52, 10), (53, 11, 32),
    (12, 33, 54), (34, 55, 13), (56, 14, 35), (15, 36, 57), (37, 58, 16), (59, 17, 38),
    (18, 39, 60), (40, 61, 19), (62, 20, 41),
]  # fmt: skip


def sha512_crypt(kode: str, salt: str) -> str:
    """`openssl passwd -6 -salt SALT` i ren Python (crypt-modulet er væk i 3.13+)."""
    p, s = kode.encode(), salt.encode()[:16]
    sha = hashlib.sha512
    b = sha(p + s + p).digest()
    a = sha(p + s)
    for _ in range(len(p) // 64):
        a.update(b)
    a.update(b[: len(p) % 64])
    i = len(p)
    while i:
        a.update(b if i & 1 else p)
        i >>= 1
    c = a.digest()
    dp = sha(p * len(p)).digest()
    pp = (dp * (len(p) // 64 + 1))[: len(p)]
    ds = sha(s * (16 + c[0])).digest()
    ss = (ds * (len(s) // 64 + 1))[: len(s)]
    for r in range(5000):
        h = sha(pp if r & 1 else c)
        if r % 3:
            h.update(ss)
        if r % 7:
            h.update(pp)
        h.update(c if r & 1 else pp)
        c = h.digest()

    def b64(w: int, n: int) -> str:
        out = ""
        for _ in range(n):
            out += _ITOA64[w & 0x3F]
            w >>= 6
        return out

    tegn = "".join(b64((c[x] << 16) | (c[y] << 8) | c[z], 4) for x, y, z in _ORDEN)
    return f"$6${salt}${tegn}{b64(c[63], 2)}"


class Router:
    def __init__(self) -> None:
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def _kald(self, metode: str, sti: str, data: dict | None = None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(
            ROUTER + sti,
            body,
            {"Content-Type": "application/x-www-form-urlencoded"},
            method=metode,
        )
        with self.op.open(req, timeout=15) as r:
            tekst = r.read().decode()
        return json.loads(tekst) if tekst.strip() else None

    def _cookie(self, navn: str) -> str | None:
        return next((c.value for c in self.cj if c.name == navn), None)

    def login(self, bruger: str, kode: str) -> None:
        self._kald("POST", "/api/v1/login-params", {"login": bruger})
        salt, nonce = self._cookie("salt"), self._cookie("nonce")
        if not salt or not nonce:
            raise RuntimeError("login-params gav ingen salt/nonce")
        crypt = sha512_crypt(kode, salt)[3:]
        cnonce = str(secrets.randbelow(10**18)).rjust(19, "0")

        def h(x: str) -> str:
            return hashlib.sha512(x.encode()).hexdigest()

        noegle = h(h(f"{bruger}:{nonce}:{crypt}") + ":0:" + cnonce)
        self._kald("POST", "/api/v1/login", {"login": bruger, "auth_key": noegle, "cnonce": cnonce})

    def logout(self) -> None:
        try:
            self._kald("POST", "/api/v1/logout", {})
        except urllib.error.URLError, OSError, ValueError:
            pass  # sessionen udløber selv efter 15 min

    def baand(self, sti: str) -> dict:
        ssid = self._kald("GET", sti)[0]["wireless"]["ssid"]
        return {
            "enable": int(ssid["enable"]),
            "ssid": ssid["id"],
            "status": ssid.get("ssid_status"),
        }

    def adgang(self) -> dict:
        return self._kald("GET", ADGANG)[0]["guestSettings"]


def main() -> int:
    onsket = sys.argv[1] if len(sys.argv) > 1 else ""
    if onsket not in ("on", "off", "status"):
        print("brug: gaeste_wifi.py on|off|status", file=sys.stderr)
        return 2
    navn = ha_secrets.get("gaeste_wifi_ssid")
    r = Router()
    try:
        r.login(ha_secrets.get("router_admin_user"), ha_secrets.get("router_admin_password"))
        foer = {b: r.baand(sti) for b, sti in BAAND.items()}
        aendret = []
        if onsket != "status":
            vil = 1 if onsket == "on" else 0
            for b, sti in BAAND.items():
                if foer[b]["enable"] != vil or foer[b]["ssid"] != navn:
                    r._kald("PUT", sti, {"ssid": navn, "enable": vil})
                    aendret.append(b)
            if vil:
                a = r.adgang()
                if a.get("guest_24g_access") != 1 or a.get("guest_5g_access") != 1:
                    r._kald("PUT", ADGANG, {"guest_access": 1})
                    aendret.append("adgang")
        slut = time.monotonic() + (VENT_S if aendret else 0)
        while True:
            nu = {b: r.baand(sti) for b, sti in BAAND.items()}
            ok = onsket == "status" or all(
                v["ssid"] == navn and v["enable"] == (onsket == "on") for v in nu.values()
            )
            if ok or time.monotonic() > slut:
                break
            time.sleep(3)
        a = r.adgang()
        r.logout()
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, RuntimeError) as e:
        print(json.dumps({"ok": False, "fejl": type(e).__name__, "detalje": str(e)[:120]}))
        return 2
    svar = {
        "ok": ok,
        "onsket": onsket,
        "taendt": {b: v["enable"] for b, v in nu.items()},
        "oppe": {b: v["status"] for b, v in nu.items()},
        "navn_ok": all(v["ssid"] == navn for v in nu.values()),
        "kun_internet": a.get("guest_24g_access") == 1 and a.get("guest_5g_access") == 1,
        "aendret": aendret,
    }
    print(json.dumps(svar, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
