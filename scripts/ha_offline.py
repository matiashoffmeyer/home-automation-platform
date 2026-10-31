#!/usr/bin/env python3
"""Home Assistant in a bottle: Home Assistant's own loader, validator and runtime, run against the repository without the host, devices or secrets.

Why it exists (docs/konsolidering.md, docs/adr/0005-offline-validation.md):

- An automation that fails validation is silently disabled (failure class #22
  in docs/fejlklasser.md), and one invalid sensor drops the whole ``template:``
  block of its file. Both used to surface only after a deploy. Home Assistant's
  own validator catches them: replayed against seven earlier incidents,
  it would have caught five before the commit.
- ``ha core check`` had been abandoned because check_config in 2026.4 forgot
  to set up the trigger helper (``KeyError: 'triggers'``). That was fixed
  upstream in 2026.9.2 and is shimmed here for older versions.
- A refactor can be *proven* behaviour-neutral: if the resolved configuration
  (after ``!include`` and the package merge) is identical before and after,
  Home Assistant has nothing to run differently.

Subcommands:
  check   [--rev R]                check_config plus log classification (~15 s)
  equiv   REV_A [REV_B]            diff of the resolved config (default B = working tree)
  staging [--rev R] [--wait 45]    boot the house headless as a fresh, sanitized install
  refs    [--rev R]                entity references that do not exist (staging + production list)
  slugcheck                        prove that scripts/ha_slug.py equals Home Assistant's slugify

Without ``--rev`` the working tree is used, including uncommitted changes and
excluding everything git-ignored: ``secrets.yaml``, ``.storage`` and ``.env``
never enter the copy, and ``!secret`` lookups get the placeholders from
``secrets.example.yaml`` instead.

The first run builds ``.cache/ha-offline/venv-<version>`` with uv (1-2 min,
about 1.1 GB; ``HA_OFFLINE_CACHE=/path`` moves it). The version is pinned in
``scripts/ha_offline_version.txt`` and must equal production. Before a core
update, ``--version <new>`` tests the house against the new core.

Exit codes: 0 clean, 1 problems found, 3 the venv could not be built.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Venv'et fylder ~1,1 GB. `.cache/*` er udelukket fra HA's backups (verificeret
# i core 2026.9.2: backup/const.py EXCLUDE_FROM_BACKUP), men på NUC'en kan det
# placeres uden for /config med HA_OFFLINE_CACHE=/sti.
CACHE = Path(os.environ.get("HA_OFFLINE_CACHE") or REPO / ".cache" / "ha-offline")
VERSION_FILE = REPO / "scripts" / "ha_offline_version.txt"
PROD_ENTITY_LIST = REPO / "config_snapshots" / "entity_ids.txt"
NEVER_COPY = {
    "secrets.yaml",
    ".env",
    ".env.local",
    ".storage",
    "home-assistant_v2.db",
    "zigbee.db",
    ".HA_VERSION",
}

# --------------------------------------------------------------------------
# Bootstrap: kør os selv i et venv med den rigtige HA-version
# --------------------------------------------------------------------------


def wanted_version(cli: str | None) -> str:
    if cli:
        return cli
    if os.environ.get("HA_OFFLINE_VERSION"):
        return os.environ["HA_OFFLINE_VERSION"]
    for line in VERSION_FILE.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            return line
    sys.exit("scripts/ha_offline_version.txt er tom")


def _venv_python(venv: Path) -> Path:
    win = venv / "Scripts" / "python.exe"
    return win if win.exists() else venv / "bin" / "python"


def _find_uv() -> str | None:
    for cand in (shutil.which("uv"), str(Path.home() / ".local" / "bin" / "uv")):
        if cand and Path(cand).exists():
            return cand
    return None


# Integrationer hvis krav SKAL ligge i venv'et før boot. HA installerer ellers
# integrations-krav selv under opstart (skip_pip=False), men lykkes det ikke —
# målt i den offentlige CI 30/10 på et frisk venv — melder hver stemme-
# automation "Integration 'conversation' does not provide trigger support" og
# checket fejler på noget der ikke er en fejl i huset.
PREINSTALL_DOMAINS = ("conversation",)


def _preinstall_requirements(venv: Path, uv: str | None) -> None:
    """Installér PREINSTALL_DOMAINS' manifest-krav, én gang pr. venv."""
    marker = venv / ".preinstalled"
    if marker.exists():
        return
    py = _venv_python(venv)
    code = (
        "import json, sys, homeassistant.components as c, pathlib\n"
        "base = pathlib.Path(c.__file__).parent\n"
        "for d in sys.argv[1:]:\n"
        "    print(*json.loads((base / d / 'manifest.json').read_text()).get('requirements', []), sep='\\n')"
    )
    r = subprocess.run([str(py), "-c", code, *PREINSTALL_DOMAINS], capture_output=True, text=True)
    reqs = r.stdout.split() if r.returncode == 0 else []
    # HA's eget venv har uv som afhængighed — brug den, hvis ingen uv på PATH.
    uv = uv or str(venv / "bin" / "uv")
    if (
        reqs
        and subprocess.run([uv, "pip", "install", "-q", "--python", str(py), *reqs]).returncode == 0
    ):
        marker.write_text("\n".join(reqs) + "\n")
    else:
        print(f"⚠️ kunne ikke forudinstallere {', '.join(PREINSTALL_DOMAINS)}-krav", file=sys.stderr)


def ensure_venv(version: str) -> Path:
    venv = CACHE / f"venv-{version}"
    py = _venv_python(venv)
    if py.exists():
        _preinstall_requirements(venv, _find_uv())
        return py
    uv = _find_uv()
    if not uv:
        print(
            "❌ uv mangler. Installér: `pip install --user -U uv` (eller "
            "`curl -LsSf https://astral.sh/uv/install.sh | sh`).",
            file=sys.stderr,
        )
        sys.exit(3)
    print(
        f"🔧 Bygger {venv} (homeassistant=={version}) — engangs, ~1-2 min, ~1,1 GB …",
        file=sys.stderr,
    )
    CACHE.mkdir(parents=True, exist_ok=True)
    # Et venv hvis python-link peger ud i ingenting (fortolkeren er opdateret
    # væk) afviser `uv venv` at overskrive — ryd det og byg forfra.
    shutil.rmtree(venv, ignore_errors=True)
    env = dict(os.environ, UV_PYTHON_DOWNLOADS="automatic")
    # HA 2026.x kræver Python >= 3.14.2. En gammel uv kender kun 3.14-rc'er →
    # `pip install --user -U uv` hvis den fejler her.
    steps = [
        [uv, "venv", "-q", "--python", ">=3.14.2", str(venv)],
        [
            uv,
            "pip",
            "install",
            "-q",
            "--python",
            str(_venv_python(venv)),
            f"homeassistant=={version}",
        ],
    ]
    for cmd in steps:
        r = subprocess.run(cmd, env=env)
        if r.returncode != 0:
            shutil.rmtree(venv, ignore_errors=True)
            print(
                f"❌ Fejlede: {' '.join(cmd)}\n   Er uv for gammel til Python 3.14.2+? "
                "`pip install --user -U uv` og prøv igen.",
                file=sys.stderr,
            )
            sys.exit(3)
    _preinstall_requirements(venv, uv)
    return _venv_python(venv)


def reexec_in_venv(version: str) -> None:
    """Kører vi ikke allerede i det rigtige venv, så hop derind."""
    # Native Windows kan ikke køre HA (runner.py importerer fcntl). Stop FØR
    # venv'et bygges: et venv på disk får pre-push-hooken til at køre check,
    # og et check der crasher blokerer hvert push fra PC'en.
    if sys.platform == "win32":
        print(
            "❌ HA kører ikke på native Windows (runner.py importerer fcntl). "
            "Brug Docker — opskrift i docs/konsolidering.md §3, punkt 3.",
            file=sys.stderr,
        )
        sys.exit(3)
    if os.environ.get("HA_OFFLINE_INNER") == version:
        return
    try:
        from homeassistant.const import __version__ as have  # noqa: PLC0415

        if have == version:
            return
    except Exception:  # noqa: BLE001
        pass
    py = ensure_venv(version)
    env = dict(os.environ, HA_OFFLINE_INNER=version)
    r = subprocess.run([str(py), str(Path(__file__).resolve()), *sys.argv[1:]], env=env)
    sys.exit(r.returncode)


# --------------------------------------------------------------------------
# Materialisering: et rent config-træ i en temp-mappe
# --------------------------------------------------------------------------


def materialize(rev: str | None, dest: Path) -> Path:
    """Kopiér repoet (en rev eller working tree) til dest — aldrig secrets."""
    dest.mkdir(parents=True, exist_ok=True)
    if rev:
        arch = subprocess.run(
            ["git", "-C", str(REPO), "archive", rev], capture_output=True, check=True
        ).stdout
        subprocess.run(["tar", "-x", "-C", str(dest)], input=arch, check=True)
    else:
        files = (
            subprocess.run(
                ["git", "-C", str(REPO), "ls-files", "-z", "-co", "--exclude-standard"],
                capture_output=True,
                check=True,
            )
            .stdout.decode()
            .split("\0")
        )
        for rel in files:
            if not rel:
                continue
            src = REPO / rel
            if not src.is_file():
                continue  # slettet men stadig i index
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
    for name in NEVER_COPY:  # livrem + seler
        p = dest / name
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()
    # !secret i configuration.yaml/packages kræver en secrets.yaml. Kopien får
    # kontraktens pladsholdere (secrets.example.yaml), aldrig de ægte værdier.
    example = dest / "secrets.example.yaml"
    if example.is_file():
        shutil.copy2(example, dest / "secrets.yaml")
    # ZHA's custom_quirks_path er absolut (/config/...). Peg den ind i kopien,
    # ellers fejler schemaet på "not a directory" i hvert miljø uden /config.
    conf = dest / "configuration.yaml"
    if conf.exists():
        txt = conf.read_text(encoding="utf-8")
        conf.write_text(
            txt.replace("/config/custom_zha_quirks", str(dest / "custom_zha_quirks")),
            encoding="utf-8",
        )
    return dest


# --------------------------------------------------------------------------
# Log-opsamling og -klassificering
# --------------------------------------------------------------------------

ERROR_PATTERNS = [
    r"Invalid config for",
    r"could not be validated",
    r"failed to setup",
    r"has been disabled",
    r"Invalid domain",
    r"Error loading .*\.yaml",
    r"must be configured under its own",
    r"setup failed",
    r"duplicate key",
    r"Package .* setup failed",
    r"Unexpected error calling config validator",
]
WARN_PATTERNS = [r"deprecat", r"will be removed", r"no longer supported"]
IGNORE_PATTERNS = [
    r"turbojpeg",
    r"TurboJPEG",
    r"zlib_ng",
    r"Attempting install of",
    r"zhaquirks",
    r"Detected blocking call",
    r"We found a custom integration",
]
# Kendte begrænsninger i staging: integrationer der kun findes som config
# entries (.storage) i prod. En automation med en mqtt-trigger kan ikke sættes
# op uden MQTT-entry'en — det er staging, ikke en fejl i huset.
STAGING_LIMITS = [
    r"Integration 'mqtt' does not provide trigger support",
    # weather.get_forecasts m.fl. mod en device der kun findes i prod
    r"Service call requested response data but did not match any entities",
]


def classify(msg: str) -> str | None:
    if any(re.search(p, msg) for p in IGNORE_PATTERNS):
        return None
    if any(re.search(p, msg) for p in STAGING_LIMITS):
        return "BEGRÆNSNING"
    if any(re.search(p, msg) for p in ERROR_PATTERNS):
        return "FEJL"
    if any(re.search(p, msg, re.I) for p in WARN_PATTERNS):
        return "ADVARSEL"
    return None


def trim(msg: str, n: int = 320) -> str:
    msg = msg.split(". Got ", 1)[0].split(" Got {", 1)[0]
    msg = " ".join(msg.split())
    return msg if len(msg) <= n else msg[: n - 1] + "…"


def _log_collector():
    import logging  # noqa: PLC0415

    class Collector(logging.Handler):
        def __init__(self):
            super().__init__(level=logging.WARNING)
            self.records: list[logging.LogRecord] = []

        def emit(self, record):
            self.records.append(record)

    col = Collector()
    root = logging.getLogger()
    root.addHandler(col)
    root.setLevel(logging.WARNING)
    # Ingen konsol-støj fra HA selv; vi rapporterer det klassificerede.
    for h in list(root.handlers):
        if h is not col:
            root.removeHandler(h)
    return col


# --------------------------------------------------------------------------
# Rå, resolved config (includes + packages) — fælles for check/equiv/refs
# --------------------------------------------------------------------------


async def load_resolved(cfg_dir: Path) -> dict:
    from homeassistant import core, loader  # noqa: PLC0415
    from homeassistant.config import load_yaml_config_file, merge_packages_config  # noqa: PLC0415
    from homeassistant.util.yaml.loader import Secrets  # noqa: PLC0415

    hass = core.HomeAssistant(str(cfg_dir))
    loader.async_setup(hass)
    cfg = load_yaml_config_file(str(cfg_dir / "configuration.yaml"), Secrets(cfg_dir))
    await merge_packages_config(hass, cfg, cfg.get("homeassistant", {}).get("packages", {}))
    await hass.async_stop(force=True)
    return cfg


LEGACY_TEMPLATE_DOMAINS = (
    "light",
    "cover",
    "switch",
    "fan",
    "lock",
    "vacuum",
    "alarm_control_panel",
    "weather",
)


def _fresh_install_snapshots(cfg: dict):
    """Alle `variables.snapshot` i init_user_preferences_first_boot (resolved)."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "variables" and isinstance(v, dict) and "snapshot" in v:
                    found.append(v["snapshot"])
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for item in cfg.get("automation") or []:
        if isinstance(item, dict) and item.get("id") == "init_user_preferences_first_boot":
            walk(item)
            return found
    return None  # automationen findes ikke


def static_lints(cfg: dict) -> list[tuple[str, str]]:
    """Ting HA's validator IKKE fanger, men som har kostet os en hændelse."""
    out = []
    # P1: `!include_dir_named` på en forkert sti giver {} UDEN fejl — så ville en
    # frisk install gendanne 0 sliders i stilhed (review 10-04, reproduceret).
    snaps = _fresh_install_snapshots(cfg)
    if snaps is not None:
        nums = [s.get("input_number") for s in snaps if isinstance(s, dict)]
        if not any(isinstance(n, dict) and n for n in nums):
            out.append(
                (
                    "FEJL",
                    "init_user_preferences_first_boot: fresh-install-snapshottet "
                    "giver 0 sliders — er `!include_dir_named ../config_snapshots/fresh_install` "
                    "brudt (sti, filnavn, include-type), eller mangler "
                    "config_snapshots/fresh_install/input_number.yaml?",
                )
            )
    # d7c39571: core 2026.9 fjernede `<domain>: - platform: template`. De tre
    # open-plan-gardiner forsvandt uden en eneste fejl i check_config.
    for dom in LEGACY_TEMPLATE_DOMAINS:
        for item in cfg.get(dom) or []:
            if isinstance(item, dict) and item.get("platform") == "template":
                src = getattr(item, "__config_file__", "?")
                out.append(
                    (
                        "FEJL",
                        f"legacy `{dom}: - platform: template` i "
                        f"{_rel(src)} — fjernet i core 2026.9 (d7c39571); flyt "
                        "til `template:`-nøglen, og bevar entity_id via name:",
                    )
                )
    return out


def _rel(path) -> str:
    s = str(path)
    m = re.search(r"/(automations|packages|script_pkg|scene_snapshots|dashboards)/.*", s)
    return m.group(0).lstrip("/") if m else os.path.basename(s)


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


async def _check_async(cfg_dir: Path) -> list[tuple[str, str]]:
    import inspect  # noqa: PLC0415

    from homeassistant.helpers import check_config as hcc  # noqa: PLC0415
    from homeassistant.scripts import check_config as scc  # noqa: PLC0415

    col = _log_collector()
    orig = scc.async_check_ha_config_file
    if "trigger.async_setup" not in inspect.getsource(hcc.async_check_ha_config_file):
        # Core < 2026.9.2: check_config satte aldrig trigger-/condition-helperen
        # op → KeyError 'triggers' og HELE automation/template/script-sektionen
        # blev "Unexpected error". Det er buggen bag "ha core check er buggy".
        from homeassistant.helpers import condition, trigger  # noqa: PLC0415

        async def shimmed(hass):
            for mod, names in (
                (
                    trigger,
                    (
                        "TRIGGER_DESCRIPTION_CACHE",
                        "TRIGGER_DISABLED_TRIGGERS",
                        "TRIGGER_PLATFORM_SUBSCRIPTIONS",
                        "TRIGGERS",
                    ),
                ),
                (
                    condition,
                    (
                        "CONDITION_DESCRIPTION_CACHE",
                        "CONDITION_DISABLED_CONDITIONS",
                        "CONDITION_PLATFORM_SUBSCRIPTIONS",
                        "CONDITIONS",
                    ),
                ),
            ):
                for name in names:
                    key = getattr(mod, name, None)
                    if key is not None and key not in hass.data:
                        hass.data[key] = (
                            set() if "DISABLED" in name else [] if "SUBSCRIPTIONS" in name else {}
                        )
            return await orig(hass)

        scc.async_check_ha_config_file = shimmed
    res = await scc.async_check_config(str(cfg_dir))
    scc.async_check_ha_config_file = orig

    findings: list[tuple[str, str]] = []
    for err in res.errors:
        if not err.message.strip() or any(re.search(p, err.message) for p in IGNORE_PATTERNS):
            continue
        level = "BEGRÆNSNING" if classify(err.message) == "BEGRÆNSNING" else "FEJL"
        findings.append((level, trim(f"[{err.domain}] {err.message}")))
    for w in res.warnings:
        if not any(re.search(p, w.message) for p in IGNORE_PATTERNS):
            findings.append(("ADVARSEL", trim(f"[{w.domain}] {w.message}")))
    for rec in col.records:
        msg = rec.getMessage()
        level = classify(msg)
        if level:
            findings.append((level, trim(msg)))
    findings += static_lints(await load_resolved(cfg_dir))
    # samme besked kan logges flere gange (package-merge + validering)
    seen, uniq = set(), []
    for f in findings:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def cmd_check(args) -> int:
    import asyncio  # noqa: PLC0415

    from homeassistant.const import __version__  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="ha-check-") as tmp:
        cfg = materialize(args.rev, Path(tmp) / "config")
        findings = asyncio.run(_check_async(cfg))
    errs = [f for f in findings if f[0] == "FEJL"]
    warns = [f for f in findings if f[0] == "ADVARSEL"]
    limits = [f for f in findings if f[0] == "BEGRÆNSNING"]
    if args.json:
        print(
            json.dumps(
                {
                    "version": __version__,
                    "errors": [m for _, m in errs],
                    "warnings": [m for _, m in warns],
                    "offline_limits": [m for _, m in limits],
                },
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        for lvl, msg in errs + (warns if not args.quiet else []):
            print(f"{'❌' if lvl == 'FEJL' else '⚠️ '} {msg}")
        src = args.rev or "working tree"
        lim = f", {len(limits)} offline-begrænsninger (mqtt-triggers)" if limits else ""
        print(
            f"{'❌' if errs else '✅'} ha_offline check ({src}, core {__version__}): "
            f"{len(errs)} fejl, {len(warns)} advarsler{lim}"
        )
    return 1 if errs else 0


# --------------------------------------------------------------------------
# equiv — bevis at et refactor ikke ændrer hvad HA ser
# --------------------------------------------------------------------------

# Lister hvor rækkefølgen IKKE betyder noget for HA (de merges fra mange filer).
# Alt andet — action-sekvenser især — sammenlignes MED rækkefølge.
UNORDERED_TOP = {
    "automation",
    "template",
    "sensor",
    "binary_sensor",
    "light",
    "cover",
    "switch",
    "scene",
    "zone",
    "command_line",
    "notify",
    "fan",
    "lock",
}
TEMPLATE_ENTITY_KEYS = {
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
    "trigger",
    "triggers",
}


def canon(x):
    if isinstance(x, dict):
        return {str(k): canon(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [canon(v) for v in x]
    if isinstance(x, bool) or x is None or isinstance(x, (int, float)):
        return x
    return str(x)


def _key(item, dom: str) -> str:
    if isinstance(item, dict):
        if dom == "automation":
            return f"id={item.get('id') or item.get('alias')}"
        if dom == "template":
            ids = sorted(
                str(e.get("unique_id") or e.get("name"))
                for k in TEMPLATE_ENTITY_KEYS - {"trigger", "triggers"}
                for e in (item.get(k) or [])
                if isinstance(e, dict)
            )
            if ids:
                return "entities=" + ",".join(ids)
        if item.get("unique_id") or item.get("name"):
            return f"{item.get('platform', '')}:{item.get('unique_id') or item.get('name')}"
    return "hash=" + json.dumps(item, sort_keys=True, ensure_ascii=False)[:80]


FRESH_KEY = "__fresh_install_data__"


def _extract_fresh_install(cfg: dict) -> None:
    """Flyt init_user_preferences' !include'de snapshot-data ud af automationen.

    Siden P1 er fresh-install-defaulterne DATA i en automation — hver
    helpers_export.py ville ellers ligne en adfærds-ændring i equiv. KUN
    slider-værdierne under snapshot.input_number er data; snapshottets FORM
    (findes input_number, er den tom, andre nøgler) bliver i automationen og
    tæller som kode — ellers bestod en brudt include-sti (= 0 gendannede
    sliders) som "ækvivalent" (review 10-04, reproduceret)."""
    data = {}

    def walk(node):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k == "variables" and isinstance(v, dict) and isinstance(v.get("snapshot"), dict):
                    snap = v["snapshot"]
                    nums = snap.get("input_number")
                    form = {sk: sv for sk, sv in snap.items() if sk != "input_number"}
                    if isinstance(nums, dict) and nums:
                        data.update(nums)
                        form["input_number"] = "<slider-værdier: data>"
                    elif "input_number" in snap:
                        form["input_number"] = nums  # tom/ugyldig = kode-forskel
                    v["snapshot"] = form
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for item in cfg.get("automation") or []:
        if isinstance(item, dict) and item.get("id") == "init_user_preferences_first_boot":
            walk(item)
    cfg[FRESH_KEY] = data


def normalize(cfg: dict) -> dict:
    cfg = canon(cfg)
    _extract_fresh_install(cfg)
    core_cfg = cfg.get("homeassistant")
    if isinstance(core_cfg, dict):
        core_cfg.pop("packages", None)  # allerede merget ind i domænerne
    if isinstance(cfg.get("zha"), dict) and "custom_quirks_path" in cfg["zha"]:
        cfg["zha"]["custom_quirks_path"] = "<materialize>/custom_zha_quirks"
    for dom in list(cfg):
        val = cfg[dom]
        base = dom.split(" ")[0]
        if base == "template" and isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    for k in TEMPLATE_ENTITY_KEYS - {"trigger", "triggers"}:
                        if isinstance(item.get(k), list):
                            item[k] = sorted(item[k], key=lambda e: json.dumps(e, sort_keys=True))
        if base in UNORDERED_TOP and isinstance(val, list):
            keyed: dict[str, object] = {}
            for item in val:
                k = _key(item, base)
                while k in keyed:  # dubletter skal også kunne ses
                    k += "'"
                keyed[k] = item
            cfg[dom] = dict(sorted(keyed.items()))
    return cfg


def _snip(v, around: int | None = None) -> str:
    t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)
    t = " ".join(t.split())
    if around is None or len(t) <= 110:
        return t[:110] + ("…" if len(t) > 110 else "")
    lo = max(0, around - 40)
    return ("…" if lo else "") + t[lo : lo + 110] + ("…" if lo + 110 < len(t) else "")


def diff(a, b, path="", out=None, limit=200):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if len(out) >= limit:
                break
            p = f"{path}.{k}" if path else k
            if k not in a:
                out.append(f"+ {p}: {_snip(b[k])}")
            elif k not in b:
                out.append(f"- {p}: {_snip(a[k])}")
            else:
                diff(a[k], b[k], p, out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                diff(x, y, f"{path}[{i}]", out, limit)
            return out
        import difflib  # noqa: PLC0415

        ja = [json.dumps(x, sort_keys=True, ensure_ascii=False) for x in a]
        jb = [json.dumps(x, sort_keys=True, ensure_ascii=False) for x in b]
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, ja, jb, autojunk=False
        ).get_opcodes():
            if op == "equal":
                continue
            if op == "replace" and i2 - i1 == j2 - j1:
                for k in range(i2 - i1):
                    diff(a[i1 + k], b[j1 + k], f"{path}[{i1 + k}]", out, limit)
                continue
            for i in range(i1, i2):
                if len(out) < limit:
                    out.append(f"- {path}[{i}]: {_snip(a[i])}")
            for j in range(j1, j2):
                if len(out) < limit:
                    out.append(f"+ {path}[{j}]: {_snip(b[j])}")
    elif a != b:
        if isinstance(a, str) and isinstance(b, str):
            i = next((n for n, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            i = len(" ".join(a[:i].split()))  # samme whitespace-foldning som _snip
            out.append(f"~ {path}: {_snip(a, i)}  →  {_snip(b, i)}")
        else:
            out.append(f"~ {path}: {_snip(a)}  →  {_snip(b)}")
    return out


def cmd_equiv(args) -> int:
    import asyncio  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="ha-equiv-") as tmp:
        a = normalize(asyncio.run(load_resolved(materialize(args.rev_a, Path(tmp) / "a"))))
        b = normalize(asyncio.run(load_resolved(materialize(args.rev_b, Path(tmp) / "b"))))
    fa, fb = a.pop(FRESH_KEY, {}), b.pop(FRESH_KEY, {})
    d = diff(a, b)
    label_b = args.rev_b or "working tree"
    if fa != fb:
        added = sorted(set(fb) - set(fa))
        removed = sorted(set(fa) - set(fb))
        changed = sorted(k for k in set(fa) & set(fb) if fa[k] != fb[k])
        note = (
            f"ℹ️  fresh-install-slider-værdier: +{len(added)} / −{len(removed)} / "
            f"~{len(changed)} (data fra helpers_export, ikke kode)"
        )
        if args.strict:
            d += [f"+ fresh_install.{k}: {fb[k]}" for k in added]
            d += [f"- fresh_install.{k}: {fa[k]}" for k in removed]
            d += [f"~ fresh_install.{k}: {fa[k]}  →  {fb[k]}" for k in changed]
        else:
            print(note + " (vis/tæl med --strict)")
            if removed:
                print(
                    f"⚠️  {len(removed)} sliders mister deres fresh-install-værdi: "
                    + ", ".join(removed[:6])
                    + (" …" if len(removed) > 6 else "")
                )
    if not d:
        n = sum(len(v) if isinstance(v, (dict, list)) else 1 for v in a.values())
        print(
            f"✅ Ækvivalent: {args.rev_a} og {label_b} giver HA præcis samme config "
            f"({len(a)} domæner, {n} elementer). Refactoret er adfærds-neutralt."
        )
        return 0
    for line in d:
        print(line)
    more = " (afkortet)" if len(d) >= 200 else ""
    print(
        f"❌ {len(d)} forskelle{more} mellem {args.rev_a} og {label_b}. "
        "Hver linje er en ADFÆRDS-ændring der skal kunne forsvares."
    )
    return 1


# --------------------------------------------------------------------------
# staging — boot huset headless som en frisk installation
# --------------------------------------------------------------------------

# Alt der kan række UD af containeren eller binde en port, fjernes efter load.
# Kører staging på NUC'en, peger shell_command-stierne på den ÆGTE /config —
# derfor skal de væk, ikke bare "fejle fordi secrets mangler".
STRIP_DOMAINS = {
    "shell_command",
    "rest_command",
    "command_line",
    "notify",
    "zha",
    "mobile_app",
    "lovelace",
    "frontend",
    "http",
    "history",
    "logbook",
    "logger",
    "hassio",
    "panel_iframe",
    "panel_custom",
    "tts",
    "cloud",
}
STRIP_PLATFORMS = {"rest", "command_line", "scrape"}
STRIP_ENV = ("SUPERVISOR", "SUPERVISOR_TOKEN", "HASSIO_TOKEN", "HA_TOKEN")


async def _staging_async(cfg_dir: Path, wait_s: int) -> dict:
    import asyncio  # noqa: PLC0415

    from homeassistant import bootstrap, runner  # noqa: PLC0415
    from homeassistant import config as conf_util  # noqa: PLC0415
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    orig = conf_util.async_hass_config_yaml
    stubs: set[tuple[str, str]] = {("logbook", "log")}

    async def sanitized(hass):
        cfg = await orig(hass)
        for dom in list(cfg):
            base = dom.split(" ")[0]
            if base in ("shell_command", "rest_command") and isinstance(cfg[dom], dict):
                stubs.update((base, k) for k in cfg[dom])
            if base in STRIP_DOMAINS:
                cfg.pop(dom)
        # notify.<x> kaldes af hundredvis af veje; uden en stub aborterer HELE
        # scriptet på "Action not found" og staging opfører sig ikke som prod.
        txt = json.dumps(canon(cfg), ensure_ascii=False)
        stubs.update(("notify", m) for m in set(re.findall(r"notify\.([a-z0-9_]+)", txt)))
        for dom, val in list(cfg.items()):
            if isinstance(val, list):
                cfg[dom] = [
                    x
                    for x in val
                    if not (isinstance(x, dict) and x.get("platform") in STRIP_PLATFORMS)
                ]
        # Recorderen i temp-mappen: history_stats/statistics/utility_meter
        # afhænger af den, og intet må skrives til en ægte database. (In-memory
        # `sqlite://` afvises af recorderen siden 2026.x.)
        cfg["recorder"] = {"db_url": f"sqlite:///{cfg_dir / 'staging_v2.db'}"}
        return cfg

    conf_util.async_hass_config_yaml = sanitized
    bootstrap.conf_util.async_hass_config_yaml = sanitized

    rc = runner.RuntimeConfig(
        config_dir=str(cfg_dir),
        skip_pip=False,
        safe_mode=False,
        recovery_mode=False,
        verbose=False,
        log_rotate_days=None,
        log_file=str(cfg_dir / "staging.log"),
        log_no_color=True,
    )
    hass = await bootstrap.async_setup_hass(rc)
    if hass is None:
        return {"boot_failed": True}
    # Stubs for de services vi fjernede: no-op, men kaldet huskes, så rapporten
    # kan sige "ved en frisk start ville huset have pushet/kørt X".
    from homeassistant.core import SupportsResponse  # noqa: PLC0415

    calls: list[str] = []

    async def _stub(call):
        calls.append(f"{call.domain}.{call.service}")
        # rest_command-kald med response_variable kræver et svar; et tomt svar
        # opfører sig som en fejlet poll, ikke som et manglende service.
        return {"status": 0, "content": {}, "headers": {}} if call.return_response else None

    for dom, svc in sorted(stubs):
        if not hass.services.has_service(dom, svc):
            hass.services.async_register(
                dom, svc, _stub, supports_response=SupportsResponse.OPTIONAL
            )
    run_task = asyncio.create_task(hass.async_run())
    # Loft på ventetiden: block_till_done venter på HVER kørende automation-run.
    # 2026-10-04 20:02 hang `refs` i 10+ min (genkørsel: 43 s); mistænkt årsag
    # er en automation der gik i en lang delay/wait ved boot — ikke bevist.
    # Rammer vi loftet, står de kørende tasks i staging.log.
    try:
        await asyncio.wait_for(hass.async_block_till_done(), timeout=60)
    except TimeoutError:
        import logging  # noqa: PLC0415

        pending = sorted({t.get_name() for t in asyncio.all_tasks() if not t.done()})
        logging.getLogger("ha_offline").warning(
            "block_till_done ramte 60 s-loftet; kørende tasks: %s", ", ".join(pending)[:2000]
        )
    await asyncio.sleep(wait_s)  # init_user_preferences venter selv 30 s
    states = {s.entity_id: s.as_dict() for s in hass.states.async_all()}
    reg = er.async_get(hass)
    registry = {
        e.entity_id: {"platform": e.platform, "unique_id": e.unique_id}
        for e in reg.entities.values()
    }
    services = {d: sorted(v) for d, v in hass.services.async_services().items()}
    await hass.async_stop()
    run_task.cancel()
    return {"states": states, "registry": registry, "stub_calls": calls, "services": services}


def _expected_template_entities(cfg: dict) -> list[tuple[str, str, str]]:
    """(domain, unique_id, name) for hver template-entity med unique_id."""
    out = []
    for dom, val in cfg.items():
        if dom.split(" ")[0] != "template" or not isinstance(val, list):
            continue
        for block in val:
            if not isinstance(block, dict):
                continue
            for k in TEMPLATE_ENTITY_KEYS - {"trigger", "triggers"}:
                for ent in block.get(k) or []:
                    if isinstance(ent, dict) and ent.get("unique_id"):
                        out.append((k, str(ent["unique_id"]), str(ent.get("name", ""))))
    return out


def _quiet_blocking_detector() -> None:
    """HA patcher open() med en blocking-call-detektor der bliver hængende efter
    at loopet er stoppet; vores egne fil-læsninger bagefter er ikke HA's sag."""
    import logging  # noqa: PLC0415

    logging.getLogger("homeassistant.util.loop").setLevel(logging.CRITICAL)


def _service_refs(node, out: list, src: str = "?") -> list:
    """Alle statiske `service:`/`action:`-kald i den resolvede config + kilde."""
    if isinstance(node, dict):
        src = (
            f"{_rel(getattr(node, '__config_file__', src))}:{getattr(node, '__line__', '?')}"
            if hasattr(node, "__config_file__")
            else src
        )
        for key in ("service", "action"):
            val = node.get(key)
            if isinstance(val, str) and re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", val):
                out.append((val, src))
        for v in node.values():
            _service_refs(v, out, src)
    elif isinstance(node, list):
        for v in node:
            _service_refs(v, out, src)
    return out


def _stripped_entity_ids(cfg: dict) -> set[str]:
    """entity_ids for de platforme staging fjerner (command_line, rest, …), så
    refs til dem ikke ligner fejl. Samme regel som HA: name: → slugify."""
    sys.path.insert(0, str(REPO / "scripts"))
    from ha_slug import slugify  # noqa: PLC0415

    out: set[str] = set()

    def add(dom, ent):
        if isinstance(ent, dict) and isinstance(ent.get("name"), str) and "{{" not in ent["name"]:
            out.add(f"{dom}.{slugify(ent['name'])}")

    for item in cfg.get("command_line") or []:
        if isinstance(item, dict):
            for k in ("sensor", "binary_sensor", "switch", "cover"):
                add(k, item.get(k))
    for item in cfg.get("rest") or []:
        if isinstance(item, dict):
            for k in ("sensor", "binary_sensor"):
                for ent in item.get(k) or []:
                    add(k, ent)
    for dom in ("sensor", "binary_sensor"):
        for ent in cfg.get(dom) or []:
            if isinstance(ent, dict) and ent.get("platform") in STRIP_PLATFORMS:
                add(dom, ent)
    return out


def run_staging(rev: str | None, wait_s: int, keep: bool, out_name: str = "staging") -> dict:
    import asyncio  # noqa: PLC0415

    for var in STRIP_ENV:
        os.environ.pop(var, None)
    # refs booter med 5 s ventetid (før init når at køre) og må derfor ALDRIG
    # overskrive en fuld staging-kørsels output — set 2026-10-04, hvor et
    # efterfølgende refs fik states.json til at ligne en init der aldrig kørte.
    out_dir = CACHE / out_name
    shutil.rmtree(out_dir, ignore_errors=True)
    tmp = Path(tempfile.mkdtemp(prefix="ha-staging-"))
    try:
        cfg_dir = materialize(rev, tmp / "config")
        raw = asyncio.run(load_resolved(cfg_dir))
        # HA logger til stderr OG til staging.log; terminalen skal kun have
        # vores klassificerede rapport, så fd 2 lånes væk mens huset kører.
        sys.stderr.flush()
        saved_fd = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
        try:
            result = asyncio.run(_staging_async(cfg_dir, wait_s))
        finally:
            sys.stderr.flush()
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
            os.close(devnull)
            _quiet_blocking_detector()
        result["expected_templates"] = _expected_template_entities(raw)
        result["service_refs"] = _service_refs(raw, [])
        result["stripped_ids"] = sorted(_stripped_entity_ids(raw))
        out_dir.mkdir(parents=True, exist_ok=True)
        log = cfg_dir / "staging.log"
        if log.exists():
            shutil.copy2(log, out_dir / "staging.log")
        if "states" in result:
            (out_dir / "states.json").write_text(
                json.dumps(result["states"], default=str, ensure_ascii=False)
            )
            (out_dir / "entity_ids.txt").write_text("\n".join(sorted(result["states"])) + "\n")
            (out_dir / "registry.json").write_text(json.dumps(result["registry"], indent=0))
        if keep:
            print(f"ℹ  staging-config bevaret i {cfg_dir}", file=sys.stderr)
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
    return result


def cmd_staging(args) -> int:
    from homeassistant.const import __version__  # noqa: PLC0415

    res = run_staging(args.rev, args.wait, args.keep)
    if res.get("boot_failed"):
        print("❌ staging bootede ikke — se .cache/ha-offline/staging/staging.log")
        return 1
    states, registry = res["states"], res["registry"]
    log_txt = (
        (CACHE / "staging" / "staging.log").read_text(errors="ignore")
        if (CACHE / "staging" / "staging.log").exists()
        else ""
    )

    errs, limits, warns = [], [], []
    # 1) Automations der ikke kunne sættes op = fejlklasse #22 (eller staging-begrænsning)
    for eid, st in sorted(states.items()):
        if eid.startswith(("automation.", "script.")) and st["state"] == "unavailable":
            alias = st["attributes"].get("friendly_name", eid)
            line = next(
                (
                    ln
                    for ln in log_txt.splitlines()
                    if f"'{alias}'" in ln and ("disabled" in ln or "failed" in ln)
                ),
                "",
            )
            if any(re.search(p, line) for p in STAGING_LIMITS):
                limits.append(f"{eid} (mqtt-trigger — MQTT findes kun som config entry i prod)")
            else:
                errs.append(
                    f"{eid} er unavailable (#22): {trim(line.split('] ', 1)[-1]) if line else '?'}"
                )
    # 2) Template-entities der aldrig blev oprettet = hele template-blokken faldt
    by_uid = {(v["platform"], v["unique_id"]): k for k, v in registry.items()}
    missing = [(d, u, n) for d, u, n in res["expected_templates"] if ("template", u) not in by_uid]
    for d, u, n in missing:
        errs.append(
            f"template-entity mangler: {d} unique_id={u} name={n!r} "
            "(blokken fejlede — søg 'Invalid config for template' i staging.log)"
        )
    # 3) Kald til services der ikke findes. Er DOMÆNET loadet i staging men
    #    servicen mangler, er det en stavefejl/ikke-eksisterende service (som
    #    input_datetime.set_value der væltede init i 2 mdr.). Er domænet slet
    #    ikke loadet (hassio, vacuum, mqtt …) kan staging ikke afgøre det.
    services = res.get("services", {})
    seen_svc = set()
    for svc, where in res.get("service_refs", []):
        dom, name = svc.split(".", 1)
        if dom in services and name not in services[dom] and svc not in seen_svc:
            seen_svc.add(svc)
            errs.append(f"service {svc} findes ikke (domænet {dom} er loadet)  ← {where}")
    for ln in log_txt.splitlines():
        m = re.search(r"^\d{4}-.*\] (.+?): .*Error executing script\. (.*)", ln)
        if m and not any(re.search(p, ln) for p in STAGING_LIMITS):
            miss = re.search(r"Action ([a-z_]+)\.([a-z0-9_]+) not found", ln)
            if miss and miss.group(1) not in services:
                limits.append(
                    f"{m.group(1)}: {miss.group(1)}.{miss.group(2)} (domænet findes kun i prod)"
                )
                continue
            errs.append(
                f"script/automation aborterede: {trim(m.group(1) + ': ' + m.group(2), 260)}"
            )
    # 4) Runtime-template-fejl ved opstart (kan være støj fra manglende devices)
    # Kun log-HOVEDER (tidsstempel-linjer) — ikke tracebackens gentagelser.
    # Mange af dem er staging-støj (en device-entity findes ikke), men en
    # template der vælter på `states.x.y.last_changed` ved opstart gør det
    # også i prod ved hver genstart, hvis x.y oprettes efter læseren.
    for ln in log_txt.splitlines():
        if re.match(r"^\d{4}-\d\d-\d\d ", ln) and re.search(
            r"Template variable error|TemplateError|UndefinedError|Error rendering", ln
        ):
            warns.append(trim(ln.split("] ", 1)[-1], 220))
    autos = [e for e in states if e.startswith("automation.")]
    for e in errs:
        print(f"❌ {e}")
    for w in sorted(set(warns))[:40]:
        print(f"⚠️  {w}")
    for li in dict.fromkeys(limits):
        print(f"ℹ️  staging-begrænsning: {li}")
    from collections import Counter  # noqa: PLC0415

    stub_calls = Counter(res.get("stub_calls", []))
    if stub_calls:
        top = ", ".join(f"{k}×{v}" for k, v in stub_calls.most_common(8))
        print(f"ℹ️  stubbede kald ved opstart (ville have ramt verden i prod): {top}")
    print(
        f"{'❌' if errs else '✅'} staging (core {__version__}, {args.rev or 'working tree'}): "
        f"{len(states)} entities, {len(autos)} automations, {len(errs)} fejl, "
        f"{len(set(warns))} runtime-advarsler, {len(set(limits))} kendte begrænsninger. "
        "Output: .cache/ha-offline/staging/"
    )
    return 1 if errs else 0


# --------------------------------------------------------------------------
# refs — refererer koden til entities der ikke findes?
# --------------------------------------------------------------------------

REF_DOMAINS = (
    "automation|binary_sensor|button|camera|climate|counter|cover|device_tracker|"
    "event|fan|group|image|input_boolean|input_button|input_datetime|input_number|"
    "input_select|input_text|light|lock|media_player|number|person|remote|scene|"
    "script|select|sensor|siren|sun|switch|text|time|timer|update|vacuum|valve|"
    "water_heater|weather|zone"
)
REF_RE = re.compile(rf"\b({REF_DOMAINS})\.([a-z0-9_]+)\b")
YAML_OWNED = (
    "input_boolean.",
    "input_number.",
    "input_select.",
    "input_text.",
    "input_datetime.",
    "input_button.",
    "script.",
    "timer.",
    "counter.",
)
# `perform_action: input_boolean.turn_on` m.fl. er service-navne, ikke entities.
SERVICE_VERBS = {
    "turn_on",
    "turn_off",
    "toggle",
    "select_option",
    "select_next",
    "select_previous",
    "select_first",
    "select_last",
    "set_value",
    "set_datetime",
    "press",
    "reload",
    "increment",
    "decrement",
    "reset",
    "start",
    "cancel",
    "finish",
    "pause",
    "change",
    "set_options",
    "create",
    "apply",
    "open_cover",
    "close_cover",
    "stop_cover",
    "set_cover_position",
}


_PROSE_KEYS = re.compile(r"^\s*-?\s*(description|alias):\s*(.*)$")


def scan_refs(root: Path) -> dict[str, list[str]]:
    """Entity-refs i koden. Falske positiver fundet af den lokale verifikation
    2026-10-04 (P9) er lukket uden at skjule ægte refs: prosa-felter (også deres
    `>`/`|`-blokke), Jinja-kommentarer (også flerlinjede), dot-stier
    (`trigger.event.data` — men `states.sensor.x` tæller stadig)."""
    refs: dict[str, list[str]] = {}
    for sub in (
        "automations",
        "packages",
        "script_pkg",
        "dashboards",
        "scene_snapshots",
        "rosters",
    ):
        for f in sorted((root / sub).glob("*.yaml")):
            text = f.read_text(encoding="utf-8", errors="ignore")
            # Jinja-kommentarer kan spænde over linjer; erstat dem med lige så
            # mange linjeskift, så linjenumrene passer.
            text = re.sub(r"\{#.*?#\}", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
            prose_indent = None
            for n, line in enumerate(text.splitlines(), 1):
                indent = len(line) - len(line.lstrip())
                if prose_indent is not None:
                    if line.strip() == "" or indent > prose_indent:
                        continue  # fortsættelse af en description: >-blok
                    prose_indent = None
                pm = _PROSE_KEYS.match(line)
                if pm:
                    if pm.group(2).strip() in (">", ">-", "|", "|-", ">+", "|+"):
                        prose_indent = indent
                    continue
                code = line.split(" #", 1)[0] if not line.lstrip().startswith("#") else ""
                if re.match(r"^\s*-?\s*(service|action):", code):
                    continue
                for m in REF_RE.finditer(code):
                    eid = f"{m.group(1)}.{m.group(2)}"
                    if m.group(2) in SERVICE_VERBS:
                        continue
                    if eid.endswith("_") or code[m.end() : m.end() + 2] == "{{":
                        continue  # templated navn: input_number.{{ x }}_foo
                    before = code[: m.start()]
                    if before.endswith(".") and not before.endswith("states."):
                        continue  # trigger.event.data, x.sensor.y …
                    refs.setdefault(eid, []).append(f"{sub}/{f.name}:{n}")
    return refs


def _scene_create_ids(root: Path) -> set[str]:
    """scene.<id> der oprettes runtime med scene.create (findes aldrig statisk)."""
    out = set()
    for sub in ("automations", "packages", "script_pkg"):
        for f in (root / sub).glob("*.yaml"):
            for m in re.finditer(
                r"scene_id:\s*['\"]?([a-z0-9_]+)['\"]?\s*$",
                f.read_text(encoding="utf-8", errors="ignore"),
                re.M,
            ):
                out.add(f"scene.{m.group(1)}")
    return out


def cmd_refs(args) -> int:
    res = run_staging(args.rev, 5, False, out_name="refs")
    if res.get("boot_failed"):
        print("❌ staging bootede ikke")
        return 1
    staging_ids = set(res["states"]) | set(res["registry"]) | set(res.get("stripped_ids", []))
    prod_ids = set()
    if PROD_ENTITY_LIST.exists():
        prod_ids = {
            ln.strip()
            for ln in PROD_ENTITY_LIST.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        }
    wl_file = REPO / "scripts" / "ha_validate_whitelist.txt"
    whitelist = (
        {ln.split("#", 1)[0].strip() for ln in wl_file.read_text().splitlines()}
        if wl_file.exists()
        else set()
    )
    # unique_id → det entity_id HA FAKTISK gav (fresh registration = name-slug)
    uid_to_eid = {}
    for eid, v in res["registry"].items():
        uid_to_eid[f"{eid.split('.')[0]}.{v['unique_id']}"] = eid
    known = staging_ids | prod_ids | whitelist
    root = REPO
    tmp = None
    if args.rev:
        tmp = Path(tempfile.mkdtemp(prefix="ha-refs-"))
        root = materialize(args.rev, tmp / "c")
    refs = scan_refs(root)
    known |= _scene_create_ids(root)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    errs, pinned, unsure = [], [], []
    for eid, where in sorted(refs.items()):
        if eid.endswith(".all"):
            continue
        at = f"← {where[0]}" + (f" (+{len(where) - 1})" if len(where) > 1 else "")
        actual = uid_to_eid.get(eid)
        if eid in known:
            if actual and actual != eid and eid in prod_ids:
                # Virker i prod (registry har låst det gamle navn), men en frisk
                # install/tabt .storage giver `actual` → hver ref brækker tavst.
                pinned.append(
                    f"{eid} virker kun fordi registry husker det; name: giver "
                    f"{actual} → pin med `default_entity_id: {eid}`  {at}"
                )
            continue
        if actual:
            msg = (
                f"{eid} bruger unique_id-formen; HA kalder den {actual} "
                f"(entity_id afledes af name:)  {at}"
            )
            if prod_ids:
                errs.append(msg)  # findes heller ikke i prod → ægte slug-fejl
            else:
                unsure.append(msg + "  [registry-låst i prod ELLER slug-fejl — kræver prod-liste]")
        elif eid.startswith(YAML_OWNED):
            errs.append(f"{eid} er ikke defineret nogen steder  {at}")
        elif prod_ids:
            errs.append(f"{eid} findes hverken i prod eller staging  {at}")
        else:
            unsure.append(None)
    for e in errs:
        print(f"❌ {e}")
    for e in pinned:
        print(f"⚠️  {e}")
    for e in (u for u in unsure if u):
        print(f"❓ {e}")
    devs = sum(1 for u in unsure if u is None)
    note = (
        ""
        if prod_ids
        else (
            f" {devs} device-refs kunne ikke afgøres og ❓-linjerne er uafklarede: "
            "config_snapshots/entity_ids.txt mangler — generér den lokalt (docs/konsolidering.md)."
        )
    )
    print(
        f"{'❌' if errs else '✅'} refs: {len(refs)} refererede entities, {len(errs)} fejl, "
        f"{len(pinned)} registry-låste.{note}"
    )
    return 1 if errs else 0


# --------------------------------------------------------------------------
# slugcheck — scripts/ha_slug.py skal være HA's slugify, bit for bit
# --------------------------------------------------------------------------


def cmd_slugcheck(args) -> int:
    from homeassistant.util import slugify as ha  # noqa: PLC0415

    sys.path.insert(0, str(REPO / "scripts"))
    from ha_slug import slugify as mine  # noqa: PLC0415

    names = set()
    for f in list(REPO.glob("**/*.yaml")):
        if any(part.startswith(".") for part in f.relative_to(REPO).parts):
            continue
        for m in re.finditer(
            r"^\s*-?\s*(?:name|alias|friendly_name|title):\s*(.+?)\s*$",
            f.read_text(encoding="utf-8", errors="ignore"),
            re.M,
        ):
            v = m.group(1).strip()
            if len(v) > 1 and v[0] in "\"'" and v.endswith(v[0]):
                v = v[1:-1]
            if "{{" not in v and v not in (">", ">-", "|"):
                names.add(v)
    bad = [(n, mine(n), ha(n)) for n in sorted(names) if mine(n) != ha(n)]
    for n, a, b in bad[:30]:
        print(f"❌ {n!r}: ha_slug={a}  HA={b}")
    print(f"{'❌' if bad else '✅'} slugcheck: {len(names)} navne, {len(bad)} afvigelser")
    return 1 if bad else 0


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--version", help="HA core-version (default: scripts/ha_offline_version.txt)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--rev")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true", help="kun fejl")
    p = sub.add_parser("equiv")
    p.add_argument("rev_a")
    p.add_argument("rev_b", nargs="?")
    p.add_argument(
        "--strict",
        action="store_true",
        help="tæl også ændrede fresh-install-snapshot-data som forskelle",
    )
    p = sub.add_parser("staging")
    p.add_argument("--rev")
    p.add_argument("--wait", type=int, default=45)
    p.add_argument("--keep", action="store_true")
    p = sub.add_parser("refs")
    p.add_argument("--rev")
    sub.add_parser("slugcheck")
    args = ap.parse_args()

    reexec_in_venv(wanted_version(args.version))
    return {
        "check": cmd_check,
        "equiv": cmd_equiv,
        "staging": cmd_staging,
        "refs": cmd_refs,
        "slugcheck": cmd_slugcheck,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
