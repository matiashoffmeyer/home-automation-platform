#!/usr/bin/env python3
"""Vogter unikke backlog-ID'er (user-spec 2026-10-04: "sørg for at vi altid har
unikke id'er").

Indtil 2026-10-03 var ti ID'er brugt to gange med forskelligt indhold (B130,
B69, B97, B96, B42, B43, B44, B49, B132, B39), så et git-grep på ID'et ramte
det forkerte item. Arkivet (docs/backlog_archive.md) er ordret og beholder de
historiske dubletter — reglen gælder fremad:

  1. Intet ID står to gange i BACKLOG.md (`B160-rest` tæller som B160).
  2. Et NYT ID i BACKLOG.md (ikke i HEAD) må ikke findes i arkivet — et lukket
     ID genbruges aldrig. Genåbner du bevidst et arkiveret item:
     BACKLOG_ID_REUSE_OK=1 git commit ...
  3. Linjen "næste ledige ID: **Bnnn**" skal være større end alt brugt.

Brug:
  python3 scripts/backlog_ids.py            # tjek arbejdskopien
  python3 scripts/backlog_ids.py --staged   # tjek det staged (pre-commit-hook)
  python3 scripts/backlog_ids.py --next     # print næste ledige B-ID
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKLOG = "BACKLOG.md"
ARCHIVE = "docs/backlog_archive.md"
ID_RE = re.compile(r"^### (?:\S+\s+)?~*([A-Z]{1,2}\d+(?:\.\d+)?)(?:-[a-z]+)?\b", re.M)
NEXT_RE = re.compile(r"næste ledige ID: \*\*B(\d+)\*\*")


def _git_show(spec: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "show", spec],
            cwd=REPO,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8")
    except subprocess.CalledProcessError, FileNotFoundError:
        return None


def _read(rel: str, staged: bool) -> str:
    if staged:
        txt = _git_show(":" + rel)
        if txt is not None:
            return txt
    p = REPO / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _ids(text: str) -> list[str]:
    return ID_RE.findall(text)


def _max_b(*texts: str) -> int:
    nums = [int(m) for t in texts for m in re.findall(r"^### (?:\S+\s+)?~*B(\d+)", t, re.M)]
    return max(nums) if nums else 0


def main() -> int:
    staged = "--staged" in sys.argv
    backlog = _read(BACKLOG, staged)
    archive = _read(ARCHIVE, staged)
    nxt = _max_b(backlog, archive) + 1
    if "--next" in sys.argv:
        # Done-linjer (`- ✅ … **B213**`) har ingen ###-overskrift, og
        # "næste ledige"-linjen er den vedligeholdte sandhed — --next gav B213
        # 2026-10-11, selvom B213 og B215 allerede var brugt.
        done = [
            int(m)
            for t in (backlog, archive)
            for m in re.findall(r"^- ✅[^\n]*?\*\*B(\d+)\*\*", t, re.M)
        ]
        m = NEXT_RE.search(backlog)
        print(f"B{max([nxt, int(m.group(1)) if m else 0] + [d + 1 for d in done])}")
        return 0

    errors: list[str] = []
    live = _ids(backlog)
    seen: dict[str, int] = {}
    for i in live:
        seen[i] = seen.get(i, 0) + 1
    for i, n in seen.items():
        if n > 1:
            errors.append(f"{i} står {n} gange i {BACKLOG} — giv det ene næste ledige ID (B{nxt}).")

    head = _git_show("HEAD:" + BACKLOG)
    if head is not None and os.environ.get("BACKLOG_ID_REUSE_OK") != "1":
        new_ids = set(live) - set(_ids(head))
        archived = set(_ids(archive))
        for i in sorted(new_ids & archived):
            errors.append(
                f"{i} er nyt i {BACKLOG} men findes allerede i {ARCHIVE} — brug B{nxt}"
                " (genåbning: BACKLOG_ID_REUSE_OK=1)."
            )

    m = NEXT_RE.search(backlog)
    if m and int(m.group(1)) < nxt:
        errors.append(
            f"'næste ledige ID' i {BACKLOG} siger B{m.group(1)}, men B{nxt - 1} er brugt"
            f" — ret den til B{nxt}."
        )

    if errors:
        print("❌ Backlog-ID'er ikke unikke:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
