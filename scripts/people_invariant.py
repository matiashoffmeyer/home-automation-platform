#!/usr/bin/env python3
"""people_invariant.py: the people count may only fall after the front door.

User-spec (2026-07-22, restated 2026-10-21): sensor.people_estimate never
decreases unless the front door opened within the door window, or the user
corrected it (+/- on Status, the "For mange" answer, the kids-off button).
v6.1 (2026-10-22): a fall to 0 while the house is Dormant within the
empty-house window after the door is the door's own verdict, and is allowed.
The rule leaked for three months because every fix guarded a PART of the
formula and nothing checked the number the house actually shows. This does.

    python3 scripts/people_invariant.py             # last 2 days
    python3 scripts/people_invariant.py --dage 14   # longer look-back

Exit 1 when a decrease has no allowed cause. Times are local.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hq  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = ROOT / "ai_feedback" / "people_estimate_feedback.jsonl"
COUNT = "sensor.people_estimate"
DOOR = "binary_sensor.parasoll_hoveddoer"
KIDS_OFF = "input_boolean.kids_home_manual_off"
MODE = "input_select.house_mode"
WINDOW = "input_number.people_afgang_vindue_minutter"
DOM = "input_number.people_afgang_dom_minutter"
STATE = "input_select.house_state"
# The held count follows the bid only after it has held zone-sustain (150 s),
# checked on a /1 tick, so a legal fall can land a few minutes after the window.
SLACK = timedelta(minutes=4)
USER_SLACK = timedelta(seconds=30)


def user_corrections(since):
    """Timestamps of the user's own corrections from the trainer log."""
    out = []
    try:
        lines = FEEDBACK.read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        user = r.get("type") == "manuel" or (
            r.get("type") == "manuel_slut" and r.get("grund") == "knap"
        )
        user = user or (r.get("type") == "answer" and r.get("answer") == "formange")
        if user and r.get("ts"):
            t = datetime.fromisoformat(r["ts"])
            if t >= since:
                out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dage", type=float, default=2)
    a = ap.parse_args()
    ha = hq.HA()
    end = hq.now_utc()
    start = end - timedelta(days=a.dage)
    window = timedelta(minutes=float(ha.template("{{ states('%s') | float(15) }}" % WINDOW)))
    dom = timedelta(minutes=float(ha.template("{{ states('%s') | float(0) }}" % DOM)))

    count = ha.history(COUNT, start, end)
    doors = [t for t, v in ha.history(DOOR, start, end) if v == "on"]
    kids_off = [t for t, v in ha.history(KIDS_OFF, start, end) if v == "on"]
    modes = [t for t, _ in ha.history(MODE, start, end)[1:]]
    states = ha.history(STATE, start, end)

    def dormant(t):
        last = [v for x, v in states if x <= t]
        return bool(last) and last[-1] == "Dormant"

    users = user_corrections(start)

    def near(times, t, before, after=USER_SLACK):
        return any(t - before <= x <= t + after for x in times)

    falls, bad, prev = 0, [], None
    for t, v in count:
        try:
            n = int(float(v))
        except TypeError, ValueError:
            if prev is not None:  # unavailable/unknown: compare across the gap
                prev = (prev[0], prev[1], True)
            continue
        if prev is not None and n < prev[1]:
            falls += 1
            if near(doors, t, window + SLACK):
                pass
            elif near(users, t, USER_SLACK) or near(kids_off, t, window + SLACK):
                pass
            elif near(modes, t, timedelta(minutes=1)):
                pass
            elif n == 0 and dormant(t) and near(doors, t, dom + SLACK, timedelta(0)):
                pass
            else:
                gap = " (efter unavailable)" if prev[2] else ""
                bad.append(f"  {hq.fmt_t(t)}  {prev[1]} → {n}{gap}")
        prev = (t, n, False)

    print(
        f"people_estimate {a.dage:g} døgn: {falls} fald, {len(bad)} uden hoveddør "
        f"(vindue {window.total_seconds() / 60:g} min) eller brugerens rettelse"
    )
    for line in bad[-40:]:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
