#!/usr/bin/env python3
"""PreToolUse hook: no bare template reload.

A template reload is not a free deploy: every template entity goes through
``unavailable`` and intermediate values, and triggers act on them. On
2026-11-02, four bare reloads darkened open plan step by step through the
price rescale. CLAUDE.md said so already, and it still happened, because the
rule was text only. The call is now rejected with exit 2, and the reason on
stderr is shown to the agent.

Allowed: ``scripts/ha_reload.py templates``, which snapshots the lights,
reloads, diffs and restores what the reload darkened. Fails open (exit 0) on
any error. See docs/adr/0006-agent-guardrails-as-hooks.md.
"""

import json
import re
import sys

RELOAD = re.compile(
    r"services/template/reload\b"
    r"|services/homeassistant/reload_all\b"
    r"|['\"]template\.reload['\"]"
)

# Commands that only MENTION a reload (grep in docs, git log -S).
READ_ONLY = {"grep", "rg", "git", "sed", "awk", "cat", "head", "tail", "less", "echo", "printf"}


def dangerous(cmd):
    if "ha_reload.py" in cmd:
        return False
    for seg in re.split(r"&&|\|\||[;|\n]", cmd):
        toks = seg.split()
        while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):  # VAR=x cmd
            toks = toks[1:]
        if toks and toks[0].rsplit("/", 1)[-1] not in READ_ONLY and RELOAD.search(seg):
            return True
    return False


try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)
if isinstance(cmd, str) and dangerous(cmd):
    print(
        "Blokeret af scripts/reload_guard.py: template.reload er ikke gratis — hver "
        "template-entity går gennem unavailable og mellemværdier, og triggers handler "
        "på dem (2/11: fire reloads mørklagde open plan via el-pris-omskaleringen). "
        "Brug `python3 scripts/ha_reload.py templates` (snapshot → reload → diff → "
        "gendan det reloaden mørklagde). Kun automations/scripts ændret? Så er "
        "automation.reload / script.reload nok.",
        file=sys.stderr,
    )
    sys.exit(2)
sys.exit(0)
