#!/usr/bin/env python3
"""Append en people_estimate feedback-linje (base64 JSON) til JSONL-loggen.

Kaldes af shell_command.people_feedback_append med ét base64-argument.
Filen overlever AirBnB recorder-purge (fil, ikke DB) og committes til git
saa senere Claude-sessioner kan kalibrere people_estimate mod facit.
"""

import base64
import json
import os
import sys
from datetime import datetime

LOG_DIR = "/config/ai_feedback"
LOG_FILE = os.path.join(LOG_DIR, "people_estimate_feedback.jsonl")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: people_feedback_append.py <base64-json>", file=sys.stderr)
        return 1
    try:
        payload = json.loads(base64.b64decode(sys.argv[1]))
    except Exception as exc:  # noqa: BLE001
        print(f"bad payload: {exc}", file=sys.stderr)
        return 1
    payload["logged_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
