#!/usr/bin/env python3
"""Databasen med i backuppen kun hver N. dag (B273, user-spec 28/10: "ugentlig er fint").

HA's automatiske backup har ét globalt flag, `create_backup.include_database`,
og ingen service der sætter det — kun websocket'en (`backup/config/update`).
Scriptet køres kl. 03:00 (før den automatiske backup ~05:00) og sætter flaget
efter ALDEREN på den nyeste backup der faktisk har databasen med, ikke efter
ugedagen: fejler søndagens backup, tager mandagens DB'en med i stedet.

  python3 scripts/backup_db_ugentlig.py set <dage>   # sæt flaget, value-compare først
  python3 scripts/backup_db_ugentlig.py status       # kun læs

En DB-backup tæller kun når den ligger på ALLE konfigurerede placeringer
(B252, 28/10): en DB-backup der kun nåede NUC'ens egen disk dør med NUC'en, så
næste nat tager DB'en med igen, indtil også Google Drive har en.

Udskriver én JSON-linje (shell_command `response_variable` → stdout). `agenter`
giver antal og nyeste alder pr. placering, så `backup_vagt_placering` og
`ha_health.sh backup` kan se en placering der er holdt op med at få backups.
HA tæller en backup som lykkedes selvom en placering er utilgængelig (fx et
udløbet Drive-login), så det fanger `backup_vagt_dagligt_tjek` ikke.
`dage` ≤ 7: retention er 7 kopier, så et længere interval ville efterlade dage
helt uden en DB-backup. Grænsen er `dage` døgn minus 12 t, så en backup fra
præcis N døgn siden (~05:00, nu kl. 03:00 = N×24 − 2 t) tæller som gammel nok.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime

import websockets

import ha_secrets

WS = "ws://127.0.0.1:8123/api/websocket"


async def run(mode, dage):
    async with websockets.connect(WS, max_size=None) as ws:
        await ws.recv()
        token = ha_secrets.get(ha_secrets.HA_API_TOKEN)
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            sys.exit("auth fejlede")
        msg_id = 0

        async def call(payload):
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({**payload, "id": msg_id}))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == msg_id:
                    if not r.get("success"):
                        sys.exit(f"{payload['type']} fejlede: {r.get('error')}")
                    return r["result"]

        info = await call({"type": "backup/info"})
        cfg = (await call({"type": "backup/config/info"}))["config"]
        nu = datetime.now(UTC)
        alle = cfg["create_backup"]["agent_ids"]

        def alder(datoer):
            return round((nu - max(datoer)).total_seconds() / 3600, 1) if datoer else None

        def dato(b):
            return datetime.fromisoformat(b["date"])

        db = [
            dato(b)
            for b in info["backups"]
            if b.get("database_included") and set(alle) <= set(b["agents"])
        ]
        alder_t = alder(db)
        har = cfg["create_backup"]["include_database"]
        agenter = {}
        for a in sorted(set(alle) | {a for b in info["backups"] for a in b["agents"]}):
            paa = [b for b in info["backups"] if a in b["agents"]]
            agenter[a] = {
                "konfigureret": a in alle,
                "antal": len(paa),
                "nyeste_alder_t": alder([dato(b) for b in paa]),
                "nyeste_db_alder_t": alder([dato(b) for b in paa if b.get("database_included")]),
            }
        out = {
            "include_database": har,
            "changed": False,
            "db_backups": len(db),
            "nyeste_db_alder_t": alder_t,
            "agenter": agenter,
            "agent_fejl": sorted(info.get("agent_errors") or {}),
        }
        if mode == "set":
            vil = alder_t is None or alder_t >= dage * 24 - 12
            if vil != har:
                await call(
                    {"type": "backup/config/update", "create_backup": {"include_database": vil}}
                )
                out.update(include_database=vil, changed=True)
        print(json.dumps(out))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode not in ("set", "status"):
        sys.exit(__doc__)
    dage = min(7, max(1, int(float(sys.argv[2])))) if mode == "set" else 0
    asyncio.run(run(mode, dage))


if __name__ == "__main__":
    main()
