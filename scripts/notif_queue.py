#!/usr/bin/env python3
"""Arrival queue for push notifications.

Notices that can only be acted on at home (plants, the robot vacuum, batteries
and so on) should not interrupt someone who is out. They are queued and
delivered when that person's GPS reaches home. This is decided per recipient:
a parent who is at home gets the push at once, while the other parent's copy
waits for their arrival.

Called from Home Assistant:
  append <b64-json>  the defer branch of script.push_notify (shell_command).
                     JSON: {nid, target, title, message, payload}
  flush              an automation on person -> home, a 30-minute backstop,
                     and leaving guest mode.
  count              a command_line sensor (JSON: total and per recipient).

The queue is ``/config/notif_queue.jsonl`` (a file survives restarts and
recorder purges). Nothing is dropped for age, but duplicates per
(target, nid, title) collapse to the newest, so a week of daily plant notices
becomes one push on arrival.

Flush gates per entry (keep, drop or send):
  - ``notif_<nid>_enabled`` or ``notif_<nid>_<who>`` switched off      -> drop (opted out)
  - master switch off, guest mode without opt-in, outside the time window -> keep
  - ``notif_<nid>_hjemme`` still on and the person not at home           -> keep
    (a person who is unknown, unavailable or missing counts as home: a
    broken GPS must not hold notices back forever)
  - otherwise send through the notify API; a failed send -> keep.

Token: ``ha_api_token`` from ``secrets.yaml`` (the script runs in the core
container through shell_command).
"""

import base64
import fcntl
import json
import os
import re
import sys
import urllib.request
from datetime import UTC, datetime

import ha_secrets

QUEUE_FILE = "/config/notif_queue.jsonl"
LOCK_FILE = "/config/.notif_queue.lock"
HA_URL = "http://127.0.0.1:8123"

TARGETS = {
    "mobile_app_phone_a": ("parent_a", "person.parent_a"),
    "mobile_app_phone_b": ("parent_b", "person.parent_b"),
}
HOME_ISH = ("home", "unknown", "unavailable")


def get_token():
    return ha_secrets.get(ha_secrets.HA_API_TOKEN)


class Lock:
    def __enter__(self):
        self.fh = open(LOCK_FILE, "w", encoding="utf-8")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def read_entries():
    if not os.path.exists(QUEUE_FILE):
        return []
    entries = []
    with open(QUEUE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def write_entries(entries):
    tmp = QUEUE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, QUEUE_FILE)


def dedupe(entries):
    """Nyeste vinder pr. (target, nid, title); bevarer kronologisk orden."""
    latest = {}
    for e in entries:
        latest[(e.get("target"), e.get("nid"), e.get("title"))] = e
    keep = set(id(e) for e in latest.values())
    return [e for e in entries if id(e) in keep]


def cmd_append(b64):
    try:
        entry = json.loads(base64.b64decode(b64))
    except Exception as exc:  # noqa: BLE001
        print(f"bad payload: {exc}", file=sys.stderr)
        return 1
    nid = entry.get("nid", "")
    if not re.fullmatch(r"[a-z_]{1,40}", nid):
        print(f"bad nid: {nid!r}", file=sys.stderr)
        return 1
    if entry.get("target") not in TARGETS:
        print(f"bad target: {entry.get('target')!r}", file=sys.stderr)
        return 1
    entry["queued_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with Lock():
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 0


def cmd_count():
    with Lock():
        entries = dedupe(read_entries())
    out = {"total": len(entries), "parent_a": 0, "parent_b": 0}
    for e in entries:
        who = TARGETS.get(e.get("target"), (None, None))[0]
        if who:
            out[who] += 1
    print(json.dumps(out))
    return 0


def fetch_states(token):
    req = urllib.request.Request(
        HA_URL + "/api/states",
        headers={"Authorization": "Bearer " + token},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return {s["entity_id"]: s for s in data}


def state_of(states, eid, default=None):
    s = states.get(eid)
    return s["state"] if s else default


def window_ok(states, nid, now):
    st = states.get(f"input_datetime.notif_{nid}_start")
    sl = states.get(f"input_datetime.notif_{nid}_slut")
    if not st or not sl:
        return True
    sh, sm = st["attributes"].get("hour"), st["attributes"].get("minute", 0)
    eh, em = sl["attributes"].get("hour"), sl["attributes"].get("minute", 0)
    if sh is None or eh is None:
        return True
    s, e, nowm = sh * 60 + sm, eh * 60 + em, now.hour * 60 + now.minute
    if s == e:
        return True
    return s <= nowm < e if s < e else (nowm >= s or nowm < e)


def send(token, target, entry, now):
    msg = entry.get("message", "")
    try:
        qt = datetime.fromisoformat(entry["queued_at"])
        if (now.astimezone() - qt).total_seconds() > 1800:
            msg += f"\n⏳ Ventet siden {qt.strftime('%d/%m kl. %H:%M')}"
    except KeyError, ValueError:
        pass
    body = json.dumps(
        {"title": entry.get("title", ""), "message": msg, "data": entry.get("payload") or {}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_URL}/api/services/notify/{target}",
        data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=30)


def cmd_flush(dry_run=False):
    with Lock():
        entries = dedupe(read_entries())
        if not entries:
            return 0
        token = get_token()
        states = fetch_states(token)
        now = datetime.now(UTC)
        airbnb = state_of(states, "input_select.house_mode") == "AirBnB"
        master_on = state_of(states, "input_boolean.notifikationer_master_enabled") != "off"
        remaining = []
        for e in entries:
            nid, target = e.get("nid"), e.get("target")
            who, person = TARGETS[target]
            if (
                state_of(states, f"input_boolean.notif_{nid}_enabled") == "off"
                or state_of(states, f"input_boolean.notif_{nid}_{who}") == "off"
            ):
                if dry_run:
                    print(f"DROP  {who} {nid} {e.get('title')!r} (fravalgt)")
                continue
            hold = None
            if not master_on:
                hold = "master off"
            elif airbnb and state_of(states, f"input_boolean.notif_{nid}_airbnb", "off") != "on":
                hold = "airbnb"
            elif (
                state_of(states, f"input_boolean.notif_{nid}_hjemme") == "on"
                and state_of(states, person, "unknown") not in HOME_ISH
            ):
                hold = f"{who} ikke hjemme"
            elif not window_ok(states, nid, datetime.now()):
                hold = "uden for tidsvindue"
            if hold:
                if dry_run:
                    print(f"HOLD  {who} {nid} {e.get('title')!r} ({hold})")
                remaining.append(e)
                continue
            if dry_run:
                print(f"SEND  {who} {nid} {e.get('title')!r}")
                continue
            try:
                send(token, target, e, now)
            except Exception as exc:  # noqa: BLE001
                print(f"send fejlede ({target}): {exc}", file=sys.stderr)
                remaining.append(e)
        if not dry_run:
            write_entries(remaining)
    return 0


def main():
    if len(sys.argv) < 2:
        print("usage: notif_queue.py append <b64>|flush [--dry-run]|count", file=sys.stderr)
        return 1
    cmd = sys.argv[1]
    if cmd == "append" and len(sys.argv) >= 3:
        return cmd_append(sys.argv[2])
    if cmd == "flush":
        return cmd_flush(dry_run="--dry-run" in sys.argv)
    if cmd == "count":
        return cmd_count()
    print(f"ukendt kommando: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
