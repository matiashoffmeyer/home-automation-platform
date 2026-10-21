#!/usr/bin/env python3
"""Stand-in for go-librespot (0.9.0/0.10.5) in the offline tests: same CLI, same API
(/status, /player/*, /events WebSocket) and - the point of it - the same
blocking PCM writes to stdout, as fast as the reader accepts.

/fake/<play|load_paused|pause|stop|inactive|volume?v=N> plays the phone's part.
/fake/reset is a zeroconf re-login: the player is replaced without an event,
only the "accepted zeroconf" log line; /fake/reset_silent leaves even that out.
/fake/stats reports the longest single stdout write (the dealer-hang proxy).
"""

import asyncio
import json
import os
import struct
import sys
import threading
import time

from aiohttp import web

cfg_dir = sys.argv[sys.argv.index("--config_dir") + 1]
cfg = json.load(open(os.path.join(cfg_dir, "config.yml"), encoding="utf-8"))
PORT = cfg["server"]["port"]

state = {"playing": False, "active": False, "stopped": True, "volume": 37, "sample": 0}
stats = {"max_write_s": 0.0, "bytes": 0, "writes": 0}
wake = threading.Event()
sockets: set = set()
loop: asyncio.AbstractEventLoop


def writer() -> None:
    out = sys.stdout.buffer
    n = 44100 // 20
    while True:
        if not state["playing"]:
            wake.wait(0.2)
            wake.clear()
            continue
        s0 = state["sample"]
        buf = b"".join(struct.pack("<hh", (s0 + i) % 32768, (s0 + i) % 32768) for i in range(n))
        state["sample"] = (s0 + n) % 32768
        t = time.monotonic()
        try:
            out.write(buf)
            out.flush()
        except BrokenPipeError:
            return
        stats["max_write_s"] = max(stats["max_write_s"], time.monotonic() - t)
        stats["bytes"] += len(buf)
        stats["writes"] += 1


async def emit(kind: str, data: dict | None = None) -> None:
    msg = json.dumps({"type": kind, "data": data or {}})
    for ws in list(sockets):
        try:
            await ws.send_str(msg)
        except Exception:  # noqa: BLE001
            sockets.discard(ws)


async def h_events(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    sockets.add(ws)
    async for _ in ws:
        pass
    sockets.discard(ws)
    return ws


async def h_status(_req):
    if not state["active"]:
        return web.Response(status=204)
    return web.json_response(
        {
            "username": "testbruger",
            "device_name": cfg["device_name"],
            "stopped": state["stopped"],
            "paused": not state["playing"],
            "volume": state["volume"],
            "volume_steps": 100,
            "track": None if state["stopped"] else {"uri": "spotify:track:x"},
        }
    )


async def set_playing(on: bool) -> None:
    state["playing"] = on
    state["stopped"] = False
    wake.set()
    await emit("playing" if on else "paused", {"uri": "spotify:track:x"})


player_calls: list = []


async def h_player(req):
    name = req.match_info["name"]
    body = await req.json() if req.can_read_body else {}
    player_calls.append([name, body, time.time()])
    if name == "pause":
        await set_playing(False)
    elif name == "resume":
        await set_playing(True)
    elif name == "volume":
        state["volume"] = int(body["volume"])
        await emit("volume", {"value": state["volume"], "max": 100})
    return web.Response(status=200)


async def h_fake(req):
    name = req.match_info["name"]
    if name in ("play", "load_paused"):
        if not state["active"]:
            state["active"] = True
            await emit("active", {})
            await emit("volume", {"value": state["volume"], "max": 100})
        await emit(
            "metadata",
            {
                "uri": "spotify:track:x",
                "name": "Sang",
                "artist_names": ["Kunstner"],
                "album_name": "Album",
                "duration": 200000,
                "position": 0,
            },
        )
        await emit("will_play", {})
        # a transfer can load the session paused: will_play, then paused
        await set_playing(name == "play")
    elif name == "skip_stop":
        # go-librespot 0.10.5 on a skip from the app: stopped, then the next track
        state.update(playing=False, stopped=True)
        await emit("stopped", {})
        await asyncio.sleep(0.3)
        await emit(
            "metadata",
            {
                "uri": "spotify:track:y",
                "name": "Sang 2",
                "artist_names": ["Kunstner"],
                "album_name": "Album",
                "duration": 200000,
                "position": 0,
            },
        )
        state.update(playing=True, stopped=False)
        wake.set()
        await emit("playing", {})
    elif name in ("reset", "reset_silent"):
        state.update(playing=False, active=False, stopped=True)
        if name == "reset":
            print(
                'time=x level=info msg="accepted zeroconf from Testtelefon" username="te**er"',
                file=sys.stderr,
                flush=True,
            )
    elif name == "reset_stats":
        stats["max_write_s"] = 0.0
    elif name == "pause":
        await set_playing(False)
    elif name == "stop":
        state.update(playing=False, stopped=True)
        await emit("stopped", {})
    elif name == "inactive":
        state["playing"] = False
        state["active"] = False
        await emit("inactive", {})
    elif name == "volume":
        state["volume"] = int(req.query["v"])
        await emit("volume", {"value": state["volume"], "max": 100})
    elif name == "stats":
        return web.json_response({**stats, "player_calls": player_calls})
    elif name == "die":
        os._exit(3)
    return web.json_response({"ok": True})


async def main() -> None:
    global loop
    loop = asyncio.get_running_loop()
    threading.Thread(target=writer, daemon=True).start()
    app = web.Application()
    app.router.add_get("/events", h_events)
    app.router.add_get("/status", h_status)
    app.router.add_post("/player/{name}", h_player)
    app.router.add_route("*", "/fake/{name}", h_fake)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()
    print('time=x level=info msg="fake go-librespot klar"', file=sys.stderr, flush=True)
    await asyncio.Event().wait()


asyncio.run(main())
