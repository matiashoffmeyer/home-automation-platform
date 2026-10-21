#!/usr/bin/env python3
"""Append en AI-traener feedback-linje (base64 JSON) til JSONL-log pr. traener.

Kaldes af shell_command.ai_feedback_append med <slug> <base64-json>.
Skriver til /config/ai_feedback/<slug>_feedback.jsonl. Fil, IKKE recorder —
overlever AirBnB recorder-purge og committes til git, saa senere Claude-
sessioner kan kalibrere systemets gaet mod brugerens facit.

Generisk soster til people_feedback_append.py (people-estimatet beholder sin
egen fil/kommando for log-kontinuitet).
"""

import base64
import json
import os
import re
import sys
from datetime import datetime

LOG_DIR = "/config/ai_feedback"


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: ai_feedback_append.py <slug> <base64-json>", file=sys.stderr)
        return 1
    slug = sys.argv[1]
    if not re.fullmatch(r"[a-z_]{1,40}", slug):
        print(f"bad slug: {slug!r}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(base64.b64decode(sys.argv[2]))
    except Exception as exc:  # noqa: BLE001
        print(f"bad payload: {exc}", file=sys.stderr)
        return 1
    payload["logged_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, f"{slug}_feedback.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
