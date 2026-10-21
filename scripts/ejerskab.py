#!/usr/bin/env python3
"""Lamp ownership: one registry per contested lamp, generating an owner sensor, a contract and a lint.

The registry (``ejerskab/<slug>.yaml``) is the order of precedence. Everything
else is derived from it:

  packages/ejerskab_<slug>.yaml   owner sensor, "borrowed" sensor, resume automation
  packages/ejerskab_index.yaml    sensor.lys_ejerskab (which lamps are governed)
  docs/auto/ejerskab/<slug>.md    the contract injected into the agent (hook)
  docs/auto/ejerskab/index.json   what the hook matches on

  python3 scripts/ejerskab.py gen             write the generated files
  python3 scripts/ejerskab.py check           exit 1 if generated files are stale
  python3 scripts/ejerskab.py lint [FILE ...] exit 1 on an unregistered or obsolete writer
  python3 scripts/ejerskab.py steder ENTITY   list every static write site (debugging)

A *write site* is an automation or script whose own action tree calls
``light.*``, ``homeassistant.turn_*``, ``scene.apply`` or ``scene.turn_on`` on
the entity: directly, through a light group that contains it, through
``entity_id: all``, as a literal inside a template, or by restoring a scene
whose snapshot contains it. Calling a script that writes is not a write site;
the script is. Templated targets without a literal entity_id are invisible to
the scanner and are registered by hand with ``dynamisk: true``.
See docs/adr/0004-lamp-ownership-registry.md.
"""

import glob
import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rosters  # noqa: E402  roster-!include → entity-listen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG_DIR = os.path.join(ROOT, "ejerskab")
GEN_DOC_DIR = os.path.join(ROOT, "docs", "auto", "ejerskab")
GEN_HEADER = "# GENERERET af scripts/ejerskab.py fra {src} — RET IKKE HER. Ret registret og kør `python3 scripts/ejerskab.py gen`.\n"

WRITE_SERVICES = {
    "light.turn_on",
    "light.turn_off",
    "light.toggle",
    "homeassistant.turn_on",
    "homeassistant.turn_off",
    "homeassistant.toggle",
    "scene.apply",
}
RESTORE_SERVICES = {"scene.turn_on"}


def is_write(svc):
    # `service: "{{ 'light.turn_on' if x else 'light.turn_off' }}"` er også en skrivning.
    return svc in WRITE_SERVICES or ("{{" in svc and any(w in svc for w in WRITE_SERVICES))


class _Loader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    pass


def _ignore(loader, tag_suffix, node):
    # En roster-!include (rosters/<navn>.yaml, konsolidering P2) er en entity-
    # liste — uden dette så scanneren sti-strengen i stedet for lamperne.
    roster = rosters.yaml_tag(loader, tag_suffix, node)
    if roster is not None:
        return roster
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_Loader.add_multi_constructor("!", _ignore)


_CACHE = {}


def load_yaml(path):
    if path not in _CACHE:
        with open(path, encoding="utf-8") as f:
            _CACHE[path] = yaml.load(f, Loader=_Loader)  # noqa: S506 - a SafeLoader subclass
    return _CACHE[path]


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def mentions(text, ent):
    return re.search(r"(?<![\w.])" + re.escape(ent) + r"(?![\w])", text) is not None


# --- registret -------------------------------------------------------------
def load_registries():
    regs = []
    for path in sorted(glob.glob(os.path.join(REG_DIR, "*.yaml"))):
        r = load_yaml(path) or {}
        r["_src"] = rel(path)
        r["_slug"] = os.path.splitext(os.path.basename(path))[0]
        regs.append(r)
    return regs


def registered_sites(reg):
    """sted → (kategori, dynamisk?)."""
    out = {}
    for k, v in (reg.get("kanaler") or {}).items():
        out[v] = ("kanal:" + k, False)
    for krav in reg.get("krav") or []:
        for s in krav.get("skrivere") or []:
            if isinstance(s, dict):
                out[s["sted"]] = ("krav:" + krav["id"], bool(s.get("dynamisk")))
            else:
                out[s] = ("krav:" + krav["id"], False)
    for s in reg.get("skrivere") or []:
        out[s["sted"]] = ("skriver:" + s.get("rolle", "?"), bool(s.get("dynamisk")))
    return out


# --- scanner ---------------------------------------------------------------
def load_groups():
    data = load_yaml(os.path.join(ROOT, "packages", "light_groups.yaml")) or {}
    raw = {}
    for item in data.get("light", []) or []:
        if isinstance(item, dict) and item.get("platform") == "group" and item.get("unique_id"):
            raw["light." + item["unique_id"]] = list(item.get("entities") or [])
    return raw


def groups_containing(ent, raw):
    found, frontier = set(), {ent}
    while frontier:
        nxt = set()
        for g, members in raw.items():
            if g not in found and frontier & set(members):
                found.add(g)
                nxt.add(g)
        frontier = nxt
    return sorted(found)


_CONTAINERS = None


def iter_containers():
    """(fil, container-id, blok) for alle automations og scripts i huset."""
    global _CONTAINERS
    if _CONTAINERS is None:
        _CONTAINERS = list(_iter_containers())
    return _CONTAINERS


def _iter_containers():
    def autos(path, blocks):
        for b in blocks:
            if isinstance(b, dict) and ("action" in b or "actions" in b):
                cid = b.get("id") or slug(b.get("alias") or "uden_alias")
                yield rel(path), str(cid), b

    def scripts(path, d):
        for k, v in (d or {}).items():
            if isinstance(v, dict) and ("sequence" in v):
                yield rel(path), str(k), v

    for path in sorted(glob.glob(os.path.join(ROOT, "automations", "*.yaml"))):
        data = load_yaml(path)
        if isinstance(data, list):
            yield from autos(path, data)
    for path in sorted(glob.glob(os.path.join(ROOT, "packages", "*.yaml"))):
        data = load_yaml(path)
        if not isinstance(data, dict):
            continue
        a = data.get("automation")
        if isinstance(a, list):
            yield from autos(path, a)
        elif isinstance(a, dict):
            yield from autos(path, [a])
        if isinstance(data.get("script"), dict):
            yield from scripts(path, data["script"])
    for path in sorted(glob.glob(os.path.join(ROOT, "script_pkg", "*.yaml"))):
        data = load_yaml(path)
        if isinstance(data, dict):
            yield from scripts(path, data)


# Én HA-kompatibel slugify for alle scripts (konsolidering 2026-10-04).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ha_slug import slugify as slug  # noqa: E402


def service_calls(node, out):
    if isinstance(node, dict):
        svc = node.get("service") or node.get("action")
        if isinstance(svc, str):
            out.append((svc, node))
        for v in node.values():
            service_calls(v, out)
    elif isinstance(node, list):
        for v in node:
            service_calls(v, out)


def target_text(node):
    parts = []
    for holder in (node, node.get("target"), node.get("data")):
        if isinstance(holder, dict):
            for key in ("entity_id", "entities", "snapshot_entities"):
                if key in holder:
                    parts.append(json.dumps(holder[key], ensure_ascii=False))
    return " ".join(parts)


def scenes_with(ent, groups):
    """statiske scene-entity_ids hvis restore rammer entiteten."""
    names = [ent] + groups
    out = set()
    for path in glob.glob(os.path.join(ROOT, "scene_snapshots", "*.yaml")):
        for sc in load_yaml(path) or []:
            if isinstance(sc, dict) and any(n in (sc.get("entities") or {}) for n in names):
                out.add("scene." + slug(sc.get("name") or sc.get("id") or ""))
    for _f, _c, block in iter_containers():
        calls = []
        service_calls(block, calls)
        for svc, node in calls:
            if svc == "scene.create":
                d = node.get("data") or {}
                sid = d.get("scene_id")
                if (
                    isinstance(sid, str)
                    and "{" not in sid
                    and any(mentions(target_text(node), n) for n in names)
                ):
                    out.add("scene." + sid)
    return sorted(out)


def scan(ent):
    """sted ('fil#id') → sorteret liste af hvordan den skriver."""
    raw = load_groups()
    groups = groups_containing(ent, raw)
    scenes = scenes_with(ent, groups)
    sites = {}
    for path, cid, block in iter_containers():
        calls = []
        service_calls(
            block.get("action") or block.get("actions") or block.get("sequence") or [], calls
        )
        hows = set()
        for svc, node in calls:
            txt = target_text(node)
            if is_write(svc):
                if mentions(txt, ent):
                    hows.add(svc + (" (template)" if "{{" in txt else ""))
                for g in groups:
                    if mentions(txt, g):
                        hows.add(f"{svc} via {g}")
                if svc.startswith("light.") and re.search(r'"all"', txt):
                    hows.add(f"{svc} via entity_id: all")
            elif svc in RESTORE_SERVICES:
                for sc in scenes:
                    if mentions(txt, sc):
                        hows.add(f"scene-restore {sc}")
        if hows:
            sites[f"{path}#{cid}"] = sorted(hows)
    return sites, groups


# --- lint ------------------------------------------------------------------
def lint(files=None):
    errors = []
    only = {f.replace("\\", "/") for f in files} if files else None
    for reg in load_registries():
        ent = reg["entity"]
        sites, _groups = scan(ent)
        known = registered_sites(reg)
        for sted, hows in sorted(sites.items()):
            if only and sted.split("#")[0] not in only:
                continue
            if sted not in known:
                errors.append(
                    f"❌ {sted} skriver {ent} ({'; '.join(hows)}) men står ikke i {reg['_src']}.\n"
                    f"   → Hører den til et krav: tilføj under det kravs `skrivere:`. Ellers: tilføj under\n"
                    f"     `skrivere:` med rolle + via. Er det en ny LÅNER: nyt krav på sin rang (se kontrakten\n"
                    f"     docs/auto/ejerskab/{reg['_slug']}.md). Kør derefter `python3 scripts/ejerskab.py gen`."
                )
        existing = {f"{f}#{c}" for f, c, _b in iter_containers()}
        for sted, (kat, dyn) in sorted(known.items()):
            if only and sted.split("#")[0] not in only:
                continue
            if dyn:
                # Templated mål kan ikke bevises statisk — men stedet skal findes.
                if sted not in existing:
                    errors.append(
                        f"❌ {reg['_src']} registrerer {sted} ({kat}, dynamisk), men den automation/det\n"
                        f"   script findes ikke længere. → Fjern/ret linjen i registret."
                    )
                continue
            if sted not in sites:
                errors.append(
                    f"❌ {reg['_src']} registrerer {sted} ({kat}), men den skriver ikke længere {ent}\n"
                    f"   (eller id'et er ændret). → Fjern/ret linjen i registret, så kortet passer til koden."
                )
    return errors


# --- generering ------------------------------------------------------------
def pylist(items):
    # Jinja-liste med enkelt-anførselstegn: den står inde i en "…"-YAML-streng.
    return "[" + ", ".join(f"'{x}'" for x in items) + "]"


def j(expr):
    return " ".join(str(expr).split())


def gen_package(reg):
    ent = reg["entity"]
    krav = [k for k in reg.get("krav") or [] if k.get("type", "krav") == "krav"]
    ejer = reg["ejer_sensor"]
    laant = reg["laant_sensor"]
    ejer_name = reg["ejer_navn"]
    laant_name = reg["laant_navn"]

    def chain(value, default, indent="          "):
        # Samme if/elif-kæde for state og attributter: en attribut der læste
        # `this.state` ville halte én opdatering efter.
        out = []
        for i, k in enumerate(krav):
            kw = "if" if i == 0 else "elif"
            out.append(f"{indent}{{%- {kw} ({j(k['naar'])}) -%}}{value(i, k)}")
        return "\n".join(out) + f"\n{indent}{{%- else -%}}{default}{{%- endif -%}}"

    state = chain(lambda i, k: k["id"], "hus")
    holdere = ["            {%- set h = namespace(l=[]) -%}"]
    for k in krav:
        holdere.append(
            f"            {{%- if ({j(k['naar'])}) -%}}{{%- set h.l = h.l + ['{k['navn']}'] -%}}{{%- endif -%}}"
        )
    holdere.append("            {{ h.l | join(', ') if h.l else '—' }}")
    aflever = [k["id"] for k in krav if k.get("aflevering") == "maal"]
    genoptag = [k for k in krav if k.get("genoptag")]

    out = [
        GEN_HEADER.format(src=reg["_src"]),
        f"# Ejer af {ent}: højeste aktive krav i registret vinder, ellers 'hus'",
        "# (= husets mål via enforceren). Rækkefølgen i registret ER prioriteten.",
        "template:",
        "  - sensor:",
        f'      - name: "{ejer_name}"',
        f"        unique_id: {ejer.split('.', 1)[1]}",
        "        icon: mdi:crown",
        "        state: >-",
        state,
        "        attributes:",
        "          navn: >-",
        chain(lambda i, k: k["navn"], "huset", "            "),
        "          rang: >-",
        chain(lambda i, k: str(i + 1), "0", "            "),
        f'          aflever_til_hus: "{{{{ {pylist(aflever)} }}}}"',
        "          holdere: >-",
        "\n".join(holdere),
        "  - binary_sensor:",
        f'      - name: "{laant_name}"',
        f"        unique_id: {laant.split('.', 1)[1]}",
        "        icon: mdi:hand-extended",
        "        state: >-",
        f"          {{{{ states('{ejer}') not in ['hus', 'unknown', 'unavailable', ''] }}}}",
        "        attributes:",
        f"          holder: \"{{{{ state_attr('{ejer}', 'holdere') or '—' }}}}\"",
    ]
    if genoptag:
        ids = [k["id"] for k in genoptag]
        out += [
            "",
            "automation:",
            f"  - id: ejerskab_{reg['_slug']}_genoptag",
            f'    alias: "Ejerskab: {reg["navn"]} — et lavere krav får lampen tilbage"',
            "    description: >-",
            "      GENERERET. Slipper et højere krav mens et lavere stadig er aktivt, maler",
            f"      det lavere sit eget udseende igen. Kun krav med `genoptag:` i {reg['_src']}.",
            "      Overtagelse fra 'hus' er kravets egen skrivers job, ikke dette.",
            "    mode: restart",
            "    trigger:",
            "      - platform: state",
            f"        entity_id: {ejer}",
            '        not_from: ["unknown", "unavailable", "hus"]',
            f"        to: {json.dumps(ids)}",
            "    action:",
            "      - delay:",
            "          seconds: 2",
            "      - condition: template",
            f"        value_template: \"{{{{ is_state('{ejer}', trigger.to_state.state) }}}}\"",
            "      - choose:",
        ]
        for k in genoptag:
            g = k["genoptag"]
            out += [
                f"          - conditions: \"{{{{ trigger.to_state.state == '{k['id']}' }}}}\"",
                "            sequence:",
                f"              - action: {g['action']}",
                "                continue_on_error: true",
            ]
            if g.get("data"):
                out.append(f"                data: {json.dumps(g['data'])}")
    return "\n".join(out) + "\n"


def gen_index(regs):
    styrede = [r["entity"] for r in regs]
    return (
        GEN_HEADER.format(src="ejerskab/*.yaml")
        + "# Lamper med et ejerskabs-register. Rum-logik må tænde/slukke dem, aldrig\n"
        + "# sætte deres udseende (script_pkg/room_logic.yaml læser listen).\n"
        + "template:\n  - sensor:\n"
        + '      - name: "Lys ejerskab"\n        unique_id: lys_ejerskab\n        icon: mdi:crown-outline\n'
        + f'        state: "{len(styrede)}"\n        attributes:\n'
        + f'          styrede: "{{{{ {pylist(styrede)} }}}}"\n'
    )


def gen_contract(reg):
    ent = reg["entity"]
    krav = reg.get("krav") or []
    k_ = reg["kanaler"]
    rows = []
    n = 0
    for k in krav:
        if k.get("type", "krav") == "overlay":
            rang = "—"
        else:
            n += 1
            rang = str(n)
        afl = k.get("aflevering", "—") if k.get("type", "krav") == "krav" else "overlay"
        if k.get("genoptag"):
            afl += " + genoptag"
        rows.append(f"| {rang} | `{k['id']}` {k['navn']} | {k.get('kort', '')} | {afl} |")
    huller = reg.get("huller") or []
    out = [
        f"# Ejerskab: `{ent}` — {reg['navn']}",
        f"GENERERET fra `{reg['_src']}` (registret ER prioriteten; ret dér + `python3 scripts/ejerskab.py gen`).",
        f"Ejer nu: `{reg['ejer_sensor']}` (state = krav-id eller `hus`). `{reg['laant_sensor']}` = ejer ≠ hus.",
        "",
        "| # | krav | aktiv når | slip |",
        "|---|---|---|---|",
        *rows,
        "| — | `hus` husets mål | ingen krav aktive | — |",
        "",
        f"**Når ejer = hus** vælger mål-sensorerne udseendet: {reg.get('hus_modes', '')}",
        "",
        "**Regler (pre-commit `ejerskab.py lint` blokerer brud på 1):**",
        "1. Enhver ny skriver skal stå i registret: under sit kravs `skrivere:` eller i `skrivere:` (rolle + via).",
        f"2. Ny låner = nyt krav på sin rang med `aflevering:` — og den skriver KUN når ejer = dens id"
        f" (`wait_template` på `{reg['ejer_sensor']}`), ellers maler enforceren over den.",
        f"3. Husets udseende males kun af `{k_['maler'].split('#')[1]}`; blink/kvitteringer kun via"
        f" `{k_['signal'].split('#')[1]}` (queued).",
        "4. Aflevering = slip dit flag. Enforceren (`aflevering: maal`) eller genoptag maler næste ejer."
        " Aldrig restore af et snapshot (fejlklasse #27).",
        "5. Rum-logik og grupper må tænde/slukke lampen, aldrig sætte dens udseende (`sensor.lys_ejerskab`).",
        "6. Ændrer du en rang eller et `naar`: kør `gen`, deploy, og tjek `sensor.<…>_ejer` live.",
        "",
        f"Kendte huller (baseline, må kun skrumpe): {len(huller)} — se `huller:` i registret.",
    ]
    return "\n".join(out) + "\n"


def gen_index_json(regs):
    idx = {}
    for r in regs:
        match = [r["entity"], r["ejer_sensor"], r["laant_sensor"]]
        match += r.get("alias_grupper") or []
        match += [v.split("#")[1] for v in (r.get("kanaler") or {}).values()]
        _sites, grupper = scan(r["entity"])
        idx[r["entity"]] = {
            "match": sorted(set(match)),
            "grupper": grupper,
            "kontrakt": f"docs/auto/ejerskab/{r['_slug']}.md",
            "register": r["_src"],
        }
    return json.dumps(idx, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def generated_files():
    regs = load_registries()
    files = {}
    for r in regs:
        files[f"packages/ejerskab_{r['_slug']}.yaml"] = gen_package(r)
        files[f"docs/auto/ejerskab/{r['_slug']}.md"] = gen_contract(r)
    files["packages/ejerskab_index.yaml"] = gen_index(regs)
    files["docs/auto/ejerskab/index.json"] = gen_index_json(regs)
    return files


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "lint"
    if cmd == "gen":
        for path, content in generated_files().items():
            full = os.path.join(ROOT, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            print("skrev", path)
        return 0
    if cmd == "check":
        stale = []
        for path, content in generated_files().items():
            full = os.path.join(ROOT, path)
            cur = open(full, encoding="utf-8").read() if os.path.exists(full) else None
            if cur != content:
                stale.append(path)
        for p in stale:
            print(
                f"❌ {p} er ikke genereret fra det nuværende register → kør `python3 scripts/ejerskab.py gen`"
            )
        return 1 if stale else 0
    if cmd == "lint":
        errs = lint(argv[2:] or None)
        for e in errs:
            print(e)
        return 1 if errs else 0
    if cmd == "steder":
        sites, groups = scan(argv[2])
        print("grupper:", ", ".join(groups))
        for s, h in sorted(sites.items()):
            print(f"{s}\n    {'; '.join(h)}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
