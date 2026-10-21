#!/usr/bin/env python3
"""Path-scoped agent rules (``.claude/rules/*.md``): lint and Bash hook.

Domain facts live in ``.claude/rules/<domain>.md`` with ``paths:`` front
matter, and Claude Code loads a rule by itself when Read/Edit/Write touches a
matching file. This script closes two gaps:

  check  Lint (pre-commit). Every rule has ``paths:`` (a rule without them
         would load in every session, which is CLAUDE.md's job); every glob
         matches at least one tracked file (otherwise a renamed file silently
         orphans the rule); every rule is listed in CLAUDE.md's index table;
         and "Seneste sprints" holds at most ``MAX_SPRINT_NOTES`` notes.
         CLAUDE.md's size is only a warning.
  hook   PreToolUse (.claude/settings.json). Native loading only sees Read, so
         a session that reads or edits YAML through ``sed``, ``cat`` or
         ``grep <file>`` in Bash never gets the rule. The hook finds
         repository paths in Bash and Grep calls and injects the matching
         rules once per session. Read/Edit/Write calls are only marked as seen
         (native loading has already loaded the rule), so Bash does not inject
         it again. Always fails open: exit 0, no output.

See docs/methodology.md, section 3.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(ROOT, ".claude", "rules")
CLAUDE_MD_WARN_BYTES = 40_000
MAX_SPRINT_NOTES = 3


def glob_to_regex(g):
    """Claude Code-globs: `**` (også over /), `*`, `?`, `{a,b}`."""
    out, i = "", 0
    while i < len(g):
        c = g[i]
        if g.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if g.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c == "{":
            j = g.index("}", i)
            out += "(?:" + "|".join(re.escape(x) for x in g[i + 1 : j].split(",")) + ")"
            i = j
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


def parse_rule(path):
    """(paths, body) — frontmatter er en simpel YAML-liste under `paths:`."""
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", txt, re.S)
    if not m:
        return [], txt
    paths, inline = [], re.search(r"^paths:\s*\[(.*)\]\s*$", m.group(1), re.M)
    if inline:
        paths = [p.strip().strip("\"'") for p in inline.group(1).split(",") if p.strip()]
    else:
        in_paths = False
        for line in m.group(1).splitlines():
            if re.match(r"^paths:\s*$", line):
                in_paths = True
            elif in_paths and re.match(r"^\s+-\s+", line):
                paths.append(line.split("-", 1)[1].strip().strip("\"'"))
            elif in_paths and line.strip():
                in_paths = False
    return paths, m.group(2)


@lru_cache(maxsize=1)
def load_rules():
    rules = {}
    if not os.path.isdir(RULES_DIR):
        return rules
    for fn in sorted(os.listdir(RULES_DIR)):
        if fn.endswith(".md"):
            paths, body = parse_rule(os.path.join(RULES_DIR, fn))
            rules[fn[:-3]] = {"paths": paths, "rx": [glob_to_regex(p) for p in paths], "body": body}
    return rules


def rules_for(relpath):
    return [k for k, r in load_rules().items() if any(rx.match(relpath) for rx in r["rx"])]


# ---------------------------------------------------------------- check ----
@lru_cache(maxsize=1)
def tracked_files():
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8")
    return [f for f in out.splitlines() if f]


def check():
    errs, warns = [], []
    files = tracked_files()
    rules = load_rules()
    with open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8") as f:
        claude_md = f.read()
    for name, r in rules.items():
        if not r["paths"]:
            errs.append(
                f".claude/rules/{name}.md: ingen `paths:` — en uscopet regel loades i HVER session "
                f"(hører i CLAUDE.md, eller giv den paths)"
            )
        for g, rx in zip(r["paths"], r["rx"]):
            if not any(rx.match(f) for f in files):
                errs.append(
                    f".claude/rules/{name}.md: glob '{g}' rammer ingen trackede filer (omdøbt/slettet?)"
                )
        if f"`{name}.md`" not in claude_md:
            errs.append(f".claude/rules/{name}.md mangler i CLAUDE.md's index-tabel (Domæne-fakta)")
    for row in re.findall(r"^\| `([a-z0-9_]+)\.md` \|", claude_md, re.M):
        if row not in rules:
            errs.append(
                f"CLAUDE.md's index nævner `{row}.md`, men .claude/rules/{row}.md findes ikke"
            )
    # Sprint-noterne ruller: én ind = den ældste ud til docs/sprint_log.md i
    # SAMME commit. Stod før kun som tekst og voksede derfor i stilhed.
    m = re.search(r"^## 🕐 Seneste sprints.*?$(.*?)^(?:---|## )", claude_md, re.M | re.S)
    if m:
        n_sprints = len(re.findall(r"^- \*\*", m.group(1), re.M))
        if n_sprints > MAX_SPRINT_NOTES:
            errs.append(
                f"CLAUDE.md har {n_sprints} sprint-noter (max {MAX_SPRINT_NOTES}) — rul den ældste "
                f"ud til docs/sprint_log.md i samme commit"
            )
    else:
        errs.append("CLAUDE.md: sektionen '## 🕐 Seneste sprints' blev ikke fundet (omdøbt?)")
    size = len(claude_md.encode("utf-8"))
    if size > CLAUDE_MD_WARN_BYTES:
        warns.append(
            f"CLAUDE.md er {size} B (> {CLAUDE_MD_WARN_BYTES}) — den loades i HVER session; "
            f"flyt domæne-fakta til .claude/rules/"
        )
    for w in warns:
        print("⚠  " + w, file=sys.stderr)
    for e in errs:
        print("❌ " + e, file=sys.stderr)
    if not errs:
        n = sum(len(r["paths"]) for r in rules.values())
        print(f"✅ {len(rules)} regler, {n} globs, alle rammer filer; CLAUDE.md {size} B")
    return 1 if errs else 0


# ---------------------------------------------------------------- hook -----
_TOP = (
    "automations/",
    "packages/",
    "script_pkg/",
    "scripts/",
    "dashboards/",
    "www/",
    "addons/",
    "entities/",
    "rosters/",
    "ejerskab/",
    "docs/",
    "esphome/",
    "custom_components/",
)


# Kun kommandoer der LÆSER eller RETTER indholdet giver reglen — `git add`,
# `python3 scripts/x.py`, `cp`, `ls` og `ssh … < fil` rører en sti uden at
# nogen ser koden (ellers loader en commit-kommando alle berørte domæner).
_READERS = {
    "cat",
    "head",
    "tail",
    "sed",
    "awk",
    "gawk",
    "grep",
    "egrep",
    "fgrep",
    "rg",
    "less",
    "more",
    "nl",
    "diff",
    "tee",
    "vim",
    "vi",
    "nano",
    "perl",
    "jq",
    "yq",
    "bat",
    "cut",
}
_GIT_READERS = {"diff", "show", "blame", "log", "grep"}


def _segments(cmd):
    """Shell-kaldet delt i simple kommandoer (&&, ||, ;, |, linjeskift)."""
    for seg in re.split(r"&&|\|\||[;|\n]", cmd):
        try:
            toks = shlex.split(seg, posix=True)
        except ValueError:
            toks = seg.split()
        while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):  # VAR=x cmd
            toks = toks[1:]
        if toks:
            yield toks


SWEEP = 3  # rører et kald flere filer end dette, er det en SØGNING, ikke en læsning


def paths_in_command(cmd):
    """Repo-relative filstier som et læsende/rettende shell-kald rører.
    `grep x docs/*.md` (målt: 11 KB regler for én søgning) er en sweep →
    intet; kun et kald der rører ≤ SWEEP konkrete filer giver regler."""
    out = set()
    for seg in _segments(cmd):
        verb = os.path.basename(seg[0])
        if verb in _READERS or (verb == "git" and len(seg) > 1 and seg[1] in _GIT_READERS):
            hit = _files_in(seg[1:])
            if len(hit) <= SWEEP:
                out |= hit
    return out


def _files_in(toks):
    out = set()
    for t in toks:
        for part in re.split(r"[;&|<>()=,]", t):
            p = part.strip().strip("\"'")
            if not p:
                continue
            p = p.replace("\\", "/")
            m = re.match(r"^/([a-zA-Z])/", p)  # Git Bash: /c/Users/... = C:/Users/...
            if m:
                p = m.group(1).upper() + ":/" + p[3:]
            for pre in (ROOT.replace("\\", "/") + "/", "/config/", "./"):
                if p.lower().startswith(pre.lower()):
                    p = p[len(pre) :]
            if not p.startswith(_TOP):
                continue
            if any(c in p for c in "*?["):
                rx = glob_to_regex(p)
                try:
                    out.update(f for f in tracked_files() if rx.match(f))
                except OSError, subprocess.SubprocessError:
                    pass
            elif os.path.isfile(os.path.join(ROOT, p)):
                out.add(p)
    return out


def hook():
    data = json.load(sys.stdin)
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id") or "ukendt"))
    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        p = ti.get("file_path") or ti.get("notebook_path") or ""
        rel = os.path.relpath(p, ROOT).replace("\\", "/") if p else ""
        paths = {rel} if rel and not rel.startswith("..") else set()
        # Native loading følger Read (og Edit kræver Read). En NY fil via Write
        # er aldrig læst → den får reglen herfra.
        native = not (tool == "Write" and p and not os.path.exists(p))
    elif tool == "Bash":
        native, paths = False, paths_in_command(str(ti.get("command") or ""))
    elif tool == "Grep":
        p = str(ti.get("path") or "")
        rel = (
            os.path.relpath(p, ROOT).replace("\\", "/")
            if p and os.path.isabs(p)
            else p.replace("\\", "/")
        )
        native = False
        paths = {rel} if rel and os.path.isfile(os.path.join(ROOT, rel)) else set()
    else:
        return
    hit = sorted({r for p in paths for r in rules_for(p)})
    if not hit:
        return
    mdir = os.path.join(tempfile.gettempdir(), "claude_rules")
    os.makedirs(mdir, exist_ok=True)
    new = []
    for r in hit:
        marker = os.path.join(mdir, f"{sid}_{r}")
        if os.path.exists(marker):
            continue
        open(marker, "w").close()
        new.append(r)
    if native or not new:
        return  # Read/Edit/Write: Claude Code har selv loadet reglen
    rules = load_rules()
    text = "\n\n".join(
        f"Contents of .claude/rules/{r}.md (path-scopet regel; dette Bash/Grep-kald rører "
        f"en fil den dækker — vises én gang pr. session):\n\n{rules[r]['body'].strip()}"
        for r in new
    )
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "hook":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            hook()
        except Exception:  # noqa: BLE001 — en hook må aldrig vælte en session
            pass
        sys.exit(0)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError, ValueError:
        pass
    sys.exit(check())
