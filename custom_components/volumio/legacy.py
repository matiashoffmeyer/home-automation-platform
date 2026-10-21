"""Volumio 2 OEM-firmware uden de nyere REST-ruter (AxiomAir N3, V2.13.2 2020).

Override af core-integrationen (2026.9.2) — se README.md i denne mappe.

Firmwaren har kun getState, listplaylists og commands over REST; alt andet
(getSystemInfo, getSystemVersion, replaceAndPlay, browse) svarer 302 → "/".
pyvolumio sluger det som {} — så core-integrationen crasher på
info["hardware"], og play_media gør tavst INGENTING. Det socket.io-API som
Volumio's egen web-UI bruger, har dem alle. Minimal Engine.IO v3 over
long-polling (ingen afhængighed): handshake → én poll (namespace-connect, uden
den bliver eventet ignoreret — målt 2026-10-08) → emit → evt. læs svaret.
"""

import asyncio
import json
import re
import time
from typing import Any

import aiohttp

_PATH = "/socket.io/?EIO=3&transport=polling"
_TIMEOUT = aiohttp.ClientTimeout(total=10)


def _frame(msg: str) -> bytes:
    return f"{len(msg)}:{msg}".encode()


def _events(payload: str) -> list[list[Any]]:
    """Plukker socket.io-events ud af en EIO3-polling-krop (length:data-frames)."""
    out = []
    for m in re.finditer(r"42(\[.*?\])(?=\d+:|[\x00-\x09�]|$)", payload, re.S):
        try:
            out.append(json.loads(m.group(1)))
        except ValueError:
            continue
    return out


async def _connect(session: aiohttp.ClientSession, base: str) -> str:
    async with session.get(base, timeout=_TIMEOUT) as r:
        hs = await r.text(errors="replace")
    sid = json.loads(hs[hs.index("{") :])["sid"]
    url = f"{base}&sid={sid}"
    async with session.get(f"{url}&t={time.time()}", timeout=_TIMEOUT) as r:
        await r.read()
    return url


async def emit(
    session: aiohttp.ClientSession,
    host: str,
    port: int,
    event: str,
    data: Any = None,
    reply: str | None = None,
    wait: float = 5,
) -> Any:
    """Send ét socket.io-event; returnér data fra `reply`-eventet hvis angivet."""
    url = await _connect(session, f"http://{host}:{port}{_PATH}")
    msg = "42" + json.dumps([event] if data is None else [event, data])
    async with session.post(
        url,
        data=_frame(msg),
        headers={"Content-Type": "text/plain;charset=UTF-8"},
        timeout=_TIMEOUT,
    ) as r:
        await r.read()
    if reply is None:
        return None
    end = time.monotonic() + wait
    while time.monotonic() < end:
        async with session.get(f"{url}&t={time.time()}", timeout=_TIMEOUT) as r:
            body = await r.text(errors="replace")
        for ev in _events(body):
            if ev and ev[0] == reply:
                return ev[1] if len(ev) > 1 else None
        await asyncio.sleep(0.2)
    return None


class Library:
    """pyvolumio's browse() (kun det browse_media.py bruger) over socket.io."""

    def __init__(self, session: aiohttp.ClientSession, volumio: Any) -> None:
        self._session = session
        self._volumio = volumio

    async def browse(self, uri: str | None = None) -> dict[str, Any]:
        host, port = self._volumio._host, self._volumio._port
        if uri is None:
            sources = await emit(
                self._session, host, port, "getBrowseSources", reply="pushBrowseSources"
            )
            return {"lists": sources or []}
        res = await emit(
            self._session,
            host,
            port,
            "browseLibrary",
            {"uri": uri},
            reply="pushBrowseLibrary",
        )
        return (res or {}).get("navigation", {})


async def listen(
    session: aiohttp.ClientSession,
    host: str,
    port: int,
    on_state: Any,
) -> None:
    """Lyt på Volumio's pushState i realtid (som web-UI'et); genforbind for evigt.

    14/10: spøgelses-radioen (myair valgt mens radioen spiller) kommer ~1 s
    efter Spotify-skiftet — 10-s-pollen så den først efter 3-13 s ("blip").
    pushState kommer i samme sekund. EIO3-polling: en GET hænger til der er
    pakker; ping ("2") hvert 20. s fra en søster-task holder sessionen i live
    (pingInterval 25 s, målt 14/10 15:01). on_state(dict) kaldes pr. pushState.
    """
    base = f"http://{host}:{port}{_PATH}"
    long_poll = aiohttp.ClientTimeout(total=90)
    while True:
        pinger = None
        try:
            url = await _connect(session, base)

            async def ping() -> None:
                while True:
                    await asyncio.sleep(20)
                    async with session.post(
                        url,  # noqa: B023 - cancelled with its connection
                        data=_frame("2"),
                        timeout=_TIMEOUT,
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
        except Exception:  # noqa: BLE001 — højttaleren væk/genstartet: prøv igen
            pass
        finally:
            if pinger is not None:
                pinger.cancel()
        await asyncio.sleep(5)
