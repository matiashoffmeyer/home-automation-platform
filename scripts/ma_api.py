#!/usr/bin/env python3
"""ma_api.py — kald Music Assistants websocket-API (B204, 2026-10-09).

MA 2.10 kræver login på API'et (port 8095). Admin-brugeren `homeassistant` blev
oprettet via `POST /setup` 09/10; navn + password står i secrets.yaml
(`music_assistant_user`/`music_assistant_password`) og printes aldrig.
Kører i HA-containeren (aiohttp findes dér), og add-on'en skal køre:

  docker exec -i homeassistant python3 /config/scripts/ma_api.py \
      '[["players/all", {}], ["config/providers", {}]]'

Hver kommando er [command, args]; svaret printes som én JSON-linje pr. kommando.
Nyttige: players/all · player_queues/play_media {queue_id, media} ·
player_queues/stop {queue_id} · players/cmd/volume_set {player_id, volume_level} ·
config/providers/get_entries {instance_id} · config/providers/save
{provider_domain, instance_id, values} · config/core/save {domain, values}.
NB en ny provider-instans oprettes KUN via config/providers/setup + config/flows/submit.

Genveje til HA's shell_commands (B205, packages/hoejttaler_annoncering.yaml):
  ma_api.py play <queue_id> <uri>  → spil ét nummer (erstatter køen), print
                                      {"ok", "navn", "sekunder"}
  ma_api.py stop <queue_id>        → stop køen
  ma_api.py play <queue_id> <uri> --klip N [--start S]
                                   → spil kun N s fra S (-1/udeladt = tilfældigt
                                      sted), print også "start". Halloween-
                                      stemningens lydklip (2026-10-24).
  ... --klip N --forsoeg 2         → hænger køen, startes den én gang til
                                      (kun play_index; køen har nummeret).
Uri'en er MA-formen (spotify://track/<id>, library://track/<n>).

Et klip kan ikke bruge play_media replace: den starter altid fra 0, og et seek
bagefter giver et hørbart stykke fra nummerets start. I stedet clear + add (add
starter ALDRIG afspilning af sig selv) + play_index med seek_position, så første
lyd er fra offset'et. fade_in afrunder det første knæk.

Et klip returnerer først når køen REELT spiller (playing, og elapsed steget;
maks. 15 s) og printer "ventet" = sekunder fra kaldet og "forspring" = hvor
længe det allerede har spillet. Målt 24/10, 8 klip: køen spillede 6,2-9,9 s
efter kaldet (seek-offset gør ingen forskel), mens play_index returnerede
0,1-5 s FØR det — fulgt af et playing-blink og ~4 s idle — og Volumio melder
slet ikke playing på en DLNA-strøm. Uden ventetiden talte HA klippets sekunder
fra et tidspunkt hvor intet lød endnu. Ca. 1 af 15 klip spiller ALDRIG (blinket,
så idle på start + 1; 24/10) → "spiller": false, og spil_sang stopper + logger.
I stemningen hang 2 af 4 (12:48 og 18:46 24/10, "ventet" 22,6/26,1 s) →
`--forsoeg 2` sender play_index igen efter loftet ("forsoeg" i svaret). Kun
til klip uden et fast øjeblik: et andet forsøg lander 15-20 s for sent. Begge
forsøg holder sig under shell_command's 60-s-timeout (26 + 2 + 15 s).
"""

import asyncio
import json
import random
import sys
import time

import aiohttp

import ha_secrets

BASE = "http://127.0.0.1:8095"


async def run(cmds, vent_koe=None):
    async with aiohttp.ClientSession() as s:
        r = await s.post(
            BASE + "/auth/login",
            json={
                "provider_id": "builtin",
                "credentials": {
                    "username": ha_secrets.get("music_assistant_user"),
                    "password": ha_secrets.get("music_assistant_password"),
                },
            },
        )
        tok = (await r.json()).get("token")
        if not tok:
            sys.exit(f"login fejlede (HTTP {r.status})")
        out = []
        async with s.ws_connect(BASE + "/ws") as ws:
            await ws.receive_json()  # server-info
            await ws.send_json({"message_id": "auth", "command": "auth", "args": {"token": tok}})
            while (await ws.receive_json()).get("message_id") != "auth":
                pass
            for i, (cmd, args) in enumerate(cmds):
                await ws.send_json({"message_id": str(i), "command": cmd, "args": args})
                while True:
                    m = await ws.receive_json()
                    if m.get("message_id") == str(i):
                        out.append(m.get("result", m))
                        break
            if vent_koe:
                out.append(await _vent_spiller(ws, vent_koe))
        return out


async def _vent_spiller(ws, queue_id, loft=15.0):
    """Sekunder køen allerede har spillet når den beviseligt spiller, eller
    None ved loftet. Bevis = state playing OG elapsed steget ≥ 0,5 s siden
    køen gik i playing. Den første playing-melding er et blink: DLNA-
    rendereren melder playing, ligger idle ~4 s mens den buffer, og spiller
    så (målt 24/10, 8 klip)."""
    t0 = time.monotonic()
    ind = None  # (tid, elapsed) da køen sidst gik i playing
    n = 0
    while time.monotonic() - t0 < loft:
        n += 1
        await ws.send_json(
            {"message_id": f"v{n}", "command": "player_queues/get", "args": {"queue_id": queue_id}}
        )
        while True:
            m = await ws.receive_json()
            if m.get("message_id") == f"v{n}":
                break
        q = m.get("result") or {}
        nu, e = time.monotonic(), q.get("elapsed_time") or 0
        if q.get("state") != "playing":
            ind = None
        elif ind is None:
            ind = (nu, e)
        elif e >= ind[1] + 0.5:
            return round(nu - ind[0], 1)
        await asyncio.sleep(0.2)
    return None


def _start(varighed, klip, start):
    """Offset i hele sekunder; tilfældigt hvis start < 0, altid så klippet når
    at slutte 3 s før nummeret (MA's flow-stream skal ikke løbe tør)."""
    loft = max(0, int(varighed - klip - 3))
    if start < 0:
        return random.randint(0, loft)
    return min(int(start), loft)


def play(queue_id, uri, dry=False, klip=0, start=-1, forsoeg=1):
    (item,) = asyncio.run(run([["music/item_by_uri", {"uri": uri}]]))
    if "name" not in item:
        sys.exit(f"ukendt uri {uri}: {item.get('details', item)}")
    varighed = item.get("duration") or 0
    svar = {"ok": True, "navn": item["name"], "sekunder": varighed}
    if klip > 0:
        svar["start"] = _start(varighed, klip, start)
        svar["sekunder"] = klip
    if dry:  # --dry: kun opslaget (test af HA's svar-parsing uden lyd)
        svar["dry"] = True
        print(json.dumps(svar, ensure_ascii=False))
        return
    if klip > 0:
        cmds = [
            ["player_queues/clear", {"queue_id": queue_id}],
            ["player_queues/play_media", {"queue_id": queue_id, "media": uri, "option": "add"}],
            [
                "player_queues/play_index",
                {
                    "queue_id": queue_id,
                    "index": 0,
                    "seek_position": svar["start"],
                    "fade_in": True,
                },
            ],
        ]
    else:
        cmds = [
            [
                "player_queues/play_media",
                {"queue_id": queue_id, "media": uri, "option": "replace"},
            ]
        ]
    t0 = time.monotonic()
    svarene = asyncio.run(run(cmds, vent_koe=queue_id if klip > 0 else None))
    for (cmd, _), res in zip(cmds, svarene):
        if isinstance(res, dict) and "error_code" in res:
            sys.exit(f"{cmd} fejlede: {res.get('details', res)}")
    n = 1
    while klip > 0 and svarene[-1] is None and n < forsoeg:
        n += 1
        svarene = asyncio.run(run(cmds[-1:], vent_koe=queue_id))
    if klip > 0:
        svar["forsoeg"] = n
        svar["spiller"] = svarene[-1] is not None
        svar["forspring"] = svarene[-1] or 0
        svar["ventet"] = round(time.monotonic() - t0, 1)
    print(json.dumps(svar, ensure_ascii=False))


def _flag(navn, default):
    if navn in sys.argv:
        return float(sys.argv[sys.argv.index(navn) + 1])
    return default


if __name__ == "__main__":
    if sys.argv[1] == "play":
        play(
            sys.argv[2],
            sys.argv[3],
            "--dry" in sys.argv[4:],
            klip=int(_flag("--klip", 0)),
            start=_flag("--start", -1),
            forsoeg=int(_flag("--forsoeg", 1)),
        )
    elif sys.argv[1] == "stop":
        asyncio.run(run([["player_queues/stop", {"queue_id": sys.argv[2]}]]))
        print(json.dumps({"ok": True}))
    else:
        for res in asyncio.run(run(json.loads(sys.argv[1]))):
            print(json.dumps(res, ensure_ascii=False))
