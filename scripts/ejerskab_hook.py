#!/usr/bin/env python3
"""Claude Code hook for lamp ownership (.claude/settings.json).

  pre   PreToolUse on Read/Edit/Write/MultiEdit: when the file writes a lamp
        that has an ownership registry, inject the lamp's contract
        (``docs/auto/ejerskab/<slug>.md``), once per session per lamp. Every
        other call costs 0 tokens.
  post  PostToolUse on Edit/Write/MultiEdit: run ``ejerskab.py lint`` on the
        edited file and tell the agent exactly what the registry is missing.

Always fails open (exit 0, no output). The pre-commit lint is the enforcement;
the hook only reports early. See docs/adr/0004-lamp-ownership-registry.md.
"""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPE = ("automations/", "packages/", "script_pkg/", "ejerskab/")


def emit(event, text):
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
            ensure_ascii=False,
        )
    )


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    data = json.load(sys.stdin)
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ""
    relp = os.path.relpath(path, ROOT).replace("\\", "/") if path else ""
    if (
        not relp.startswith(SCOPE)
        or not relp.endswith(".yaml")
        or relp.startswith("packages/ejerskab_")
    ):
        return
    with open(os.path.join(ROOT, "docs", "auto", "ejerskab", "index.json"), encoding="utf-8") as f:
        index = json.load(f)

    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    text += "\n" + str(ti.get("new_string") or "") + str(ti.get("content") or "")
    for e in ti.get("edits") or []:
        text += "\n" + str(e.get("new_string") or "")

    if mode == "pre":
        sid = str(data.get("session_id") or "ukendt")
        for ent, info in sorted(index.items()):
            if not any(m in text for m in info["match"]) and not relp == info["register"]:
                continue
            marker = os.path.join(tempfile.gettempdir(), "claude_ejerskab", f"{sid}_{ent}")
            if os.path.exists(marker):
                continue
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            open(marker, "w").close()
            with open(os.path.join(ROOT, info["kontrakt"]), encoding="utf-8") as f:
                kontrakt = f.read()
            emit(
                "PreToolUse",
                f"{relp} rører {ent}, som har et ejerskabs-register. "
                f"Kontrakten (vises én gang pr. session):\n\n{kontrakt}",
            )
            return
    elif mode == "post":
        lint_match = set()
        for info in index.values():
            lint_match |= set(info["match"]) | set(info.get("grupper") or [])
        if relp.startswith("ejerskab/") or any(m in text for m in lint_match):
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            import ejerskab

            errs = ejerskab.lint(None if relp.startswith("ejerskab/") else [relp])
            if errs:
                emit(
                    "PostToolUse",
                    "Ejerskabs-lint (pre-commit vil afvise dette):\n" + "\n".join(errs),
                )


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        main()
    except Exception:  # noqa: BLE001 — en hook må aldrig vælte en session
        pass
    sys.exit(0)
