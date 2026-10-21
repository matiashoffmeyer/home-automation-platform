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
Uri'en er MA-formen (spotify://track/<id>, library://track/<n>).
"""

import asyncio
import json
import sys

import aiohttp

import ha_secrets

BASE = "http://127.0.0.1:8095"


async def run(cmds):
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
        return out


def play(queue_id, uri, dry=False):
    (item,) = asyncio.run(run([["music/item_by_uri", {"uri": uri}]]))
    if "name" not in item:
        sys.exit(f"ukendt uri {uri}: {item.get('details', item)}")
    if dry:  # --dry: kun opslaget (test af HA's svar-parsing uden lyd)
        print(
            json.dumps(
                {
                    "ok": True,
                    "navn": item["name"],
                    "dry": True,
                    "sekunder": item.get("duration") or 0,
                },
                ensure_ascii=False,
            )
        )
        return
    (res,) = asyncio.run(
        run(
            [
                [
                    "player_queues/play_media",
                    {"queue_id": queue_id, "media": uri, "option": "replace"},
                ]
            ]
        )
    )
    if isinstance(res, dict) and "error_code" in res:
        sys.exit(f"play_media fejlede: {res.get('details', res)}")
    print(
        json.dumps(
            {"ok": True, "navn": item["name"], "sekunder": item.get("duration") or 0},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    if sys.argv[1] == "play":
        play(sys.argv[2], sys.argv[3], "--dry" in sys.argv[4:])
    elif sys.argv[1] == "stop":
        asyncio.run(run([["player_queues/stop", {"queue_id": sys.argv[2]}]]))
        print(json.dumps({"ok": True}))
    else:
        for res in asyncio.run(run(json.loads(sys.argv[1]))):
            print(json.dumps(res, ensure_ascii=False))
