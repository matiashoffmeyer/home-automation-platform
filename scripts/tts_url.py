#!/usr/bin/env python3
"""tts_url.py — byg en afspillelig TTS-URL til højttaleren (AxiomAir N3 / Volumio).

Volumio-integrationens play_media tager KUN JSON ({"uri": …, "service": …}), så
HA's egen `tts.speak` (der sender media-source://tts/…) kaster JSONDecodeError
på den. Vi beder derfor HA om en almindelig HTTP-URL til lydfilen via
POST /api/tts_get_url og pakker den selv ind (packages/hoejttaler_annoncering.yaml).

Brug (fra shell_command, i core-containeren):
    python3 /config/scripts/tts_url.py <besked som base64> [sprog] [engine]

Beskeden kommer som base64, fordi HA shlex-splitter et templated shell_command
EFTER renderingen — et anførselstegn eller en apostrof i teksten ville ellers
flytte argument-grænserne. Base64 består kun af [A-Za-z0-9+/=].

Udskriver JSON på stdout: {"url": …, "sekunder": …}. URL'en bygger HA af
internal_url (http://192.0.2.151:8123), som højttaleren kan nå på LAN'et, og
tts_proxy kræver intet login (målt 2026-10-07: 200 audio/mpeg uden token).
Scriptet HENTER selv filen én gang: det varmer HA's TTS-cache (højttaleren får
filen med det samme) og giver lydens præcise længde, så musikken genoptages når
sætningen er slut — Volumio-integrationen poller kun hvert 10. s og kan ikke
selv sige det. Google Translate leverer CBR MPEG-2 Layer III, 64 kbps / 24 kHz
(målt: "Kitchen timer is done" = 16 896 B = 2,1 s). Exit 1 + besked på stderr
ved fejl — kalderen tjekker at url starter med "http".

STILHED BAGI (2026-10-13): Volumio afspiller filen som "webradio" og starter
den FORFRA når den er slut — og vi genoptager radioen først længde + 2 s efter
play_media, så højttaleren nåede at sige "Good morning" igen (13/10 06:38).
Derfor lægges PAD_SEKUNDER stille MP3-frames bag talen (samme header, nul
side-info = dekoder-stilhed), og højttaleren får kopien fra /config/www
(/local/, intet login som tts_proxy). "sekunder" er stadig TALENS længde.

Token: ha_api_token fra secrets.yaml (samme long-lived token
som notif_queue.py/plant_notify.py). SUPERVISOR_TOKEN duer IKKE her: proxyen
afviser den for /core/api fra shell_command (.claude/rules/scripts_api.md).
"""

import base64
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

import ha_secrets

HA_URL = "http://127.0.0.1:8123"
DEFAULT_ENGINE = "tts.google_translate_en_com"
WWW_DIR = "/config/www/hoejttaler_tts"
PAD_SEKUNDER = 5
MAX_ALDER_S = 2 * 86400


def get_token():
    return ha_secrets.get(ha_secrets.HA_API_TOKEN)


# kbps pr. bitrate-indeks, Layer III. MPEG-1 og MPEG-2/2.5 har hver sin tabel.
_BITRATE_L3 = {
    "1": [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    "2": [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}


_SAMPLERATE = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def foerste_frame(data):
    """Index for første MPEG-frame-header (efter et evt. ID3v2-tag), ellers -1."""
    i = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        # ID3v2: størrelsen er 4 syncsafe-bytes (7 bit hver).
        i = 10 + ((data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9])
    while i + 4 <= len(data) and not (data[i] == 0xFF and data[i + 1] & 0xE0 == 0xE0):
        i += 1
    return i if i + 4 <= len(data) else -1


def mp3_sekunder(data):
    """Længde af en CBR-MP3 ud fra første frame-header. 0 hvis ukendt."""
    i = foerste_frame(data)
    if i < 0:
        return 0.0
    version = (data[i + 1] >> 3) & 0x03  # 3 = MPEG-1, 2 = MPEG-2, 0 = 2.5
    layer = (data[i + 1] >> 1) & 0x03  # 1 = Layer III
    idx = (data[i + 2] >> 4) & 0x0F
    if layer != 1 or idx in (0, 15):
        return 0.0
    kbps = _BITRATE_L3["1" if version == 3 else "2"][idx]
    return round((len(data) - i) * 8 / (kbps * 1000), 2)


def stille_frames(data, sekunder):
    """Stille frames i samme format som filens første frame. b'' hvis ukendt."""
    i = foerste_frame(data)
    if i < 0:
        return b""
    version = (data[i + 1] >> 3) & 0x03
    layer = (data[i + 1] >> 1) & 0x03
    idx = (data[i + 2] >> 4) & 0x0F
    sr_idx = (data[i + 2] >> 2) & 0x03
    if layer != 1 or idx in (0, 15) or sr_idx == 3 or version == 1:
        return b""
    kbps = _BITRATE_L3["1" if version == 3 else "2"][idx]
    sr = _SAMPLERATE[version][sr_idx]
    mpeg1 = version == 3
    laengde = (144000 if mpeg1 else 72000) * kbps // sr
    samples = 1152 if mpeg1 else 576
    # Protection-bit 1 (ingen CRC), padding-bit 0; resten nul = main_data_begin 0
    # og part2_3_length 0 → dekoderen giver stilhed.
    header = bytes([data[i], data[i + 1] | 0x01, data[i + 2] & 0xFD, data[i + 3]])
    return (header + bytes(laengde - 4)) * math.ceil(sekunder * sr / samples)


def gem_med_stilhed(data, url, noegle):
    """Skriv talen + stilhed til WWW_DIR og returnér /local/-URL'en (samme host
    som tts-URL'en). Fejler noget, returneres tts-URL'en uændret."""
    pad = stille_frames(data, PAD_SEKUNDER)
    if not pad:
        return url
    os.makedirs(WWW_DIR, exist_ok=True)
    nu = time.time()
    for navn in os.listdir(WWW_DIR):
        sti = os.path.join(WWW_DIR, navn)
        if nu - os.path.getmtime(sti) > MAX_ALDER_S:
            os.remove(sti)
    navn = hashlib.sha1(noegle.encode()).hexdigest()[:16] + ".mp3"
    sti = os.path.join(WWW_DIR, navn)
    with open(sti + ".tmp", "wb") as f:
        f.write(data + pad)
    os.replace(sti + ".tmp", sti)
    u = urllib.parse.urlsplit(url)
    return f"{u.scheme}://{u.netloc}/local/hoejttaler_tts/{navn}"


def main(argv):
    if len(argv) < 2:
        print("brug: tts_url.py <besked-base64> [sprog] [engine]", file=sys.stderr)
        return 1
    besked = base64.b64decode(argv[1]).decode("utf-8").strip()
    sprog = argv[2] if len(argv) > 2 and argv[2] else "en"
    engine = argv[3] if len(argv) > 3 and argv[3] else DEFAULT_ENGINE
    if not besked:
        print("tom besked", file=sys.stderr)
        return 1
    body = json.dumps({"engine_id": engine, "message": besked, "language": sprog}).encode()
    req = urllib.request.Request(
        HA_URL + "/api/tts_get_url",
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + get_token(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        url = json.loads(resp.read().decode("utf-8")).get("url", "")
    if not url.startswith("http"):
        print(f"intet url i svaret: {url!r}", file=sys.stderr)
        return 1
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = resp.read()
    sekunder = mp3_sekunder(data)
    try:
        url = gem_med_stilhed(data, url, f"{engine}|{sprog}|{besked}")
    except OSError as e:
        print(f"tts_url: ingen stilhed bagi ({e}) — bruger tts-URL'en", file=sys.stderr)
    print(json.dumps({"url": url, "sekunder": sekunder}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as e:  # noqa: BLE001 — shell_command skal se en ren fejl
        print(f"tts_url: {e}", file=sys.stderr)
        sys.exit(1)
