#!/usr/bin/env python3
"""Trail Buddy's API keys from secrets.yaml into the add-on's options (user 2026-11-26: Mapy.com
as a closure source). The add-on reads `mapy_api_key` from its options (run.sh → MAPY_API_KEY);
a reinstall empties them, so this puts it back. Never prints a value, only whether it changed.

  python3 scripts/trailbuddy_keys.py            set what differs (the add-on restarts to read it:
                                                ask first, `live_godkend.py spørg … --genstart`)
  python3 scripts/trailbuddy_keys.py --restart  ...and restart the add-on when something changed
"""

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ha_secrets  # noqa: E402

ADDON = "local_trailbuddy"
MAPY_KEY = "mapy_api_key"  # secrets_contract.py wants the key as a constant
KEYS = {"mapy_api_key": MAPY_KEY}  # add-on option → the secret's key


def supervisor(path, body=None):
    req = urllib.request.Request(
        f"http://supervisor{path}",
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}",
            "Content-Type": "application/json",
        },
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--restart", action="store_true", help="restart the add-on after a change")
    a = ap.parse_args()
    opts = supervisor(f"/addons/{ADDON}/info")["data"]["options"]
    changed = []
    vals = {MAPY_KEY: ha_secrets.get(MAPY_KEY)}
    for opt, key in KEYS.items():
        val = vals[key]
        if not val:
            print(f"{key}: not set in secrets.yaml (scripts/secret_set.py ask {key} …)")
            return 1
        if opts.get(opt) != val:
            opts[opt] = val
            changed.append(opt)
    if not changed:
        print("the add-on's keys match secrets.yaml")
        return 0
    supervisor(f"/addons/{ADDON}/options", {"options": opts})
    print(f"set: {', '.join(changed)}")
    if a.restart:
        supervisor(f"/addons/{ADDON}/restart", {})
        print("restarted")
    else:
        print("the add-on reads them at its next start")
    return 0


if __name__ == "__main__":
    sys.exit(main())
