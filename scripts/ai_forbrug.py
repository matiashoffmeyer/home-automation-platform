#!/usr/bin/env python3
"""ai_forbrug.py — ÉN vej til husets AI-kald (HA's ai_task), med regnskab og loft.

User-spec 2026-11-04: "hold øje med costs! jeg vil ikke betale særlig meget for
det her" → "giv visuals på cost! både for det og folketinget". Alle scripts der
kalder en model går gennem `generer()`, så hvert kald skrives i ét regnskab og
et fælles månedsloft (input_number.ai_loft_kr_maaned) kan stoppe dem alle.

PRISEN ER ANSLÅET, ikke faktureret: ai_task-svaret har ingen token-tal, og
Anthropic-nøglen må ikke ligge i filer. Tokens ≈ tegn/3 (dansk tekst) + et fast
tillæg for HA's egen system-prompt og struktur-skemaet. Konservativt: hellere
for højt end for lavt. Den rigtige regning: console.anthropic.com → Usage.

Modellen sættes i Anthropic-integrationen (ai_task-subentry'en, 2026-11-04:
claude-haiku-4-5, thinking slået fra). Skiftes den, ret MODEL herunder.

Kommandoer (packages/ai_forbrug.yaml):
  status [formål]   JSON til command_line-sensorerne sensor.ai_udgift[_<formål>]
                    (state = kr i alt, total_increasing → statistik-grafer)

Biblioteket:
  generer(formaal, instruktioner, struktur=None) → svarets `data` (dict/str)
  AiLoft            kastes FØR kaldet hvis månedens loft er nået

Regnskab: /config/.ai_forbrug.jsonl (gitignored), én linje pr. kald.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ha_secrets  # noqa: E402

TZ = ZoneInfo("Europe/Copenhagen")
HA_URL = "http://127.0.0.1:8123"
REGNSKAB = "/config/.ai_forbrug.jsonl"
E_LOFT = "input_number.ai_loft_kr_maaned"
LOFT_DEFAULT = 10.0

MODEL = "claude-haiku-4-5"
# USD pr. million tokens (ind, ud). Ukendt model → Sonnet-pris (hellere for højt).
PRISER = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
}
UKENDT_PRIS = (3.0, 15.0)
USD_DKK = 7.0  # rundet op (kursen lå ~6,5-6,9 i 2026)
TEGN_PR_TOKEN = 3.0
TILLAEG_IND = 400  # HA's system-prompt + struktur-skemaet, tokens pr. kald
TILLAEG_UD = 30  # tool-call-indpakningen om et struktureret svar


class AiLoft(Exception):
    """Månedens AI-loft er nået — kalderen falder tilbage til sin ikke-AI-vej."""


def _ha(method, path, payload=None, timeout=30):
    token = ha_secrets.get(ha_secrets.HA_API_TOKEN)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def kr(model, tok_ind, tok_ud):
    pi, pu = PRISER.get(model, UKENDT_PRIS)
    return (tok_ind * pi + tok_ud * pu) / 1e6 * USD_DKK


def anslaa(tegn_ind, tegn_ud=0):
    """→ (tokens ind, tokens ud) for ét kald."""
    return (
        round(tegn_ind / TEGN_PR_TOKEN) + TILLAEG_IND,
        round(tegn_ud / TEGN_PR_TOKEN) + TILLAEG_UD,
    )


def laes():
    ud = []
    try:
        with open(REGNSKAB, encoding="utf-8") as f:
            for line in f:
                try:
                    ud.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return ud


def skriv(post):
    with open(REGNSKAB, "a", encoding="utf-8") as f:
        f.write(json.dumps(post, ensure_ascii=False) + "\n")


def maaned_nu():
    return datetime.now(TZ).strftime("%Y-%m")


def loft_kr():
    try:
        return float(_ha("GET", f"/api/states/{E_LOFT}")["state"])
    except Exception:
        return LOFT_DEFAULT


def ai_entity():
    ids = sorted(
        s["entity_id"] for s in _ha("GET", "/api/states") if s["entity_id"].startswith("ai_task.")
    )
    if not ids:
        raise RuntimeError("ingen ai_task-entity i HA")
    return ids[0]


def generer(formaal, instruktioner, struktur=None, timeout=120):
    """Ét ai_task-kald. Loftet tjekkes FØR (månedens forbrug + dette kalds
    anslåede input), og kaldet skrives i regnskabet bagefter — også når svaret
    ikke kan bruges, for det er betalt alligevel."""
    m = maaned_nu()
    brugt = sum(p.get("kr", 0) for p in laes() if p.get("tid", "")[:7] == m)
    loft = loft_kr()
    if brugt + kr(MODEL, *anslaa(len(instruktioner), 0)) > loft:
        raise AiLoft(f"månedens AI-loft {loft:.0f} kr er nået ({brugt:.2f} kr brugt)")
    payload = {"task_name": formaal, "entity_id": ai_entity(), "instructions": instruktioner}
    if struktur:
        payload["structure"] = struktur
    svar = _ha("POST", "/api/services/ai_task/generate_data?return_response", payload, timeout)
    data = (svar.get("service_response") or {}).get("data")
    ud_tekst = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    ti, tu = anslaa(len(instruktioner), len(ud_tekst or ""))
    skriv(
        {
            "tid": datetime.now(TZ).isoformat(timespec="seconds"),
            "formaal": formaal.split()[0],
            "model": MODEL,
            "tegn_ind": len(instruktioner),
            "tegn_ud": len(ud_tekst or ""),
            "tok_ind": ti,
            "tok_ud": tu,
            "kr": round(kr(MODEL, ti, tu), 5),
        }
    )
    return data


def _kald(poster):
    # En efterregnet linje kan dække flere kald ("kald": N).
    return sum(p.get("kald", 1) for p in poster)


def status(formaal=None):
    poster = [p for p in laes() if formaal is None or p.get("formaal") == formaal]
    m = maaned_nu()
    mdr = [p for p in poster if p.get("tid", "")[:7] == m]
    alle_mdr = [p for p in laes() if p.get("tid", "")[:7] == m]
    return {
        "state": round(sum(p.get("kr", 0) for p in poster), 4),
        "kr_maaned": round(sum(p.get("kr", 0) for p in mdr), 3),
        "kald_maaned": _kald(mdr),
        "kald_i_alt": _kald(poster),
        "tokens_ind_maaned": sum(p.get("tok_ind", 0) for p in mdr),
        "tokens_ud_maaned": sum(p.get("tok_ud", 0) for p in mdr),
        "kr_pr_kald": (
            round(sum(p.get("kr", 0) for p in poster) / _kald(poster), 4) if poster else 0
        ),
        "husets_kr_maaned": round(sum(p.get("kr", 0) for p in alle_mdr), 3),
        "loft_kr_maaned": loft_kr(),
        "model": MODEL,
        "sidste_kald": poster[-1]["tid"] if poster else None,
    }


def main(argv):
    if len(argv) >= 2 and argv[1] == "status":
        print(json.dumps(status(argv[2] if len(argv) > 2 else None), ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
