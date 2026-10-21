#!/usr/bin/env python3
"""Repository-level YAML checks that catch known pitfalls before they reach production.

Complements ``ha_offline.py check``, which runs Home Assistant's own validator.
These checks cover what that validator does not see, each one a category of
defect that reached the live house at least once:

  refs             entity references that do not exist (a placeholder left in,
                   hardware not yet paired, a renamed entity); needs the live
                   entity list (``--live``) or the cached snapshot
  dups             duplicate automation ids (the second one silently wins)
  hazards          numeric values that overlap as text: a bulk replace of
                   ``transition: 60`` also rewrites ``transition: 600``
  placeholders     ``PLACEHOLDER`` markers that have been left too long
  jinja            template syntax errors that would otherwise only fail at runtime
  matter           Matter light calls without ``continue_on_error: true``
                   (registry and light groups; static targets only); a CHIP
                   timeout would otherwise abort the whole script. Blocks in
                   pre-commit.
  unused           helpers that are defined but never referenced
  stale_whitelist  whitelist entries that now exist and can be removed
  scene_drift      the scene list, which is kept in several places, has diverged

Usage::

  python3 scripts/ha_validate.py                    all checks
  python3 scripts/ha_validate.py --files f1 f2      only these files
  python3 scripts/ha_validate.py --check matter     one check
  python3 scripts/ha_validate.py --quiet            errors only

Exit codes: 0 clean, 1 errors, 2 warnings only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# Windows console fix: force UTF-8 stdout/stderr så Unicode-emojis (✅❌) ikke
# crasher med UnicodeEncodeError på cp1252. No-op på Linux.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _find_repo_root():
    """Find repo root: env var > git > marker file > script's parent."""
    env_root = os.environ.get("HA_REPO")
    if env_root:
        return Path(env_root).resolve()
    try:
        # Uden hookens GIT_*-variabler: i en pre-commit-hook er GIT_DIR sat, og
        # så svarer `--show-toplevel` med cwd (= scripts/) i stedet for roden —
        # set i en git-worktree 2026-10-04 (relative_to(REPO) crashede).
        out = (
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=Path(__file__).resolve().parent,
                stderr=subprocess.DEVNULL,
                env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            )
            .decode()
            .strip()
        )
        if out:
            return Path(out)
    except subprocess.CalledProcessError, FileNotFoundError:
        pass
    # Marker: look for CLAUDE.md or .HA_REPO file
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "CLAUDE.md").exists() or (p / ".HA_REPO").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent


REPO = _find_repo_root()
ENV_FILE = REPO / ".env"

# Entity domains we track (HA's standard set)
ENTITY_DOMAINS = {
    "automation",
    "binary_sensor",
    "button",
    "camera",
    "climate",
    "cover",
    "device_tracker",
    "fan",
    "group",
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
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
    "switch",
    "timer",
    "update",
    "weather",
    "zone",
}

# Entities we expect to ALWAYS exist (HA built-ins)
BUILTIN_ENTITIES = {
    "sun.sun",
    "weather.home",
    "person.parent_a",
    "person.parent_b",
    "zone.home",
    "zone.work",
}

# Service names that match entity_id pattern but are SERVICES not entities.
# Filter these to avoid false positives in entity ref check.
SERVICE_PATTERNS = {
    # Light, switch, fan, cover, input_boolean services
    ".turn_on",
    ".turn_off",
    ".toggle",
    ".reload",
    # input_select services
    ".select_option",
    ".select_next",
    ".select_previous",
    ".select_first",
    ".select_last",
    # input_number and input_text services
    ".set_value",
    ".increment",
    ".decrement",
    # input_datetime
    ".set_datetime",
    # cover
    ".open_cover",
    ".close_cover",
    ".stop_cover",
    ".set_cover_position",
    # climate
    ".set_temperature",
    ".set_hvac_mode",
    ".set_fan_mode",
    # media_player
    ".play_media",
    ".media_play",
    ".media_pause",
    ".volume_set",
    # notify
    ".persistent_notification",
    # script — script.X is both entity and service. Default treat as entity.
    # automation
    ".trigger",
}


# Known-missing entities (hardware ikke paret endnu pre-flyt). Optional whitelist
# fra scripts/ha_validate_whitelist.txt (én entity_id per linje).
def load_whitelist():
    wl_file = REPO / "scripts" / "ha_validate_whitelist.txt"
    if not wl_file.exists():
        # Fallback: search common HA paths
        for p in [
            Path("/config/scripts/ha_validate_whitelist.txt"),
            Path("/homeassistant/scripts/ha_validate_whitelist.txt"),
        ]:
            if p.exists():
                wl_file = p
                break
        else:
            return set()
    out = set()
    for line in wl_file.read_text().splitlines():
        # Strip inline comments
        if "#" in line:
            line = line[: line.index("#")]
        line = line.strip()
        if line:
            out.add(line)
    return out


def red(s):
    return f"\033[31m{s}\033[0m"


def yellow(s):
    return f"\033[33m{s}\033[0m"


def green(s):
    return f"\033[32m{s}\033[0m"


def cyan(s):
    return f"\033[36m{s}\033[0m"


def load_ha_token():
    """Resolve API credentials as (token, base_url).

    Priority: HA_TOKEN env → .env HA_TOKEN → SUPERVISOR_TOKEN (on-HAOS/NUC
    sessions have no HA_TOKEN; the Supervisor proxies core's API)."""
    env = os.environ.get("HA_TOKEN")
    if env:
        return env.strip().strip('"').strip("'"), "http://homeassistant.local:8123"
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("HA_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip(
                    "'"
                ), "http://homeassistant.local:8123"
    sup = os.environ.get("SUPERVISOR_TOKEN")
    if sup:
        return sup.strip(), "http://supervisor/core"
    return None, None


def fetch_live_entities(token, base_url="http://homeassistant.local:8123", allow_snapshot=True):
    """Fetch all entity_ids from HA's REST API.

    Returns (set, source) where source is "live", "snapshot-fallback", or None.
    If HA unreachable AND allow_snapshot, tries .cache/snapshot_latest.json.
    """
    if not token:
        if allow_snapshot:
            return _load_snapshot_fallback()
        return None, None
    import urllib.request

    try:
        req = urllib.request.Request(
            f"{base_url}/api/states",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return {s["entity_id"] for s in data}, "live"
    except Exception as e:
        print(yellow(f"⚠  Could not fetch live entities: {e}"))
        if allow_snapshot:
            return _load_snapshot_fallback()
        return None, None


def _load_snapshot_fallback():
    """Try to load entities from .cache/snapshot_latest.json (offline fallback)."""
    snap = REPO / ".cache" / "snapshot_latest.json"
    if not snap.exists():
        return None, None
    try:
        import time

        age_days = (time.time() - snap.stat().st_mtime) / 86400
        data = json.loads(snap.read_text())
        entities = {s["entity_id"] for s in data.get("states", [])}
        if entities:
            print(
                yellow(
                    f"⚠  Using snapshot fallback ({snap.name}, {len(entities)} entities, {age_days:.0f}d old)"
                )
            )
            if age_days > 7:
                print(
                    red(
                        f"⚠  Snapshot is {age_days:.0f} days old — broken-ref findings may be FALSE POSITIVES. "
                        "Run with live API access (HA_TOKEN or SUPERVISOR_TOKEN) to refresh."
                    )
                )
            return entities, "snapshot-fallback"
    except Exception as e:
        print(yellow(f"⚠  Snapshot read failed: {e}"))
    return None, None


def find_yaml_files(specific=None):
    """Find all YAML files in repo (or specific list)."""
    if specific:
        return [Path(f).resolve() for f in specific if Path(f).exists()]
    out = []
    for p in REPO.rglob("*.yaml"):
        # Skip git, node_modules, etc.
        if any(part.startswith(".") for part in p.parts):
            continue
        if "node_modules" in p.parts:
            continue
        # secrets.yaml indeholder pr. definition ingen entity-referencer, men
        # tokens/URL'er ligner dem: `https://script.google.com/...` matcher
        # regexen som `script.google` og blokerede pre-push-hooken paa en ren
        # falsk positiv (2026-08-15). Filen er heller ikke i git — den maa
        # ikke citeres i en rapport. Kontrakten (secrets.example.yaml) har
        # samme slags pladsholder-URL'er og heller ingen entities.
        if p.name in ("secrets.yaml", "secrets.example.yaml"):
            continue
        out.append(p)
    return sorted(out)


def extract_entity_refs(text):
    """Find all entity_id references in YAML text. Returns set of (line_no, entity_id)."""
    domains_re = "|".join(ENTITY_DOMAINS)
    pattern = re.compile(rf"\b({domains_re})\.([a-z_0-9]+)\b")
    out = set()
    for line_no, line in enumerate(text.splitlines(), 1):
        # Strip comments
        if "#" in line:
            line = line[: line.index("#")]
        for match in pattern.finditer(line):
            domain, name = match.group(1), match.group(2)
            out.add((line_no, f"{domain}.{name}"))
    return out


_TEMPLATE_KEYS = (
    "sensor",
    "binary_sensor",
    "number",
    "select",
    "button",
    "image",
    "weather",
    "light",
    "cover",
    "switch",
    "fan",
    "lock",
    "vacuum",
    "alarm_control_panel",
    "event",
    "update",
)


def _derived_entity_ids(text):
    """entity_ids som HA giver template-/sensor-entities ved første registrering.

    default_entity_id vinder; ellers slugify(name:) med HA's regler
    (scripts/ha_slug.py, bevist mod HA via `ha_offline.py slugcheck`).
    Returnerer None hvis PyYAML mangler.
    """
    try:
        import yaml

        sys.path.insert(0, str(REPO / "scripts"))
        from ha_slug import slugify
    except ImportError:
        return None

    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_multi_constructor("!", lambda loader, suffix, node: None)
    try:
        data = yaml.load(text, Loader=_Loader)  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError:
        return set()
    out = set()

    def add(domain, ent):
        if not isinstance(ent, dict):
            return
        if isinstance(ent.get("default_entity_id"), str):
            out.add(ent["default_entity_id"])
        elif isinstance(ent.get("name"), str) and "{{" not in ent["name"]:
            out.add(f"{domain}.{slugify(ent['name'])}")
        elif isinstance(ent.get("unique_id"), str):
            out.add(f"{domain}.{ent['unique_id']}")  # uden navn: ukendt slug

    if isinstance(data, dict):
        for block in data.get("template") or []:
            if isinstance(block, dict):
                for k in _TEMPLATE_KEYS:
                    for ent in block.get(k) or []:
                        add(k, ent)
        for dom in ("sensor", "binary_sensor"):  # statistics, history_stats, …
            for ent in data.get(dom) or []:
                if isinstance(ent, dict) and ent.get("platform") not in (None, "template", "group"):
                    add(dom, ent)
        for key in data.get("utility_meter") or {}:
            out.add(f"sensor.{key}")
        # Moderne command_line / rest: `- sensor: {name: …}` pr. liste-element
        for item in data.get("command_line") or []:
            if isinstance(item, dict):
                for k in ("sensor", "binary_sensor", "switch", "cover"):
                    add(k, item.get(k))
        for item in data.get("rest") or []:
            if isinstance(item, dict):
                for k in ("sensor", "binary_sensor"):
                    for ent in item.get(k) or []:
                        add(k, ent)
    return out


def check_broken_entity_refs(files, live_entities):
    """Check #1: entities referenced but not in HA's live state list."""
    if live_entities is None:
        return [], "skipped (no HA_TOKEN or HA unreachable)"

    findings = []
    # First pass: collect ALL defined entities from YAML (helpers, templates, etc.)
    yaml_defined = set()
    yaml_defined |= BUILTIN_ENTITIES
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # Match top-level helper definitions: input_boolean: \n  name: ...
        # NB: block-body allows blank lines between entries (2026-06-17) — ellers
        # blev en helper efter en tom linje i et multi-entry block ikke registreret
        # som lokalt-defineret → falsk "broken ref" for endnu-ikke-deployede entities.
        for m in re.finditer(
            r"^(input_boolean|input_select|input_number|input_datetime|input_text|input_button|timer):\n((?:(?:  [^\n]*)?\n)+)",
            text,
            re.MULTILINE,
        ):
            domain = m.group(1)
            for name_match in re.finditer(r"^  ([a-z_][a-z_0-9]*):\s*$", m.group(2), re.MULTILINE):
                yaml_defined.add(f"{domain}.{name_match.group(1)}")
        # Template-/sensor-entities: entity_id afledes af `name:` (eller
        # default_entity_id), ALDRIG af unique_id. Indtil 2026-10-04 stod her
        # `sensor.<unique_id>` som "defineret" — og dermed var netop slug-
        # fejlen usynlig (86a51787, d1420cc4, 2cfed6f6, 7bf32af0: en ref på
        # unique_id-formen til en helt ny sensor bestod valideringen).
        derived = _derived_entity_ids(text)
        if derived is None:  # ingen PyYAML: gammel heuristik hellere end intet
            for m in re.finditer(r"unique_id:\s*([a-z_][a-z_0-9]*)", text):
                yaml_defined.add(f"sensor.{m.group(1)}")
                yaml_defined.add(f"binary_sensor.{m.group(1)}")
        else:
            yaml_defined |= derived
        # Match light groups: light: - platform: group + name: ...
        for m in re.finditer(
            r"^[^#]*platform:\s*group[^\n]*\n(?:[^\n]*\n)*?\s*name:\s*[\"']?([^\"'\n]+)",
            text,
            re.MULTILINE,
        ):
            slug = re.sub(
                r"[^a-z0-9_]",
                "_",
                m.group(1).lower().replace("æ", "ae").replace("ø", "o").replace("å", "a"),
            )
            yaml_defined.add(f"light.{slug}")
            yaml_defined.add(f"group.{slug}")
        # 2026-06-18: groups OGSÅ via unique_id. Name-regex'en ovenfor er
        # non-greedy og springer nogle grupper over (fx light.stue_room, og
        # historisk Depot all / Entré all — de fejlede bare aldrig fordi de var
        # live). Bounded scan (≤4 linjer fra platform: group til unique_id) er
        # robust og rammer alle grupper med et unique_id.
        for m in re.finditer(
            r"platform:\s*group\b(?:[^\n]*\n){0,4}?[ \t]*unique_id:\s*([a-z_][a-z_0-9]*)", text
        ):
            yaml_defined.add(f"light.{m.group(1)}")
            yaml_defined.add(f"group.{m.group(1)}")
        # Match scripts and scenes — top-level (script_pkg/) OG indrykket under
        # en package's `script:`-nøgle (2026-10-07: scripts i packages/ blev
        # ellers meldt som brudte refs indtil første deploy).
        for m in re.finditer(
            r"^(?:  )?([a-z_][a-z_0-9]*):[ \t]*\n[ \t]+alias:", text, re.MULTILINE
        ):
            yaml_defined.add(f"script.{m.group(1)}")
            yaml_defined.add(f"scene.{m.group(1)}")

    whitelist = load_whitelist()
    valid = live_entities | yaml_defined | whitelist

    # Built-in HA entities that always exist if integration enabled
    valid |= {"sensor.date", "sensor.time", "sensor.date_time"}
    # scene.create is a service used to dynamically create scenes
    valid |= {"scene.create"}

    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        for line_no, ref in extract_entity_refs(text):
            if ref in valid:
                continue
            # Skip refs to common service-call targets
            if ref.endswith(".all"):
                continue
            # Skip templated entity_ids (regex captures up to _{{ X }}{...)
            # These names end in _ which is unusual for real entities
            if ref.endswith("_"):
                continue
            # Skip service-name patterns
            if any(ref.endswith(svc) for svc in SERVICE_PATTERNS):
                continue
            # Skip if line context indicates service call OR scene creation
            if line_no <= len(lines):
                line = lines[line_no - 1]
                # NB: "- service: x.y" (foerste element i en action-liste) skal
                # ogsaa fanges — uden "-?" flagges fx `- service: update.install`
                # som en manglende entity. Fundet 2026-09-17 da pre-push-hooken
                # blokerede en helt gyldig update.install.
                if re.search(r"^\s*-?\s*service:\s*", line):
                    continue
                if re.search(r"^\s*-?\s*action:\s*", line):
                    continue
                # Skip if entity_id is RHS of scene_id (scene.create dynamically defines)
                if re.search(r"scene_id:\s*", line):
                    continue
            # Skip dynamically-created scenes (created by scene.create at runtime)
            if ref.startswith("scene.") and "_undo_snapshot" in ref:
                continue
            # Defensive: relative_to fails if file is outside REPO (e.g. /tmp test)
            try:
                rel = str(f.relative_to(REPO))
            except ValueError:
                rel = str(f)
            findings.append((rel, line_no, ref))
    return findings, None


def check_duplicate_automation_ids(files):
    """Check #2: duplicate automation/script id= across files."""
    ids = defaultdict(list)
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"^- id:\s*([a-z_][a-z_0-9]*)\s*$", text, re.MULTILINE):
            ids[m.group(1)].append(str(f.relative_to(REPO)))
    return {k: v for k, v in ids.items() if len(v) > 1}


def check_replace_all_hazards(files):
    """Check #3: numeric values that have prefix-overlap risk for replace_all."""
    findings = []
    # Find common numeric attrs that we've actually had bugs with
    risky_keys = ["transition", "brightness_pct", "delay", "for"]
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # Group values per key per file
        values_per_key = defaultdict(set)
        for line in text.splitlines():
            for key in risky_keys:
                m = re.match(rf"^\s*{key}:\s*(\d+)\s*(?:#.*)?$", line)
                if m:
                    values_per_key[key].add(int(m.group(1)))
        for key, values in values_per_key.items():
            for v in values:
                # If 60 exists AND 600 exists, replace_all 60→90 would cycle 600→900
                for v2 in values:
                    if v != v2 and str(v2).startswith(str(v)) and v < v2:
                        findings.append((str(f.relative_to(REPO)), key, v, v2))
                        break
    return findings


def check_stale_placeholders(files):
    """Check #4: PLACEHOLDER/TODO/FIXME markers (informational)."""
    findings = []
    pattern = re.compile(r"\b(PLACEHOLDER|TODO|FIXME|XXX|HACK)\b")
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                findings.append((str(f.relative_to(REPO)), line_no, line.strip()[:80]))
    return findings


def check_jinja_syntax(files):
    """Check #6: jinja template syntax errors."""
    try:
        from jinja2 import Environment, TemplateSyntaxError
    except ImportError:
        return [], "skipped (jinja2 not installed)"

    env = Environment()
    findings = []

    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # Find inline Jinja (anything with {% or {{)
        for m in re.finditer(r"({{[^}]*}}|{%[^%]*%})", text):
            tpl = m.group(0)
            try:
                env.parse(tpl)
            except TemplateSyntaxError as e:
                line_no = text[: m.start()].count("\n") + 1
                findings.append((str(f.relative_to(REPO)), line_no, str(e)[:80], tpl[:60]))
    return findings, None


LIGHT_SERVICES = {"light.turn_on", "light.turn_off", "light.toggle"}


def _matter_light_targets():
    """Matter-lys fra entity-registry + lysgrupper (YAML og UI-helpers) der
    indeholder ét, transitivt. None når .storage mangler (cloud/offline)."""
    reg_path = REPO / ".storage" / "core.entity_registry"
    if not reg_path.exists():
        return None
    import yaml

    sys.path.insert(0, str(REPO / "scripts"))
    from ha_slug import slugify

    reg = json.loads(reg_path.read_text(encoding="utf-8"))["data"]["entities"]
    targets = {
        e["entity_id"]
        for e in reg
        if e.get("platform") == "matter"
        and e["entity_id"].startswith("light.")
        and not e.get("disabled_by")
    }
    groups = {}

    class _L(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
        pass

    _L.add_multi_constructor("!", lambda l, s, n: None)

    def walk(o):
        if isinstance(o, dict):
            if (
                o.get("platform") == "group"
                and isinstance(o.get("entities"), list)
                and o.get("name")
            ):
                groups["light." + slugify(str(o["name"]))] = o["entities"]
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for sub in ("packages", "automations", "script_pkg"):
        for p in (REPO / sub).rglob("*.yaml"):
            try:
                walk(yaml.load(p.read_text(encoding="utf-8"), Loader=_L))  # noqa: S506 - a SafeLoader subclass
            except Exception:
                continue
    ce_path = REPO / ".storage" / "core.config_entries"
    if ce_path.exists():
        for e in json.loads(ce_path.read_text(encoding="utf-8"))["data"]["entries"]:
            opts = e.get("options") or {}
            if e.get("domain") == "group" and opts.get("group_type") == "light":
                groups["light." + slugify(e.get("title", ""))] = opts.get("entities", [])
    changed = True
    while changed:
        changed = False
        for gid, members in groups.items():
            if gid not in targets and any(m in targets for m in members):
                targets.add(gid)
                changed = True
    return targets


def check_matter_continue_on_error(files):
    """Check #9: light-kald der rammer et Matter-lys (direkte eller via en
    lysgruppe) uden `continue_on_error: true`. CHIP Error 0x00000032 (Timeout)
    aborterer ellers HELE scriptet på det trin (CLAUDE.md, Radio). Kun
    statiske entity_ids — templatede mål kan ikke afgøres offline."""
    targets = _matter_light_targets()
    if targets is None:
        return [], "skipped (ingen .storage/core.entity_registry)"
    import yaml

    class _L(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
        pass

    _L.add_multi_constructor("!", lambda l, s, n: None)

    def ids(node):
        out = []
        if isinstance(node, yaml.ScalarNode):
            out += [x.strip() for x in node.value.split(",")]
        elif isinstance(node, yaml.SequenceNode):
            out += [x.value for x in node.value if isinstance(x, yaml.ScalarNode)]
        return out

    findings = []
    for f in files:
        try:
            root = yaml.compose(f.read_text(encoding="utf-8"), Loader=_L)
        except Exception:
            continue
        try:
            rel = str(f.relative_to(REPO))
        except ValueError:
            rel = str(f)
        stack = [root]
        while stack:
            n = stack.pop()
            if isinstance(n, yaml.MappingNode):
                d = {k.value: v for k, v in n.value if isinstance(k, yaml.ScalarNode)}
                svc = d.get("action") or d.get("service")
                if isinstance(svc, yaml.ScalarNode) and svc.value in LIGHT_SERVICES:
                    ents = ids(d.get("entity_id"))
                    for sub in ("target", "data"):
                        if isinstance(d.get(sub), yaml.MappingNode):
                            ents += ids({k.value: v for k, v in d[sub].value}.get("entity_id"))
                    hit = sorted({e for e in ents if e in targets})
                    coe = d.get("continue_on_error")
                    if hit and not (
                        isinstance(coe, yaml.ScalarNode) and coe.value.lower() == "true"
                    ):
                        findings.append((rel, n.start_mark.line + 1, svc.value, hit))
                stack.extend(v for _, v in n.value)
            elif isinstance(n, yaml.SequenceNode):
                stack.extend(n.value)
    return sorted(findings), None


def check_scene_list_drift(files):
    """Check #9 (A13 fix sprint 2026-05-06): scenes are defined in 4-5 places.

    Verifies all locations contain the SAME set of scene names. Drift between
    them = silent breakage (e.g. add new scene to entre_scene_cycle but forget
    input_select options → cycle works but dashboard tile broken).

    Locations checked:
      1. script_pkg/scenes.yaml::entre_scene_cycle variables.scenes list
      2. script_pkg/room_logic.yaml::scene_toggle variables.scene_idx_map dict
      3. packages/scene_state.yaml::input_select.active_scene options
      4. packages/scene_state.yaml::template binary_sensor scene_*_active names
      5. dashboards/scenes.yaml tile entity_ids (binary_sensor.scene_*_active)
    """
    locations = {}

    def read_file(rel_path):
        p = REPO / rel_path
        return p.read_text(encoding="utf-8") if p.exists() else None

    # Track ORDERED versions for cycle ↔ idx_map order-drift check (A38)
    cycle_order = None
    idx_map_order = None  # list of (name, idx) tuples

    # Location 1: entre_scene_cycle scenes list (ORDER matters for cycle index)
    text = read_file("script_pkg/scenes.yaml")
    if text:
        m = re.search(
            r"entre_scene_cycle:.*?variables:.*?scenes:\s*\n((?:\s*-\s*\w+\n)+)",
            text,
            re.DOTALL,
        )
        if m:
            cycle_order = re.findall(r"-\s*(\w+)", m.group(1))
            locations["entre_scene_cycle"] = set(cycle_order)

    # Location 2: scene_toggle scene_idx_map (ORDER matters — must match cycle)
    text = read_file("script_pkg/room_logic.yaml")
    if text:
        m = re.search(
            r"scene_idx_map:\s*\n((?:\s*\w+:\s*\d+\n)+)",
            text,
        )
        if m:
            # Extract as list of (name, idx) tuples in source order
            idx_map_order = [
                (n, int(i)) for n, i in re.findall(r"^\s*(\w+):\s*(\d+)", m.group(1), re.MULTILINE)
            ]
            locations["scene_idx_map"] = set(n for n, _ in idx_map_order)

    # Location 3: input_select.active_scene options
    text = read_file("packages/scene_state.yaml")
    if text:
        # Find options block — terminate at next top-level YAML key (no leading space)
        m = re.search(
            r"active_scene:.*?options:\s*\n((?:\s*(?:-\s*[\"']?\w+[\"']?\s*(?:#[^\n]*)?|#[^\n]*)\n)+)",
            text,
            re.DOTALL,
        )
        if m:
            # Accept lines like '- name', '- "name"', '- name # comment'
            opts = set(re.findall(r"^\s*-\s*[\"']?(\w+)[\"']?", m.group(1), re.MULTILINE))
            opts.discard("none")  # "none" is sentinel, not a real scene
            locations["input_select_options"] = opts

        # Location 4: template binary_sensor unique_ids
        ids = re.findall(r"unique_id:\s*scene_(\w+)_active", text)
        if ids:
            locations["template_binary_sensors"] = set(ids)

    # Location 5: dashboards/scenes.yaml tile entities
    text = read_file("dashboards/scenes.yaml")
    if text:
        ids = re.findall(r"entity:\s*binary_sensor\.scene_(\w+)_active", text)
        if ids:
            locations["dashboard_tiles"] = set(ids)

    if len(locations) < 2:
        return [], "skipped (too few scene locations parseable)"

    # Find drift: union vs each location (SET-based check)
    all_scenes = set().union(*locations.values())
    drifts = []
    for loc, scenes in locations.items():
        missing = all_scenes - scenes
        extra = scenes - all_scenes
        if missing or extra:
            drifts.append((loc, missing, extra))

    # A38 fix sprint 2026-05-06 PM: ORDER drift check.
    # entre_scene_cycle iterates scenes by index (modulo). scene_idx_map maps
    # name → idx for reverse-sync. If their orders disagree, Styrbar cycle and
    # dashboard tap will desync silently. Verify cycle_order[idx] == idx_map[name].
    if cycle_order and idx_map_order:
        idx_map_dict = dict(idx_map_order)
        for i, name in enumerate(cycle_order):
            if name not in idx_map_dict:
                continue  # already caught by SET drift
            if idx_map_dict[name] != i:
                drifts.append(
                    (
                        "ORDER drift",
                        {f"'{name}' at cycle pos {i}"},
                        {f"'{name}' has idx_map={idx_map_dict[name]}"},
                    )
                )

    # Phase 5 fix audit 2026-05-07: MAX drift check. entre_scene_idx.max
    # should match scene_count - 1. Otherwise set_value can land on
    # shadow indices (clamped or modulo). Comment in room_modes.yaml line
    # 230 already claimed this guard exists — now it actually does.
    text = read_file("packages/room_modes.yaml")
    if text and cycle_order:
        m = re.search(
            r"entre_scene_idx:[^a-zA-Z]+name:[^\n]*\n[^\n]*min:\s*\d+\s*\n[^\n]*max:\s*(\d+)", text
        )
        if m:
            actual_max = int(m.group(1))
            expected_max = len(cycle_order) - 1
            if actual_max != expected_max:
                drifts.append(
                    (
                        "MAX drift",
                        {f"entre_scene_idx.max should be {expected_max} (= scene_count - 1)"},
                        {f"actual max={actual_max}, scenes={len(cycle_order)}"},
                    )
                )
    return drifts, None


def check_unused_helpers(files, live_entities):
    """Check #7: input_boolean/sensor defined but never referenced."""
    if not live_entities:
        return [], "skipped"
    defined = set()
    referenced = set()
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # Defined in helper sections
        for m in re.finditer(
            r"^(input_boolean|input_select|input_number|input_datetime):\n((?:  [^\n]*\n)+)",
            text,
            re.MULTILINE,
        ):
            domain = m.group(1)
            for name_match in re.finditer(r"^  ([a-z_][a-z_0-9]*):\s*$", m.group(2), re.MULTILINE):
                defined.add(f"{domain}.{name_match.group(1)}")
        # Referenced anywhere
        for _, ref in extract_entity_refs(text):
            referenced.add(ref)
    unused = defined - referenced
    return sorted(unused), None


def check_whitelist_staleness(live_entities):
    """Check #8: whitelist entries that now exist in HA (= can be removed)."""
    if not live_entities:
        return [], "skipped (no live entities available)"
    whitelist = load_whitelist()
    now_existing = sorted(whitelist & live_entities)
    return now_existing, None


def main():
    parser = argparse.ArgumentParser(description="HA YAML validator")
    parser.add_argument("--files", nargs="+", help="Only check specific files")
    parser.add_argument(
        "--check",
        choices=[
            "all",
            "refs",
            "dups",
            "hazards",
            "placeholders",
            "jinja",
            "matter",
            "unused",
            "stale_whitelist",
            "scene_drift",
        ],
        default="all",
    )
    parser.add_argument("--quiet", action="store_true", help="Only output errors, no info")
    parser.add_argument("--json", action="store_true", help="Output as JSON for scripting")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Force live HA entity fetch for refs check (otherwise skips refs check)",
    )
    parser.add_argument(
        "--no-snapshot-fallback",
        action="store_true",
        help="Don't fall back to .cache/snapshot_latest.json if HA unreachable",
    )
    args = parser.parse_args()

    files = find_yaml_files(args.files)
    if not args.quiet:
        print(cyan(f"Validating {len(files)} YAML files in {REPO}"))

    # Live fetch only if explicitly requested (--live) OR if "all" check (default behavior).
    # For --check refs without --live: skip refs (caller likely doesn't want network call).
    needs_live = args.check in ("all", "refs", "unused", "stale_whitelist") and (
        args.live or args.check in ("all", "stale_whitelist")
    )
    live_entities = None
    if needs_live:
        token, base_url = load_ha_token()
        live_entities, source = fetch_live_entities(
            token, base_url, allow_snapshot=not args.no_snapshot_fallback
        )
        if live_entities and not args.quiet:
            tag = " (snapshot fallback)" if source == "snapshot-fallback" else ""
            print(cyan(f"Loaded {len(live_entities)} live entities from HA{tag}"))
    elif args.check == "refs" and not args.quiet:
        print(
            yellow("ℹ  refs check requires --live flag (otherwise skipped to avoid network call)")
        )

    results = {"errors": 0, "warnings": 0, "checks": {}}

    if args.check in ("all", "refs"):
        broken, skip = check_broken_entity_refs(files, live_entities)
        results["checks"]["broken_refs"] = len(broken)
        if skip:
            if not args.quiet:
                print(yellow(f"⏭  broken refs: {skip}"))
        elif broken:
            print(red(f"❌ {len(broken)} broken entity references:"))
            for f, ln, ref in broken[:20]:
                print(f"   {f}:{ln}  {ref}")
            if len(broken) > 20:
                print(f"   ... and {len(broken) - 20} more")
            results["errors"] += len(broken)
        elif not args.quiet:
            print(green("✅ No broken entity references"))

    if args.check in ("all", "dups"):
        dups = check_duplicate_automation_ids(files)
        results["checks"]["duplicate_ids"] = len(dups)
        if dups:
            print(red(f"❌ {len(dups)} duplicate automation IDs:"))
            for aid, locs in dups.items():
                print(f"   {aid}: {', '.join(locs)}")
            results["errors"] += len(dups)
        elif not args.quiet:
            print(green("✅ No duplicate automation IDs"))

    if args.check in ("all", "hazards"):
        hazards = check_replace_all_hazards(files)
        results["checks"]["replace_all_hazards"] = len(hazards)
        if hazards:
            print(yellow(f"⚠  {len(hazards)} replace_all hazards (numeric prefix overlap):"))
            seen = set()
            for f, k, v1, v2 in hazards:
                key = (f, k, v1, v2)
                if key in seen:
                    continue
                seen.add(key)
                print(
                    f"   {f}  {k}: {v1} AND {v2} (replace {v1}→X risks cycling {v2}→X{str(v2)[len(str(v1)) :]})"
                )
            results["warnings"] += len(seen)
        elif not args.quiet:
            print(green("✅ No replace_all hazards"))

    if args.check in ("all", "placeholders"):
        placeholders = check_stale_placeholders(files)
        results["checks"]["placeholders"] = len(placeholders)
        if placeholders and not args.quiet:
            print(yellow(f"⚠  {len(placeholders)} TODO/PLACEHOLDER markers (informational):"))
            for f, ln, line in placeholders[:10]:
                print(f"   {f}:{ln}  {line}")
            if len(placeholders) > 10:
                print(f"   ... and {len(placeholders) - 10} more")

    if args.check in ("all", "jinja"):
        bad_jinja, skip = check_jinja_syntax(files)
        results["checks"]["jinja_errors"] = len(bad_jinja)
        if skip:
            if not args.quiet:
                print(yellow(f"⏭  jinja syntax: {skip}"))
        elif bad_jinja:
            print(red(f"❌ {len(bad_jinja)} jinja syntax errors:"))
            for f, ln, err, tpl in bad_jinja[:10]:
                print(f"   {f}:{ln}  {err}  (in: {tpl})")
            results["errors"] += len(bad_jinja)
        elif not args.quiet:
            print(green("✅ Jinja templates parse cleanly"))

    if args.check in ("all", "matter"):
        no_coe, skip = check_matter_continue_on_error(files)
        results["checks"]["matter_no_continue_on_error"] = len(no_coe)
        if skip:
            if not args.quiet:
                print(yellow(f"⏭  matter continue_on_error: {skip}"))
        elif no_coe:
            print(
                red(
                    f"❌ {len(no_coe)} light-kald til Matter-lys uden continue_on_error: true "
                    "(CHIP-timeout aborterer ellers hele scriptet):"
                )
            )
            for f, ln, svc, ents in no_coe[:20]:
                print(f"   {f}:{ln}  {svc}  {', '.join(ents)}")
            results["errors"] += len(no_coe)
        elif not args.quiet:
            print(green("✅ Alle statiske Matter-lys-kald har continue_on_error"))

    if args.check in ("all", "unused"):
        unused, skip = check_unused_helpers(files, live_entities)
        results["checks"]["unused_helpers"] = len(unused) if isinstance(unused, list) else 0
        if not skip and unused:
            if not args.quiet:
                print(yellow(f"⚠  {len(unused)} potentially unused helpers (informational):"))
                for h in unused[:10]:
                    print(f"   {h}")
                if len(unused) > 10:
                    print(f"   ... and {len(unused) - 10} more")

    if args.check in ("all", "stale_whitelist"):
        stale, skip = check_whitelist_staleness(live_entities)
        results["checks"]["stale_whitelist"] = len(stale) if isinstance(stale, list) else 0
        if skip:
            if not args.quiet:
                print(yellow(f"⏭  whitelist staleness: {skip}"))
        elif stale:
            if not args.quiet:
                print(
                    yellow(f"ℹ  {len(stale)} whitelist entries now EXIST in HA (can be removed):")
                )
                for e in stale:
                    print(f"   ✅ {e}")

    if args.check in ("all", "scene_drift"):
        drifts, skip = check_scene_list_drift(files)
        results["checks"]["scene_drift"] = len(drifts) if isinstance(drifts, list) else 0
        if skip:
            if not args.quiet:
                print(yellow(f"⏭  scene drift: {skip}"))
        elif drifts:
            print(red(f"❌ {len(drifts)} scene-list locations have drift:"))
            for loc, missing, extra in drifts:
                if missing:
                    print(f"   {loc}: MISSING {sorted(missing)}")
                if extra:
                    print(f"   {loc}: EXTRA {sorted(extra)}")
            results["errors"] += len(drifts)
        elif not args.quiet:
            print(green("✅ Scene lists in sync across all 5 locations"))

    if args.json:
        print(json.dumps(results, indent=2))

    if results["errors"] > 0:
        sys.exit(1)
    if results["warnings"] > 0:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
