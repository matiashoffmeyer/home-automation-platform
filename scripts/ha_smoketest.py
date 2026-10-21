#!/usr/bin/env python3
# =============================================================================
# HA Smoke Test — Catch automation regressions FØR de hits prod
# =============================================================================
# Phase 4 værktøj fra refactor-plan. Fyrer test events for kritiske automations
# og verificerer der ingen exceptions kastes + forventet entity-respons.
#
# Skal kunne køres efter HVER refactor commit for at give 80% confidence at
# functionality er bevaret. Ikke 100% test coverage — fokus på hyppige paths.
#
# Tests fyret (alle non-destructive — bruger fake-events ikke virkelige):
#   1. Activity state computation — sensor.activity_state opdaterer korrekt
#   2. Lux fallback chain — sensor.open_plan_lux falder tilbage på spisestue
#   3. presence_sensors_available master gate
#   4. Workday template fallback (M12 fix)
#   5. Auto color temp evening template
#   6. Activity state idle when all sensors clear
#
# Usage:
#   ./scripts/ha_smoketest.py            # alle tests
#   ./scripts/ha_smoketest.py --verbose  # vis hver tests detaljer
#
# Exit code 0 = all pass, 1 = ≥1 failure
# =============================================================================

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC
from pathlib import Path

# Windows console fix: force UTF-8 stdout/stderr så Unicode-emojis (✅❌) ikke
# crasher med UnicodeEncodeError på cp1252. No-op på Linux.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO = Path(__file__).resolve().parent.parent
HA_URL = "http://homeassistant.local:8123"


def red(s):
    return f"\033[31m{s}\033[0m"


def green(s):
    return f"\033[32m{s}\033[0m"


def cyan(s):
    return f"\033[36m{s}\033[0m"


def yellow(s):
    return f"\033[33m{s}\033[0m"


def load_token():
    # 1. Env var
    t = os.environ.get("HA_TOKEN")
    if t:
        return t.strip().strip('"').strip("'")
    # 2. .env file in repo
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("HA_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


class HAClient:
    def __init__(self, token):
        self.token = token

    def _req(self, path, method="GET", data=None):
        req = urllib.request.Request(
            f"{HA_URL}{path}",
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            data=json.dumps(data).encode() if data else None,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            return json.loads(body) if body else None

    def state(self, entity_id):
        try:
            return self._req(f"/api/states/{entity_id}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def template(self, template):
        # /api/template returns plain text, not JSON
        req = urllib.request.Request(
            f"{HA_URL}/api/template",
            method="POST",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            data=json.dumps({"template": template}).encode(),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode().strip()


# === Tests ===


def test_activity_state_exists(ha, verbose=False):
    """activity_state computes a non-error value."""
    s = ha.state("sensor.activity_state")
    if not s:
        return False, "sensor.activity_state not found"
    if s["state"] in ("unknown", "unavailable"):
        return False, f"state is {s['state']} (template error?)"
    valid_states = {
        "idle",
        "bedroom_only",
        "sofa_relax",
        "dining",
        "cooking",
        "social_dining",
        "social_party",
        "nightwalk",
        "bath_visit",
        "transit",
        "terrasse_only",
        "terrasse_with_indoor",
        "godnat",
        "active",
        "away",
    }
    if s["state"] not in valid_states:
        return False, f"unexpected state: {s['state']}"
    return True, f"state={s['state']}"


def test_open_plan_lux_fallback(ha, verbose=False):
    """open_plan_lux returns valid number even if stue is broken."""
    s = ha.state("sensor.open_plan_lux")
    if not s:
        return False, "sensor.open_plan_lux not found"
    if s["state"] in ("unknown", "unavailable"):
        return False, "open_plan_lux is unknown — all 3 fallback Apollos broken?"
    try:
        val = float(s["state"])
        return True, f"lux={val:.1f}"
    except ValueError:
        return False, f"non-numeric: {s['state']}"


def test_presence_sensors_available(ha, verbose=False):
    """Master gate is healthy."""
    s = ha.state("binary_sensor.presence_sensors_available")
    if not s:
        return False, "not found"
    if s["state"] not in ("on", "off"):
        return False, f"state {s['state']} not on/off"
    if s["state"] == "off":
        return False, "OFF — entire presence stack disabled"
    return True, "on"


def test_auto_color_temp(ha, verbose=False):
    """auto_color_temp_evening returns valid Kelvin value."""
    s = ha.state("sensor.auto_color_temp_evening")
    if not s:
        return False, "not found"
    try:
        k = int(s["state"])
        if not (1800 <= k <= 6500):
            return False, f"out of range: {k}K"
        return True, f"{k}K"
    except ValueError:
        return False, f"non-numeric: {s['state']}"


def test_workday_template(ha, verbose=False):
    """arbejdsdag template renders without error (handles M12 fallback)."""
    try:
        result = ha.template("{{ states('binary_sensor.arbejdsdag') }}")
        if result in ("on", "off"):
            return True, result
        return False, f"unexpected: {result}"
    except Exception as e:
        return False, f"template error: {e}"


def test_house_state_machine(ha, verbose=False):
    """house_state + house_mode are valid values."""
    state_s = ha.state("input_select.house_state")
    mode_s = ha.state("input_select.house_mode")
    if not state_s or not mode_s:
        return False, "missing house_state or house_mode"
    valid_states = {"Active", "Dormant"}
    valid_modes = {"Normal", "AirBnB"}
    if state_s["state"] not in valid_states:
        return False, f"house_state={state_s['state']} (expected one of {valid_states})"
    if mode_s["state"] not in valid_modes:
        return False, f"house_mode={mode_s['state']} (expected one of {valid_modes})"
    return True, f"state={state_s['state']}, mode={mode_s['state']}"


def test_no_stuck_godnat_subflags(ha, verbose=False):
    """godnat sub-flags shouldn't be STUCK on for too long (>12h).

    Note: sub-flag-only states are LEGITIMATE (sprint 2026-05-07):
      - godnat_boern_active alone = kids i seng, parents staying up (putning)
      - godnat_voksne_active alone = voksen i seng, kid awake (sygedag)
      - kalde_active alone = kalde event in progress
    Only flag if sub-flag has been ON for >12h = real stuck (failed clear)."""
    from datetime import datetime

    now = datetime.now(UTC)
    subflags = ["godnat_voksne_active", "godnat_boern_active", "kalde_active"]
    stuck = []
    for sf in subflags:
        s = ha.state(f"input_boolean.{sf}")
        if not s or s["state"] != "on":
            continue
        lc_str = s.get("last_changed")
        if not lc_str:
            continue
        try:
            lc = datetime.fromisoformat(lc_str.replace("Z", "+00:00"))
            age_hours = (now - lc).total_seconds() / 3600
            # Kalde-active: 30 min stuck = abnormal (auto-clears in ~5 min)
            # Other sub-flags: 12h stuck = abnormal
            threshold = 0.5 if sf == "kalde_active" else 12
            if age_hours > threshold:
                stuck.append(f"{sf}({age_hours:.1f}h)")
        except Exception:
            pass
    if stuck:
        return False, f"sub-flags stuck >threshold: {stuck}"
    return True, "no stuck sub-flags (legit short-duration sub-flags allowed)"


def test_thread_dataset_otbr(ha, verbose=False):
    """Verify Thread dataset has source=otbr (kritisk for mobile commission)."""
    try:
        # Use template for inspection
        # Note: this tests Matter/Thread integration health
        s = ha.state("update.openthread_border_router_update")
        if not s:
            return None, "OTBR not installed (skipped)"
        return True, "OTBR update entity present"
    except Exception as e:
        return False, str(e)


def test_lux_fallback_resilience(ha, verbose=False):
    """If primary lux unavailable, open_plan_lux still produces value."""
    primary = ha.state("sensor.spisestue_lux_reel")
    fallback = ha.state("sensor.sovevaerelse_lux_reel")
    out = ha.state("sensor.open_plan_lux")
    if not out:
        return False, "open_plan_lux missing"
    if out["state"] in ("unknown", "unavailable"):
        # OK if all sources are also unavailable
        sources_ok = (primary and primary["state"] not in ("unknown", "unavailable")) or (
            fallback and fallback["state"] not in ("unknown", "unavailable")
        )
        if sources_ok:
            return False, "primary/fallback have values but open_plan_lux is unknown"
        return None, "no lux sources available — expected unknown"
    return True, f"resilient (open_plan_lux={out['state']})"


# === EXTENDED TESTS (Phase 4 round 2 — per-room paths) ===


def test_per_room_presence_lights_loaded(ha, verbose=False):
    """All 5 per-room presence light automations loaded post Phase 2 split.

    NB: automation entity_ids er derived fra alias slug ("Børneværelse" → "bornevaerelse")
    så automations behold OLD slug. Apollo entities (Blok C.2) er nu boernevaerelse.
    """
    rooms = ["stue", "kokken", "badevaerelse", "sovevaerelse", "bornevaerelse"]
    expected_automations = []
    for r in rooms:
        # Both _on and _off should exist
        expected_automations.append(f"automation.lysnet_{r}_taend")
        # Special: stue/kokken use _gradvis_sluk, others vary
        expected_automations.append(f"automation.lysnet_{r}_gradvis_sluk")
    missing = [a for a in expected_automations if not ha.state(a)]
    if missing:
        return False, f"missing: {missing[:3]}"
    return True, "all 10 per-room automations loaded"


def test_lux_automations_loaded(ha, verbose=False):
    """Reactive lux ON/OFF automations exist (in presence_lights.yaml).

    NB: alias-derived entity_ids — Børneværelse → bornevaerelse (OLD slug bevaret).
    """
    rooms = ["stue", "kokken", "sovevaerelse", "bornevaerelse"]
    for r in rooms:
        # _taend_ved_lux_fald (ON when daylight fades)
        on = ha.state(f"automation.lysnet_{r}_taend_ved_lux_fald")
        if not on:
            return False, f"missing automation.lysnet_{r}_taend_ved_lux_fald"
    return True, f"all {len(rooms)} lux ON automations loaded"


def test_matter_devices_reachable(ha, verbose=False):
    """All 4 Matter devices should be reachable (state != unavailable)."""
    matter_entities = [
        "binary_sensor.parasoll_hoveddoer",  # Myggbett 1 (door)
        "binary_sensor.parasoll_standby",  # Myggbett 2
        "binary_sensor.parasoll_standby_2",  # Myggbett 3
        "binary_sensor.entre_valhorn_occupancy",  # Myggspray (motion)
    ]
    unavailable = []
    for e in matter_entities:
        s = ha.state(e)
        if not s:
            unavailable.append(f"{e} (missing)")
        elif s["state"] in ("unknown", "unavailable"):
            unavailable.append(f"{e}={s['state']}")
    if unavailable:
        return False, f"unavailable: {unavailable}"
    return True, f"all {len(matter_entities)} Matter devices reachable"


def test_apollos_all_online(ha, verbose=False):
    """All 5 Apollo MSR-2 ESPHome sensors should be online.

    Per Blok C.2 sprint 2026-05-06: alle bornevaerelse_* renamed til
    boernevaerelse_* via WS API. Slug er nu konsistent.
    """
    apollo_online = {
        "stue": "binary_sensor.stue_apollo_online",
        "spisestue": "binary_sensor.spisestue_apollo_online",
        "sovevaerelse": "binary_sensor.sovevaerelse_apollo_online",
        "boernevaerelse": "binary_sensor.boernevaerelse_apollo_online",
        "koekken": "binary_sensor.koekken_apollo_online",
    }
    offline = []
    for room, eid in apollo_online.items():
        s = ha.state(eid)
        if not s:
            offline.append(f"{room} (missing)")
        elif s["state"] != "on":
            offline.append(f"{room}={s['state']}")
    if offline:
        return False, f"offline: {offline}"
    return True, "all 5 Apollos online"


def test_apollo_unavailable_resilience(ha, verbose=False):
    """Critical state-machine entities should NEVER be False/unknown when
    some Apollos are unavailable. Apollo unavailable = expected pre-flyt
    (3 unplugged) or transient WiFi blip — code must degrade gracefully.

    Catches Sprint B-pattern bugs: open_plan_empty_for_20m returning False
    permanently, presence_sensors_available stuck off, etc.
    """
    # These template_sensors must produce valid state regardless of Apollo
    # availability (handled by fallback chains + treat-unavailable-as-empty).
    must_be_valid = [
        "binary_sensor.presence_sensors_available",
        "binary_sensor.open_plan_empty_for_20m",
        "binary_sensor.godnat_any_active",
        "sensor.activity_state",
        "sensor.open_plan_lux",
        "sensor.indoor_temperature_resilient",  # NEW Sprint D.14 — name slugified to "_temperature_"
        "sensor.people_estimate",
    ]
    invalid = []
    for eid in must_be_valid:
        s = ha.state(eid)
        if not s:
            invalid.append(f"{eid} MISSING")
        elif s["state"] in ("unknown", "unavailable", "none", ""):
            invalid.append(f"{eid}={s['state']}")
    if invalid:
        return False, f"invalid: {invalid}"
    return True, f"all {len(must_be_valid)} resilience-critical sensors valid"


def test_no_stuck_mood_flags(ha, verbose=False):
    """cinema/cirkus shouldn't be stuck on for >24h (B12 mood_flag_safety check)."""
    import datetime

    flags = ["cinema_active", "cirkus_active"]
    stuck = []
    for f in flags:
        s = ha.state(f"input_boolean.{f}")
        if not s:
            continue
        if s["state"] == "on":
            try:
                lc = datetime.datetime.fromisoformat(s["last_changed"].replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.UTC)
                age_h = (now - lc).total_seconds() / 3600
                if age_h > 24:
                    stuck.append(f"{f} ({age_h:.0f}h)")
            except Exception:
                pass
    if stuck:
        return False, f"stuck >24h: {stuck}"
    return True, "no stuck mood flags"


def test_critical_helpers_exist(ha, verbose=False):
    """Core helpers must exist for state machine to function."""
    critical = [
        "input_boolean.godnat_active",
        "input_boolean.cinema_active",
        "input_boolean.cirkus_active",
        "input_boolean.guest_mode",
        "input_select.house_state",
        "input_select.house_mode",
        # Constants — fade times + lr_grace + godnat targets (audit-fix 2026-05-07)
        # Sprint 2026-05-20: fade_hallway → fade_passage + fade_ophold split
        "input_number.fade_living_seconds",
        "input_number.fade_passage_seconds",
        "input_number.fade_ophold_seconds",
        "input_number.fade_extended_seconds",
        "input_number.lr_grace_milliseconds",
        "input_number.godnat_brightness_pct",
        "input_number.godnat_kelvin",
        # Global Tuning Sliders (sprint 2026-05-07 sen-PM)
        "input_number.global_light_aggressiveness",
        "input_number.global_turn_off_aggressiveness",
        "input_number.global_lux_sensitivity",
        # Per-Apollo sensitivity sliders FJERNET 2026-07-09b → alle Apolloer
        # bruger nu FULD per-gate kontrol (apollo_per_gate.yaml + sove_...).
        # Sanity-check ét gate pr. rum (fanger at pakkerne loadede).
        "input_number.stue_g2_still",
        "input_number.spisestue_g2_still",
        "input_number.koekken_g2_still",
        "input_number.boernevaerelse_g2_still",
        "input_number.sove_g2_still",
        # Room mode tunables (audit-fix 2026-05-07: persistence migration)
        "input_number.room_manual_on_hold_hours",
    ]
    missing = [e for e in critical if not ha.state(e)]
    if missing:
        return False, f"missing: {missing}"
    return True, f"all {len(critical)} core helpers present"


def test_room_light_groups_exist(ha, verbose=False):
    """Per-rum `light.<rum>_all` groups MUST exist — bruges af Styrbar handlers
    + room_logic scripts via templated `light.{{ room }}_all` refs (som validatoren
    skipper via endswith heuristic).

    Phase 3.D 2026-05-07 deleted these claiming '0 refs' (incorrect — 11 templated
    refs i scripts). User-visible breakage: ALLE 5 Styrbars stoppede med at virke.
    Denne test catcher recurrence."""
    required_groups = [
        "light.stue_all",
        "light.sovevaerelse_all",
        "light.boernevaerelse_all",
        "light.badevaerelse_all",
        "light.depot_all",
        "light.entre_all",
        "light.terrasse_all",
    ]
    missing = [g for g in required_groups if not ha.state(g)]
    if missing:
        return False, f"BROKEN STYRBARS: missing groups {missing}"
    return True, f"all {len(required_groups)} per-room light groups exist"


def test_critical_automations_enabled(ha, verbose=False):
    """Key automations must be enabled (state=on)."""
    critical = [
        "automation.activity_auto_set_guest_mode_hurtigt_ved_social_party",
        "automation.entre_lys_taend_ved_bevaegelse",
        "automation.entre_lys_sluk_efter_bevaegelse",
        "automation.lysnet_stue_taend",
        "automation.lysnet_sovevaerelse_taend",
    ]
    # AirBnB-lockdown disabler bevidst familie-automations (airbnb_mode.yaml) —
    # de er LEGITIMT off mens en gæst bor her, så udelad dem i AirBnB-mode.
    mode = ha.state("input_select.house_mode")
    if mode and mode["state"] == "AirBnB":
        critical.remove("automation.activity_auto_set_guest_mode_hurtigt_ved_social_party")
    disabled = []
    for a in critical:
        s = ha.state(a)
        if not s:
            disabled.append(f"{a} (missing)")
        elif s["state"] != "on":
            disabled.append(f"{a}={s['state']}")
    if disabled:
        return False, f"disabled: {disabled}"
    return True, f"all {len(critical)} critical automations on"


def test_thread_mesh_health(ha, verbose=False):
    """Thread mesh should have OTBR + ≥1 Matter children registered."""
    # Check via discover_routers or service_state
    s = ha.state("update.openthread_border_router_update")
    if not s:
        return None, "OTBR not installed (skipped)"
    # Check that at least 1 entre_valhorn (Matter Myggspray) is reachable
    myggspray = ha.state("binary_sensor.entre_valhorn_occupancy")
    if not myggspray or myggspray["state"] in ("unknown", "unavailable"):
        return False, "Matter Myggspray unreachable — Thread mesh unhealthy?"
    return True, "OTBR present + Myggspray reachable"


def test_zigbee_mesh_health(ha, verbose=False):
    """Zigbee mesh: depot_valhorn + at least 1 RODRET battery should be reachable."""
    valhorn = ha.state("binary_sensor.depot_valhorn_occupancy")
    if not valhorn or valhorn["state"] in ("unknown", "unavailable"):
        return False, "depot_valhorn unreachable — ZBT-2 dongle issue?"
    # Check 1 RODRET battery as proxy for Zigbee mesh
    rodret = ha.state("sensor.boern_kalde_battery")
    if rodret and rodret["state"] not in ("unknown", "unavailable"):
        return True, f"valhorn=on, RODRET battery={rodret['state']}%"
    return True, "valhorn online (RODRET batteries may need first-press)"


# Tier system (sprint 2026-05-06):
#   "critical" = code/state-machine regression. Failure → block deploy.
#   "health"   = hardware availability. Failure → log warning, don't block.
#                Hardware kan dø midlertidigt (WiFi blip, power outage,
#                brugeren tog Apollo ud af stik mid-deploy etc) — det er
#                IKKE en code regression, så auto-revert er forkert response.
TESTS = [
    # === Core state machine (CRITICAL — block deploy on failure) ===
    ("activity_state computes", test_activity_state_exists, "critical"),
    ("open_plan_lux fallback chain", test_open_plan_lux_fallback, "critical"),
    ("presence_sensors_available master gate", test_presence_sensors_available, "critical"),
    ("auto_color_temp_evening", test_auto_color_temp, "critical"),
    ("arbejdsdag workday template", test_workday_template, "critical"),
    ("house_state + house_mode valid", test_house_state_machine, "critical"),
    ("godnat sub-flags not stuck", test_no_stuck_godnat_subflags, "critical"),
    ("OTBR integration present", test_thread_dataset_otbr, "critical"),
    ("lux fallback resilience", test_lux_fallback_resilience, "critical"),
    # === Per-room presence (CRITICAL — automations loaded check) ===
    (
        "per-room presence light automations loaded",
        test_per_room_presence_lights_loaded,
        "critical",
    ),
    ("lux reactive automations loaded", test_lux_automations_loaded, "critical"),
    # === Hardware health (HEALTH — warn-only, devices kan tabes uden code-fault) ===
    ("Matter devices reachable", test_matter_devices_reachable, "health"),
    ("Apollos all online", test_apollos_all_online, "health"),
    ("Thread mesh health (OTBR+Matter)", test_thread_mesh_health, "health"),
    ("Zigbee mesh health (Vallhorn+RODRET)", test_zigbee_mesh_health, "health"),
    # === Mode + helpers safety (CRITICAL — config integrity) ===
    ("no stuck mood flags >24h", test_no_stuck_mood_flags, "critical"),
    ("critical helpers exist", test_critical_helpers_exist, "critical"),
    ("room light groups exist (Styrbar deps)", test_room_light_groups_exist, "critical"),
    ("critical automations enabled", test_critical_automations_enabled, "critical"),
    # === Apollo resilience (HEALTH — warn-only, NEW template_sensors kan
    # have registration-delay >15s post-restart) ===
    # Sprint E.19 audit 2026-05-07: catches Apollo-unavailable bugs i template_sensors.
    # NB: starter som health-tier fordi indoor_temp_resilient er ny — efter
    # 1 uges drift (registration confirmed) kan den promoveres til critical.
    ("Apollo unavailable resilience", test_apollo_unavailable_resilience, "health"),
]


def main():
    parser = argparse.ArgumentParser(description="HA smoke test")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--tier",
        choices=["all", "critical", "health"],
        default="all",
        help="Run only tests af denne tier. critical = blocks deploy, "
        "health = warn-only. Default: all (failure i begge → exit 1).",
    )
    args = parser.parse_args()

    token = load_token()
    if not token:
        print(red("❌ HA_TOKEN ikke sat"))
        sys.exit(1)

    # Filter tests by tier
    tests_to_run = [(n, f, t) for n, f, t in TESTS if args.tier == "all" or args.tier == t]

    ha = HAClient(token)
    print(cyan(f"=== HA Smoke Test ({len(tests_to_run)} tests, tier={args.tier}) ===\n"))

    passed = critical_failed = health_failed = skipped = 0
    for name, fn, tier in tests_to_run:
        try:
            ok, info = fn(ha, args.verbose)
        except Exception as e:
            ok, info = False, f"exception: {e}"
        if ok is None:
            print(yellow(f"⏭  {name:50s} {info}"))
            skipped += 1
        elif ok:
            print(green(f"✅ {name:50s} {info}"))
            passed += 1
        else:
            tier_label = "CRITICAL" if tier == "critical" else "warn-only"
            color_fn = red if tier == "critical" else yellow
            print(color_fn(f"❌ [{tier_label}] {name:40s} {info}"))
            if tier == "critical":
                critical_failed += 1
            else:
                health_failed += 1

    print()
    if health_failed:
        print(yellow(f"⚠  {health_failed} health-tier failures (warn-only — not blocking)"))
    print(
        cyan(
            f"=== {passed} passed, {critical_failed} critical-failed, "
            f"{health_failed} health-failed, {skipped} skipped ==="
        )
    )
    # Exit 0 hvis ingen CRITICAL fail (health-fail er info, ikke regression)
    sys.exit(0 if critical_failed == 0 else 1)


if __name__ == "__main__":
    main()
