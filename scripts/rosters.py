#!/usr/bin/env python3
"""One shared understanding of ``rosters/`` for every repository tool.

An entity list that used to be copied verbatim into many files now lives in
one place, ``rosters/<name>.yaml`` (a plain YAML list), and its consumers write
``entity_id: !include ../rosters/<name>.yaml``. Home Assistant resolves
``!include`` itself. The repository's own scanners did not: their loaders
turned any ``!tag`` into ``None`` or into the path string, so a lamp in a
roster would silently disappear from triggers_scan, the ownership lint and the
room dossiers. Every tool therefore goes through this module:

  yaml_tag(loader, suffix, node)  the list for a roster ``!include``, otherwise None
                                  (for yaml.add_multi_constructor handlers)
  text_refs(text)                 [(line, entity)] for every roster ``!include``
                                  and every ``{% from 'rosters.jinja' import x %}``
                                  in a file (for regex-based scanners)

A list inside a template cannot be ``!include``-d. ``python3 scripts/rosters.py
jinja`` generates ``custom_templates/rosters.jinja`` (one ``{% set <name> = [...] %}``
per roster), and a template writes::

  {% from 'rosters.jinja' import <name> %}{{ <name> | select(...) }}

Home Assistant loads ``custom_templates`` before the integrations, and
``homeassistant.reload_custom_templates`` reloads them without a restart.
Pre-commit runs ``rosters.py jinja --check``: edit the roster, regenerate and
commit both.

To find a roster's consumers: ``grep -rn "rosters/<name>" .``
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROSTER_DIR = REPO / "rosters"
INCLUDE_RE = re.compile(r"!include\s+['\"]?(?:\.\./)*rosters/([a-z0-9_]+)\.yaml")
JINJA_FILE = REPO / "custom_templates" / "rosters.jinja"
JINJA_IMPORT_RE = re.compile(
    r"from\s+['\"]rosters\.jinja['\"]\s+import\s+([a-z0-9_]+(?:\s*,\s*[a-z0-9_]+)*)"
)
_ITEM_RE = re.compile(r"^- ([a-z_]+\.[a-z0-9_]+)\s*(?:#.*)?$")


@cache
def load(name: str) -> tuple[str, ...]:
    """Rosterens entities i fil-rækkefølge. Flad parser (ingen PyYAML-krav)."""
    out = []
    for line in (ROSTER_DIR / f"{name}.yaml").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _ITEM_RE.match(line)
        if not m:
            raise ValueError(
                f"rosters/{name}.yaml: kun '- domæne.entity'-linjer er tilladt, fik {line[:60]!r}"
            )
        out.append(m.group(1))
    return tuple(out)


def yaml_tag(loader, suffix, node):
    """Til en `!`-multi-constructor: en roster-!include bliver til sin liste."""
    if suffix != "include" or not hasattr(node, "value") or not isinstance(node.value, str):
        return None
    m = INCLUDE_RE.search(f"!include {node.value}")
    return list(load(m.group(1))) if m else None


def text_refs(text: str) -> list[tuple[int, str]]:
    """(linjenummer, entity) for hver roster-!include og rosters.jinja-import i en tekst."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        m = INCLUDE_RE.search(line.split(" #", 1)[0])
        if m:
            out += [(n, e) for e in load(m.group(1))]
        for m in JINJA_IMPORT_RE.finditer(line):
            for name in re.split(r"\s*,\s*", m.group(1)):
                out += [(n, e) for e in load(name)]
    return out


def jinja_text() -> str:
    """custom_templates/rosters.jinja, afledt af rosters/*.yaml."""
    out = [
        "{# GENERERET af scripts/rosters.py jinja fra rosters/*.yaml — ret rosteren,",
        "   ikke denne fil. Brug: {% from 'rosters.jinja' import <navn> %} #}",
    ]
    for p in sorted(ROSTER_DIR.glob("*.yaml")):
        items = ", ".join(f"'{e}'" for e in load(p.stem))
        out.append(f"{{%- set {p.stem} = [{items}] %}}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    import subprocess
    import sys

    if sys.argv[1:2] == ["jinja"]:
        want = jinja_text()
        have = JINJA_FILE.read_text(encoding="utf-8") if JINJA_FILE.exists() else ""
        if "--check" in sys.argv:
            if have != want:
                print(
                    "❌ custom_templates/rosters.jinja passer ikke til rosters/ — "
                    "kør: python3 scripts/rosters.py jinja",
                    file=sys.stderr,
                )
                sys.exit(1)
            sys.exit(0)
        if have != want:
            JINJA_FILE.parent.mkdir(exist_ok=True)
            JINJA_FILE.write_text(want, encoding="utf-8")
            print(f"skrev {JINJA_FILE.relative_to(REPO)}")
        sys.exit(0)
    for p in sorted(ROSTER_DIR.glob("*.yaml")):
        users = subprocess.run(
            [
                "git",
                "-C",
                str(REPO),
                "grep",
                "-lE",
                f"rosters/{p.stem}\\.yaml|import .*\\b{p.stem}\\b",
            ],
            capture_output=True,
            text=True,
        ).stdout.split()
        print(f"{p.stem}: {len(load(p.stem))} entities, {len(users)} filer — {', '.join(users)}")
    sys.exit(0)
