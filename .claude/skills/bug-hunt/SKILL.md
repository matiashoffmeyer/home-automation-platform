---
name: bug-hunt
description: Use when asked to hunt for bugs in the automations. Runs a quota-safe workflow (two cheap-model finders, one sceptic per finder), then verifies every confirmed finding in the code and the recorded history before anything is fixed.
---

# Bug hunt

Subagents are expensive here: each starts by writing 50-65k tokens of
context, and the quota is shared with the main session. A hunt that runs out
of quota halfway returns nothing. This shape has finished within quota every
time; `scripts/agent_guard.py` enforces the limits.

## 1. Choose the area, not the whole repository

Pick one or two clusters, in this order of yield:

- **A contested lamp's ownership registry and its history.** Start the finder
  in `docs/auto/ejerskab/<lamp>.md` and `python3 scripts/hq.py who <lamp>`:
  the real collisions are in `who`, not in the code.
- **Fresh code**: files changed in the last three days (`git log --since=3.days --name-only`).
- **Fix churn**: `git log --grep=fix --name-only --since=30.days | sort | uniq -c | sort -rn | head`.

## 2. Run the workflow

Constraints that the agent guard checks:

- every `agent()` has `model: 'sonnet'`;
- no `pipeline()`, no `while` loops;
- `parallel()` only over `.slice(i, i + 2)`;
- at most two agents running at a time.

Shape: two finders, one per cluster or lens, each with a schema output of at
most 8 findings and a budget of about 35 tool calls, read-only (GET against the
REST API only). Then one adversarial sceptic per finder, which tries to
refute that finder's batch.

## 3. Verify before fixing

The sceptic is not the last word. A "confirmed" finding has turned out to be
half of the mechanism before. For each one:

- read the consumer code yourself (failure class 10);
- pull the history around the claimed incident (`hq.py flanks`, `hq.py who`,
  the logbook) and check that the timeline really shows it;
- grep for the same pattern elsewhere: a real bug often has a sister.

## 4. Act

- Real and proven: fix it, run the `failure-class-review` and `deploy` skills.
- Plausible but unproven: add it to `BACKLOG.md` (`python3 scripts/backlog_ids.py --next`),
  do not fix it.
- Refuted: report it as refuted, with the evidence.
