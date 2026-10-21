#!/usr/bin/env python3
"""Vis eller sæt hvilke entities Assist (conversation) må se.

Speech-to-Phrase bygger sit Kaldi-ordforråd af PRÆCIS de entities der er
eksponeret til `conversation` — hvert navn bliver til et alternativ i
afkodnings-grafen, som køkken-mikrofonens få kommandoer skal konkurrere mod.

    list                     hvad er eksponeret nu
    prune                    fjern ALT undtagen ALLOWLIST herunder
    expose <entity_id> ...   eksponér igen

Eksponeringen lever i .storage, ikke i git — kør `list` efter en HA-opgradering
eller når nye devices er parret; nye entities eksponeres som udgangspunkt SELV.
"""

import asyncio
import json
import os
import sys

import websockets

WS = "ws://supervisor/core/websocket"
TOKEN = os.environ["SUPERVISOR_TOKEN"]

# Tom = køkken-mikrofonens kommandoer kommer fra `platform: conversation`-
# triggers (ExtraSentences), ikke fra entity-navne. Skal telefon-Assist kunne
# styre en bestemt ting igen, hører dens entity_id her.
ALLOWLIST: set[str] = set()


async def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    async with websockets.connect(WS, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        auth = json.loads(await ws.recv())
        if auth.get("type") != "auth_ok":
            sys.exit(f"auth fejlede: {auth}")

        msg_id = 1

        async def call(payload: dict) -> dict:
            nonlocal msg_id
            payload["id"] = msg_id
            msg_id += 1
            await ws.send(json.dumps(payload))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == payload["id"]:
                    return r

        listed = await call({"type": "homeassistant/expose_entity/list"})
        exposed = [
            eid for eid, a in listed["result"]["exposed_entities"].items() if a.get("conversation")
        ]

        if cmd == "list":
            print(f"{len(exposed)} eksponeret til conversation")
            for eid in sorted(exposed):
                print(" ", eid)
            return

        if cmd == "prune":
            drop = sorted(set(exposed) - ALLOWLIST)
            if not drop:
                print("intet at fjerne")
                return
            r = await call(
                {
                    "type": "homeassistant/expose_entity",
                    "assistants": ["conversation"],
                    "entity_ids": drop,
                    "should_expose": False,
                }
            )
            print(f"fjernede {len(drop)}: success={r.get('success')}")
            return

        if cmd == "expose":
            add = sys.argv[2:]
            r = await call(
                {
                    "type": "homeassistant/expose_entity",
                    "assistants": ["conversation"],
                    "entity_ids": add,
                    "should_expose": True,
                }
            )
            print(f"eksponerede {len(add)}: success={r.get('success')}")
            return

        sys.exit(f"ukendt kommando: {cmd}")


asyncio.run(main())
