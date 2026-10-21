#!/usr/bin/env python3
"""Offline end-to-end test of the Spotify bridge - no speaker, no Spotify.

Runs bro.py against tests/fake_librespot.py (blocking PCM writes like the real
daemon) and an in-process fake N3: Volumio REST + socket.io (EIO3 polling),
MPD on TCP, and a "player" that pulls the stream at real time like MPD does,
honours ICY metadata, stops reading on pause and can drop the connection.

    python3 addons/spotify_bro/tests/test_bro.py
"""

import asyncio
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time

import aiohttp
from aiohttp import web

HERE = os.path.dirname(os.path.abspath(__file__))
BRO = os.path.join(HERE, "..", "bro.py")
FAKE = os.path.join(HERE, "fake_librespot.py")
BPS = 44100 * 4


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeSpeaker:
    def __init__(self) -> None:
        self.st = {"status": "stop", "service": "webradio", "uri": "", "title": "", "volume": 25}
        self.mpd_log: list[str] = []
        self.vol_cmds: list[int] = []
        self.replace: list[dict] = []
        self.sessions: dict[str, dict] = {}
        self.reader: asyncio.Task | None = None
        self.paused = asyncio.Event()
        self.bytes = 0
        self.breaks = 0  # discontinuities in the sample counter
        self.last_sample = None
        self.icy_titles: list[str] = []
        self.first_sample: int | None = None
        self.connect_delay = 1.5  # MPD fetches the stream a while after replaceAndPlay
        self.http: aiohttp.ClientSession | None = None

    # --- state push
    def push(self) -> None:
        msg = "42" + json.dumps(["pushState", dict(self.st)])
        for s in self.sessions.values():
            s["q"].put_nowait(msg)

    # --- the "MPD player": pull the stream at real time
    async def play(self, uri: str) -> None:
        if self.reader:
            self.reader.cancel()
        self.st.update(status="play", uri=uri)
        self.paused.clear()
        self.first_sample = None
        self.reader = asyncio.ensure_future(self._read(uri))
        self.push()

    async def _read(self, uri: str) -> None:
        if not uri.startswith("http://127.0.0.1"):
            return  # "radio": nothing to fetch
        try:
            await asyncio.sleep(self.connect_delay)
            async with self.http.get(
                uri, headers={"Icy-MetaData": "1"}, timeout=aiohttp.ClientTimeout(total=None)
            ) as r:
                metaint = int(r.headers.get("icy-metaint", "0"))
                assert r.headers["Content-Type"].startswith("audio/L16"), r.headers
                t0 = time.monotonic()
                got = 0
                buf = b""
                until = metaint
                while True:
                    while self.paused.is_set():
                        await asyncio.sleep(0.05)
                        t0 = time.monotonic() - got / BPS
                    data = await r.content.read(8192)
                    if not data:
                        return
                    buf += data
                    audio = b""
                    while buf:
                        if metaint and until == 0:
                            if not buf:
                                break
                            n = buf[0] * 16
                            if len(buf) < 1 + n:
                                break
                            if n:
                                m = re.search(rb"StreamTitle='(.*?)';", buf[1 : 1 + n])
                                if m:
                                    self.icy_titles.append(m.group(1).decode())
                            buf = buf[1 + n :]
                            until = metaint
                            continue
                        take = len(buf) if not metaint else min(until, len(buf))
                        audio += buf[:take]
                        buf = buf[take:]
                        if metaint:
                            until -= take
                    self._check(audio)
                    got += len(audio)
                    # real time after a 1 s "buffer_before_play"
                    ahead = got / BPS - (time.monotonic() - t0) - 1.0
                    if ahead > 0:
                        await asyncio.sleep(ahead)
        except asyncio.CancelledError:
            pass

    def _check(self, audio: bytes) -> None:
        self.bytes += len(audio)
        self._carry = getattr(self, "_carry", b"") + audio
        n = len(self._carry) // 4 * 4
        for i in range(0, n, 4):
            left, right = struct.unpack(">hh", self._carry[i : i + 4])
            assert left == right, (left, right)
            if self.first_sample is None:
                self.first_sample = left
            if self.last_sample is not None and left != (self.last_sample + 1) % 32768:
                self.breaks += 1
            self.last_sample = left
        self._carry = self._carry[n:]

    # --- Volumio REST
    async def h_state(self, _r):
        return web.json_response(self.st)

    async def h_cmd(self, r):
        cmd = r.query.get("cmd")
        if cmd == "stop":
            if self.reader:
                self.reader.cancel()
            self.st["status"] = "stop"
            self.push()
        elif cmd == "volume":
            v = int(r.query["volume"])
            self.vol_cmds.append(v)
            self.st["volume"] = v
            self.push()
        return web.json_response({"response": "ok"})

    # --- socket.io EIO3 polling
    async def h_sio(self, r):
        sid = r.query.get("sid")
        if r.method == "GET" and not sid:
            sid = f"s{len(self.sessions)}"
            self.sessions[sid] = {"q": asyncio.Queue(), "first": True}
            hs = "0" + json.dumps(
                {"sid": sid, "upgrades": [], "pingInterval": 25000, "pingTimeout": 60000}
            )
            return web.Response(body=f"{len(hs)}:{hs}".encode())
        s = self.sessions[sid]
        if r.method == "GET":
            if s["first"]:
                s["first"] = False
                return web.Response(body=b"2:40")
            try:
                msg = await asyncio.wait_for(s["q"].get(), 10)
            except TimeoutError:
                return web.Response(body=b"1:6")
            return web.Response(body=f"{len(msg)}:{msg}".encode())
        body = (await r.read()).decode()
        for m in re.finditer(r"\d+:(42\[.*?\])(?=\d+:|$)", body):
            ev = json.loads(m.group(1)[2:])
            if ev[0] == "getState":
                self.push()
            elif ev[0] == "replaceAndPlay":
                self.replace.append(ev[1])
                self.st.update(service=ev[1].get("service"), title=ev[1].get("title"))
                await self.play(ev[1]["uri"])
        return web.Response(body=b"ok")

    # --- MPD
    async def mpd(self, reader, writer):
        writer.write(b"OK MPD 0.20.0\n")
        while line := await reader.readline():
            c = line.decode().strip()
            self.mpd_log.append(c)
            if c == "close":
                break
            if c == "status":
                writer.write(f"volume: {self.st['volume']}\nstate: {self.st['status']}\n".encode())
            elif c == "currentsong":
                if self.st["uri"]:
                    writer.write(f"file: {self.st['uri']}\n".encode())
            elif c == "outputs":
                writer.write(
                    b"outputid: 0\noutputname: alsa\noutputenabled: 1\n"
                    b"outputid: 1\noutputname: multiroom\noutputenabled: 0\n"
                )
            elif c == "pause 1":
                self.paused.set()
                self.st["status"] = "pause"
                self.push()
            elif c == "pause 0":
                self.paused.clear()
                self.st["status"] = "play"
                self.push()
            writer.write(b"OK\n")
            await writer.drain()
        writer.close()


EXPECTED = 26
GRACE = 1.0  # stop_grace_s in the test


async def wait_for(pred, timeout: float, what: str):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if asyncio.iscoroutine(v):
            v = await v
        if v:
            return v
        await asyncio.sleep(0.1)
    raise AssertionError(f"timeout: {what}")


async def main() -> None:
    sp = FakeSpeaker()
    sp.http = aiohttp.ClientSession()
    vport, mport, sport, aport = free_port(), free_port(), free_port(), free_port()
    app = web.Application()
    app.router.add_get("/api/v1/getState", sp.h_state)
    app.router.add_get("/api/v1/commands/", sp.h_cmd)
    app.router.add_route("*", "/socket.io/", sp.h_sio)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", vport).start()
    mpd_srv = await asyncio.start_server(sp.mpd, "127.0.0.1", mport)

    tmp = tempfile.mkdtemp(prefix="bro_test_")
    opts = {
        "binary": FAKE,
        "api_port": aport,
        "speaker_host": "127.0.0.1",
        "volumio_port": vport,
        "mpd_port": mport,
        "stream_host": "127.0.0.1",
        "stream_port": sport,
        "bind": "127.0.0.1",
        "interface": "",
        "own_grace_s": 1.0,
        "confirm_s": 1.0,
        "reconcile_s": 0.5,
        "stop_grace_s": GRACE,
        "ha_entity": "",
        "log_level": "debug",
    }
    with open(os.path.join(tmp, "options.json"), "w") as f:
        json.dump(opts, f)
    env = dict(os.environ, BRO_OPTIONS=os.path.join(tmp, "options.json"), BRO_DATA=tmp)
    os.chmod(FAKE, 0o755)
    log = open(os.path.join(tmp, "bro.log"), "w")
    proc = subprocess.Popen([sys.executable, BRO], env=env, stdout=log, stderr=subprocess.STDOUT)
    bro = f"http://127.0.0.1:{sport}"
    lib = f"http://127.0.0.1:{aport}"
    url = f"{bro}/spotify.l16"
    h = sp.http
    passed = []

    async def status():
        async with h.get(f"{bro}/status") as r:
            return await r.json()

    async def fake(name, **q):
        async with h.post(f"{lib}/fake/{name}", params=q) as r:
            return await r.json()

    def ok(name):
        passed.append(name)
        print(f"  ✓ {name}", flush=True)

    try:
        await wait_for(lambda: _try(status), 10, "bro /status")
        await wait_for(lambda: _try(lambda: fake("stats")), 10, "fake librespot")
        await wait_for(lambda: _try(lambda: _events_up(status)), 10, "librespot-events")
        await wait_for(lambda: sp.sessions, 10, "pushState-lytter")
        ok("bro og fake go-librespot kører")

        # 0a. Volumio pushes only on change: the bridge asks on connect
        await wait_for(
            lambda: _try(lambda: _hoejttaler(status, "anden")), 3, "getState ved connect"
        )
        ok("højttalerens tilstand kendt fra start (getState ved connect)")

        # 0b. a transfer that loads the session PAUSED must not touch the speaker
        await fake("load_paused")
        await wait_for(lambda: _try(lambda: _tilstand(status, "paused")), 3, "pauset session")
        await asyncio.sleep(1.5)
        assert not sp.replace, sp.replace
        ok("session indlæst på pause → højttaleren røres ikke")

        # 1. a phone starts playing: speaker onto our stream, real-time audio
        await fake("play")
        await wait_for(lambda: sp.replace, 5, "replaceAndPlay")
        assert sp.replace[-1]["uri"] == url and sp.replace[-1]["service"] == "webradio"
        ok("play → replaceAndPlay med broens URL som webradio")
        await wait_for(lambda: sp.bytes, 5, "første lyd")
        assert sp.first_sample == 0, sp.first_sample
        stats = await fake("stats")
        assert 1.0 < stats["max_write_s"] < 3.5, stats["max_write_s"]
        ok(
            f"start-hold: nummeret starter fra første sample trods {sp.connect_delay} s "
            f"til MPD forbinder (daemonen ventede {stats['max_write_s']:.1f} s)"
        )
        b0 = sp.bytes
        await asyncio.sleep(4)
        secs = (sp.bytes - b0) / BPS
        assert 3.0 < secs < 6.5, secs
        assert sp.breaks == 0, sp.breaks
        ok(f"lyd i realtid, big-endian og sammenhængende ({secs:.1f} s på 4 s)")
        st = await status()
        assert st["tilstand"] == "playing" and st["bruger"] == "testbruger", st
        assert st["titel"] == "Sang" and st["hoejttaler"] == "spiller", st
        await wait_for(lambda: "Kunstner - Sang" in sp.icy_titles, 5, "ICY-titel")
        ok("status + ICY-titel 'Kunstner - Sang'")

        # 2. the session's first volume (37, the phone's memory) must not move the room
        stats = await fake("stats")
        vol_calls = [c for c in stats["player_calls"] if c[0] == "volume"]
        assert sp.st["volume"] == 25 and 37 not in sp.vol_cmds, sp.vol_cmds
        assert vol_calls and vol_calls[0][1] == {"volume": 25}, vol_calls
        ok("sessionens start-volumen: højttaleren (25) vinder, appen følger")

        # 3. app slider → speaker, no echo
        await fake("volume", v=40)
        await wait_for(lambda: sp.st["volume"] == 40, 3, "app-volumen til højttaler")
        await asyncio.sleep(1.5)
        stats = await fake("stats")
        n_lib = len([c for c in stats["player_calls"] if c[0] == "volume"])
        assert n_lib == 1 and sp.vol_cmds == [40], (n_lib, sp.vol_cmds)
        ok("app-volumen → højttaler, intet ekko")

        # 4. speaker volume from HA/the knob → app
        sp.st["volume"] = 30
        sp.push()
        await wait_for(lambda: _try(lambda: _lib_vol(fake, 30)), 3, "højttaler-volumen til app")
        ok("højttaler-volumen → appen")

        # 4b. Volumio reports floats: 30.00076 is 30, 44.99924 is 45 (int() made 44)
        n0 = len((await fake("stats"))["player_calls"])
        sp.st["volume"] = 30.00076
        sp.push()
        await asyncio.sleep(1)
        assert len((await fake("stats"))["player_calls"]) == n0
        sp.st["volume"] = 44.99924
        sp.push()
        await wait_for(lambda: _try(lambda: _lib_vol(fake, 45)), 3, "højttaler-volumen 45")
        await asyncio.sleep(1.5)
        assert not await _lib_vol(fake, 44) and 44 not in sp.vol_cmds and 45 not in sp.vol_cmds, (
            sp.vol_cmds
        )
        ok("float-volumen afrundes (45, ikke 44) og giver ingen ping-pong")

        # 5. app pause / resume → MPD pause 1 / pause 0
        await fake("pause")
        await wait_for(lambda: "pause 1" in sp.mpd_log, 3, "MPD pause 1")
        await wait_for(lambda: _try(lambda: _tilstand(status, "paused")), 3, "status paused")
        ok("app-pause → MPD pause 1")
        b0 = sp.bytes
        await asyncio.sleep(2)
        assert sp.bytes - b0 < BPS * 1.5, sp.bytes - b0
        await fake("play")
        await wait_for(lambda: "pause 0" in sp.mpd_log, 3, "MPD pause 0")
        assert len(sp.replace) == 1, sp.replace
        ok("app-play efter pause → MPD pause 0 (ingen ny replaceAndPlay)")

        # 5b. Volumio flashes another source for a moment (P4 at a start, 16/10)
        await asyncio.sleep(1.5)
        n0 = len((await fake("stats"))["player_calls"])
        sp.st.update(uri="http://radio.example/p4")
        sp.push()
        await asyncio.sleep(0.3)
        sp.st.update(uri=url)
        sp.push()
        await asyncio.sleep(2.5)
        st = await status()
        calls = (await fake("stats"))["player_calls"][n0:]
        assert st["tilstand"] == "playing" and st["ejer_hoejttaler"], st
        assert not [c for c in calls if c[0] == "pause"], calls
        ok("et kort blink af en anden kilde pauser IKKE appen")

        # 6. the B204 dealer hang: the stream is torn down mid-song and the
        #    daemon keeps writing. Its writes must never block.
        await fake("reset_stats")
        sp.reader.cancel()
        await asyncio.sleep(5)
        stats = await fake("stats")
        assert stats["max_write_s"] < 1.0, stats["max_write_s"]
        st = await status()
        assert st["klienter"] == 0 and st["tilstand"] == "playing", st
        ok(
            f"strømmen revet ned midt i et nummer: daemonens længste skrivning "
            f"{stats['max_write_s']:.2f} s (MA: for evigt)"
        )

        # 7. something else takes the speaker → the app is paused
        await sp.play("http://radio.example/p4")
        sp.st.update(title="DR P4")
        sp.push()
        await wait_for(lambda: _try(lambda: _tilstand(status, "paused")), 4, "Spotify pauset")
        st = await status()
        assert st["hoejttaler"] == "anden" and not st["ejer_hoejttaler"], st
        ok("radio tager højttaleren → Spotify pauses i appen")

        # 8. the phone presses play again → it takes the speaker back
        await fake("play")
        await wait_for(lambda: len(sp.replace) == 2, 4, "ny replaceAndPlay")
        assert sp.replace[-1]["uri"] == url
        ok("app-play efter radio → broen tager højttaleren tilbage")

        # 9. HA stops the speaker → the app pauses
        await asyncio.sleep(1.5)
        sp.reader.cancel()
        sp.st["status"] = "stop"
        sp.push()
        await wait_for(lambda: _try(lambda: _tilstand(status, "paused")), 4, "pauset efter HA-stop")
        ok("HA/Volumio stopper højttaleren → Spotify pauses")

        # 10. session ends (phone picks another device) → Volumio stop
        await fake("play")
        await wait_for(lambda: sp.st["status"] == "play", 4, "spiller igen")
        await asyncio.sleep(1.5)
        n_stop = sp.mpd_log.count("status")
        await fake("inactive")
        await wait_for(lambda: sp.st["status"] == "stop", 4, "Volumio stop ved inactive")
        assert n_stop <= sp.mpd_log.count("status")
        ok("session slut → Volumio stop (ikke MPD stop)")

        # 11. HA command endpoint
        async with h.post(f"{bro}/cmd/volume", params={"v": "55"}) as r:
            assert r.status == 200, r.status
        await wait_for(lambda: _try(lambda: _lib_vol(fake, 55)), 3, "cmd/volume")
        ok("HA-kommando /cmd/volume")

        # 11a. a skip that go-librespot sends as stopped → playing keeps the
        #      stream: no Volumio stop, no new replaceAndPlay (17:43 16/10)
        await fake("play")
        await wait_for(lambda: _try(lambda: _hoejttaler(status, "spiller")), 6, "spiller før skip")
        n_rep = len(sp.replace)
        seen = []
        watch = asyncio.create_task(_watch_status(sp, seen))
        await fake("skip_stop")
        await asyncio.sleep(GRACE + 1)
        assert len(sp.replace) == n_rep and "stop" not in seen, (sp.replace, seen)
        assert (await status())["titel"] == "Sang 2"
        ok("skip som stopped → playing: strømmen fortsætter (ingen ny forbindelse)")

        # 11a2. two quick skips: the first skip's timer must not fire inside
        #       the second skip's gap (code review 16/10)
        await fake("skip_stop")
        await asyncio.sleep(GRACE - 0.45)  # 2nd 'stopped' lands just before the 1st timer
        await fake("skip_stop")
        await asyncio.sleep(GRACE + 1)
        watch.cancel()
        assert len(sp.replace) == n_rep and "stop" not in seen, (sp.replace, seen)
        ok("to hurtige skip: intet gammelt stop-ur river strømmen ned")

        # 11a3. the end of the queue ('stopped' with nothing after) still
        #       stops Volumio - after the grace, not before
        t0 = time.monotonic()
        await fake("stop")
        await wait_for(
            lambda: sp.st["status"] == "stop", GRACE + 3, "Volumio stop efter køens slut"
        )
        assert time.monotonic() - t0 >= GRACE - 0.1, time.monotonic() - t0
        assert not (await status())["ejer_hoejttaler"]
        ok("køen slut (stopped uden playing) → Volumio stop efter stop_grace_s")

        # 11b. a zeroconf re-login mid-song replaces go-librespot's player
        #      without an event: the bridge must let go of the speaker
        await fake("play")
        await wait_for(lambda: _try(lambda: _hoejttaler(status, "spiller")), 6, "spiller igen")
        await fake("reset")
        await wait_for(lambda: sp.st["status"] == "stop", 4, "Volumio stop efter zeroconf-login")
        st = await status()
        assert st["tilstand"] == "idle" and not st["ejer_hoejttaler"], st
        assert st["session_nulstillet"] == 1, st
        ok("zeroconf-login midt i et nummer → højttaleren slippes (ingen stille 'playing')")

        # 11c. ... and the same without even the log line: /status backstop
        await fake("play")
        await wait_for(lambda: _try(lambda: _hoejttaler(status, "spiller")), 6, "spiller igen")
        await fake("reset_silent")
        await wait_for(lambda: sp.st["status"] == "stop", 5, "Volumio stop via /status-backstop")
        assert (await status())["session_nulstillet"] == 2
        ok("tabt session uden event → /status-backstoppet slipper højttaleren")

        # 12. go-librespot crashes → restarted
        try:
            await fake("die")
        except Exception:  # noqa: BLE001
            pass
        await wait_for(lambda: _try(lambda: _restarts(status)), 10, "genstart")
        await wait_for(lambda: _try(lambda: fake("stats")), 10, "fake oppe igen")
        ok("go-librespot død → genstartet")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        await h.close()
        mpd_srv.close()
        await runner.cleanup()
        log.close()
        failed = len(passed) < EXPECTED
        txt = open(os.path.join(tmp, "bro.log")).read()
        odd = [ln for ln in txt.splitlines() if re.search(r"WARNING|ERROR|Traceback|fejlede", ln)]
        print(
            "\n--- advarsler i bro.log ---\n" + "\n".join(odd[-20:])
            if odd
            else "\nbro.log: ingen advarsler"
        )
        if failed:
            print("\n--- bro.log ---")
            print(open(os.path.join(tmp, "bro.log")).read()[-6000:])
    print(f"\n{len(passed)} trin bestået")
    sys.exit(0 if len(passed) == EXPECTED else 1)


async def _try(fn):
    try:
        return await fn()
    except Exception:  # noqa: BLE001
        return None


async def _tilstand(status, want):
    return (await status())["tilstand"] == want


async def _watch_status(sp, seen):
    while True:
        seen.append(sp.st["status"])
        await asyncio.sleep(0.05)


async def _hoejttaler(status, want):
    return (await status())["hoejttaler"] == want


async def _events_up(status):
    return (await status())["events"]


async def _restarts(status):
    return (await status())["librespot_genstarter"] >= 1


async def _lib_vol(fake, v):
    stats = await fake("stats")
    return any(c[0] == "volume" and c[1] == {"volume": v} for c in stats["player_calls"])


if __name__ == "__main__":
    asyncio.run(main())
