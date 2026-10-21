#!/usr/bin/env python3
"""Generate the discoverability documents in docs/auto/ from the codebase.

  1. docs/auto/rooms/<room>.md
     Per room: every entity, automation, scene, helper and script that
     affects the room. For debugging and onboarding.
  2. docs/auto/dependency_map.md
     Overview of which automations depend on which template sensors,
     input_booleans and cross-cutting helpers.

There is no entity catalogue any more: "where is X used?" is answered by
``python3 scripts/hq.py where X``, which runs ``scan_codebase()`` from this
module live against the working tree in under a second.

Usage::

  python3 scripts/gen_docs.py            both outputs
  python3 scripts/gen_docs.py --rooms    room dossiers only
  python3 scripts/gen_docs.py --map      dependency map only

Output goes to docs/auto/. Do not edit it by hand; regenerate it.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rosters  # noqa: E402  roster-!include → forbrugerens referencer

# Windows console fix: force UTF-8 stdout så Unicode-emojis (✅) ikke crasher
# med UnicodeEncodeError på cp1252. No-op på Linux.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------- Setup ----------


def _find_repo_root():
    env_root = os.environ.get("HA_REPO")
    if env_root:
        return Path(env_root).resolve()
    try:
        out = (
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=Path(__file__).resolve().parent,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        if out:
            return Path(out)
    except Exception:
        pass
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "CLAUDE.md").exists() or (p / ".HA_REPO").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent


REPO = _find_repo_root()
OUT = REPO / "docs" / "auto"

# Entity-domæner. notify/tts/conversation er bevidst UDE: i huset er de næsten
# kun service-kald (`notify.mobile_app_phone_a`), og de ville drukne scannet.
ENTITY_DOMAINS = {
    "alarm_control_panel",
    "automation",
    "binary_sensor",
    "button",
    "calendar",
    "camera",
    "climate",
    "counter",
    "cover",
    "date",
    "datetime",
    "device_tracker",
    "event",
    "fan",
    "group",
    "humidifier",
    "image",
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
    "lawn_mower",
    "light",
    "lock",
    "media_player",
    "number",
    "person",
    "remote",
    "scene",
    "script",
    "select",
    "sensor",
    "siren",
    "sun",
    "switch",
    "text",
    "time",
    "timer",
    "todo",
    "update",
    "vacuum",
    "valve",
    "water_heater",
    "weather",
    "zone",
}

SERVICE_PATTERNS = {
    ".turn_on",
    ".turn_off",
    ".toggle",
    ".reload",
    ".select_option",
    ".select_next",
    ".select_previous",
    ".select_first",
    ".select_last",
    ".set_value",
    ".increment",
    ".decrement",
    ".set_datetime",
    ".open_cover",
    ".close_cover",
    ".stop_cover",
    ".set_cover_position",
    ".set_temperature",
    ".set_hvac_mode",
    ".set_fan_mode",
    ".play_media",
    ".media_play",
    ".media_pause",
    ".volume_set",
    ".persistent_notification",
    ".trigger",
    ".press",
    ".open",
    ".close",
    ".send_command",
    ".create",
    ".delete",
    ".apply",
    ".start",
    ".stop",
    ".pause",
    ".cancel",
    ".finish",
    ".reset",
    ".lock",
    ".unlock",
    ".locate",
    ".return_to_base",
    ".add_item",
    ".get_items",
    ".remove_item",
    ".update_item",
    ".get_events",
    ".snapshot",
    ".install",
    ".skip",
    ".set_options",
    ".change",
    ".started",
    ".finished",
    ".cancelled",
    ".restarted",
    ".paused",  # event-typer
}
# `action: light.turn_on` / `service: vacuum.start` er service-kald, ikke
# entities — undtagen scripts, hvor `action: script.x` ER en reference til x.
_SERVICE_LINE = re.compile(r"^\s*-?\s*(?:action|service):\s*['\"]?([a-z_]+)\.[a-z0-9_]+['\"]?\s*$")
# En ref der fortsætter i en template er et PRÆFIKS (`input_number.koekken_g{{ n }}_move`,
# `'sensor.stue_' ~ rum`), ikke en entity — `hq.py where` viser dem som dynamiske.
_DYNAMIC_TAIL = re.compile(r"^(?:\{\{|\{%|['\"]?\s*~)")

ROOMS = {
    "stue": ["stue", "open_plan"],
    "koekken": ["koekken", "kokken"],
    "spisestue": ["spisestue"],
    "sovevaerelse": ["sovevaerelse", "sove"],
    "boernevaerelse": ["boernevaerelse", "bornevaerelse", "boern"],
    "badevaerelse": ["badevaerelse", "bad"],
    "entre": ["entre"],
    "depot": ["depot"],
    "terrasse": ["terrasse"],
    "hoveddor": ["hoveddoer", "parasoll_hoveddoer"],
    "altandor": ["altandoer", "parasoll_altandoer"],
}

# ---------- Scanning ----------


def find_yaml_files():
    out = []
    for p in REPO.rglob("*.yaml"):
        # Relativ sti: en git-worktree ligger under .claude/worktrees/, og et
        # filter på den absolutte sti droppede derfor HVER fil (2026-10-04).
        rel = p.relative_to(REPO).parts
        if any(part.startswith(".") for part in rel):
            continue
        if "node_modules" in rel or "auto" in rel:
            continue
        out.append(p)
    return sorted(out)


def extract_entity_refs(text):
    """Returns list of (line_no, entity_id) tuples from YAML text."""
    domains_re = "|".join(ENTITY_DOMAINS)
    # Lookbehind: `trigger.event.data` er ikke entity'en event.data, men
    # `states.sensor.x` ER en reference til sensor.x.
    pattern = re.compile(rf"(?:(?<=states\.)|(?<![\w.]))({domains_re})\.([a-z_0-9]+)\b")
    out = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if "#" in line:
            line = line[: line.index("#")]
        svc = _SERVICE_LINE.match(line)
        if svc and svc.group(1) != "script":
            continue
        for match in pattern.finditer(line):
            domain, name = match.group(1), match.group(2)
            ref = f"{domain}.{name}"
            # Filter service-name patterns
            if any(ref.endswith(svc) for svc in SERVICE_PATTERNS):
                continue
            if ref.endswith("_") or ref.endswith(".all"):
                continue
            if _DYNAMIC_TAIL.match(line[match.end() :]):
                continue
            out.append((line_no, ref))
    return out


def extract_automation_meta(text, file_path):
    """Returns list of dicts: {id, alias, description, line_no, mode}."""
    out = []
    # Match: - id: foo \n  alias: ... \n  ...
    for m in re.finditer(r"^- id:\s*([a-z_][a-z_0-9]*)\s*\n((?:  [^\n]*\n)+)", text, re.MULTILINE):
        line_no = text[: m.start()].count("\n") + 1
        body = m.group(2)
        alias_m = re.search(r"^\s*alias:\s*[\"']?([^\"\n]+)", body, re.MULTILINE)
        mode_m = re.search(r"^\s*mode:\s*([a-z_]+)", body, re.MULTILINE)
        desc_m = re.search(r"^\s*description:\s*>?-?\s*\n\s*([^\n]+)", body, re.MULTILINE)
        out.append(
            {
                "id": m.group(1),
                "alias": alias_m.group(1).strip() if alias_m else "",
                "mode": mode_m.group(1).strip() if mode_m else "single",
                "description": desc_m.group(1).strip()[:120] if desc_m else "",
                "line_no": line_no,
            }
        )
    return out


def extract_helpers(text):
    """Returns dict {domain: [names]} for input_*, timer, etc."""
    helpers = defaultdict(list)
    for m in re.finditer(
        r"^(input_boolean|input_select|input_number|input_datetime|input_text|input_button|timer):\s*\n((?:  [^\n]*\n)+)",
        text,
        re.MULTILINE,
    ):
        domain = m.group(1)
        for nm in re.finditer(r"^  ([a-z_][a-z_0-9]*):\s*$", m.group(2), re.MULTILINE):
            helpers[domain].append(nm.group(1))
    return helpers


def scan_codebase():
    """One-pass scan. Returns dict with: refs (entity → [(file, line)]),
    automations (file → [{id,alias,...}]), helpers (domain → [names])."""
    refs = defaultdict(list)
    automations = defaultdict(list)
    helpers = defaultdict(list)

    for f in find_yaml_files():
        text = f.read_text(encoding="utf-8", errors="ignore")
        rel = f.relative_to(REPO).as_posix()  # / også på Windows (docs/auto er delt)
        for line_no, ref in extract_entity_refs(text):
            refs[ref].append((rel, line_no))
        # `entity_id: !include ../rosters/x.yaml` (konsolidering P2): forbrugeren
        # refererer rosterens entities, ikke kun selve rosters/-filen.
        for line_no, ref in rosters.text_refs(text):
            refs[ref].append((rel, line_no))
        for auto in extract_automation_meta(text, rel):
            auto["file"] = rel
            automations[rel].append(auto)
        for domain, names in extract_helpers(text).items():
            for n in names:
                helpers[domain].append((n, rel))
    return {"refs": refs, "automations": automations, "helpers": helpers}


# ---------- Generators ----------


def gen_room_dossier(room, keywords, scan):
    """Generate docs/auto/rooms/<room>.md."""
    # Find entities matching room keywords
    room_refs = {
        ref: locs for ref, locs in scan["refs"].items() if any(kw in ref for kw in keywords)
    }
    # Find automations from per-room files OR with room keyword in id/alias
    room_autos = []
    for file, autos in scan["automations"].items():
        for auto in autos:
            in_filename = any(kw in file.lower() for kw in keywords)
            in_id = any(kw in auto["id"] for kw in keywords)
            in_alias = any(kw in auto["alias"].lower() for kw in keywords)
            if in_filename or in_id or in_alias:
                room_autos.append(auto)
    # Find helpers
    room_helpers = {}
    for domain, names in scan["helpers"].items():
        room_helpers[domain] = [n for n in names if any(kw in n[0] for kw in keywords)]

    lines = [
        f"# Rum-dossier: {room}",
        "",
        "Auto-generated. **DON'T edit manually** — re-run `./scripts/gen_docs.py --rooms`.",
        "",
        f"Search keywords: `{', '.join(keywords)}`",
        "",
        "## Indhold",
        f"- [Automations]({room}.md#automations) ({len(room_autos)})",
        f"- [Entities]({room}.md#entities) ({len(room_refs)})",
        f"- [Helpers]({room}.md#helpers) ({sum(len(v) for v in room_helpers.values())})",
        "",
        "---",
        "",
        "## Automations",
        "",
    ]
    if room_autos:
        # Group by file
        by_file = defaultdict(list)
        for a in room_autos:
            by_file[a["file"]].append(a)
        for file in sorted(by_file):
            lines.append(f"### `{file}`")
            lines.append("")
            for a in by_file[file]:
                lines.append(
                    f"- **{a['alias'] or a['id']}** (line {a['line_no']}, mode={a['mode']})"
                )
                if a["description"]:
                    lines.append(f"  - {a['description']}")
            lines.append("")
    else:
        lines.append("_No automations found referencing this room._")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Entities",
            "",
        ]
    )
    if room_refs:
        by_domain = defaultdict(list)
        for ref in room_refs:
            by_domain[ref.split(".")[0]].append(ref)
        for domain in sorted(by_domain):
            lines.append(f"### `{domain}.*`")
            lines.append("")
            for ref in sorted(by_domain[domain]):
                n = len(room_refs[ref])
                files = sorted(set(l[0] for l in room_refs[ref]))
                lines.append(f"- `{ref}` — {n} refs in {len(files)} file(s)")
            lines.append("")
    else:
        lines.append("_No entities found for this room._")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Helpers",
            "",
        ]
    )
    any_helpers = False
    for domain, items in sorted(room_helpers.items()):
        if not items:
            continue
        any_helpers = True
        lines.append(f"### `{domain}.*`")
        lines.append("")
        for name, file in sorted(items):
            lines.append(f"- `{domain}.{name}` (defined in `{file}`)")
        lines.append("")
    if not any_helpers:
        lines.append("_No helpers found for this room._")
        lines.append("")

    return "\n".join(lines)


def gen_dependency_map(scan):
    """Generate docs/auto/dependency_map.md — high-level cross-cutting deps."""
    # High-traffic entities (refed in >5 files)
    hot = [(ref, len(set(l[0] for l in locs))) for ref, locs in scan["refs"].items()]
    hot.sort(key=lambda x: -x[1])
    top = hot[:25]

    # State machine entities
    state_machine = [
        ("input_select.house_state", "Top-level state: Active vs Dormant"),
        ("input_select.house_mode", "Top-level mode: Normal vs AirBnB"),
        ("input_boolean.godnat_active", "Godnat night mode"),
        ("input_boolean.godnat_pending", "Godnat in progress"),
        ("input_boolean.cinema_active", "Cinema mode (mood)"),
        ("input_boolean.cirkus_active", "Cirkus mode (terrasse party)"),
        ("input_boolean.guest_mode", "Auto-detected guest activity"),
        ("input_boolean.bedroom_only_winddown", "Soft winddown for bedroom-only"),
        ("input_boolean.kalde_active", "Kids' kalde-button active"),
        ("input_boolean.airbnb_mode", "AirBnB shortcut (rare)"),
        ("sensor.activity_state", "Computed activity classifier"),
        ("sensor.people_estimate", "Computed people count estimate"),
        (
            "binary_sensor.presence_sensors_available",
            "Master gate for all presence-driven automations",
        ),
        ("binary_sensor.terrasse_active", "Terrasse activity (Sherlock-deduktion)"),
        ("sensor.open_plan_lux", "Lux fallback chain (spisestue→sove→stue)"),
        ("sensor.auto_color_temp_evening", "Sun-elevation-based CT for all rooms"),
    ]

    lines = [
        "# Dependency Map (auto-generated)",
        "",
        "Generated by `scripts/gen_docs.py`. **DON'T edit manually** — re-run script.",
        "",
        "## High-traffic entities (refed in 5+ files)",
        "",
        "Alle fil:linjer for én entity: `python3 scripts/hq.py where <entity>`.",
        "",
        "| Entity | Files | Refs |",
        "|---|---|---|",
    ]
    for ref, n in top:
        if n < 5:
            continue
        lines.append(f"| `{ref}` | {n} | {len(scan['refs'][ref])} |")
    lines.append("")

    lines.extend(
        [
            "## State machine entities (kritiske)",
            "",
            "| Entity | Purpose | Files |",
            "|---|---|---|",
        ]
    )
    for ref, purpose in state_machine:
        n = len(set(l[0] for l in scan["refs"].get(ref, [])))
        lines.append(f"| `{ref}` | {purpose} | {n} |")
    lines.append("")

    lines.extend(
        [
            "## Cross-cutting templates",
            "",
            "Disse er centrale abstractions defineret i `packages/`. Ændringer i template",
            "ripper på tværs af alle filer der bruger dem.",
            "",
            "- **`sensor.open_plan_lux`** (`packages/activity_state.yaml`) — fallback chain spisestue→sove→stue",
            "- **`sensor.auto_color_temp_evening`** (`packages/activity_state.yaml`) — sun-elev-based Kelvin",
            "- **`sensor.activity_state`** (`packages/activity_state.yaml`) — multi-room activity classifier",
            "- **`binary_sensor.presence_sensors_available`** — master gate (alle presence-automations)",
            "- **`binary_sensor.open_plan_empty_for_20m`** — used by stue/koekken off automations",
            "",
        ]
    )

    return "\n".join(lines)


def gen_room_index(rooms_done):
    """Generate docs/auto/rooms/README.md."""
    lines = [
        "# Per-room dossiers (auto-generated)",
        "",
        "Hver rum har en file med alle automations + entities + helpers der affekter rummet.",
        "",
    ]
    for r in sorted(rooms_done):
        lines.append(f"- [{r}]({r}.md)")
    return "\n".join(lines)


# ---------- Main ----------


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rooms", action="store_true", help="kun room dossiers")
    parser.add_argument("--map", action="store_true", help="kun dependency map")
    args = parser.parse_args()
    do_all = not (args.rooms or args.map)

    print(f"Scanning {REPO}...")
    scan = scan_codebase()
    print(f"  {len(scan['refs'])} unique entity references")
    print(
        f"  {sum(len(v) for v in scan['automations'].values())} automations across {len(scan['automations'])} files"
    )
    print(f"  {sum(len(v) for v in scan['helpers'].values())} helpers")

    OUT.mkdir(parents=True, exist_ok=True)

    if do_all or args.rooms:
        print("Generating per-room dossiers...")
        rooms_dir = OUT / "rooms"
        rooms_dir.mkdir(exist_ok=True)
        for room, keywords in ROOMS.items():
            (rooms_dir / f"{room}.md").write_text(
                gen_room_dossier(room, keywords, scan), encoding="utf-8"
            )
        (rooms_dir / "README.md").write_text(gen_room_index(list(ROOMS)), encoding="utf-8")

    if do_all or args.map:
        print("Generating dependency_map.md...")
        (OUT / "dependency_map.md").write_text(gen_dependency_map(scan), encoding="utf-8")

    print(f"✅ Done. Output: {OUT}")


if __name__ == "__main__":
    main()
