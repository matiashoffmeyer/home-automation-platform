#!/usr/bin/env python3
"""connect_burst_s: how much audio a listener gets in its first second.

Feeds pump() more PCM than real time allows (go-librespot decodes far faster
than it plays) and counts what reaches a fast-reading listener, like MPD while
it fills its buffer. No speaker, no Spotify, no network.

    python3 addons/spotify_bro/tests/test_burst.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bro  # noqa: E402


async def first_second(burst_s: float, then_skip: bool = False) -> tuple[float, float]:
    """→ (seconds of audio delivered in the first second, same after a skip)."""
    b = bro.Bro(dict(bro.DEFAULTS, connect_burst_s=burst_s))
    got = 0

    class Listener(bro.Client):
        def offer(self, data: bytes) -> None:
            nonlocal got
            got += len(data)

    # What h_stream does when the speaker connects to an empty room.
    if burst_s > 0:
        b.burst = max(0.0, min(burst_s, float(b.o["client_queue_s"]) - 1.0))
        b.burst_at = time.monotonic()
    b.clients.add(Listener("test", 4.0))
    reader = asyncio.StreamReader()
    reader.feed_data(bytes(bro.BPS * 8))
    task = asyncio.create_task(b.pump(reader))
    await asyncio.sleep(1.0)
    first = got / bro.BPS
    second = 0.0
    if then_skip:
        # A skip: the daemon is silent for a moment, then the next track comes.
        await asyncio.sleep(7.5)  # everything fed has been paced out; the pipe is empty
        got = 0
        reader.feed_data(bytes(bro.BPS * 8))
        await asyncio.sleep(1.0)
        second = got / bro.BPS
    task.cancel()
    return first, second


async def main() -> None:
    off, _ = await first_second(0.0)
    assert 1.0 < off < 1.7, off  # real time + lead_ms, as before
    print(f"  ✓ burst 0 (default): {off:.2f} s of audio in the first second — unchanged")
    on, skip = await first_second(3.0, then_skip=True)
    assert 3.9 < on < 4.7, on
    print(f"  ✓ burst 3: {on:.2f} s of audio in the first second")
    assert 1.0 < skip < 1.7, skip
    print(f"  ✓ burst 3, after a skip: {skip:.2f} s — no second head start")
    capped, _ = await first_second(10.0)
    assert capped < 4.7, capped  # client_queue_s 4 - 1 = 3 s at most
    print(f"  ✓ burst 10 is capped by the listener's queue: {capped:.2f} s")


if __name__ == "__main__":
    asyncio.run(main())
