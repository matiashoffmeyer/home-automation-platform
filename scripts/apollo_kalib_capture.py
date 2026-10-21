#!/usr/bin/env python3
"""Tomt-rum-baseline for Apollo MSR-2: støjgulv pr. gate med engineering mode.

Kaldes af shell_command.apollo_kalib_capture (packages/apollo_spoegelse_maaling.yaml)
når de bestilte rum har været tomme i 30 min — eller manuelt fra SSH-add-on'et:

    python3 scripts/apollo_kalib_capture.py stue,koekken [--sek 420]
    python3 scripts/apollo_kalib_capture.py --detach stue        # baggrund

Slår engineering mode til, sampler alle 18 gate-energier pr. rum ~1 Hz via
/api/template, og slår det ALTID fra igen (finally). 420 s default — sikkerheds-
automationen (automations/apollo_safety_switches.yaml) slukker selv efter 10 min.

Samples hvor rummets rå occupancy er on (± 10 s) er IKKE støj og holdes ude af
statistikken (talt som `n_beskidt`). Resultat:
  * ai_feedback/apollo_kalib_feedback.jsonl — én linje pr. rum: p50/p95/max pr.
    gate + slider-tærsklen + margin (tærskel − max). Committes.
  * /share/apollo_kalib/<ts>_<rum>.jsonl — rå samples (ikke i git).
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

import ha_secrets

ROOMS = {"stue", "koekken", "spisestue", "boernevaerelse", "sovevaerelse"}
SLIDER = {"sovevaerelse": "sove"}  # input_number-præfiks pr. Apollo
FEEDBACK = "/config/ai_feedback/apollo_kalib_feedback.jsonl"
RAW_DIRS = ["/share/apollo_kalib", "/config/apollo_kalib_raw"]


def api_base():
    """(base, token). secrets-tokenet FØRST (B182, 2026-10-03).

    HA Core's shell_command-subproces HAR en SUPERVISOR_TOKEN, men supervisor-
    proxyen afviser den (401) for /core/api — kun add-ons med homeassistant_api
    må bruge den. Før denne rettelse prøvede scriptet den først, så den bestilte
    nat-baseline dødede tavst: automationen fyrede 01:00 (bestillingen blev ryddet),
    `--detach` sender stderr i /dev/null, og første template-kald fik 401 → INGEN
    outputfil nogen nat. Samme token-valg som plant_notify/notif_queue/sky_notify
    (long-lived token + loopback virker fra både HA Core og SSH-add-on'et).
    """
    tok = ha_secrets.get(ha_secrets.HA_API_TOKEN, required=False)
    if tok:
        return "http://127.0.0.1:8123/api", tok
    tok = os.environ.get("SUPERVISOR_TOKEN")
    if tok:
        return "http://supervisor/core/api", tok
    raise RuntimeError("intet token (ha_api_token i secrets.yaml eller SUPERVISOR_TOKEN)")


BASE, TOKEN = api_base()


def call(path, body=None, timeout=10):
    req = urllib.request.Request(
        f"{BASE}/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def eng(rooms, on):
    ids = [f"switch.{r}_apollo_radar_engineering_mode" for r in rooms]
    call(f"services/switch/turn_{'on' if on else 'off'}", {"entity_id": ids})


def template_for(rooms):
    parts = []
    for r in rooms:
        p = f"sensor.{r}_apollo_"
        parts.append(
            f"'{r}': {{'occ': states('binary_sensor.{r}_apollo_occupancy'),"
            f" 's': [{','.join(f'states({chr(39)}{p}g{g}_still_energy{chr(39)})|float(-1)' for g in range(9))}],"
            f" 'm': [{','.join(f'states({chr(39)}{p}g{g}_move_energy{chr(39)})|float(-1)' for g in range(9))}]}}"
        )
    return "{{ {" + ", ".join(parts) + "} | to_json }}"


def context_for(rooms):
    """Tærskler (slider + NVRAM) og temperaturer pr. rum."""
    parts = []
    for r in rooms:
        sl = SLIDER.get(r, r)
        parts.append(
            f"'{r}': {{"
            f"'slider_s': [{','.join(f'states({chr(39)}input_number.{sl}_g{g}_still{chr(39)})|float(-1)' for g in range(9))}],"
            f"'slider_m': [{','.join(f'states({chr(39)}input_number.{sl}_g{g}_move{chr(39)})|float(-1)' for g in range(9))}],"
            f"'nvram_s': [{','.join(f'states({chr(39)}number.{r}_apollo_g{g}_still_threshold{chr(39)})|float(-1)' for g in range(9))}],"
            f"'nvram_m': [{','.join(f'states({chr(39)}number.{r}_apollo_g{g}_move_threshold{chr(39)})|float(-1)' for g in range(9))}],"
            f"'temp': states('sensor.{r}_apollo_temperature')|float(-1),"
            f"'esp': states('sensor.{r}_apollo_esp_temperature')|float(-1)}}"
        )
    return (
        "{{ {"
        + ", ".join(parts)
        + ", 'hus': states('input_select.house_state'), 'tomt': is_state('binary_sensor.hus_bevist_tomt','on')} | to_json }}"
    )


def log_path():
    for d in RAW_DIRS:
        try:
            os.makedirs(d, exist_ok=True)
            return os.path.join(d, "capture.log")
        except OSError:
            continue
    return os.devnull


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p / 100 * len(v)))] if v else None


def summarize(rooms, samples, ctx_start, ctx_end, sek):
    out = []
    for r in rooms:
        occ_t = [s["t"] for s in samples if s[r]["occ"] == "on"]
        clean = [
            s
            for s in samples
            if s[r]["occ"] == "off"
            and not any(abs(s["t"] - t) <= 10 for t in occ_t)
            and all(x >= 0 for x in s[r]["s"] + s[r]["m"])
        ]
        row = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "rum": r,
            "sek": sek,
            "n": len(clean),
            "n_beskidt": len(samples) - len(clean),
            "hus": ctx_start.get("hus"),
            "tomt": ctx_start.get("tomt"),
            "temp": [ctx_start[r]["temp"], ctx_end[r]["temp"]],
            "esp": [ctx_start[r]["esp"], ctx_end[r]["esp"]],
            "gates": {},
        }
        for k, lab in (("s", "still"), ("m", "move")):
            for g in range(9):
                v = [s[r][k][g] for s in clean]
                thr = ctx_start[r]["slider_" + k][g]
                mx = max(v) if v else None
                row["gates"][f"{lab}_g{g}"] = {
                    "p50": pct(v, 50),
                    "p95": pct(v, 95),
                    "max": mx,
                    "taerskel": thr,
                    "nvram": ctx_start[r]["nvram_" + k][g],
                    "margin": (thr - mx) if (mx is not None and thr >= 0) else None,
                }
        out.append(row)
    return out


def main():
    args = [a for a in sys.argv[1:]]
    if "--detach" in args:
        args.remove("--detach")
        # Log til fil, ikke /dev/null: en tavs død er præcis hvad der skjulte
        # token-fejlen ovenfor. (Et første linje-stempel viser at barnet startede.)
        logf = open(log_path(), "a", encoding="utf-8")
        logf.write(f"{datetime.now().isoformat(timespec='seconds')} start {' '.join(args)}\n")
        logf.flush()
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), *args],
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=logf,
            start_new_session=True,
        )
        return 0
    sek = 420
    if "--sek" in args:
        i = args.index("--sek")
        sek = min(int(args[i + 1]), 540)
        del args[i : i + 2]
    rooms = [r for r in (args[0] if args else "").split(",") if r]
    if not rooms or not set(rooms) <= ROOMS or not all(re.fullmatch(r"[a-z]+", r) for r in rooms):
        print(
            f"usage: apollo_kalib_capture.py [--detach] rum[,rum] [--sek N]  (rum ∈ {sorted(ROOMS)})"
        )
        return 1
    tpl, ctx_tpl = template_for(rooms), context_for(rooms)
    ctx_start = json.loads(call("template", {"template": ctx_tpl}))
    samples = []
    try:
        eng(rooms, True)
        time.sleep(10)  # energierne begynder først at streame efter skiftet
        t_end = time.time() + sek
        while time.time() < t_end:
            t = time.time()
            try:
                s = json.loads(call("template", {"template": tpl}, timeout=5))
                s["t"] = round(t, 1)
                samples.append(s)
            except Exception:  # noqa: BLE001 — ét tabt sample er ligegyldigt
                pass
            time.sleep(max(0.0, 1.0 - (time.time() - t)))
    finally:
        for _ in range(3):
            try:
                eng(rooms, False)
                break
            except Exception:  # noqa: BLE001
                time.sleep(5)
    ctx_end = json.loads(call("template", {"template": ctx_tpl}))
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    for d in RAW_DIRS:
        try:
            os.makedirs(d, exist_ok=True)
            with open(
                os.path.join(d, f"{stamp}_{'_'.join(rooms)}.jsonl"), "w", encoding="utf-8"
            ) as fh:
                for s in samples:
                    fh.write(json.dumps(s) + "\n")
            break
        except OSError:
            continue
    rows = summarize(rooms, samples, ctx_start, ctx_end, sek)
    os.makedirs(os.path.dirname(FEEDBACK), exist_ok=True)
    with open(FEEDBACK, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    msg = " · ".join(
        f"{row['rum']}: n={row['n']}, mindste margin "
        + str(
            min(
                (
                    g["margin"]
                    for g in row["gates"].values()
                    if g["margin"] is not None and g["taerskel"] < 100
                ),
                default="–",
            )
        )
        for row in rows
    )
    try:
        call(
            "services/logbook/log",
            {
                "name": "Apollo-kalibrering",
                "message": "baseline færdig — " + msg,
                "entity_id": "input_text.apollo_kalib_bestilling",
            },
        )
    except Exception:  # noqa: BLE001
        pass
    print(msg)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — traceback til loggen (detach-barnet har ingen terminal)
        import traceback

        print(f"{datetime.now().isoformat(timespec='seconds')} FEJL", file=sys.stderr)
        traceback.print_exc()
        sys.exit(2)
