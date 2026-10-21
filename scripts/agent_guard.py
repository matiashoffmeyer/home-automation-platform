#!/usr/bin/env python3
"""PreToolUse/SubagentStop hook: enforces the subagent budget.

The policy in CLAUDE.md ("Subagenter") allows one or two subagents at a time,
a cheaper model for read-only triage, and no fleets of verifiers. Each subagent
starts by writing 50-65k tokens of context, and the quota is shared. On
2026-10-10 a session broke the written rule anyway (Opus finders plus one
sceptic per finding), and the quota ran out while the agents were still
working. A rule in text was not enough, so this hook blocks:

  Workflow  every ``agent()`` in the script needs ``model: 'sonnet'`` or
            ``'haiku'``; no ``pipeline()`` (it fans out up to the CPU limit);
            ``parallel()`` only over ``.slice(i, i + 2)``; no ``while`` loops
            (loop-until-dry); no named workflows (they cannot be inspected).
  Agent     at most two running at a time (counted here, decremented by
            SubagentStop); a non-Sonnet agent (Opus, fork) only when no other
            agent is running.

An "ultracode" session does not lift the rule. Only the user can switch the
hook off, by creating the git-ignored file ``.claude/agent_guard_off`` and
deleting it afterwards. Exit 2 with a message on stderr blocks the call; the
message is shown to the model. See docs/adr/0006-agent-guardrails-as-hooks.md.
"""

import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE = Path.home() / ".claude" / "agent_guard_state.json"
MAX_RUNNING = 2
STALE_S = 45 * 60  # en agent uden SubagentStop glemmes efter 45 min
CHEAP = ("sonnet", "haiku")


def block(msg: str) -> None:
    print(
        f"🚦 agent_guard: {msg}\n(CLAUDE.md 🚦 Subagenter — max 2 ad gangen, "
        f"Sonnet til triage. Kun brugeren må oprette .claude/agent_guard_off.)",
        file=sys.stderr,
    )
    sys.exit(2)


def load_state() -> list[float]:
    try:
        ts = json.loads(STATE.read_text())
    except Exception:
        ts = []
    now = time.time()
    return [t for t in ts if now - t < STALE_S]


def save_state(ts: list[float]) -> None:
    try:
        STATE.write_text(json.dumps(ts))
    except Exception:
        pass


def check_workflow(inp: dict) -> None:
    script = inp.get("script") or ""
    if inp.get("scriptPath"):
        try:
            script = Path(inp["scriptPath"]).read_text(encoding="utf-8")
        except Exception:
            block(f"kan ikke læse scriptPath {inp['scriptPath']} — kan ikke tjekkes.")
    if not script:
        block(
            f"navngivet workflow ({inp.get('name')!r}) kan ikke inspiceres — skriv scriptet inline."
        )
    code = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", script, flags=re.S))
    n_agent = len(re.findall(r"\bagent\s*\(", code))
    n_cheap = len(re.findall(r"model\s*:\s*['\"](?:%s)['\"]" % "|".join(CHEAP), code))
    bad = re.findall(r"model\s*:\s*['\"](\w+)['\"]", code)
    bad = [m for m in bad if m not in CHEAP]
    errs = []
    if bad:
        errs.append(f"model {sorted(set(bad))} — workflow-agenter er read-only triage = sonnet")
    if n_agent > n_cheap:
        errs.append(
            f"{n_agent} agent()-kald men kun {n_cheap} model:'sonnet' — "
            "uden model arver agenten Opus"
        )
    if re.search(r"\bpipeline\s*\(", code):
        errs.append(
            "pipeline() fan-out'er til CPU-loftet — kør i par: "
            "for (i=0;i<items.length;i+=2) await parallel(items.slice(i, i + 2).map(...))"
        )
    if re.search(r"\bparallel\s*\(", code) and not re.search(
        r"\.slice\(\s*\w+\s*,\s*\w+\s*\+\s*[12]\s*\)", code
    ):
        errs.append("parallel() uden .slice(i, i + 2)-batching")
    if re.search(r"\bwhile\s*\(", code):
        errs.append("while-løkke (loop-until-dry/-count) har intet agent-loft")
    if errs:
        block("Workflow afvist:\n  - " + "\n  - ".join(errs))


def check_agent(inp: dict) -> None:
    running = load_state()
    model = (inp.get("model") or "").lower()
    cheap = model in CHEAP and inp.get("subagent_type") != "fork"
    if len(running) >= MAX_RUNNING:
        block(f"{len(running)} subagenter kører allerede — vent på deres rapport.")
    if not cheap and running:
        block(
            "en Opus-/fork-subagent må kun køre ALENE (der kører allerede én). "
            "Triage → model:'sonnet'."
        )
    running.append(time.time())
    save_state(running)


def main() -> None:
    if (REPO / ".claude" / "agent_guard_off").exists():
        sys.exit(0)
    try:
        ev = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if ev.get("hook_event_name") == "SubagentStop" or sys.argv[1:2] == ["stop"]:
        running = load_state()
        if running:
            running.pop(0)
        save_state(running)
        sys.exit(0)
    tool = ev.get("tool_name")
    inp = ev.get("tool_input") or {}
    if tool == "Workflow":
        check_workflow(inp)
    elif tool in ("Agent", "Task"):
        check_agent(inp)
    sys.exit(0)


if __name__ == "__main__":
    main()
