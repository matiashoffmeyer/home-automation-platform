#!/usr/bin/env python3
"""Synk husets egne Lovelace-kort (www/*.js) til Lovelace-ressourcerne.

Ressourcerne bor i .storage/lovelace_resources (IKKE i git), og app'en cacher
en JS-fil så længe URL'en er uændret. Scriptet registrerer hver fil i
LOCAL_CARDS som `/local/<fil>?v=<hash af indholdet>` og opdaterer URL'en når
filen ændrer sig — kør det efter HVER ændring af et kort, og efter en
gendannelse hvor .storage er tabt.

  python3 scripts/lovelace_resources.py          # synk
  python3 scripts/lovelace_resources.py --list   # vis ressourcerne
"""

import asyncio
import hashlib
import json
import os
import sys

import websockets

WS = "ws://supervisor/core/websocket"
TOKEN = os.environ["SUPERVISOR_TOKEN"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Kort der skal være registreret. Kun filer vi selv har skrevet.
LOCAL_CARDS = ["indstillinger-soeg.js", "thread-net-card.js", "zigbee-net-card.js"]


async def main() -> None:
    async with websockets.connect(WS, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            sys.exit("auth fejlede")
        msg_id = 0

        async def call(payload: dict) -> dict:
            nonlocal msg_id
            msg_id += 1
            payload["id"] = msg_id
            await ws.send(json.dumps(payload))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == msg_id:
                    if not r.get("success"):
                        sys.exit(f"fejl: {r}")
                    return r["result"]

        existing = await call({"type": "lovelace/resources"})
        if "--list" in sys.argv:
            for r in existing:
                print(f"{r['type']:7} {r['url']}")
            return
        for fn in LOCAL_CARDS:
            path = os.path.join(ROOT, "www", fn)
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:8]
            url = f"/local/{fn}?v={digest}"
            match = [r for r in existing if r["url"].split("?")[0] == f"/local/{fn}"]
            if match and match[0]["url"] == url:
                print(f"uændret  {url}")
            elif match:
                await call(
                    {
                        "type": "lovelace/resources/update",
                        "resource_id": match[0]["id"],
                        "res_type": "module",
                        "url": url,
                    }
                )
                print(f"opdateret {match[0]['url']} → {url}")
            else:
                await call({"type": "lovelace/resources/create", "res_type": "module", "url": url})
                print(f"oprettet {url}")


if __name__ == "__main__":
    asyncio.run(main())
