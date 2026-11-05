#!/usr/bin/env python3
"""PreToolUse hook: no software installs without the user's yes to the source.

An installed MCP server, plugin or package runs code with the agent's rights,
which here means root in the SSH add-on with a supervisor token. CLAUDE.md
already said "installs need the user's yes to the exact source", but that was
text only (B298, user choice c on 2026-11-05). The call is now rejected with
exit 2, and the reason on stderr is shown to the agent.

Blocked: ``claude mcp add``, ``claude plugin install``/``marketplace add``,
``npx``/``bunx``/``pnpm dlx``/``uvx``, ``pip install <pkg>`` (also
``python -m pip``, ``uv pip``, ``uv add``, ``uv tool``, ``pipx``),
``npm install -g``, ``ha addons install`` of a store add-on, adding a
supervisor store repository, and piping a download into a shell (``curl … | sh``,
``bash <(curl …)``).

Allowed: ``bash scripts/dev_setup.sh`` (pinned tools from git),
``pip install -r <file>`` and ``npm install``/``npm ci`` (the pins are in the
repository), ``npx --no`` (only what is already installed), and the house's own
``local_*`` add-ons (built from git). The user runs
anything else themselves with ``! <command>``, which does not pass this hook.
Fails open (exit 0) on any error. See docs/adr/0006-agent-guardrails-as-hooks.md.
"""

import json
import re
import shlex
import sys

# Commands that only MENTION an install (grep in docs, git log -S, commit text).
READ_ONLY = {"grep", "rg", "git", "sed", "awk", "cat", "head", "tail", "less", "echo", "printf"}
WRAPPERS = {"sudo", "env", "exec", "time", "nice", "nohup", "command"}
SHELLS = {"sh", "bash", "zsh", "dash", "ash", "python", "python3", "perl", "node"}
FETCH = {"curl", "wget"}
# `bash <(curl …)`, `sh -c "$(curl …)"`: the download IS the program, not an argument.
FETCH_AS_PROGRAM = re.compile(
    r"(?:^|\s|/)(?:" + "|".join(sorted(SHELLS)) + r")\s+(?:-[a-z]*\s+)*"
    r"(?:<\(|-[a-z]*c\s+[\"']?\$\()\s*(?:curl|wget)\b"
)


def words(seg):
    try:
        toks = shlex.split(seg, posix=True)
    except ValueError:
        toks = seg.split()
    while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or toks[0] in WRAPPERS):
        toks = toks[1:]
    if toks:
        toks[0] = toks[0].rsplit("/", 1)[-1]
    return toks


def runs_stdin(toks):
    """An interpreter fed by a pipe runs it as code unless given -c or a script file."""
    if not toks or toks[0] not in SHELLS:
        return False
    for a in toks[1:]:
        if a == "--":
            return True
        if a == "-c" or (a.startswith("-") and "c" in a[1:] and not a.startswith("--")):
            return False
        if a != "-" and not a.startswith("-"):
            return False
    return True


def pip_install(args):
    """True for ``install <pkg>``; False for ``install -r <file>`` only."""
    if not args or args[0] != "install":
        return False
    rest = args[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("-r", "--requirement", "-c", "--constraint", "--python", "--target", "-t"):
            i += 2
            continue
        if not a.startswith("-"):
            return True
        i += 1
    return False


def install(toks):
    if not toks:
        return None
    cmd, args = toks[0], toks[1:]
    if cmd in READ_ONLY:
        return None
    if cmd == "claude" and args[:2] in (
        ["mcp", "add"],
        ["mcp", "add-json"],
        ["mcp", "add-from-claude-desktop"],
    ):
        return "MCP-server"
    if cmd == "claude" and args[:1] == ["plugin"] and ("install" in args or "add" in args):
        return "Claude-plugin"
    if cmd == "npm" and args[:1] == ["exec"]:
        cmd, args = "npx", args[1:]
    offline = {"--no", "--no-install", "--offline"} & set(args)
    if (
        cmd == "npx"
        and not offline
        or cmd in ("bunx", "uvx")
        or (cmd == "pnpm" and args[:1] == ["dlx"])
    ):
        return f"{cmd} (henter og kører en pakke)"
    if cmd in ("npm", "pnpm", "yarn", "bun") and args[:1] in (
        ["install"],
        ["i"],
        ["add"],
        ["global"],
    ):
        if cmd == "yarn" and args[:1] == ["global"] or {"-g", "--global"} & set(args):
            return f"{cmd} global install"
    if re.fullmatch(r"pip3?(\.\d+)?", cmd) and pip_install(args):
        return "pip install"
    if (
        re.fullmatch(r"python3?(\.\d+)?", cmd)
        and args[:2] == ["-m", "pip"]
        and pip_install(args[2:])
    ):
        return "pip install"
    if cmd == "uv" and args[:1] == ["pip"] and pip_install(args[1:]):
        return "uv pip install"
    if cmd == "uv" and (
        args[:1] == ["add"] or args[:2] == ["tool", "install"] or args[:2] == ["tool", "run"]
    ):
        return "uv add/tool"
    if cmd == "pipx" and args[:1] in (["install"], ["run"], ["inject"]):
        return "pipx"
    if (
        cmd == "ha"
        and args[:1] in (["addons"], ["apps"])
        and args[1:2] == ["install"]
        and not any(a.startswith("local_") for a in args[2:])
    ):
        return "add-on-install"
    if cmd == "ha" and args[:2] in (["store", "add"], ["store", "repositories"]):
        return "add-on-repo"
    return None


def dangerous(cmd):
    if "dev_setup.sh" in cmd:
        return None
    store = re.search(r"/store/(repositories|addons/(?!local_)[^/\s]+/install)\b", cmd)
    if (
        store
        and re.search(r"-X\s*POST|--data|\s-d\s", cmd)
        and not re.match(r"\s*(" + "|".join(READ_ONLY) + r")\b", cmd)
    ):
        return "add-on-install via supervisor-API'et"
    for chain in re.split(r"&&|\|\||[;\n]", cmd):
        if words(chain)[:1] and words(chain)[0] not in READ_ONLY and FETCH_AS_PROGRAM.search(chain):
            return "download kørt direkte i en shell"
    for chain in re.split(r"&&|\|\||[;\n]", cmd):
        stages = [words(s) for s in re.split(r"(?<!\|)\|(?!\|)", chain)]
        for i, toks in enumerate(stages):
            what = install(toks)
            if what:
                return what
            if toks and toks[0] in FETCH and any(runs_stdin(t) for t in stages[i + 1 :]):
                return "download kørt direkte i en shell"
    return None


if __name__ == "__main__":
    try:
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
        what = dangerous(cmd) if isinstance(cmd, str) else None
    except Exception:
        sys.exit(0)
    if what:
        print(
            f"Blokeret af scripts/install_guard.py ({what}): installationer kræver users ja "
            "til den præcise kilde (CLAUDE.md 🔐, B298). Gennemgå kilden først (udgiver, "
            "look-alike-navn, install-scripts, netværkskald, skjulte instruktioner), lås "
            "versionen, og bed user køre kommandoen selv med `! <kommando>`. Udviklings-"
            "værktøjer: `bash scripts/dev_setup.sh` (pins fra git); node-værktøjer som "
            "devDependency med lockfile + `npm ci`, derefter `npx --no <bin>`.",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(0)
