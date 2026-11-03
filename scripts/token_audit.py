#!/usr/bin/env python3
"""Measure what Claude Code sessions in this repo cost, from their own transcripts.

Token claims in CLAUDE.md are hypotheses with a timestamp, like every other
note ("MÅL altid selv"). This script makes them measurable without re-deriving
the method each time (2026-10-08 and 2026-11-03 both started from scratch).

  sessions [--days N]  One line per session from ~/.claude/projects/<repo>/:
                       API calls, context at the first call, mean and max
                       context, compactions, weighted cost, subagent cost.
                       Warns about sessions that grew past the auto-compact
                       window without compacting (the cap is not in effect).
  context              Starts an interactive Claude Code in a pty, runs
                       `/context` and prints the fixed context per category
                       (system tools, CLAUDE.md, skills) and the effective
                       auto-compact window. No model call.

Weights are relative to the input price: cache read 0.1, input 1, cache write
2 (1 h TTL) / 1.25 (5 min), output 5. Thinking counts as output and stays in
the context for the rest of the session (measured 2026-11-03), so every later
call reads it again at 0.1.

See docs/standing_instructions.md, "Token-økonomi".
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS = os.path.expanduser("~/.claude/projects/")
W = {"inp": 1.0, "cr": 0.1, "cw1h": 2.0, "cw5m": 1.25, "out": 5.0}
WINDOW = 200_000  # .claude/settings.json autoCompactWindow


def transcript_dir() -> str:
    return PROJECTS + re.sub(r"[^A-Za-z0-9]", "-", ROOT)


def load_calls(path: str) -> tuple[list[dict], int]:
    """API calls (one per message.id) and the number of compactions."""
    calls, seen, compactions = [], set(), 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("isCompactSummary") or (
                d.get("type") == "system" and "compact" in str(d.get("subtype", ""))
            ):
                compactions += 1
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            if not u or m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            cc = u.get("cache_creation") or {}
            calls.append(
                {
                    "t": dt.datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")),
                    "inp": u.get("input_tokens", 0),
                    "cr": u.get("cache_read_input_tokens", 0),
                    "cw1h": cc.get(
                        "ephemeral_1h_input_tokens", u.get("cache_creation_input_tokens", 0)
                    ),
                    "cw5m": cc.get("ephemeral_5m_input_tokens", 0),
                    "out": u.get("output_tokens", 0),
                    "think": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
                }
            )
    return calls, compactions


def cost(c: dict) -> float:
    return sum(c[k] * w for k, w in W.items())


def ctx(c: dict) -> int:
    return c["inp"] + c["cr"] + c["cw1h"] + c["cw5m"]


def cmd_sessions(days: int) -> int:
    base = transcript_dir()
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    rows = []
    for f in sorted(glob.glob(os.path.join(base, "*.jsonl"))):
        calls, comp = load_calls(f)
        if len(calls) < 2 or calls[-1]["t"] < since:
            continue
        sid = os.path.basename(f)[:-6]
        sub = sum(
            cost(c)
            for s in glob.glob(
                os.path.join(base, sid, "subagents", "**", "*.jsonl"), recursive=True
            )
            for c in load_calls(s)[0]
        )
        n = len(calls)
        rows.append(
            {
                "sid": sid[:8],
                "start": calls[0]["t"].astimezone().strftime("%m-%d %H:%M"),
                "calls": n,
                "ctx0": ctx(calls[0]),
                "mean": sum(map(ctx, calls)) / n,
                "max": max(map(ctx, calls)),
                "comp": comp,
                "cost": sum(map(cost, calls)),
                "sub": sub,
                "think_out": sum(c["think"] for c in calls) * W["out"],
                "think_reread": sum(
                    c["think"] * W["cr"] * (n - i - 1) for i, c in enumerate(calls)
                ),
                "cr": sum(c["cr"] for c in calls) * W["cr"],
            }
        )
    if not rows:
        print(f"ingen sessioner de sidste {days} døgn i {base}")
        return 1
    print("session  start        kald  ctx0  snit   max  comp  pris(M)  sub(M)")
    for r in rows:
        flag = "  ⚠ over vinduet uden compaction" if r["max"] > WINDOW and not r["comp"] else ""
        print(
            f"{r['sid']} {r['start']}  {r['calls']:4d} {r['ctx0'] / 1e3:4.0f}k {r['mean'] / 1e3:4.0f}k"
            f" {r['max'] / 1e3:4.0f}k  {r['comp']:4d}  {r['cost'] / 1e6:7.2f}  {r['sub'] / 1e6:6.2f}{flag}"
        )
    tot = sum(r["cost"] for r in rows)
    calls = sum(r["calls"] for r in rows)
    print(
        f"\n{len(rows)} sessioner, {calls} kald, {tot / 1e6:.1f}M vægtet"
        f" (+ subagenter {sum(r['sub'] for r in rows) / 1e6:.1f}M), {tot / calls / 1e3:.0f}k pr. kald"
    )
    print(
        f"andele: cache-read {100 * sum(r['cr'] for r in rows) / tot:.0f} %,"
        f" thinking som output {100 * sum(r['think_out'] for r in rows) / tot:.0f} %,"
        f" thinking genlæst {100 * sum(r['think_reread'] for r in rows) / tot:.0f} %"
    )
    over = [r["sid"] for r in rows if r["max"] > WINDOW and not r["comp"]]
    if over:
        print(f"⚠ {len(over)} sessioner voksede over {WINDOW // 1000}k uden compaction — er")
        print(
            "  autoCompactWindow i .claude/settings.json stadig i kraft? (`token_audit.py context`)"
        )
    return 0


def cmd_context(extra: list[str]) -> int:
    import pty
    import select
    import signal

    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(ROOT)
        os.environ["TERM"] = "xterm-256color"
        os.execvp("claude", ["claude", *extra])
    try:
        import fcntl
        import struct
        import termios

        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 60, 200, 0, 0))
    except OSError:
        pass
    buf = b""

    def pump(sec: float, *until: bytes) -> None:
        nonlocal buf
        end = time.time() + sec
        while time.time() < end and not any(u in buf for u in until):
            if select.select([fd], [], [], 0.3)[0]:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    return
                buf += data
                if b"\x1b[6n" in data:  # TUI'en spørger efter cursor-position
                    os.write(fd, b"\x1b[1;1R")

    pump(40, b'Try "', b"auto mode", b"for shortcuts")  # prompten er tegnet
    pump(4)
    os.write(fd, b"/context")
    pump(2)
    os.write(fd, b"\r")
    pump(40, b"Auto-compact window")
    pump(3)
    os.kill(pid, signal.SIGKILL)
    text = re.sub(
        r"\s+", " ", re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]", b" ", buf).decode("utf-8", "replace")
    )
    i = text.rfind("Estimated usage by category")
    if i < 0:
        print("fik ingen /context-tabel (TUI'en svarede ikke inden 85 s)")
        return 1
    s = text[i:]
    total = re.search(r"([\d.]+k)/([\d.]+[km]) tokens", text)
    if total:
        print(f"fast kontekst ved sessionsstart: {total.group(1)} (vindue {total.group(2)})")
    for k in ("System prompt", "System tools", "MCP tools", "Memory files", "Skills"):
        m = re.search(re.escape(k) + r": ([\d.]+k?) tokens", s)
        if m:
            print(f"  {k:14s} {m.group(1)}")
    m = re.search(r"Auto-compact window: ([\d.]+[km]) tokens", s)
    print(f"  auto-compact-vindue: {m.group(1) if m else '?'}")
    j = s.find("Skills · /skills")
    if j >= 0:
        skills = re.findall(r"([\w:.-]+): ~(\d+) tokens", s[j : j + 4000])
        top = sorted(skills, key=lambda x: -int(x[1]))[:8]
        print("  største skills: " + ", ".join(f"{n} {t}" for n, t in top))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("sessions", help="pris og kontekst pr. session")
    p.add_argument("--days", type=int, default=7)
    p = sp.add_parser("context", help="fast kontekst pr. kategori via /context")
    p.add_argument("--settings", help="ekstra settings-JSON (sammenlign en ændring før commit)")
    a = ap.parse_args(argv)
    if a.cmd == "sessions":
        return cmd_sessions(a.days)
    return cmd_context(["--settings", a.settings] if a.settings else [])


if __name__ == "__main__":
    sys.exit(main())
