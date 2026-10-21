---
name: failure-class-review
description: Use before declaring an automation or package change done. Walks the diff against the failure-class signatures in CLAUDE.md (co-owners, missing re-arm, kill switches, unavailable, template reload, guest mode) and runs the automated checks that cover the rest.
---

# Failure-class review

The failure classes in CLAUDE.md are defects that recurred in this
repository's history. Each is cheap to avoid and expensive to find in
production. This is the pass that applies them to *your* diff.

## 1. Run the automated checks

```sh
python3 scripts/ha_offline.py check         # Home Assistant's own validator
python3 scripts/ha_validate.py --quiet      # refs, duplicates, Jinja, Matter continue_on_error, …
python3 scripts/b103_scan.py                # `to:` without `from:` on template entities
python3 scripts/roster_drift.py             # copied entity lists that drifted apart (#16, #2)
python3 scripts/ejerskab.py gen             # if a lamp with an ownership registry was touched
```

## 2. List what the diff touches

```sh
git diff --stat
git diff -U0 | grep -oE '(light|switch|input_boolean|input_number|binary_sensor|sensor|cover)\.[a-z0-9_]+' | sort -u
```

## 3. Ask the signature questions, per touched entity

| # | Question | How to answer it |
|---|---|---|
| 1 | Who else writes this entity? Is "single owner" true? | `grep -rn <entity> automations/ packages/ script_pkg/ rosters/`; `hq.py who <entity>` for writers in practice |
| 2 | Is the same rule coded somewhere else? | grep the rule's key expression (entity + operator) |
| 3 | Does "manual wins" rely on `parent_id is none`? | manual = `context.user_id is not none` |
| 4 | What re-fires if the edge happens while blocked? | every flank trigger needs a re-arm path |
| 9 | What happens on `unavailable`? | gate on health sensors, not on a skewed state |
| 12 | Did a sister automation get the same guard? | grep the siblings with the same physics |
| 19 | Does the blocked action fire the second the block lifts? | the action needs its own condition |
| 21 | Is the kill switch a `condition` on every path in? | `grep -rn <feature>_enabled` against `grep -rn <action>` |
| 22 | Did every automation load? | `./scripts/ha_health.sh deploy` after reload |
| 26 | Is a house-wide gate locking a room-scoped state? | scope the gate and its neighbour conditions |
| 27 | Does a borrower hand back a stale snapshot? | ask the house again at hand-back |

Also check the guest mode: `house_mode` has three options (`Normal`,
`AirBnB`, `Home Vacation`), so family logic is `in ['Normal','Home Vacation']`,
not `== 'Normal'`; a suppressor needs an automatic way out for a guest who
does not know the system.

## 4. Trace the claims

Every comment you wrote that claims behaviour ("manual always wins", "only
this automation…") must be checked against the code (#3, #10). Unproven
claims are removed or proven.

## Report

One line per class that applied: the class, what you checked, and the verdict.
Do not list classes that do not apply.
