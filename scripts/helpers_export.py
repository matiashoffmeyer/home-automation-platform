#!/usr/bin/env python3
"""Snapshot every helper value to git.

Slider and toggle values live in Home Assistant's ``.storage``. They survive
reboots but not a lost ``.storage`` (fresh install or corruption), after which
every slider would fall back to a default that does not match the tuned value.
This script writes the current values to tracked files, which makes the
repository the source of truth; ``helpers_restore.py`` applies them again.
See docs/adr/0001-tunable-values-in-git.md.

Usage::

  python3 scripts/helpers_export.py                 write the snapshot and the fresh-install file
  python3 scripts/helpers_export.py --print         dump to stdout instead
  python3 scripts/helpers_export.py --derive        re-derive the fresh-install file
                                                    from helper_values.yaml (no HA needed)
  python3 scripts/helpers_export.py --check-derived [--staged | --rev REV]
                                                    do the two files match? (pre-commit
                                                    uses --staged, pre-push --rev HEAD)

The files only persist once ``config_snapshots/`` is committed.

The ``input_number`` part is also the fresh-install default:
``init_user_preferences`` includes ``config_snapshots/fresh_install/input_number.yaml``,
which this script derives (numbers only, so no string can be invalid YAML or
Jinja). Home Assistant reads that file on every start, so it is written
atomically (temp file and rename). The raw ``helper_values.yaml`` is not loaded
by Home Assistant, so a snapshot with a stray backslash or a merge conflict
cannot send the house into recovery mode. A helper that is unknown or
unavailable during the export but still defined in YAML keeps its previous
value instead of disappearing; otherwise it would silently lose its
fresh-install default. Runtime counters (``RUNTIME_NUMBERS``) are not
configuration and are left out.
"""

import json
import os
import sys
import urllib.request
from datetime import UTC, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "config_snapshots", "helper_values.yaml")
# Den del HA selv læser (init_user_preferences, !include_dir_named på mappen:
# mangler mappen, bliver det {} — ingen recovery mode, bare ingen restore).
DERIVED = os.path.join(ROOT, "config_snapshots", "fresh_install", "input_number.yaml")
HA_URL = "http://homeassistant.local:8123"
DOMAINS = ("input_number", "input_boolean", "input_datetime", "input_select", "input_text")
# Kun KONFIG/tunable helpers — ikke runtime-state (learning, cursors, timestamps),
# så filen er stabil i git (ændres kun når en faktisk indstilling ændres).
DATETIME_CONFIG = {
    "puttelys_start",
    "hoejttaler_morgenradio_tidligst",
    "natlys_start",
    "putning_vindue_start",
    "terrasse_lys_nat_sluk_tid",
    "dormant_skema_hverdag_tid",
    "dormant_skema_weekend_start",
    "dormant_skema_weekend_slut",
    # 2026-10-10: konfig-tider der tavst manglede (init-seedet,
    # men brugerens tunede værdi blev aldrig snapshottet)
    "dormant_idle_dagstart",
    "dormant_idle_dagslut",
    "badevaerelse_dagmode_senest",
    "putning_vindue_slut",
    "kids_home_hverdag_afgang_senest",  # B270
    "wakeup_fallback_tid",
    "badevaerelse_bruser_vagt_start",
    "badevaerelse_bruser_vagt_slut",
    "koekken_lyskaede_cooking_taend_start",
    "koekken_lyskaede_cooking_taend_slut",
    "varsel_apollo_rgb_on",
    "varsel_apollo_rgb_off",
    "varsel_morgen_blink_start",
    "varsel_morgen_blink_slut",
    "varsel_morgen_push",
    "varsel_aften_1",
    "varsel_aften_2",
    "varsel_aften_3",
    "sove_aften_graense",
    "people_feedback_tid",
    "trainer_aktivitet_tid",
    "trainer_dug_tid",
    "flagermus_ekstra_dim_tid",
    "flagermus_curfew_tid",
    "dark_mode_godnat_cutover",
    "cykel_lader_deadline",
    "cykel_lader_vindue_start",
    "cykel_lader_nat_probe",
    "cykel_lader_rapport_tid",
    "cykel_lader_baseline_start",
    "cykel_lader_baseline_slut",
    "mad_spoergsmaal_tid",
    "mad_indkoeb_tid",
    "mad_indkoeb_anker",
    # mad_indkoeb_sprunget_dato er BEVIDST udeladt: den er en
    # kvittering for ét svar, ikke en indstilling.
    "mad_indkoeb_morgen_tid",
    "mad_side_paamind_tid",
    "boern_ankomst_suppress_timer",
    "godnat_autooff_tidligst",
    "regn_rapport_tid",
    "roborock_morgen_udskyd_start",
    "roborock_morgen_udskyd_slut",
    "dug_laas_tid",
    "dug_varsel_tid",
    "dug_apollo_rgb_on",
    "dug_apollo_rgb_off",
    "sleepover_morgen_slut",
    "boern_morgen_beskyttelse_slut",
    "sove_manual_off_lock_start",
    "boern_manual_off_lock_start",
    # Sofa Zen automatik: tidsvindue for automatisk tænd (2026-10-03)
    "sofa_zen_fra",
    "sofa_zen_til",
}

# input_select er som udgangspunkt RUNTIME state (room_mode, visit_stage,
# house_mode…) og snapshottes IKKE. Kun eksplicitte konfig-selects herunder.
SELECT_CONFIG = {
    "mad_indkoeb_ugedag",
    # Styrbar-fjernbetjeningens to OP-handlinger (2026-08-24) —
    # rent brugervalg, ikke runtime.
    "roborock_styrbar_kort_op",
    "roborock_styrbar_lang_op",
    # Hvad auto-rengoeringen paa Dormant goer (2026-09-01) — rent
    # brugervalg, ikke runtime.
    "roborock_auto_dormant_handling",
    # Morgenradioens kanal (2026-10-05, B193) — rent brugervalg.
    "hoejttaler_morgenradio_kanal",
    "hoejttaler_morgenradio_dage",
    "airbnb_velkomst_sprog",
}

# input_text er næsten udelukkende runtime-display (last_flap, spøgelses-lister,
# cursors) og snapshottes IKKE. Undtagelsen er gate-gulvene: de er husets dyrest
# opnåede kalibrering — hvert ciffer er et målt flap-forløb — og de er ENESTE
# spærre mod at gate-decay walker en tærskel tilbage under det niveau der
# beviseligt stoppede et spøgelse. Tabtes de, ville huset selv gen-åbne
# spøgelserne, og kun en ny måleserie kunne finde værdien igen.
# koekken_stemme_arm_gestus er den anden slags undtagelse: den er en
# KONFIGURATION klædt ud som en input_text (hvilken gestus armerer mikrofonen),
# valgt som input_text netop fordi det er husets eneste gratis helper-reload.
# Tabt ville den stå på 'unknown' — som er truthy og aldrig matcher et
# gestus-navn — og mikrofonen ville være tavs uden at noget så forkert ud.
# Stemplet `koekken_stemme_armeret_at` er derimod ren runtime og hører ikke her.
# batteri_watchdog_undtag (2026-10-04, B151): brugerens bevidste fravalg (fx
# sonoff_swv i en skuffe) — tabt ville watchdog'en genoptage påmindelserne.
# stue_spot_1/2_brugerfarve (2026-10-05): den farve brugeren selv har valgt til
# sofa-spotsene (packages/stue_spots.yaml) — tabt ville spotsene tænde i
# hvad en effekt sidst efterlod.
TEXT_CONFIG = {
    "stue_gate_floors",
    "spisestue_gate_floors",
    "koekken_gate_floors",
    "boernevaerelse_gate_floors",
    "sove_gate_floors",
    "koekken_stemme_arm_gestus",
    "batteri_watchdog_undtag",
    "stue_spot_1_brugerfarve",
    "stue_spot_2_brugerfarve",
}


# input_numbers der er TILSTAND, ikke indstilling (navnet afslører det ikke).
# people_boern_antal står bevidst IKKE her: den måles hver morgen, men min (0
# børn) er en værre frisk værdi end den sidst målte.
RUNTIME_NUMBERS = {
    "roborock_aktiv_minutter_akkumuleret",  # roborock_aktiv_timer.yaml: "RUNTIME-akkumulator"
    "sove_seng_personer",  # sove_seng_taeller.yaml: "RUNTIME-tællingen"
    "wakeup_fallback_udskyd_min",  # parent_b_alarm.yaml: "kun i nat", ryddes kl. 10
    "foedselsdag_sidste_skift_ts",  # foedselsdag_mood.yaml: epoch for sidste skift
    "dyrespil_vol_foer",  # festlys_dyrespil.yaml: "RUNTIME" volumen før spillet, -1 = lukket
    "gardin_syd_antaget_pos",  # broadlink_gardiner.yaml: antaget RF-position
    "gardin_vest_antaget_pos",
    "gardin_spisestue_antaget_pos",
    "thread_watchdog_forsoeg",  # thread_otbr_watchdog.yaml: kure i igangværende nedetid
}


def is_config(domain, name):
    if domain == "input_number":
        if name.startswith("adaptive_"):
            return False
        if "_idx" in name or "cursor" in name or name == "scene_spread_level":
            return False
        if name == "airbnb_gaeste_antal":  # runtime pr. booking, ikke config
            return False
        # People-gulvene er runtime high-water-marks (people_estimate.yaml) —
        # en restore ville genopstå et gammelt antal personer.
        if name in ("people_ekstra_gulv", "people_gulv", "people_manuel"):
            return False
        if name == "user_prefs_version":  # intern init-gate-markoer (B39) —
            return False  # MAA IKKE restores: en .storage-tab skal give 0 → fresh init
        # Runtime-tællere og -stempler (verificeret i pakkerne 2026-10-04). Siden
        # P1 gendanner init alt herfra på en frisk install — en gammel akkumulator
        # ville fx sende robotten afsted før tid, og et aften-snapshot af
        # sengetælleren ville tømme badets sluk-alt-undtagelse.
        if name in RUNTIME_NUMBERS:
            return False
        return True
    if domain == "input_boolean":
        # Styrbar-fjernbetjeningens rum-valg er konfiguration, ikke runtime —
        # et .storage-tab må ikke efterlade knappen uden rum (= tavs knap).
        if name.startswith("roborock_styrbar_"):
            return True
        # Indkøbs-præferencer: konfiguration, men hedder ikke *_enabled.
        # Fanget 2026-08-31 — nemlig_foretraek_oeko/_tilbud kunne ikke
        # gendannes efter et .storage-tab, fordi allowlisten kun så på
        # suffikset. Et navn er ikke en garanti for at være med i backuppen.
        if name.startswith("nemlig_foretraek_"):
            return True
        # Afbryder pr. stemme-kommando-ord (tapo_tuning.yaml) — samme fælde:
        # de hedder voice_cmd_*, ikke *_enabled.
        if name.startswith("voice_cmd_"):
            return True
        # Music Assistant-knappen (B204/B205) — konfiguration, ikke *_enabled.
        # + Spotify-bro-knappen (B237); uden add-on'en er start en logget no-op.
        if name in ("hoejttaler_spotify_via_ha", "hoejttaler_spotify_bro", "hoejttaler_myair"):
            return True
        # Frost-sangenes kill-switch (packages/festlys_frost.yaml, 2026-10-26).
        if name == "festlys_frost":
            return True
        # kill-switches + notifikations-toggles (master/enable/phone-valg)
        return name.endswith("_enabled") or name.startswith("notif_")
    if domain == "input_datetime":
        # config-tider + notifikations-tidsvinduer (notif_*_start/_slut)
        return name in DATETIME_CONFIG or name.startswith("notif_")
    if domain == "input_select":
        return name in SELECT_CONFIG
    if domain == "input_text":
        return name in TEXT_CONFIG
    return False


def load_token():
    # HA_TOKEN (PC/.env) foretrækkes; on-HAOS-sessioner har kun
    # SUPERVISOR_TOKEN → skift base-URL til Supervisor-proxyen.
    global HA_URL
    if os.environ.get("HA_TOKEN"):
        return os.environ["HA_TOKEN"]
    for p in (os.path.join(ROOT, ".env"), "/config/.env"):
        if os.path.isfile(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line.startswith("HA_TOKEN"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    if os.environ.get("SUPERVISOR_TOKEN"):
        HA_URL = "http://supervisor/core"
        return os.environ["SUPERVISOR_TOKEN"]
    raise SystemExit("HA_TOKEN/SUPERVISOR_TOKEN ikke fundet (env eller .env)")


def fetch_states(tok):
    req = urllib.request.Request(f"{HA_URL}/api/states", headers={"Authorization": "Bearer " + tok})
    return json.load(urllib.request.urlopen(req, timeout=30))


def _quote(s):
    # En JSON-streng er en gyldig YAML-dobbeltcitat-streng — også med backslash
    # og kontroltegn. Før 2026-10-04 escapede vi kun `"`, så en værdi med `\x`
    # gav ugyldig YAML.
    return json.dumps(s, ensure_ascii=False)


def yaml_value(v, force_quote=False):
    """Emit a value safely as YAML scalar (no pyyaml dependency)."""
    s = str(v)
    # Gate-gulvene er RENE CIFRE med betydningsbærende foranstillede nuller
    # ("0000...9950..."), så float() lykkes og ville emitte dem unquoted — en
    # rigtig YAML-læser ville så gøre dem til et tal og æde nullerne.
    if force_quote:
        return _quote(s)
    # tal (int/float) uden quotes; alt andet quotes for at undgå type-tvetydighed.
    # nan/inf er "tal" for float(), men ikke for YAML → quotes.
    try:
        f = float(s)
        if f == f and f not in (float("inf"), float("-inf")):
            return s
    except ValueError:
        pass
    return _quote(s)


def parse_snapshot(path):
    """Flad parser (ingen pyyaml): 'domain:' headers + '  name: value' linjer.

    ÉN parser for export (forrige værdier), --derive og helpers_restore.py.
    Citerede værdier læses som JSON (det vi skriver), med fallback til det
    gamle format hvor kun `\"` var escapet.
    """
    with open(path, encoding="utf-8") as f:
        return parse_snapshot_lines(f, path)


def parse_snapshot_lines(lines, label="snapshot"):
    import re

    data, dom = {}, None
    for raw in lines:
        line = raw.rstrip("\n").lstrip("\ufeff")
        if not line or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\w+):\s*$", line)
        if m:
            dom = m.group(1)
            data[dom] = {}
            continue
        m = re.match(r"^  (\S+):\s*(.*)$", line)
        if m and dom:
            val = m.group(2).strip()
            if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                try:
                    val = json.loads(val)
                except ValueError:
                    val = val[1:-1].replace('\\"', '"')
            data[dom][m.group(1)] = val
        elif line.strip() and not line.startswith(" "):
            # fx en merge-konflikt-markør — hellere fejle end aflede noget halvt
            raise ValueError(f"{label}: uventet linje {line[:60]!r}")
    return data


def _num_literal(v):
    """Et tal som YAML 1.1 læser som float: aldrig '1e-05' (= streng i PyYAML)."""
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError(v)
    s = ("%.10f" % f).rstrip("0")
    return s + "0" if s.endswith(".") else s


def derive_text(numbers):
    """Fresh-install-filen: kun input_number-tal, deterministisk (ingen tidsstempel)."""
    lines = [
        "# =============================================================================",
        "# GENERERET af scripts/helpers_export.py fra helper_values.yaml — RET IKKE HER.",
        "# init_user_preferences (!include_dir_named ../config_snapshots/fresh_install)",
        "# gendanner disse værdier på en FRISK install. Kun tal, så filen hverken kan",
        "# være ugyldig YAML eller indeholde Jinja. Gen-afled: helpers_export.py --derive",
        "# =============================================================================",
    ]
    for name in sorted(numbers):
        # Samme autoritet som exporten: står et runtime-tal stadig i et gammelt
        # eller merget snapshot (mains exporter før denne commit skrev dem),
        # må --derive ikke føre det ind i den fil HA gendanner fra (review 10-04).
        if not is_config("input_number", name):
            continue
        try:
            lines.append(f"{name}: {_num_literal(numbers[name])}")
        except ValueError:
            continue  # ikke-numerisk = ikke en slider-værdi
    return "\n".join(lines) + "\n"


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def yaml_defined_helpers():
    """{domain: {navne}} for helpers der stadig er defineret i packages/ (eller None)."""
    try:
        import yaml
    except ImportError:
        return None

    class _L(yaml.SafeLoader):
        pass

    _L.add_multi_constructor("!", lambda loader, suffix, node: None)
    out = {d: set() for d in DOMAINS}
    pkg = os.path.join(ROOT, "packages")
    for fn in sorted(os.listdir(pkg)):
        if not fn.endswith(".yaml"):
            continue
        try:
            data = yaml.load(open(os.path.join(pkg, fn), encoding="utf-8"), Loader=_L) or {}  # noqa: S506 - a SafeLoader subclass
        except yaml.YAMLError:
            continue
        for d in DOMAINS:
            out[d] |= set((data.get(d) or {}).keys()) if isinstance(data, dict) else set()
    return out


def derive_from_snapshot():
    return derive_text(parse_snapshot(OUT).get("input_number", {}))


def _git_blob(spec):
    """Indhold af `<rev>:<sti>` (rev '' = index), eller None hvis den ikke findes."""
    import subprocess

    r = subprocess.run(
        ["git", "-C", ROOT, "show", spec], capture_output=True, text=True, encoding="utf-8"
    )
    return r.stdout if r.returncode == 0 else None


def check_derived(source="worktree"):
    """(ok, besked). source: 'worktree', 'index' eller en git-rev.

    Pre-commit SKAL bruge 'index': arbejdstræet kan være konsistent mens kun
    helper_values.yaml er staged (review 10-04, reproduceret af 3 reviewere) —
    så committes et par der ikke passer, og en frisk install fra git gendanner
    forældede værdier. Pre-push bruger HEAD (rebase/cherry-pick kører ikke
    pre-commit)."""
    rel_out = os.path.relpath(OUT, ROOT).replace(os.sep, "/")
    rel_der = os.path.relpath(DERIVED, ROOT).replace(os.sep, "/")
    if source == "worktree":
        if not os.path.isfile(OUT):
            return True, "intet snapshot"
        snap = open(OUT, encoding="utf-8").read()
        have = open(DERIVED, encoding="utf-8").read() if os.path.isfile(DERIVED) else None
    else:
        prefix = ":" if source == "index" else f"{source}:"
        snap, have = _git_blob(prefix + rel_out), _git_blob(prefix + rel_der)
        if snap is None:
            return True, "intet snapshot"
    try:
        want = derive_text(
            parse_snapshot_lines(snap.splitlines(True), rel_out).get("input_number", {})
        )
    except ValueError as e:
        return False, f"{e} — løs konflikten i {rel_out} først"
    if have != want:
        where = {"worktree": "arbejdstræet", "index": "det STAGEDE"}.get(source, source)
        return False, (
            f"{rel_der} passer ikke til {rel_out} i {where} — kør "
            "`python3 scripts/helpers_export.py --derive` og `git add config_snapshots/`"
        )
    return True, "ok"


def main():
    if "--derive" in sys.argv:
        _atomic_write(DERIVED, derive_from_snapshot())
        print(f"Afledte {DERIVED} fra {OUT}")
        return
    if "--check-derived" in sys.argv:
        src = "worktree"
        if "--staged" in sys.argv:
            src = "index"
        elif "--rev" in sys.argv:
            src = sys.argv[sys.argv.index("--rev") + 1]
        ok, msg = check_derived(src)
        if not ok:
            print(f"❌ {msg}", file=sys.stderr)
            sys.exit(1)
        return
    tok = load_token()
    states = fetch_states(tok)
    buckets = {d: {} for d in DOMAINS}
    # Er det forrige snapshot ulæseligt (fx konflikt-markører efter en stash
    # pop), er en frisk eksport fra live netop LØSNINGEN — så den må ikke
    # crashe; vi mister kun carry-forward for denne kørsel.
    try:
        previous = parse_snapshot(OUT) if os.path.isfile(OUT) else {}
    except ValueError as e:
        print(f"⚠️  forrige snapshot ulæseligt ({e}) — eksporterer uden carry-forward")
        previous = {}
    defined = yaml_defined_helpers()
    if defined is None:
        print("⚠️  PyYAML mangler — carry-forward slået fra (helpers der ikke svarer, droppes)")
    carried, dropped = [], []
    for st in states:
        dom, _, name = st["entity_id"].partition(".")
        if dom not in buckets or not is_config(dom, name):
            continue
        # unavailable/unknown: en orphan-helper (fjernet fra YAML men endnu ikke
        # purged fra entity-registry) må ALDRIG snapshottes (2026-06-18). Men en
        # helper der stadig er DEFINERET og bare ikke svarer lige nu (fx dens
        # pakke fejlede ved denne start), beholder sin forrige værdi — siden P1
        # er snapshottet dens fresh-install-default, og at droppe den i stilhed
        # ville lade den lande på min efter en geninstallation.
        if st["state"] in ("unavailable", "unknown"):
            prev = previous.get(dom, {}).get(name)
            if prev is not None and defined is not None and name in defined.get(dom, ()):
                buckets[dom][name] = prev
                carried.append(f"{dom}.{name}")
            elif prev is not None:
                dropped.append(f"{dom}.{name}")
            continue
        buckets[dom][name] = st["state"]

    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = sum(len(b) for b in buckets.values())
    lines = [
        "# =============================================================================",
        "# helper_values.yaml — konfig-helper-værdier: sliders + kill-switches + tids-",
        "# settings (source-of-truth backup; runtime-state/learning er bevidst udeladt)",
        "# =============================================================================",
        "# Genereret af scripts/helpers_export.py. Genskab med scripts/helpers_restore.py.",
        "# Commit denne fil for at persistere slider/toggle-værdier i git.",
        f"# Senest opdateret: {ts}  ({total} helpers)",
        "# =============================================================================",
        "",
    ]
    for dom in DOMAINS:
        lines.append(f"{dom}:")
        for name in sorted(buckets[dom]):
            lines.append(f"  {name}: {yaml_value(buckets[dom][name], dom == 'input_text')}")
        lines.append("")
    text = "\n".join(lines)

    if "--print" in sys.argv:
        sys.stdout.write(text)
        return
    _atomic_write(OUT, text)
    _atomic_write(DERIVED, derive_text(buckets["input_number"]))
    print(f"Skrev {total} helper-værdier til {OUT}")
    print(f"Afledte {len(buckets['input_number'])} slider-værdier til {DERIVED}")
    if carried:
        print(
            f"⚠️  {len(carried)} svarede ikke under eksporten — forrige værdi beholdt: "
            + ", ".join(carried[:8])
            + (" …" if len(carried) > 8 else "")
        )
    if dropped:
        print(
            f"⚠️  {len(dropped)} stod i det forrige snapshot men er DROPPET (ikke defineret "
            "i packages/ eller PyYAML mangler): "
            + ", ".join(dropped[:8])
            + (" …" if len(dropped) > 8 else "")
        )
    print("HUSK: commit config_snapshots/ for at persistere i git.")


if __name__ == "__main__":
    main()
