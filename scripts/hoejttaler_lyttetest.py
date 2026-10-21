#!/usr/bin/env python3
"""hoejttaler_lyttetest.py — HØRER køkken-kameraet højttalerens radio? (2026-10-09)

Bevis for "radioen spiller" der ikke stoler på Volumio/MPD's egen state:
krydskorrelerer kameraets mikrofon (Tapo 192.0.2.188, RTSP fra secrets.yaml
`gestus_kamera_rtsp`) med den stream højttaleren spiller (getState `uri`).

MÅLT 09/10 (P4, volumen 25 %): lydNIVEAU skiller IKKE (mean −57 dB med og uden
radio — baggrunden er lige så høj), men envelope-korrelationen gør: spiller
5/5 gange 0,23-0,48 ved lag 0,3-0,8 s; stoppet fandt søgningen kun støj ved
TILFÆLDIGT lag (−0,19 @ 14,9 s, 0,12 @ 13,9 s) → afgørelsen søger kun lag
−0,5…2 s og kræver ≥ 0,15.
Kører i HA-containeren (ffmpeg + numpy). Intet gemmes; kun tal printes.
I AirBnB er kameraet pakket væk → scriptet fejler (forventet).

  docker exec homeassistant python3 /config/scripts/hoejttaler_lyttetest.py [sek]
"""

import json
import subprocess
import sys
import threading
import urllib.request

import numpy as np

import ha_secrets

SR, HOP = 8000, 160  # 50 Hz envelope
T = int(sys.argv[1]) if len(sys.argv) > 1 else 40
cam = ha_secrets.get("gestus_kamera_rtsp")
st = json.load(urllib.request.urlopen("http://192.0.2.42:3000/api/v1/getState", timeout=5))
ref = st.get("uri") or ""
if not ref.startswith("http"):
    sys.exit(
        f"ingen stream at sammenligne med (service {st.get('service')}, status {st.get('status')})"
    )
out = {}


def grab(k, args):
    r = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            *args,
            "-t",
            str(T),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SR),
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        timeout=T + 60,
    )
    out[k] = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)


th = [
    threading.Thread(target=grab, args=("cam", ["-rtsp_transport", "tcp", "-i", cam])),
    threading.Thread(target=grab, args=("ref", ["-i", ref])),
]
[t.start() for t in th]
[t.join() for t in th]


def env(x):
    x = np.diff(x)
    n = len(x) // HOP
    e = np.log(np.sqrt((x[: n * HOP].reshape(n, HOP) ** 2).mean(1)) + 1)
    return (e - e.mean()) / (e.std() + 1e-9)


def best(c, r):
    L = min(len(c), len(r))
    b = (0.0, 0.0)
    for lag in range(-25, 101):  # −0,5…2 s: højttaler→mikrofon-forsinkelsen
        x, y = (c[lag:L], r[: L - lag]) if lag >= 0 else (c[: L + lag], r[-lag:L])
        if len(x) >= 500:
            v = float(np.dot(x, y) / len(x))
            if v > b[0]:
                b = (v, lag * HOP / SR)
    return b


if min(len(out.get("cam", [])), len(out.get("ref", []))) < SR * 10:
    sys.exit("for lidt lyd fra kamera eller stream")
c, r = env(out["cam"]), env(out["ref"])
v, lag = best(c, r)
nul, _ = best(c, r[::-1])  # samme søgning mod baglæns reference = støjgulvet
print(
    f"korrelation {v:.3f} (lag {lag:.2f} s), støjgulv {nul:.3f} → "
    f"{'HØRBAR' if v >= 0.15 and v > nul + 0.08 else 'ikke hørbar'}  [{st.get('status')} {st.get('service')} vol {st.get('volume')}]"
)
