#!/usr/bin/env python3
"""PreToolUse hook: no Home Assistant restart without saving state first.

Home Assistant segfaults during shutdown on this host (a pychromecast thread
under Python 3.14), so its final restore-state write never happens and helper
changes from the last 15 minutes are lost on a plain restart. The rule used to
be text only. Now the call is rejected with exit 2, and the reason on stderr is
shown to the agent.

Allowed: ``scripts/ha_restart.sh``, or a command that itself calls
``save_persistent_states`` before the restart. Fails open (exit 0) on any
error. See docs/adr/0006-agent-guardrails-as-hooks.md.
"""

import json
import re
import sys

STOP = re.compile(
    r"\bha\s+core\s+(restart|stop|rebuild|update)\b"
    r"|/core/(restart|stop|rebuild)\b"
    r"|services/homeassistant/(restart|stop)\b"
)

# Søge-/læse-kommandoer der blot NÆVNER en genstart (grep i docs, git log -S).
# Afgøres pr. simpel kommando, så `grep … && <genstart>` stadig fanges.
READ_ONLY = {"grep", "rg", "git", "sed", "awk", "cat", "head", "tail", "less", "echo", "printf"}


def dangerous(cmd):
    if "ha_restart.sh" in cmd or "save_persistent_states" in cmd:
        return False
    for seg in re.split(r"&&|\|\||[;|\n]", cmd):
        toks = seg.split()
        while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):  # VAR=x cmd
            toks = toks[1:]
        if toks and toks[0].rsplit("/", 1)[-1] not in READ_ONLY and STOP.search(seg):
            return True
    return False


try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)
if isinstance(cmd, str) and dangerous(cmd):
    print(
        "Blokeret af scripts/restart_guard.py: HA segfaulter ved nedlukning, så "
        "restore-state fra de sidste 15 min går tabt. Brug `bash scripts/ha_restart.sh` "
        "(gemmer først; --force hvis HA er nede), eller kald "
        "homeassistant.save_persistent_states i samme kommando før genstarten.",
        file=sys.stderr,
    )
    sys.exit(2)
sys.exit(0)
