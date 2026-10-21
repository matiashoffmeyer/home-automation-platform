#!/usr/bin/env python3
"""Re-send the kitchen microphone's saved clips to speech-to-phrase.

The shim (gesture_frame_shim >= 0.13.0) keeps every region that fell inside an
open arming window in /share/gesture_frame_shim/clips, named
`<time>_<camera>_<verdict>-<seconds>s.wav`. This replays them against the same
STT the shim uses, as-is and in a few variants, so a mishearing can be split
into "the cut was wrong" and "the engine hears it wrong" without asking the
cook to speak again.

    python3 scripts/stemme_replay.py                 # all clips, all variants
    python3 scripts/stemme_replay.py 20260928-1725   # filename filter
    python3 scripts/stemme_replay.py --join A B      # glue two regions together

Variants:
    raw     exactly what the shim sent
    pad     0.4 s of silence before and after (Kaldi likes a run-in)
    norm    peak-normalised to -3 dBFS (the camera mic is quiet)
    padnorm both
"""

import array
import glob
import json
import math
import os
import socket
import sys
import wave

HOST, PORT = "core-speech-to-phrase", 10300
RATE = 16000
CLIPS = "/share/gesture_frame_shim/clips"


def transcribe(pcm):
    sock = socket.create_connection((HOST, PORT), timeout=30)
    rd = sock.makefile("rb")

    def send(kind, data=None, payload=None):
        ev = {"type": kind, "data": data or {}}
        if payload:
            ev["payload_length"] = len(payload)
        sock.sendall((json.dumps(ev) + "\n").encode())
        if payload:
            sock.sendall(payload)

    audio = {"rate": RATE, "width": 2, "channels": 1}
    send("transcribe")
    send("audio-start", audio)
    step = RATE * 2 // 10
    for i in range(0, len(pcm), step):
        send("audio-chunk", audio, pcm[i : i + step])
    send("audio-stop")
    try:
        while True:
            line = rd.readline()
            if not line:
                return "<closed>"
            ev = json.loads(line)
            if ev.get("data_length"):
                ev["data"] = json.loads(rd.read(ev["data_length"]))
            if ev.get("payload_length"):
                rd.read(ev["payload_length"])
            if ev["type"] == "transcript":
                return ev.get("data", {}).get("text", "")
    finally:
        sock.close()


def load(path):
    with wave.open(path) as w:
        return w.readframes(w.getnframes())


def stats(pcm):
    s = array.array("h")
    s.frombytes(pcm)
    peak = max(abs(v) for v in s) or 1
    rms = math.sqrt(sum(v * v for v in s) / len(s)) or 1
    return 20 * math.log10(peak / 32768), 20 * math.log10(rms / 32768)


def norm(pcm, target_db=-3.0):
    s = array.array("h")
    s.frombytes(pcm)
    peak = max(abs(v) for v in s) or 1
    g = (32768 * 10 ** (target_db / 20)) / peak
    return array.array("h", (max(-32768, min(32767, int(v * g))) for v in s)).tobytes()


def pad(pcm, sec=0.4):
    z = b"\x00\x00" * int(RATE * sec)
    return z + pcm + z


def variants(pcm):
    return {"raw": pcm, "pad": pad(pcm), "norm": norm(pcm), "padnorm": pad(norm(pcm))}


def main(argv):
    if argv[:1] == ["--join"]:
        paths = [p if os.path.isabs(p) else os.path.join(CLIPS, p) for p in argv[1:]]
        pcm = b"".join(load(p) for p in paths)
        print("joined", [os.path.basename(p) for p in paths])
        for name, v in variants(pcm).items():
            print(f"  {name:8s} {transcribe(v)!r}")
        return
    filt = argv[0] if argv else ""
    for path in sorted(glob.glob(os.path.join(CLIPS, "*.wav"))):
        if filt not in os.path.basename(path):
            continue
        pcm = load(path)
        peak, rms = stats(pcm)
        print(
            f"{os.path.basename(path)}  {len(pcm) / 2 / RATE:.2f}s "
            f"peak {peak:.1f} dBFS rms {rms:.1f} dBFS"
        )
        for name, v in variants(pcm).items():
            print(f"  {name:8s} {transcribe(v)!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
