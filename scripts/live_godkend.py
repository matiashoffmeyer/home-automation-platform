#!/usr/bin/env python3
"""Ask the household for a yes before a live test or a restart.

User-spec 2026-10-28: anything the household can see or hear (lights, sound,
curtains, the robot) and any restart needs permission first, given with the
action buttons of a push: Godkend, Afvis, Om 20 min. "Om 20 min" asks again
20 minutes later. A late tap on an old push does nothing, because nobody is
listening any more.

    python3 scripts/live_godkend.py spørg "<hvad, kort dansk>" [--genstart]
        [--minutter N] [--frist M]
        Sends the push and waits for a button. Exit 0 = approved (the approval
        file is written and is valid for N minutes), 1 = rejected, 2 = no
        answer within M minutes, 3 = AirBnB (no push is sent: the phone may be
        in a guest's hands, ask in the chat), 4 = error. The wait can be long:
        run it in the background.
    python3 scripts/live_godkend.py status
    python3 scripts/live_godkend.py slut        # withdraw it when the test is done
    python3 scripts/live_godkend.py chat "<the user's own words>" [--genstart]
        AirBnB only: records a yes given in the chat.

scripts/live_guard.py (PreToolUse on Bash) reads the approval file and blocks
light, sound and restart commands without a valid one. See
docs/adr/0006-agent-guardrails-as-hooks.md.
"""

import argparse
import asyncio
import json
import os
import secrets
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

GODKENDELSE = Path(__file__).resolve().parent.parent / ".cache" / "live_godkendelse.json"
LOG = GODKENDELSE.with_suffix(".log")
NOTIFY = "mobile_app_phone_a"
TAG = "claude_godkend"
EVENT = "mobile_app_notification_action"
OM_MIN = 20
MAX_RUNDER = 6  # 5 udsættelser = 1 t 40 min, så er svaret nej
WS = "ws://supervisor/core/websocket"
REST = "http://supervisor/core/api"


def token():
    t = os.environ.get("SUPERVISOR_TOKEN")
    if not t:
        sys.exit("live_godkend: SUPERVISOR_TOKEN mangler — kør fra SSH-add-on'et")
    return t


def house_mode():
    req = urllib.request.Request(
        f"{REST}/states/input_select.house_mode",
        headers={"Authorization": f"Bearer {token()}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["state"]


def log(linje):
    GODKENDELSE.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {linje}\n")


def skriv_godkendelse(hvad, slags, minutter, kilde):
    nu = time.time()
    GODKENDELSE.parent.mkdir(exist_ok=True)
    tmp = GODKENDELSE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "hvad": hvad,
                "slags": slags,
                "kilde": kilde,
                "godkendt": nu,
                "udloeber": nu + minutter * 60,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(GODKENDELSE)
    return datetime.fromtimestamp(nu + minutter * 60).strftime("%H:%M")


async def forbind():
    import websockets

    ws = await websockets.connect(WS, max_size=None)
    await ws.recv()  # auth_required
    await ws.send(json.dumps({"type": "auth", "access_token": token()}))
    if json.loads(await ws.recv()).get("type") != "auth_ok":
        await ws.close()
        raise RuntimeError("websocket-auth afvist")
    return ws


async def kald(ws, mid, msg):
    await ws.send(json.dumps({"id": mid, **msg}))
    async with asyncio.timeout(15):
        while True:
            m = json.loads(await ws.recv())
            if m.get("type") == "result" and m.get("id") == mid:
                if not m.get("success"):
                    raise RuntimeError(f"{msg.get('type')}: {m.get('error')}")
                return m


async def service(ws, mid, domain, svc, data):
    await kald(
        ws, mid, {"type": "call_service", "domain": domain, "service": svc, "service_data": data}
    )


async def runde(hvad, slags, minutter, frist_s, rid, nr):
    """Én push og ét svar. Returnerer godkend / afvis / om20 / intet."""
    import websockets

    titel = "Må Claude genstarte HA?" if "genstart" in slags else "Må Claude teste live?"
    tekst = f"{hvad}\nGælder {minutter} min fra du godkender."
    if nr > 1:
        tekst += f"\n(spurgt igen efter {OM_MIN} min)"
    svar_paa = {
        f"CLAUDE_GODKEND_{rid}": "godkend",
        f"CLAUDE_AFVIS_{rid}": "afvis",
        f"CLAUDE_OM20_{rid}": "om20",
    }
    frist = time.time() + frist_s
    sendt = False
    while True:
        try:
            ws = await forbind()
            try:
                # Abonnér FØR pushen, så et hurtigt tryk ikke går tabt.
                await kald(ws, 1, {"type": "subscribe_events", "event_type": EVENT})
                if not sendt:
                    await service(
                        ws,
                        2,
                        "notify",
                        NOTIFY,
                        {
                            "title": titel,
                            "message": tekst,
                            "data": {
                                "tag": TAG,
                                "priority": "high",
                                "ttl": 0,
                                "actions": [
                                    {"action": f"CLAUDE_GODKEND_{rid}", "title": "Godkend"},
                                    {"action": f"CLAUDE_AFVIS_{rid}", "title": "Afvis"},
                                    {"action": f"CLAUDE_OM20_{rid}", "title": f"Om {OM_MIN} min"},
                                ],
                            },
                        },
                    )
                    sendt = True
                    print(f"SPURGT ({nr}/{MAX_RUNDER}): {hvad}", flush=True)
                svar = "intet"
                while time.time() < frist:
                    try:
                        async with asyncio.timeout(frist - time.time()):
                            m = json.loads(await ws.recv())
                    except TimeoutError:
                        break
                    if m.get("type") == "event":
                        a = m["event"].get("data", {}).get("action", "")
                        if a in svar_paa:
                            svar = svar_paa[a]
                            break
                # Fjern boblen, så et sent tryk ikke ligner et svar. Svaret er
                # givet; fejler oprydningen, må den ikke starte ventetiden igen.
                try:
                    await service(
                        ws,
                        3,
                        "notify",
                        NOTIFY,
                        {"message": "clear_notification", "data": {"tag": TAG}},
                    )
                    await service(
                        ws,
                        4,
                        "logbook",
                        "log",
                        {"name": "Claude-godkendelse", "message": f"{svar}: {hvad}"},
                    )
                except Exception:  # noqa: BLE001, S110
                    pass
                return svar
            finally:
                await ws.close()
        except (OSError, RuntimeError, TimeoutError, websockets.ConnectionClosed) as e:
            if time.time() >= frist:
                return "intet"
            if not sendt:
                raise
            print(f"forbindelsen faldt ({e}) — lytter igen", flush=True)
            await asyncio.sleep(10)


def spoerg(a):
    try:
        mode = house_mode()
    except OSError as e:
        print(f"FEJL: HA svarer ikke ({e}) — ingen push mulig", file=sys.stderr)
        return 4
    slags = ["genstart"] if a.genstart else ["test"]
    if mode == "AirBnB":
        print(
            "AIRBNB: ingen push (telefonen kan være hos gæsten). Spørg user i chatten; "
            'et ja registreres med `live_godkend.py chat "<brugerens ord>"`.'
        )
        return 3
    rid = secrets.token_hex(4)
    for nr in range(1, MAX_RUNDER + 1):
        try:
            svar = asyncio.run(runde(a.hvad, slags, a.minutter, a.frist * 60, rid, nr))
        except Exception as e:  # noqa: BLE001 — scriptet skal svare med en exit-kode
            print(f"FEJL: {e}", file=sys.stderr)
            return 4
        log(f"{svar:8} {'/'.join(slags)}  {a.hvad}")
        if svar == "godkend":
            til = skriv_godkendelse(a.hvad, slags, a.minutter, "push")
            print(f"GODKENDT til {til}: {a.hvad}")
            return 0
        if svar == "afvis":
            print(f"AFVIST: {a.hvad}")
            return 1
        if svar == "intet":
            print(f"INTET SVAR på {a.frist} min = nej: {a.hvad}")
            return 2
        if nr < MAX_RUNDER:
            print(f"UDSAT {OM_MIN} min (runde {nr})", flush=True)
            time.sleep(OM_MIN * 60)
    print(f"UDSAT {MAX_RUNDER} gange = nej: {a.hvad}")
    return 2


def status(_):
    if not GODKENDELSE.exists():
        print("ingen godkendelse")
        return 1
    g = json.loads(GODKENDELSE.read_text(encoding="utf-8"))
    rest = g["udloeber"] - time.time()
    til = datetime.fromtimestamp(g["udloeber"]).strftime("%H:%M")
    tilstand = f"gyldig til {til} ({rest / 60:.0f} min)" if rest > 0 else f"UDLØBET {til}"
    print(f"{'/'.join(g['slags'])} via {g['kilde']}: {g['hvad']} — {tilstand}")
    return 0 if rest > 0 else 1


def slut(_):
    if GODKENDELSE.exists():
        GODKENDELSE.unlink()
        log("slut     godkendelsen trukket tilbage")
    print("ingen godkendelse")
    return 0


def chat(a):
    try:
        mode = house_mode()
    except OSError as e:
        print(f"FEJL: HA svarer ikke ({e})", file=sys.stderr)
        return 4
    if mode != "AirBnB":
        print(
            "chat-godkendelse gælder kun i AirBnB — brug `spørg` (push med knapper)",
            file=sys.stderr,
        )
        return 4
    slags = ["genstart"] if a.genstart else ["test"]
    til = skriv_godkendelse(a.citat, slags, a.minutter, "chat")
    log(f"chat     {'/'.join(slags)}  {a.citat}")
    print(f"GODKENDT (chat, AirBnB) til {til}: {a.citat}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spørg", aliases=["spoerg"], help="push med Godkend / Afvis / Om 20 min")
    s.add_argument("hvad", help="hvad der skal ske, kort dansk (står i pushen)")
    s.add_argument("--genstart", action="store_true", help="det er en genstart, ikke en test")
    s.add_argument("--minutter", type=int, default=None, help="gyldighed (default 15, genstart 10)")
    s.add_argument(
        "--frist", type=int, default=30, help="minutter at vente på et svar (default 30)"
    )
    s.set_defaults(fn=spoerg)
    sub.add_parser("status").set_defaults(fn=status)
    sub.add_parser("slut").set_defaults(fn=slut)
    c = sub.add_parser("chat", help="kun AirBnB: registrér et ja givet i chatten")
    c.add_argument("citat")
    c.add_argument("--genstart", action="store_true")
    c.add_argument("--minutter", type=int, default=None)
    c.set_defaults(fn=chat)
    a = p.parse_args()
    if getattr(a, "minutter", 0) is None:
        a.minutter = 10 if a.genstart else 15
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
