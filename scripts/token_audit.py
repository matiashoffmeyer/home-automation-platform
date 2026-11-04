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
  push                 Hourly aggregates -> Home Assistant long-term statistics
                       (external, `claude:*`), shown on Statistik -> Claude.
                       Backfills everything the transcripts still hold; hours
                       whose transcripts Claude Code has since cleaned up are
                       kept in .cache/token_audit/hourly.json. Runs in the
                       background from the SessionStart/SessionEnd hooks.

Weights are relative to the input price: cache read 0.1, input 1, cache write
2 (1 h TTL) / 1.25 (5 min), output 5. Thinking counts as output and stays in
the context for the rest of the session (measured 2026-11-03), so every later
call reads it again at 0.1.

See docs/standing_instructions.md, "Token-økonomi".
"""

from __future__ import annotations

import argparse
import asyncio
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


def load_calls(path: str) -> tuple[list[dict], list[str]]:
    """API calls (one per message.id) and the timestamps of compactions."""
    calls, seen, compactions = [], set(), []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("isCompactSummary") or (
                d.get("type") == "system" and "compact" in str(d.get("subtype", ""))
            ):
                compactions.append(d.get("timestamp", ""))
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
                "comp": len(comp),
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


CACHE = os.path.join(ROOT, ".cache", "token_audit", "hourly.json")
WS = "ws://supervisor/core/websocket"
# (statistic_id, navn, enhed, slags): "mean" = gennemsnit/min/max pr. time,
# "sum" = timens total + løbende sum (statistics-graph `change` = pr. dag).
STATS = [
    ("tokens_pr_kald", "Pris pr. kald", "k tokens", "mean"),
    ("kontekst_pr_kald", "Kontekst pr. kald", "k tokens", "mean"),
    ("fast_kontekst", "Kontekst ved sessionsstart", "k tokens", "mean"),
    ("tokens", "Pris i alt", "M tokens", "sum"),
    ("tokens_cache_laes", "Cache-læsning", "M tokens", "sum"),
    ("tokens_cache_skriv", "Cache-skrivning", "M tokens", "sum"),
    ("tokens_output", "Output", "M tokens", "sum"),
    ("tokens_thinking", "Heraf thinking", "M tokens", "sum"),
    ("tokens_subagenter", "Heraf subagenter", "M tokens", "sum"),
    ("kald", "API-kald", "kald", "sum"),
    ("sessioner", "Sessioner", "sessioner", "sum"),
    ("compactions", "Compactions", "compactions", "sum"),
]
# Enheden bestemmer skalaen: rå tokens gav 8-cifrede tal, som HA's kort ikke
# kan vise på en telefon (målt med scripts/dash_screenshot.py 3/11).
SCALE = {"k tokens": 1e3, "M tokens": 1e6}


def _hour(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).replace(minute=0, second=0, microsecond=0).isoformat()


def hourly() -> dict[str, dict]:
    """Time-aggregater fra alle transcripts (hovedsessioner + subagenter)."""
    base = transcript_dir()
    hours: dict[str, dict] = {}

    def h(key: str) -> dict:
        return hours.setdefault(
            key,
            {
                "calls": 0,
                "cost": 0.0,
                "ctx": 0,
                "ctx_min": None,
                "ctx_max": 0,
                "c_min": None,
                "c_max": 0.0,
                "cr": 0.0,
                "cw": 0.0,
                "out": 0.0,
                "think": 0.0,
                "sub": 0.0,
                "ctx0": [],
                "comp": 0,
            },
        )

    for f in glob.glob(os.path.join(base, "*.jsonl")):
        calls, comp = load_calls(f)
        if len(calls) >= 2:  # én-kalds-prober (`claude -p`) er ikke sessioner
            h(_hour(calls[0]["t"]))["ctx0"].append(ctx(calls[0]))
        for c in calls:
            b = h(_hour(c["t"]))
            k, x = cost(c), ctx(c)
            b["calls"] += 1
            b["cost"] += k
            b["ctx"] += x
            b["ctx_min"] = x if b["ctx_min"] is None else min(b["ctx_min"], x)
            b["ctx_max"] = max(b["ctx_max"], x)
            b["c_min"] = k if b["c_min"] is None else min(b["c_min"], k)
            b["c_max"] = max(b["c_max"], k)
            b["cr"] += c["cr"] * W["cr"]
            b["cw"] += c["cw1h"] * W["cw1h"] + c["cw5m"] * W["cw5m"] + c["inp"] * W["inp"]
            b["out"] += c["out"] * W["out"]
            b["think"] += c["think"] * W["out"]
        for ts in comp:
            if ts:
                h(_hour(dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))))["comp"] += 1
        sid = os.path.basename(f)[:-6]
        for s in glob.glob(os.path.join(base, sid, "subagents", "**", "*.jsonl"), recursive=True):
            for c in load_calls(s)[0]:
                k = cost(c)
                b = h(_hour(c["t"]))
                b["sub"] += k
                b["cr"] += c["cr"] * W["cr"]
                b["cw"] += c["cw1h"] * W["cw1h"] + c["cw5m"] * W["cw5m"] + c["inp"] * W["inp"]
                b["out"] += c["out"] * W["out"]
                b["think"] += c["think"] * W["out"]
    # Claude Code sletter gamle transcripts (cleanupPeriodDays) → behold de
    # timer cachen kender, ellers falder de løbende summer tilbage.
    try:
        with open(CACHE, encoding="utf-8") as fh:
            old = json.load(fh)
    except OSError, ValueError:
        old = {}
    merged = {**old, **hours}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(merged, fh)
    os.replace(CACHE + ".tmp", CACHE)
    return merged


def build_stats(hours: dict[str, dict]) -> dict[str, list[dict]]:
    unit = {sid: u for sid, _, u, _ in STATS}

    def sc(sid: str, v: float) -> float:
        f = SCALE.get(unit[sid], 1)
        return round(v / f, 3 if f > 1 else 0)

    out: dict[str, list[dict]] = {sid: [] for sid, *_ in STATS}
    run: dict[str, float] = {}
    for key in sorted(hours):
        b = hours[key]
        means = {}
        if b["calls"]:
            means["tokens_pr_kald"] = (b["cost"] / b["calls"], b["c_min"], b["c_max"])
            means["kontekst_pr_kald"] = (b["ctx"] / b["calls"], b["ctx_min"], b["ctx_max"])
        if b["ctx0"]:
            v = b["ctx0"]
            means["fast_kontekst"] = (sum(v) / len(v), min(v), max(v))
        for sid, (m, lo, hi) in means.items():
            out[sid].append(
                {"start": key, "mean": sc(sid, m), "min": sc(sid, lo), "max": sc(sid, hi)}
            )
        per_hour = {
            "tokens": b["cost"] + b["sub"],
            "tokens_cache_laes": b["cr"],
            "tokens_cache_skriv": b["cw"],
            "tokens_output": b["out"],
            "tokens_thinking": b["think"],
            "tokens_subagenter": b["sub"],
            "kald": b["calls"],
            "sessioner": len(b["ctx0"]),
            "compactions": b["comp"],
        }
        for sid, v in per_hour.items():
            run[sid] = run.get(sid, 0.0) + v
            out[sid].append({"start": key, "state": sc(sid, v), "sum": sc(sid, run[sid])})
    return out


async def _import(stats: dict[str, list[dict]]) -> int:
    import websockets

    tok = os.environ.get("SUPERVISOR_TOKEN")
    if not tok:
        raise RuntimeError("SUPERVISOR_TOKEN mangler (kører vi uden for add-on'et?)")
    async with websockets.connect(WS, max_size=None, open_timeout=10) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": tok}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            raise RuntimeError("websocket-auth afvist")
        n = 0
        for i, (sid, name, unit, kind) in enumerate(STATS, start=1):
            rows = stats[sid]
            if not rows:
                continue
            meta = {
                "source": "claude",
                "statistic_id": f"claude:{sid}",
                "name": name,
                "unit_of_measurement": unit,
                "unit_class": None,
                "has_sum": kind == "sum",
                "mean_type": 1 if kind == "mean" else 0,
            }
            msg = {"id": i, "type": "recorder/import_statistics", "metadata": meta, "stats": rows}
            await ws.send(json.dumps(msg))
            res = json.loads(await asyncio.wait_for(ws.recv(), 30))
            if not res.get("success"):
                raise RuntimeError(f"claude:{sid}: {res.get('error')}")
            n += len(rows)
        return n


def cmd_push(quiet: bool) -> int:
    hours = hourly()
    stats = build_stats(hours)
    try:
        n = asyncio.run(_import(stats))
    except (OSError, RuntimeError, TimeoutError) as e:
        if not quiet:
            print(f"push fejlede: {e}", file=sys.stderr)
        return 1
    if not quiet:
        print(f"{n} time-rækker i {len(STATS)} statistikker (claude:*), {len(hours)} timer i alt")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("sessions", help="pris og kontekst pr. session")
    p.add_argument("--days", type=int, default=7)
    p = sp.add_parser("push", help="time-statistik til Home Assistant (claude:*)")
    p.add_argument("--quiet", action="store_true", help="intet output (hooks)")
    p = sp.add_parser("context", help="fast kontekst pr. kategori via /context")
    p.add_argument("--settings", help="ekstra settings-JSON (sammenlign en ændring før commit)")
    a = ap.parse_args(argv)
    if a.cmd == "sessions":
        return cmd_sessions(a.days)
    if a.cmd == "push":
        return cmd_push(a.quiet)
    return cmd_context(["--settings", a.settings] if a.settings else [])


if __name__ == "__main__":
    sys.exit(main())
