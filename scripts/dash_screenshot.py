#!/usr/bin/env python3
"""Screenshot a Lovelace view the way a phone or a desktop browser shows it.

A dashboard change is a visible change, and "it parses" says nothing about
whether the text can be read (2026-11-03: the Claude tab on Statistik was
unreadable on the phone, and nothing but a picture showed why). This starts a
throwaway headless Chromium container (zenika/alpine-chrome, host network),
logs in with the long-lived `ha_api_token` from secrets.yaml (frontend
localStorage), opens the view and saves a PNG that the agent can look at.

  python3 scripts/dash_screenshot.py /forbrug-dash/claude            # phone
  python3 scripts/dash_screenshot.py /forbrug-dash/claude --desktop
  python3 scripts/dash_screenshot.py /lys-dash/0 --out /tmp/x.png --wait 12
  python3 scripts/dash_screenshot.py /forbrug-dash/claude --height 800 --scroll 1600

Read-only for the house: it only renders pages. The container is removed
afterwards; the image stays (`docker rmi zenika/alpine-chrome` frees ~1 GB).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ha_secrets  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE = "zenika/alpine-chrome:latest"
HA = "http://127.0.0.1:8123"
PORT = 9333


def start_chrome(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "--network", "host", "--shm-size=512m",
         IMAGE, "--no-sandbox", "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={PORT}", "--remote-debugging-address=127.0.0.1",
         "about:blank"],
        check=True, capture_output=True,
    )  # fmt: skip
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("Chromium svarede ikke på CDP-porten")


async def shoot(path: str, out: str, desktop: bool, wait: float, height: int, scroll: int) -> None:
    import websockets

    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5))
    page = next(t for t in tabs if t.get("type") == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
        n = 0

        async def cdp(method: str, **params):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": method, "params": params}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == n:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg.get("result", {})

        w, h, scale, mobile = (
            (1280, height or 1600, 1, False) if desktop else (412, height or 2400, 2, True)
        )
        await cdp("Emulation.setDeviceMetricsOverride", width=w, height=h,
                  deviceScaleFactor=scale, mobile=mobile)  # fmt: skip
        await cdp("Page.enable")
        await cdp("Page.navigate", url=HA + "/")
        await asyncio.sleep(2)
        tokens = {
            "access_token": ha_secrets.get("ha_api_token"),
            "token_type": "Bearer",
            "expires_in": 315360000,
            "hassUrl": HA,
            "clientId": HA + "/",
            "expires": 4102444800000,
            "refresh_token": "",
        }
        await cdp("Runtime.evaluate",
                  expression=f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(tokens))});"
                  "localStorage.setItem('selectedTheme', JSON.stringify({theme:'default',dark:true}));")  # fmt: skip
        await cdp("Page.navigate", url=HA + path)
        await asyncio.sleep(wait)
        if scroll:  # HA ruller dokumentet; et kort viewport + scroll = læsbar fuld opløsning
            await cdp("Runtime.evaluate", expression=f"window.scrollTo(0, {scroll})")
            await asyncio.sleep(1.5)
        shot = await cdp("Page.captureScreenshot", format="png", captureBeyondViewport=False)
        with open(out, "wb") as fh:
            fh.write(base64.b64decode(shot["data"]))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", help="fx /forbrug-dash/claude")
    ap.add_argument("--desktop", action="store_true", help="1280 px bred i stedet for en telefon")
    ap.add_argument("--out", default=os.path.join(ROOT, ".cache", "dash_screenshot.png"))
    ap.add_argument("--wait", type=float, default=10, help="sekunder til graferne har tegnet")
    ap.add_argument("--height", type=int, default=0, help="viewport-højde i CSS-px")
    ap.add_argument("--scroll", type=int, default=0, help="rul N CSS-px ned før billedet")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    name = "dash_screenshot"
    start_chrome(name)
    try:
        asyncio.run(shoot(a.path, a.out, a.desktop, a.wait, a.height, a.scroll))
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
