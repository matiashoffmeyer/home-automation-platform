#!/usr/bin/env python3
"""PreToolUse hook: no live test and no restart without the household's yes.

User-spec 2026-10-28: "hvis der skal testes live med lys eller noget jeg kan
høre eller der genstartes så skal jeg spørges med action knapper før". The yes
comes from scripts/live_godkend.py (a push with Godkend / Afvis / Om 20 min),
which writes .cache/live_godkendelse.json. This hook rejects, with exit 2 and
the reason on stderr, a Bash command that

- calls a service the household can see or hear (light, switch, scene, script,
  media_player, tts, cover, siren, remote, button, fan, vacuum,
  automation.trigger, homeassistant.turn_on/off/toggle) without a valid
  approval of kind ``test``, or
- restarts Home Assistant, the host or an add-on (``ha_restart.sh`` included)
  without a valid approval of kind ``genstart``. If Home Assistant does not
  answer, the restart is let through: nothing can be asked, and a dead house
  has nothing to disturb.

Reloads, notifications, helper writes and reads pass. Commands that only
mention a pattern (grep, git, echo, a heredoc fed to cat or git) pass. Fails
open on a parse error. Only the user may switch it off, by creating the
git-ignored file ``.claude/live_guard_off``. See
docs/adr/0006-agent-guardrails-as-hooks.md.
"""

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROD = Path(__file__).resolve().parent.parent
GODKENDELSE = ROD / ".cache" / "live_godkendelse.json"

# (?!reload\b): script.reload and scene.reload are reloads, which the docstring
# lets through; without it, `services/script/reload` was blocked (29/10).
LIVE = re.compile(
    r"services/(light|switch|scene|script|media_player|tts|cover|siren|remote|button|fan|vacuum)/(?!reload\b)"
    r"|services/automation/trigger\b"
    r"|services/homeassistant/(turn_on|turn_off|toggle)\b"
)
GENSTART = re.compile(
    r"ha_restart\.sh"
    r"|\bha\s+core\s+(restart|stop|rebuild|update)\b"
    r"|\bha\s+host\s+(reboot|shutdown)\b"
    r"|\bha\s+(addons|apps)\s+(restart|rebuild|stop|update)\b"
    r"|/core/(restart|stop|rebuild)\b"
    r"|/host/(reboot|shutdown)\b"
    r"|/addons/[^/\s]+/(restart|rebuild|stop|update)\b"
    r"|services/homeassistant/(restart|stop)\b"
    r"|services/hassio/(host_reboot|host_shutdown|addon_restart|addon_stop|addon_update)\b"
)
# Kommandoer der blot NÆVNER et mønster (grep i docs, git log -S, en commit-
# besked). Afgøres pr. simpel kommando, så `grep … && <kald>` stadig fanges.
READ_ONLY = {
    "grep",
    "rg",
    "git",
    "sed",
    "awk",
    "cat",
    "head",
    "tail",
    "less",
    "echo",
    "printf",
    "tee",
    "wc",
}
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")


def foerste(seg):
    toks = seg.split()
    while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):  # VAR=x cmd
        toks = toks[1:]
    while toks and toks[0] in {"sudo", "time", "nohup", "!"}:
        toks = toks[1:]
    return toks[0].rsplit("/", 1)[-1] if toks else ""


def fund(cmd):
    """{'test', 'genstart'} for de dele af kommandoen der udfører noget."""
    hit = set()
    slut_paa, spring = None, False
    for linje in cmd.split("\n"):
        if slut_paa is not None:
            if linje.strip() == slut_paa:
                slut_paa = None
            elif not spring:
                hit |= klassificer(linje)
            continue
        m = HEREDOC.search(linje)
        for seg in re.split(r"&&|\|\||[;|]", linje):
            # Spørgsmålets egen tekst ("genstarte med ha_restart.sh") er ikke et kald.
            if foerste(seg) not in READ_ONLY and "live_godkend.py" not in seg:
                hit |= klassificer(seg)
        if m:
            slut_paa = m.group(1)
            # Heredoc til cat/git/tee er tekst (en fil, en besked); til python/bash er det kode.
            spring = foerste(linje[: m.start()].split("|")[-1]) in READ_ONLY
    return hit


def klassificer(tekst):
    out = set()
    if LIVE.search(tekst):
        out.add("test")
    if GENSTART.search(tekst):
        out.add("genstart")
    return out


def gyldig():
    try:
        g = json.loads(GODKENDELSE.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return g if g.get("udloeber", 0) > time.time() else None


def ha_svarer():
    tok = os.environ.get("SUPERVISOR_TOKEN")
    if not tok:
        return True  # kan ikke afgøre → antag at der er nogen at spørge
    req = urllib.request.Request(
        "http://supervisor/core/api/", headers={"Authorization": f"Bearer {tok}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=2):
            return True
    except OSError:
        return False


def main():
    if (ROD / ".claude" / "live_guard_off").exists():
        return 0
    try:
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except Exception:  # noqa: BLE001 — fail open
        return 0
    if not isinstance(cmd, str):
        return 0
    behov = fund(cmd)
    if not behov:
        return 0
    g = gyldig()
    mangler = behov - set(g["slags"] if g else [])
    if mangler == {"genstart"} and not ha_svarer():
        return 0
    if not mangler:
        return 0
    hvad = " og ".join(
        sorted("en genstart" if x == "genstart" else "en live-test (lys/lyd)" for x in mangler)
    )
    flag = " --genstart" if "genstart" in mangler else ""
    print(
        f"Blokeret af scripts/live_guard.py: {hvad} kræver brugerens ja via push med "
        f"knapper (user-spec 2026-10-28). Kør `python3 scripts/live_godkend.py spørg "
        f'"<hvad, kort dansk>"{flag}` med run_in_background og vent på svaret: exit 0 = '
        f"godkendt, 1 = afvist, 2 = intet svar (= nej), 3 = AirBnB (spørg i chatten, "
        f'registrér brugerens ja med `live_godkend.py chat "<brugerens ord>"`). Skriver du blot '
        f"TEKST der nævner mønstret (en heredoc til python), så brug Edit/Write. Omgå aldrig.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
