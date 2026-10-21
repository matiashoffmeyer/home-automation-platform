#!/usr/bin/env python3
"""ma_watch.py — vagt over Music Assistants Spotify-dele (B207, 2026-10-09).

HVORFOR
  1. PAUSE FRA SPOTIFY-APPEN SLOG IKKE IGENNEM (user 09/10 18:37). Når MA selv
     spiller et Spotify-nummer (fx et album startet i HA), kører det i MA's
     "soloist"-motor, som telefonen ser som Connect-enheden "Music Assistant
     Playback". Pause dér pauser KUN motoren — MA's kø og DLNA-højttaleren
     spiller videre på en tom strøm, og efter ~20 s erklærer MA "Source
     stalled" og SPRINGER TIL NÆSTE NUMMER. Målt: soloist "paused" 18:37:19 →
     stall-fejl 18:37:44 → "Million Miles" fra 18:37:46; først HA's pause
     (18:38:09) stoppede lyden. → Vi læser soloistens "paused <track>" i MA's
     log og pauser den MA-kø der spiller netop det nummer.
     PLAY FRA APPEN BAGEFTER (user 09/10 20:4x: "koble play på i appen også"):
     soloistens næste "playing <samme track>" efter vores pause → genoptag
     køen. NB virker kun så længe soloisten lever: MA lukker den ~20-25 s efter
     pausen (målt 18:38:09 → 18:38:33), og så forsvinder "Music Assistant
     Playback" fra appen. Senere = lys-sidens play (Volumio-override'en
     genoptager MA-køen når den sidste strøm var MA's).
  2. SPOTIFY CONNECT-PLUGINNETS DEALER HÆNGER og kommer aldrig selv igen
     (B204a): "did not receive last pong from dealer, Ns passed" hvert 30. s,
     09/10 fra 16:41:55 til 19:03 (8490 s) → "Højttaler via HA" kan ikke
     styres fra telefonen. `config/providers/reload spotify_connect` kurerede
     det 19:03:28 (ny AP-login, playback_ready på 1 s). → Reload når N ≥ 90 s
     (3 missede pongs), max 1×/30 min, og ALDRIG mens køen spiller.

HVOR DEN KØRER
  Som daemon i Advanced SSH-add-on'en (har docker-CLI'en og SUPERVISOR_TOKEN),
  startet fra add-on'ens init_commands ligesom otbr_selfheal.sh. MA-kaldene går
  via `docker exec homeassistant python3 /config/scripts/ma_api.py` (aiohttp
  findes kun dér; password i secrets.yaml, printes aldrig).

AFHÆNGIGHED
  Begge signaler er DEBUG-linjer i MA's log (spotify/spotify_connect-loggerne
  står på DEBUG via MA's globale niveau). Sættes de til INFO, er vagten blind —
  tjek `docker logs app_d5369777_music_assistant | grep -c "\\[soloist\\]"`.

KILL-SWITCH
  input_boolean.hoejttaler_spotify_vagt_enabled ("Hold Spotify i live") —
  samme knap som myair-genopliveren (B202). Off = vagten læser videre men
  handler ikke.

  ma_watch.py daemon   → kør (pidfil forhindrer dubletter)
  Log: /data/ma_watch/ma_watch.log (add-on'ens storage, ikke git).
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

CONTAINER = "app_d5369777_music_assistant"
STATE_DIR = "/data/ma_watch"
LOG = f"{STATE_DIR}/ma_watch.log"
PIDFILE = f"{STATE_DIR}/daemon.pid"
KILL_SWITCH = "input_boolean.hoejttaler_spotify_vagt_enabled"
DEALER_MIN_S = 90  # 3 missede pongs (de logges hvert 30. s)
RELOAD_COOLDOWN_S = 1800

RE_SOLO = re.compile(r"\[soloist\] \S+ \S+: (paused|playing) spotify:track:(\w+)")
RE_SOLO_DOWN = re.compile(r"\[soloist\] \S+ \S+: shutting down")
RESUME_MAX_S = 600  # app-play genoptager kun en pause vi selv lavede
RE_DEALER = re.compile(r"did not receive last pong from dealer, (\d+)s passed")


def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def enabled():
    """Kill-switch; default on hvis HA ikke svarer (som otbr_selfheal)."""
    try:
        req = urllib.request.Request(
            f"http://supervisor/core/api/states/{KILL_SWITCH}",
            headers={"Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}"},
        )
        return json.load(urllib.request.urlopen(req, timeout=5))["state"] != "off"
    except Exception as e:  # noqa: BLE001
        log(f"kill-switch ulæselig ({e}) → antager on")
        return True


def ma(cmds):
    r = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "homeassistant",
            "python3",
            "/config/scripts/ma_api.py",
            json.dumps(cmds),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[-300:])
    return [json.loads(x) for x in r.stdout.splitlines() if x.strip()]


def queue_track(q):
    """Spotify-id'et på køens nummer. NB `current_item` har intet `uri`-felt —
    det ligger i media_item (spotify--<inst>://track/<id>) og streamdetails
    (B207's første version matchede derfor aldrig)."""
    ci = q.get("current_item") or {}
    return " ".join(
        filter(
            None,
            [
                (ci.get("media_item") or {}).get("uri"),
                (ci.get("streamdetails") or {}).get("item_id"),
            ],
        )
    )


def on_paused(track_id, state):
    if not enabled():
        log(f"soloist pause {track_id} — kill-switch off, ingen handling")
        return
    (queues,) = ma([["player_queues/all", {}]])
    hits = [
        q["queue_id"] for q in queues if q.get("state") == "playing" and track_id in queue_track(q)
    ]
    if not hits:
        log(f"soloist pause {track_id} — ingen spillende kø med nummeret")
        return
    ma([["player_queues/pause", {"queue_id": q}] for q in hits])
    state["app_pause"] = (track_id, hits, time.time())
    log(f"soloist pause {track_id} → player_queues/pause {hits}")


def on_resumed(track_id, state):
    """Soloisten gik paused → playing på samme nummer = play i appen."""
    track, hits, t = state.pop("app_pause", (None, [], 0.0))
    if track != track_id or time.time() - t > RESUME_MAX_S:
        return
    if not enabled():
        log(f"soloist play {track_id} — kill-switch off, ingen handling")
        return
    (queues,) = ma([["player_queues/all", {}]])
    resume = [
        q["queue_id"]
        for q in queues
        if q["queue_id"] in hits
        and q.get("state") in ("paused", "idle")
        and track_id in queue_track(q)
    ]
    if not resume:
        log(f"soloist play {track_id} — køen spiller allerede/er skiftet")
        return
    ma([["player_queues/play", {"queue_id": q}] for q in resume])
    log(f"soloist play {track_id} → player_queues/play {resume}")


def on_dealer(passed, state):
    if passed < DEALER_MIN_S or time.time() - state["reload"] < RELOAD_COOLDOWN_S:
        return
    if not enabled():
        return
    (queues,) = ma([["player_queues/all", {}]])
    if any(q.get("state") == "playing" for q in queues):
        return  # pong-linjen kommer igen om 30 s; reload aldrig midt i musik
    ma([["config/providers/reload", {"instance_id": "spotify_connect"}]])
    state["reload"] = time.time()
    log(f"dealer hængt {passed} s → reload spotify_connect")


def follow(state):
    p = subprocess.Popen(
        ["docker", "logs", "-f", "--since", "1s", CONTAINER],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    for line in p.stdout:
        try:
            if m := RE_SOLO.search(line):
                status, track = m.groups()
                prev = state.get("solo")
                state["solo"] = (status, track)
                if status == "paused" and prev != ("paused", track):
                    on_paused(track, state)
                elif status == "playing" and prev == ("paused", track):
                    on_resumed(track, state)
            elif RE_SOLO_DOWN.search(line):
                state["solo"] = None  # ny run = ny soloist; dens første "playing" er MA's egen
            elif m := RE_DEALER.search(line):
                on_dealer(int(m.group(1)), state)
        except Exception as e:  # noqa: BLE001
            log(f"fejl: {e}")
    p.wait()


def daemon():
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        old = int(open(PIDFILE).read())
        os.kill(old, 0)
        sys.exit(f"kører allerede (pid {old})")
    except OSError, ValueError:
        pass
    open(PIDFILE, "w").write(str(os.getpid()))
    log("start")
    state = {"reload": 0.0}
    while True:
        follow(state)  # returnerer når MA-containeren stopper/genstarter
        time.sleep(30)


if __name__ == "__main__":
    if sys.argv[1:] == ["daemon"]:
        daemon()
    else:
        sys.exit(__doc__)
