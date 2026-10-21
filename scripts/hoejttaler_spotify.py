#!/usr/bin/env python3
"""hoejttaler_spotify.py — er højttalerens Spotify Connect i live? (B202, 2026-10-09)

MÅLT 08-09/10: AxiomAir N3'ens librespot (0.1.0, inde i Volumio 2-OEM'en) var
VÆK om aftenen 08/10 — ingen `_spotify-connect._tcp` i mDNS, og Spotify på
telefonerne fandt ikke højttaleren — mens Volumio selv svarede (radioen kørte,
`getInfoNetwork` sagde `online: no`). Efter at højttaleren havde været af nettet
01:23 → 06:41 var den tilbage (zeroconf-port 43115, `getInfo` svarede). Intet på
N3'en genstarter librespot af sig selv, og firmwaren har intet kald der
genstarter KUN Spotify-servicen (web-UI'ets socket.io-events gennemgået) →
værktøjet er et reboot når den står stille.

Kører i HA-containeren (command_line-sensor, host-netværk, python-zeroconf):

  python3 hoejttaler_spotify.py           # JSON: connect on/off, aktiv bruger, Volumio-kilde,
                                          #       kilde=ha når MPD spiller Music Assistants strøm,
                                          #       kilde=bro når MPD spiller Spotify-broens,
                                          #       myair=true når en telefon spiller på Connect
  python3 hoejttaler_spotify.py reboot    # socket.io `reboot` (som web-UI'ets knap)
  python3 hoejttaler_spotify.py myair on|off   # myair til/fra (plugin'ets "Multi-user device")

myair til/fra (17/10): Volumios disablePlugin/enablePlugin er no-ops på N3'en
(librespot kørte uændret). Plugin'ets konto-side virker: "Multi-user device"
FRA uden brugernavn → librespot genstartes uden zeroconf og forsvinder fra
telefonerne (målt 05:41: gammel port død inden 5 s, mDNS tom). Højttaleren
genstartes IKKE. initvol/normalvolume læses og gemmes uændret.

librespots zeroconf-port er TILFÆLDIG pr. opstart → porten caches og slås kun op
i mDNS igen når den holder op med at svare.

`kilde` (B204): "Spotify via HA" spiller gennem Music Assistant → DLNA → MPD.
Volumios getState følger MPD's play/stop, men IKKE metadata under DLNA (målt
09/10: viste stadig P4's uri mens MPD spillede MA's strøm) → filen læses i MPD
selv (port 6600, intet password). MA's stream-server er port 8097.
"""

import json
import socket
import sys
import time
import urllib.request

HOST = "192.0.2.42"
SIO = f"http://{HOST}:3000/socket.io/?EIO=3&transport=polling"
CACHE = "/tmp/hoejttaler_spotify_port"
STYPE = "_spotify-connect._tcp.local."


def get(url, timeout=4):
    return urllib.request.urlopen(url, timeout=timeout).read().decode("utf-8", "replace")


def get_info(port):
    try:
        d = json.loads(get(f"http://{HOST}:{port}/?action=getInfo", 3))
        return d if d.get("remoteName") is not None else None
    except Exception:
        return None


def mdns_port():
    """Port for den spotify-connect-instans i mDNS der peger på HOST."""
    try:
        from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf
    except ImportError:
        return None
    names = []

    class L:
        def add_service(self, zc, t, n):
            names.append(n)

        def update_service(self, zc, t, n):
            pass

        def remove_service(self, zc, t, n):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, STYPE, L())
        time.sleep(3)
        for n in set(names):
            info = ServiceInfo(STYPE, n)
            if info.request(zc, 2000) and HOST in info.parsed_addresses():
                return info.port
    finally:
        zc.close()
    return None


def mpd_kilde():
    """'ha' når MPD spiller en Music Assistant-strøm, 'bro' når den spiller
    Spotify-broens (B237, port 8098), 'play'/'stop'/… ellers."""
    try:
        with socket.create_connection((HOST, 6600), timeout=3) as sk:
            sk.sendall(b"status\ncurrentsong\nclose\n")
            data = b""
            while chunk := sk.recv(4096):
                data += chunk
    except OSError:
        return None
    felt = dict(
        line.split(": ", 1) for line in data.decode("utf-8", "replace").splitlines() if ": " in line
    )
    if felt.get("state") == "play" and ":8097/" in felt.get("file", ""):
        return "ha"
    if felt.get("state") == "play" and ":8098/spotify." in felt.get("file", ""):
        return "bro"
    return felt.get("state")


def probe():
    out = {
        "connect": "off",
        "user": "",
        "port": None,
        "service": None,
        "status": None,
        "kilde": None,
        "myair": False,
    }
    try:
        s = json.loads(get(f"http://{HOST}:3000/api/v1/getState"))
        out["service"] = s.get("service") or s.get("trackType")
        out["status"] = s.get("status")
    except Exception:
        print(json.dumps(out))  # højttaleren er væk — ikke et Spotify-problem
        return
    out["kilde"] = mpd_kilde()
    port = None
    try:
        with open(CACHE) as f:
            port = int(f.read().strip())
    except OSError, ValueError:
        pass
    info = get_info(port) if port else None
    if info is None:
        port = mdns_port()
        info = get_info(port) if port else None
        if info is not None:
            try:
                with open(CACHE, "w") as f:
                    f.write(str(port))
            except OSError:
                pass
    if info is not None:
        out.update(connect="on", port=port, user=info.get("activeUser") or "")
    # myair = en telefon spiller Spotify på højttalerens egen Connect. MÅLT 10/10
    # 09:47-09:50: activeUser forblev TOM under 3 min myair-afspilning (telefonen
    # er logget ind med konto, ikke zeroconf) — kun Volumios kilde viste det
    # (service volspotconnect2, status play/pause). activeUser beholdes som 2. vej.
    out["myair"] = bool(out["user"]) or (
        out["service"] == "volspotconnect2" and out["status"] in ("play", "pause")
    )
    print(json.dumps(out))


def sio_emit(event, data=None, wait=3.0):
    """Ét socket.io-event (EIO=3 polling) → svar-teksten fra de næste polls."""
    hs = get(SIO)
    url = f"{SIO}&sid={json.loads(hs[hs.index('{') :])['sid']}"
    get(f"{url}&t={time.time()}")
    msg = "42" + json.dumps([event] + ([data] if data is not None else []))
    urllib.request.urlopen(
        urllib.request.Request(
            url,
            data=f"{len(msg)}:{msg}".encode(),
            headers={"Content-Type": "text/plain;charset=UTF-8"},
        ),
        timeout=10,
    ).read()
    out, end = [], time.time() + wait
    while time.time() < end:
        try:
            out.append(get(f"{url}&t={time.time()}", wait))
        except Exception:
            break
    return "".join(out)


def myair(on):
    page = "music_service/volspotconnect2"
    svar = sio_emit("getUiConfig", {"page": page})
    cfg = json.JSONDecoder().raw_decode(svar[svar.index('"pushUiConfig",') + 15 :])[0]
    felter = {c["id"]: c for sek in cfg["sections"] for c in sek["content"]}
    initvol = int(felter["initvol"]["config"]["bars"][0]["value"])
    sio_emit(
        "callMethod",
        {
            "endpoint": page,
            "method": "saveVolspotconnectAccount",
            "data": {
                "initvol": [initvol],
                "normalvolume": bool(felter["normalvolume"]["value"]),
                "shareddevice": on,
                "username": "",
                "password": "",
            },
        },
        wait=1.0,
    )
    print(f"myair {'til' if on else 'fra'} (initvol {initvol})")


def reboot():
    hs = get(SIO)
    sid = json.loads(hs[hs.index("{") :])["sid"]
    url = f"{SIO}&sid={sid}"
    get(f"{url}&t={time.time()}")
    msg = '42["reboot"]'
    req = urllib.request.Request(
        url, data=f"{len(msg)}:{msg}".encode(), headers={"Content-Type": "text/plain;charset=UTF-8"}
    )
    urllib.request.urlopen(req, timeout=10).read()
    print("reboot sendt")


if __name__ == "__main__":
    if sys.argv[1:2] == ["reboot"]:
        reboot()
    elif sys.argv[1:2] == ["myair"] and sys.argv[2:3] in (["on"], ["off"]):
        myair(sys.argv[2] == "on")
    else:
        probe()
