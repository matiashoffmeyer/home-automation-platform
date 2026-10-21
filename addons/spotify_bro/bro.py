#!/usr/bin/env python3
"""Spotify bridge: go-librespot -> HTTP stream -> Volumio/MPD on the AxiomAir N3.

Why this exists (B204/B207/B237): the speaker's own Spotify Connect (Volumio's
volspotconnect2, librespot 0.1.0) dies several times a week and only a reboot
brings it back; Music Assistant's Spotify Connect plugin runs the same
go-librespot this bridge runs, but it only reads the daemon's PCM while a
player is streaming. When the stream is torn down mid-song the daemon's write
to stdout blocks forever, its dealer connection misses the pong and never
reconnects, and MA's release call deadlocks behind it (measured 14/10
13:20:27 -> 13:20:39 -> 13:21:19). Everything here follows from not letting
that happen:

* The PCM pipe is ALWAYS drained, paced to real time (go-librespot writes as
  fast as the reader accepts). No reader, a paused speaker or a dead HTTP
  client only means the audio is dropped - the daemon never blocks.
* The speaker plays the stream as a Volumio webradio (socket.io
  replaceAndPlay, always with an explicit URI - never a resume of Volumio's
  own queue, which is what turned an app play into P4 on 14/10).
* Pause in the app -> MPD `pause 1` (MPD keeps its buffer, and Volumio does
  not restart a paused webradio the way it restarts a stopped one, measured
  14/10 14:58:57). Resume -> `pause 0`.
* Anything else taking the speaker (radio, an announcement, AirPlay) pauses
  the Spotify session, so the app shows what the room hears.
* Volume is external: the app slider drives Volumio's volume and the other
  way round, with the speaker as the authority when a session starts (a phone
  last used at 100 % must not blast the kitchen).

Home Assistant reads /status (rest sensor) and is poked to refresh it on
every change; /cmd/<name> lets HA pause/resume/stop the session.
"""

import array
import asyncio
import json
import logging
import os
import re
import signal
import time
from collections import deque
from typing import Any

import aiohttp
from aiohttp import web

VERSION = "0.1.4"
RATE = 44100
CHANNELS = 2
FRAME = 4  # s16 stereo
BPS = RATE * FRAME  # bytes of PCM per second
CHUNK = BPS // 20  # 50 ms reads

LOG = logging.getLogger("bro")

DEFAULTS: dict[str, Any] = {
    "device_name": "Højttaler",
    "binary": "/usr/local/bin/go-librespot",
    "bitrate": 320,
    "normalisation": True,
    "interface": "enp0s25",
    "api_port": 38950,
    "speaker_host": "192.0.2.42",
    "volumio_port": 3000,
    "mpd_port": 6600,
    "stream_host": "192.0.2.151",
    "stream_port": 8098,
    "bind": "0.0.0.0",
    "format": "l16",
    "icy": True,
    "lead_ms": 300,
    "backlog_s": 0.5,
    "start_hold_s": 3.0,
    "client_queue_s": 4.0,
    "own_grace_s": 6.0,
    "confirm_s": 2.5,
    "stop_grace_s": 2.0,
    "reconcile_s": 10.0,
    "speaker_control": True,
    "volume_sync": True,
    "ha_entity": "sensor.spotify_bro",
    "cmd_allow": ["127.0.0.1", "::1", "192.0.2.151", "172.30.32."],
    "log_level": "info",
}


def load_options() -> dict[str, Any]:
    path = os.environ.get("BRO_OPTIONS", "/data/options.json")
    opts = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            opts.update({k: v for k, v in json.load(f).items() if v is not None})
    except FileNotFoundError:
        pass
    return opts


# --------------------------------------------------------------------------
# Volumio 2 socket.io (EIO3 long-polling) - same minimal client as
# custom_components/volumio/legacy.py: the N3's firmware has no REST
# replaceAndPlay, and an emit is ignored until the namespace-connect poll.
_SIO = "/socket.io/?EIO=3&transport=polling"
_TO = aiohttp.ClientTimeout(total=10)


def _frame(msg: str) -> bytes:
    return f"{len(msg)}:{msg}".encode()


def _events(payload: str) -> list[list[Any]]:
    out = []
    for m in re.finditer(r"42(\[.*?\])(?=\d+:|[\x00-\x09�]|$)", payload, re.S):
        try:
            out.append(json.loads(m.group(1)))
        except ValueError:
            continue
    return out


async def _sio_connect(session: aiohttp.ClientSession, base: str) -> str:
    async with session.get(base, timeout=_TO) as r:
        hs = await r.text(errors="replace")
    sid = json.loads(hs[hs.index("{") :])["sid"]
    url = f"{base}&sid={sid}"
    async with session.get(f"{url}&t={time.time()}", timeout=_TO) as r:
        await r.read()
    return url


async def sio_emit(
    session: aiohttp.ClientSession, host: str, port: int, event: str, data: Any = None
) -> None:
    url = await _sio_connect(session, f"http://{host}:{port}{_SIO}")
    msg = "42" + json.dumps([event] if data is None else [event, data])
    async with session.post(
        url, data=_frame(msg), timeout=_TO, headers={"Content-Type": "text/plain;charset=UTF-8"}
    ) as r:
        await r.read()


async def sio_listen(session: aiohttp.ClientSession, host: str, port: int, on_state) -> None:
    """pushState in real time; reconnects forever (the speaker reboots, sleeps)."""
    base = f"http://{host}:{port}{_SIO}"
    long_poll = aiohttp.ClientTimeout(total=90)
    while True:
        pinger = None
        try:
            url = await _sio_connect(session, base)
            # Volumio pushes state only on a change: ask for it now, or the
            # bridge knows nothing about the speaker until the next one.
            async with session.post(
                url,
                data=_frame('42["getState"]'),
                timeout=_TO,
                headers={"Content-Type": "text/plain;charset=UTF-8"},
            ) as r:
                await r.read()

            async def ping() -> None:
                while True:
                    await asyncio.sleep(20)
                    async with session.post(
                        url,  # noqa: B023 - cancelled with its connection
                        data=_frame("2"),
                        timeout=_TO,
                        headers={"Content-Type": "text/plain;charset=UTF-8"},
                    ) as r:
                        await r.read()

            pinger = asyncio.ensure_future(ping())
            while True:
                async with session.get(f"{url}&t={time.time()}", timeout=long_poll) as r:
                    if r.status != 200:
                        break
                    body = await r.text(errors="replace")
                for ev in _events(body):
                    if ev and ev[0] == "pushState" and len(ev) > 1 and isinstance(ev[1], dict):
                        await on_state(ev[1])
                if pinger.done():
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - speaker away/rebooting: retry
            LOG.debug("pushState-lytter: %s", e)
        finally:
            if pinger is not None:
                pinger.cancel()
        await asyncio.sleep(5)


class MpdError(Exception):
    pass


def _pct(v: Any) -> int | None:
    """Volumio reports volume as a float (49.99924 for 50): round, never
    truncate - int() made 50 -> 49 -> 48 walk down in a ping-pong (16/10)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(round(v))


# --------------------------------------------------------------------------
class Client:
    """One HTTP listener (in practice: the speaker's MPD)."""

    def __init__(self, peer: str, seconds: float) -> None:
        self.peer = peer
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=max(4, int(seconds * 20)))
        self.dropped = 0
        self.since = time.time()

    def offer(self, data: bytes) -> None:
        # A listener that stops reading (MPD paused, a dead socket) must never
        # back up into the pipe: drop its OLDEST audio instead.
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.dropped += 1
        self.queue.put_nowait(data)


class Bro:
    def __init__(self, opts: dict[str, Any]) -> None:
        self.o = opts
        self.ext = "flac" if opts["format"] == "flac" else "l16"
        self.url = f"http://{opts['stream_host']}:{opts['stream_port']}/spotify.{self.ext}"
        self.data_dir = os.environ.get("BRO_DATA", "/data")
        self.api = f"http://127.0.0.1:{opts['api_port']}"
        self.session: aiohttp.ClientSession | None = None
        self.clients: set[Client] = set()
        self.backlog: deque[bytes] = deque()
        self.backlog_bytes = 0
        self.speaker_lock = asyncio.Lock()
        # go-librespot
        self.lib_up = False
        self.events_up = False
        self.lib_restarts = 0
        self.active = False
        self.status = "idle"  # idle | playing | paused | stopped
        self.user: str | None = None
        self.track: dict[str, Any] = {}
        self.position_ms = 0
        self.position_at = time.time()
        self.volume: int | None = None  # 0-100
        self.vol_first = False  # next volume event is the session's initial one
        # speaker
        self.speaker: dict[str, Any] = {}
        self.owns = False  # the speaker is (or should be) on our stream
        self.own_cmd_at = 0.0
        self.vol_to_speaker: tuple[int, float] = (-1, 0.0)
        self.vol_to_lib: tuple[int, float] = (-1, 0.0)
        self.last_event = ""
        self.last_event_at = 0.0
        self.pcm_bytes = 0
        self.pcm_last = 0.0
        self.max_read_gap = 0.0
        self._notify_task: asyncio.Task | None = None
        # Start-hold: from the moment the speaker is asked onto the stream
        # until MPD connects, the pump stops reading, so go-librespot waits
        # instead of playing the song's start to nobody (or into a backlog
        # that then sits as lag in MPD for the rest of the session).
        self.hold_until = 0.0
        self.client_came = asyncio.Event()
        self._confirm_task: asyncio.Task | None = None
        self._stop_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self.resets = 0

    # ------------------------------------------------------------- helpers
    def ours(self, uri: str | None) -> bool:
        return bool(uri) and uri.split("?")[0] == self.url

    def _icy_title(self) -> str:
        t = self.track
        if not t.get("name"):
            return ""
        artists = ", ".join(t.get("artist_names") or [])
        return f"{artists} - {t['name']}" if artists else t["name"]

    def snapshot(self) -> dict[str, Any]:
        pos = self.position_ms
        if self.status == "playing":
            pos += int((time.time() - self.position_at) * 1000)
        dur = int(self.track.get("duration") or 0)
        sp = self.speaker
        if not sp:
            hoejttaler = "ukendt"
        elif self.ours(sp.get("uri")):
            hoejttaler = {"play": "spiller", "pause": "pause"}.get(sp.get("status"), "stop")
        else:
            hoejttaler = "anden"
        return {
            "tilstand": self.status if self.lib_up else "nede",
            "aktiv": self.active,
            "bruger": self.user,
            "titel": self.track.get("name"),
            "kunstner": ", ".join(self.track.get("artist_names") or []) or None,
            "album": self.track.get("album_name"),
            "cover": self.track.get("album_cover_url"),
            "uri": self.track.get("uri"),
            "varighed_s": dur // 1000,
            "position_s": min(pos, dur) // 1000 if dur else pos // 1000,
            "volumen": self.volume,
            "hoejttaler": hoejttaler,
            "ejer_hoejttaler": self.owns,
            "klienter": len(self.clients),
            "tabte_bidder": sum(c.dropped for c in self.clients),
            "pcm_mb": round(self.pcm_bytes / 1e6, 1),
            "max_laese_pause_s": round(self.max_read_gap, 2),
            "librespot_genstarter": self.lib_restarts,
            "session_nulstillet": self.resets,
            "events": self.events_up,
            "sidste_event": self.last_event,
            "url": self.url,
            "version": VERSION,
        }

    def _spawn(self, coro) -> None:
        t = asyncio.ensure_future(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    def changed(self) -> None:
        """Ask HA to re-read /status (debounced); the rest sensor's own poll is
        the fallback when the Supervisor API is not there (tests)."""
        if not self.o.get("ha_entity") or not os.environ.get("SUPERVISOR_TOKEN"):
            return
        if self._notify_task is None or self._notify_task.done():
            self._notify_task = asyncio.ensure_future(self._notify_ha())

    async def _notify_ha(self) -> None:
        await asyncio.sleep(0.5)
        try:
            async with self.session.post(
                "http://supervisor/core/api/services/homeassistant/update_entity",
                json={"entity_id": self.o["ha_entity"]},
                timeout=_TO,
                headers={"Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}"},
            ) as r:
                await r.read()
        except Exception as e:  # noqa: BLE001
            LOG.debug("HA-opdatering fejlede: %s", e)

    # ------------------------------------------------------------- speaker IO
    async def mpd(self, *cmds: str) -> list[str]:
        r, w = await asyncio.wait_for(
            asyncio.open_connection(self.o["speaker_host"], self.o["mpd_port"]), 3
        )
        lines: list[str] = []
        try:
            greet = await asyncio.wait_for(r.readline(), 3)
            if not greet.startswith(b"OK MPD"):
                raise MpdError(greet.decode(errors="replace").strip())
            for c in cmds:
                w.write((c + "\n").encode())
                await w.drain()
                while True:
                    raw = await asyncio.wait_for(r.readline(), 3)
                    if not raw:
                        raise MpdError("forbindelsen lukket")
                    line = raw.decode("utf-8", "replace").rstrip("\n")
                    if line == "OK":
                        break
                    if line.startswith("ACK"):
                        raise MpdError(f"{c}: {line}")
                    lines.append(line)
        finally:
            w.close()
        return lines

    async def mpd_state(self) -> tuple[str, str]:
        felt: dict[str, str] = {}
        for line in await self.mpd("status", "currentsong"):
            k, _, v = line.partition(": ")
            felt.setdefault(k, v)
        return felt.get("state", ""), felt.get("file", "")

    async def volumio_cmd(self, query: str) -> None:
        url = f"http://{self.o['speaker_host']}:{self.o['volumio_port']}/api/v1/commands/?{query}"
        async with self.session.get(url, timeout=_TO) as r:
            await r.read()

    async def volumio_state(self) -> dict[str, Any]:
        url = f"http://{self.o['speaker_host']}:{self.o['volumio_port']}/api/v1/getState"
        async with self.session.get(url, timeout=_TO) as r:
            return json.loads(await r.text())

    def _mark_own(self) -> None:
        self.own_cmd_at = time.monotonic()

    async def speaker_play(self) -> None:
        """Get the speaker onto our stream (idempotent)."""
        if not self.o["speaker_control"]:
            self.owns = True
            return
        if not self.clients:
            self.hold_until = time.monotonic() + self.o["start_hold_s"]
        async with self.speaker_lock:
            try:
                state, fil = await self.mpd_state()
                if self.ours(fil) and state == "play":
                    self.owns = True
                    return
                if self.ours(fil) and state == "pause":
                    self._mark_own()
                    await self.mpd("pause 0")
                    self.owns = True
                    LOG.info("Højttaler: genoptaget (MPD pause 0)")
                    return
                # The HA override may have switched the ALSA output off for up
                # to 60 s (ghost-radio cure). A phone that chose the speaker
                # must be heard.
                cur = None
                alsa_off = False
                for line in await self.mpd("outputs"):
                    k, _, v = line.partition(": ")
                    if k == "outputid":
                        cur = v
                    elif k == "outputenabled" and cur == "0":
                        alsa_off = v == "0"
                if alsa_off:
                    await self.mpd("enableoutput 0")
                    LOG.warning("Højttaler: MPD-udgang 0 var slået fra - slået til")
                self._mark_own()
                vst = await self.volumio_state()
                # After a button power-on the N3 sits in an empty state without
                # "status", where replaceAndPlay is ignored until a stop (08/10).
                if not vst.get("status"):
                    await self.volumio_cmd("cmd=stop")
                item = {
                    "uri": self.url,
                    "service": "webradio",
                    "type": "webradio",
                    "title": "Spotify",
                    "name": "Spotify",
                }
                await sio_emit(
                    self.session,
                    self.o["speaker_host"],
                    self.o["volumio_port"],
                    "replaceAndPlay",
                    item,
                )
                self.owns = True
                LOG.info("Højttaler: replaceAndPlay %s", self.url)
            except Exception as e:  # noqa: BLE001
                self.hold_until = 0.0
                LOG.warning("Højttaler: start fejlede: %s", e)
        self.changed()

    async def speaker_pause(self) -> None:
        if not self.o["speaker_control"]:
            return
        async with self.speaker_lock:
            try:
                state, fil = await self.mpd_state()
                if self.ours(fil) and state == "play":
                    self._mark_own()
                    await self.mpd("pause 1")
                    LOG.info("Højttaler: pause (MPD pause 1)")
            except Exception as e:  # noqa: BLE001
                LOG.warning("Højttaler: pause fejlede: %s", e)

    async def speaker_stop(self) -> None:
        """Session over: Volumio's own stop (an MPD stop would make Volumio
        restart the webradio, i.e. reconnect to an empty stream)."""
        self.owns = False
        if not self.o["speaker_control"]:
            return
        async with self.speaker_lock:
            # a speaker_play that held the lock has just set owns again
            self.owns = False
            try:
                state, fil = await self.mpd_state()
                if self.ours(fil) and state in ("play", "pause"):
                    self._mark_own()
                    await self.volumio_cmd("cmd=stop")
                    LOG.info("Højttaler: stop (session slut)")
            except Exception as e:  # noqa: BLE001
                LOG.warning("Højttaler: stop fejlede: %s", e)

    async def speaker_volume(self, pct: int) -> None:
        if not self.o["speaker_control"]:
            return
        self.vol_to_speaker = (pct, time.monotonic())
        try:
            await self.volumio_cmd(f"cmd=volume&volume={pct}")
        except Exception as e:  # noqa: BLE001
            LOG.warning("Højttaler: volumen fejlede: %s", e)

    # ------------------------------------------------------------- go-librespot API
    async def lib_post(self, path: str, body: dict | None = None) -> bool:
        try:
            async with self.session.post(f"{self.api}{path}", json=body, timeout=_TO) as r:
                await r.read()
                return r.status < 300
        except Exception as e:  # noqa: BLE001
            LOG.warning("librespot %s fejlede: %s", path, e)
            return False

    async def lib_session(self) -> tuple[bool, dict[str, Any] | None]:
        """(answered, status); status None = no session (204)."""
        try:
            async with self.session.get(f"{self.api}/status", timeout=_TO) as r:
                if r.status == 204:
                    return True, None
                if r.status >= 300:
                    return False, None
                return True, json.loads(await r.text())
        except Exception:  # noqa: BLE001
            return False, None

    async def lib_status(self) -> dict[str, Any] | None:
        return (await self.lib_session())[1]

    async def lib_volume(self, pct: int) -> None:
        self.vol_to_lib = (pct, time.monotonic())
        await self.lib_post("/player/volume", {"volume": pct})

    # ------------------------------------------------------------- events
    async def on_lib_event(self, kind: str, data: dict[str, Any]) -> None:
        self.last_event = kind
        self.last_event_at = time.time()
        if kind == "active":
            self.active = True
            self.vol_first = True
            st = await self.lib_status()
            self.user = (st or {}).get("username") or self.user
            LOG.info("Session aktiv (%s)", self.user or "?")
        elif kind == "inactive":
            LOG.info("Session inaktiv")
            self.active = False
            self.status = "idle"
            self._clear_backlog()
            if self.owns:
                await self.speaker_stop()
        elif kind == "metadata":
            self.track = data
            self.position_ms = int(data.get("position") or 0)
            self.position_at = time.time()
            LOG.info("Nummer: %s", self._icy_title())
        elif kind == "playing":
            # Only on "playing", never "will_play": a transfer can load the
            # session PAUSED (will_play, then paused). Starting the speaker
            # then left MPD on a silent stream, Volumio fell back to P4, and
            # the bridge paused the app as "another source" (16/10).
            self._cancel_stop()
            self.status = "playing"
            self.position_at = time.time()
            await self.speaker_play()
        elif kind == "paused":
            self._cancel_stop()
            self._freeze_position()
            self.status = "paused"
            await self.speaker_pause()
        elif kind in ("stopped", "not_playing"):
            self._freeze_position()
            self.status = "stopped"
            self._clear_backlog()
            if self.owns:
                # A skip can come as stopped → playing within a second (17:43
                # 16/10). Stopping the speaker at once tore MPD's stream down
                # and made the next track wait for a fresh connect + prebuffer.
                # One pending stop: an older timer must not fire inside the
                # gap of a later skip.
                self._cancel_stop()
                self._stop_task = asyncio.ensure_future(self._deferred_stop())
        elif kind == "seek":
            self.position_ms = int(data.get("position") or 0)
            self.position_at = time.time()
        elif kind == "volume" and data.get("value") is not None:
            await self._on_lib_volume(data)
        self.changed()

    def _cancel_stop(self) -> None:
        if self._stop_task is not None and not self._stop_task.done():
            self._stop_task.cancel()
        self._stop_task = None

    async def _deferred_stop(self) -> None:
        await asyncio.sleep(self.o["stop_grace_s"])
        if self.status != "stopped" or not self.owns:
            return
        # The 'playing' after a skip can be lost in an events reconnect: ask
        # go-librespot itself before tearing the stream down.
        ok, st = await self.lib_session()
        if ok and st and not st.get("stopped") and not st.get("paused"):
            LOG.warning("librespot spiller uden at have sagt det - følger")
            self._stop_task = None  # or 'playing' would cancel this very task
            await self.on_lib_event("playing", {})
            return
        if self.status == "stopped" and self.owns:
            await self.speaker_stop()

    def _freeze_position(self) -> None:
        if self.status == "playing":
            self.position_ms += int((time.time() - self.position_at) * 1000)
        self.position_at = time.time()

    async def _on_lib_volume(self, data: dict[str, Any]) -> None:
        mx = int(data.get("max") or 100) or 100
        pct = max(0, min(100, round(int(data["value"]) * 100 / mx)))
        self.volume = pct
        if not self.o["volume_sync"]:
            return
        sent, at = self.vol_to_lib
        if abs(pct - sent) <= 1 and time.monotonic() - at < 3:
            return  # our own echo
        if self.vol_first:
            # The session's first volume is the phone's memory, not an intent:
            # the room's current volume wins, and the app is told.
            self.vol_first = False
            sp_vol = _pct(self.speaker.get("volume"))
            if sp_vol is not None and sp_vol != pct:
                LOG.info(
                    "Volumen: appen kom med %s %%, højttaleren står på %s %% - appen følger",
                    pct,
                    sp_vol,
                )
                await self.lib_volume(sp_vol)
                self.volume = sp_vol
            return
        if self.owns and _pct(self.speaker.get("volume")) != pct:
            LOG.info("Volumen fra appen: %s %%", pct)
            await self.speaker_volume(pct)

    async def on_speaker_state(self, st: dict[str, Any]) -> None:
        prev = self.speaker
        self.speaker = st
        ours = self.ours(st.get("uri"))
        status = st.get("status")
        in_grace = time.monotonic() - self.own_cmd_at < self.o["own_grace_s"]
        # Volume: the speaker (HA, the knob, Volumio's UI) moved it.
        vol = _pct(st.get("volume"))
        if (
            self.o["volume_sync"]
            and self.active
            and self.owns
            and ours
            and vol is not None
            and vol != _pct(prev.get("volume"))
        ):
            sent, at = self.vol_to_speaker
            if not (abs(vol - sent) <= 1 and time.monotonic() - at < 3) and vol != self.volume:
                LOG.info("Volumen fra højttaleren: %s %%", vol)
                self.volume = vol
                await self.lib_volume(vol)
        if not in_grace and self.owns:
            if self._takeover(st):
                # A single pushState is not proof: Volumio flashed P4 for a
                # moment at a start (16/10). Re-read after confirm_s.
                if self._confirm_task is None or self._confirm_task.done():
                    self._confirm_task = asyncio.ensure_future(self._confirm_takeover())
            elif ours and status == "play" and self.status == "paused":
                LOG.info("Højttaleren genoptog udefra - Spotify fortsætter")
                await self.lib_post("/player/resume")
        self.changed()

    def _takeover(self, st: dict[str, Any]) -> str | None:
        """Why the room no longer hears this session, or None."""
        ours = self.ours(st.get("uri"))
        status = st.get("status")
        if not ours and status == "play":
            return "anden"
        if ours and status in ("stop", "pause") and self.status == "playing":
            return status
        return None

    async def _confirm_takeover(self) -> None:
        await asyncio.sleep(self.o["confirm_s"])
        if not self.owns or time.monotonic() - self.own_cmd_at < self.o["own_grace_s"]:
            return
        try:
            st = await self.volumio_state()
        except Exception as e:  # noqa: BLE001
            LOG.debug("bekræftelse af højttaler-tilstand fejlede: %s", e)
            return
        why = self._takeover(st)
        if why is None:
            LOG.info("Højttaleren blinkede væk og kom tilbage - Spotify fortsætter")
            return
        self.speaker = st
        if why == "anden":
            # Radio, an announcement, AirPlay: the room hears something
            # else, so the app must stop claiming it plays.
            LOG.info("Højttaleren spiller nu %s - Spotify pauses", st.get("title") or st.get("uri"))
            self.owns = False
            if self.status == "playing":
                await self.lib_post("/player/pause")
        else:
            LOG.info("Højttaleren blev %s udefra - Spotify pauses", why)
            await self.lib_post("/player/pause")
        self.changed()

    async def on_session_reset(self, why: str) -> None:
        """go-librespot replaced its session (every zeroconf addUser does,
        even from the same phone, 16/10) or lost it: the old player is gone
        without a single event, so the bridge must let go itself - or the
        room plays silence while the status says playing."""
        if self.status not in ("playing", "paused") and not self.owns:
            LOG.info("librespot: ny session (%s)", why)
            return
        LOG.warning("librespot-sessionen er nulstillet (%s) - højttaleren slippes", why)
        self.resets += 1
        self._freeze_position()
        self.active = False
        self.status = "idle"
        self.hold_until = 0.0
        self._clear_backlog()
        if self.owns:
            await self.speaker_stop()
        self.changed()

    async def reconcile_loop(self) -> None:
        """Backstop for a missed event: what go-librespot itself says."""
        misses = 0
        while True:
            await asyncio.sleep(self.o["reconcile_s"])
            if not self.lib_up or self.status not in ("playing", "paused"):
                misses = 0
                continue
            ok, st = await self.lib_session()
            if not ok:
                continue
            gone = st is None or bool(st.get("stopped"))
            paused = not gone and bool(st.get("paused")) and self.status == "playing"
            misses = misses + 1 if (gone or paused) else 0
            if misses < 2:  # twice in a row: not a track change mid-flight
                continue
            misses = 0
            if gone:
                await self.on_session_reset("librespot har intet nummer")
            else:
                LOG.warning("librespot er på pause uden at have sagt det - følger")
                await self.on_lib_event("paused", {})

    async def events_loop(self) -> None:
        while True:
            try:
                async with self.session.ws_connect(
                    f"{self.api.replace('http', 'ws', 1)}/events", heartbeat=30
                ) as ws:
                    LOG.info("librespot-events forbundet")
                    self.events_up = True
                    self.changed()
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            ev = json.loads(msg.data)
                        except ValueError:
                            continue
                        if ev.get("type"):
                            try:
                                await self.on_lib_event(ev["type"], ev.get("data") or {})
                            except Exception:  # noqa: BLE001
                                LOG.exception("event %s", ev.get("type"))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                LOG.debug("events: %s", e)
            self.events_up = False
            await asyncio.sleep(2)

    # ------------------------------------------------------------- PCM pump
    def _clear_backlog(self) -> None:
        self.backlog.clear()
        self.backlog_bytes = 0

    def _deliver(self, pcm_le: bytes) -> None:
        out = pcm_le
        if self.ext == "l16":
            a = array.array("h")
            a.frombytes(pcm_le)
            a.byteswap()  # audio/L16 is big-endian (RFC 2586)
            out = a.tobytes()
        if self.clients:
            for c in list(self.clients):
                c.offer(out)
        else:
            # The speaker connects ~0.5-1 s after replaceAndPlay: keep the
            # newest few seconds so the song does not start mid-bar.
            self.backlog.append(out)
            self.backlog_bytes += len(out)
            cap = int(self.o["backlog_s"] * BPS)
            while self.backlog_bytes > cap and self.backlog:
                self.backlog_bytes -= len(self.backlog.popleft())

    async def pump(self, stdout: asyncio.StreamReader) -> None:
        lead = self.o["lead_ms"] / 1000
        t0 = 0.0
        sent = 0
        rest = b""
        last = 0.0
        while True:
            wait = self.hold_until - time.monotonic()
            if wait > 0 and not self.clients:
                self.client_came.clear()
                try:
                    await asyncio.wait_for(self.client_came.wait(), wait)
                except TimeoutError:
                    LOG.warning(
                        "Højttaleren hentede ikke strømmen inden %.0f s", self.o["start_hold_s"]
                    )
                self.hold_until = 0.0
            before = time.monotonic()
            data = await stdout.read(CHUNK)
            if not data:
                return
            now = time.monotonic()
            if last and self.status == "playing":
                self.max_read_gap = max(self.max_read_gap, now - before)
            if not last or now - last > 0.25:
                # Start, or a pause/stall: restart the real-time clock.
                t0 = now
                sent = 0
            last = now
            self.pcm_bytes += len(data)
            self.pcm_last = time.time()
            data = rest + data
            cut = len(data) - len(data) % FRAME
            rest = data[cut:]
            if cut:
                self._deliver(data[:cut])
            sent += cut
            # Real-time pacing: go-librespot would otherwise race through the
            # song, and position/skip/pause would drift from what the room hears.
            ahead = sent / BPS - (time.monotonic() - t0) - lead
            if ahead > 0:
                await asyncio.sleep(ahead)

    async def librespot_loop(self) -> None:
        cfg_dir = os.path.join(self.data_dir, "librespot")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg: dict[str, Any] = {
            "device_name": self.o["device_name"],
            "device_type": "speaker",
            "bitrate": int(self.o["bitrate"]),
            "audio_backend": "pipe",
            "audio_output_pipe": "/dev/stdout",
            "audio_output_pipe_format": "s16le",
            "external_volume": True,
            "volume_steps": 100,
            "normalisation_disabled": not self.o["normalisation"],
            "zeroconf_enabled": True,
            "credentials": {"type": "zeroconf", "zeroconf": {"persist_credentials": True}},
            "server": {"enabled": True, "address": "127.0.0.1", "port": int(self.o["api_port"])},
            "log_level": "debug" if str(self.o["log_level"]).lower() == "debug" else "info",
        }
        if self.o.get("interface"):
            cfg["zeroconf_interfaces_to_advertise"] = [self.o["interface"]]
        with open(os.path.join(cfg_dir, "config.yml"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        backoff = 2.0
        while True:
            started = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                self.o["binary"],
                "--config_dir",
                cfg_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=CHUNK * 4,
            )
            self.lib_up = True
            LOG.info("go-librespot startet (pid %s)", proc.pid)
            self.changed()
            pump = asyncio.ensure_future(self.pump(proc.stdout))
            logs = asyncio.ensure_future(self._librespot_logs(proc.stderr))
            rc = await proc.wait()
            pump.cancel()
            logs.cancel()
            self.lib_up = False
            self.active = False
            self.status = "idle"
            self._clear_backlog()
            if self.owns:
                await self.speaker_stop()
            self.lib_restarts += 1
            self.changed()
            backoff = 2.0 if time.monotonic() - started > 300 else min(backoff * 2, 60)
            LOG.warning("go-librespot stoppede (rc %s) - starter igen om %.0f s", rc, backoff)
            await asyncio.sleep(backoff)

    async def _librespot_logs(self, stderr: asyncio.StreamReader) -> None:
        pat = re.compile(r'level=(\w+) msg="?(.*?)"?$')
        while line := await stderr.readline():
            text = line.decode("utf-8", "replace").rstrip()
            m = pat.search(text)
            lvl, msg = (m.group(1), m.group(2)) if m else ("info", text)
            if "accepted zeroconf" in msg:
                who = msg.split(" from ", 1)[-1].split('"')[0]
                self._spawn(self.on_session_reset(f"{who} loggede ind"))
            if lvl in ("debug", "trace"):
                LOG.debug("librespot: %s", msg)
            elif lvl == "info":
                LOG.info("librespot: %s", msg)
            else:
                LOG.warning("librespot [%s]: %s", lvl, msg)

    # ------------------------------------------------------------- HTTP
    async def h_stream(self, req: web.Request) -> web.StreamResponse:
        icy = bool(self.o["icy"]) and req.headers.get("Icy-MetaData") == "1"
        metaint = 16384
        headers = {"Cache-Control": "no-cache", "icy-name": self.o["device_name"]}
        if self.ext == "l16":
            headers["Content-Type"] = f"audio/L16;rate={RATE};channels={CHANNELS}"
        else:
            headers["Content-Type"] = "audio/flac"
        if icy:
            headers["icy-metaint"] = str(metaint)
        resp = web.StreamResponse(headers=headers)
        await resp.prepare(req)
        client = Client(req.remote or "?", self.o["client_queue_s"])
        for chunk in self.backlog:
            client.offer(chunk)
        self._clear_backlog()
        self.clients.add(client)
        self.client_came.set()
        LOG.info("Lytter forbundet: %s (icy=%s)", client.peer, icy)
        self.changed()
        enc = None
        feeder = None
        try:
            if self.ext == "flac":
                enc = await asyncio.create_subprocess_exec(
                    "flac",
                    "-s",
                    "-0",
                    "--force-raw-format",
                    "--endian=little",
                    "--sign=signed",
                    f"--channels={CHANNELS}",
                    "--bps=16",
                    f"--sample-rate={RATE}",
                    "-c",
                    "-",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                )

                async def feed() -> None:
                    while True:
                        enc.stdin.write(await client.queue.get())
                        await enc.stdin.drain()

                feeder = asyncio.ensure_future(feed())

            async def next_bytes() -> bytes:
                if enc is not None:
                    b = await enc.stdout.read(8192)
                    if not b:
                        raise ConnectionResetError("flac-encoder stoppede")
                    return b
                return await client.queue.get()

            until_meta = metaint
            last_title = None
            while True:
                buf = await next_bytes()
                if not icy:
                    await resp.write(buf)
                    continue
                while buf:
                    part, buf = buf[:until_meta], buf[until_meta:]
                    await resp.write(part)
                    until_meta -= len(part)
                    if until_meta == 0:
                        title = self._icy_title()
                        if title != last_title:
                            safe = title.replace("'", "’")
                            meta = f"StreamTitle='{safe}';".encode()
                            meta += b"\0" * (-len(meta) % 16)
                            await resp.write(bytes([len(meta) // 16]) + meta)
                            last_title = title
                        else:
                            await resp.write(b"\0")
                        until_meta = metaint
        except (OSError, asyncio.CancelledError, RuntimeError):
            pass
        finally:
            self.clients.discard(client)
            if feeder:
                feeder.cancel()
            if enc and enc.returncode is None:
                enc.kill()
            LOG.info("Lytter væk: %s (%s bidder tabt)", client.peer, client.dropped)
            self.changed()
        return resp

    async def h_status(self, _req: web.Request) -> web.Response:
        return web.json_response(self.snapshot())

    def _allowed(self, req: web.Request) -> bool:
        peer = req.remote or ""
        return any(
            peer == a or (a.endswith(".") and peer.startswith(a)) for a in self.o["cmd_allow"]
        )

    async def h_cmd(self, req: web.Request) -> web.Response:
        if not self._allowed(req):
            raise web.HTTPForbidden()
        name = req.match_info["name"]
        ok = True
        if name in ("pause", "next", "prev"):
            ok = await self.lib_post(f"/player/{name}")
        elif name in ("play", "resume"):
            ok = await self.lib_post("/player/resume")
        elif name == "stop":
            ok = await self.lib_post("/player/pause")
            if self.owns:
                await self.speaker_stop()
        elif name == "toggle":
            ok = await self.lib_post(
                "/player/pause" if self.status == "playing" else "/player/resume"
            )
        elif name == "volume":
            try:
                pct = max(0, min(100, int(req.query.get("v", ""))))
            except ValueError:
                raise web.HTTPBadRequest(text="v=0-100") from None
            await self.lib_volume(pct)
        else:
            raise web.HTTPNotFound()
        return web.json_response({"ok": ok, **self.snapshot()})

    # ------------------------------------------------------------- main
    async def run(self) -> None:
        self.session = aiohttp.ClientSession()
        app = web.Application()
        app.router.add_get(f"/spotify.{self.ext}", self.h_stream)
        app.router.add_get("/status", self.h_status)
        app.router.add_post("/cmd/{name}", self.h_cmd)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, self.o["bind"], int(self.o["stream_port"])).start()
        LOG.info("Spotify-bro %s: strøm %s", VERSION, self.url)
        tasks = [
            asyncio.ensure_future(self.librespot_loop()),
            asyncio.ensure_future(self.events_loop()),
            asyncio.ensure_future(self.reconcile_loop()),
        ]
        if self.o["speaker_control"]:
            tasks.append(
                asyncio.ensure_future(
                    sio_listen(
                        self.session,
                        self.o["speaker_host"],
                        self.o["volumio_port"],
                        self.on_speaker_state,
                    )
                )
            )
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        if self.owns:
            await self.speaker_stop()
        for t in tasks:
            t.cancel()
        await runner.cleanup()
        await self.session.close()


def main() -> None:
    opts = load_options()
    logging.basicConfig(
        level=getattr(logging, str(opts["log_level"]).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(Bro(opts).run())


if __name__ == "__main__":
    main()
