# 6. Rules that protect the house or the budget run as hooks

- **Status:** accepted
- **Date:** 2026-10-04, extended 2026-10-07 and 2026-10-10

## Context

The platform is developed by a coding agent with production access. Its
instructions live in `CLAUDE.md` and in path-scoped rule files under
`.claude/rules/`. Written rules have two weaknesses:

- **They are not always in context.** A rule file loads natively when a
  matching file is read. The agent often reaches a domain through a shell
  command, for example a history query, and then the rule never loads.
- **They are advice.** A rule can be broken in one session, and the damage is
  done before anyone reads the transcript. Two rules mattered most. A plain
  `ha core restart` loses the last state write, because Home Assistant crashes
  during shutdown on this host. Too many concurrent subagents exhaust the API
  quota, and the agents then die without reporting.

## Decision

Rules with a direct cost when broken are enforced in the agent's tool calls
through hooks configured in `.claude/settings.json`:

| Hook | Blocks or adds |
|---|---|
| `scripts/session_start.sh` | installs the git hooks and reports how far the checkout is behind `origin/main` |
| `scripts/claude_rules.py hook` | loads the rule file for a domain the first time a call touches it, including through shell commands |
| `scripts/ejerskab_hook.py` | shows a lamp's ownership contract before an edit and lints the edit afterwards ([ADR 4](0004-lamp-ownership-registry.md)) |
| `scripts/restart_guard.py` | rejects a plain `ha core restart`; restarts go through `scripts/ha_restart.sh`, which saves state first |
| `scripts/live_guard.py` | rejects light, sound and restart commands until the household has said yes on a push with Godkend / Afvis / Om 20 min (`scripts/live_godkend.py spørg`); a restart passes when Home Assistant is down |
| `scripts/agent_guard.py` | at most two subagents at a time; a cheaper model on every workflow agent; no unbounded fan-out |

Context hooks fail open: a broken hook must never block a session.
Enforcement belongs to the git hooks and CI.

`scripts/claude_rules.py check` keeps the rule layer itself honest. It fails
when a rule's `paths:` glob matches no tracked file, which would silently
orphan the rule after a rename, and when `CLAUDE.md` holds more than three
sprint notes.

## Consequences

- A rule that is broken once becomes a hook. The subagent limits had been a
  written rule; after one session exceeded them and the quota ran out, the
  agent guard was added the same day.
- Only the user can switch the agent guard off, by creating a git-ignored
  marker file.
- Hooks are local to the agent. Git hooks do not follow a clone, so the
  session hook reinstalls them, and a commit made elsewhere without them is
  caught only by CI.
- Every hook adds latency to tool calls. The context hooks therefore inject
  each rule or contract at most once per session.

## Further reading

The design notes are in Danish.

- [`docs/standing_instructions.md`](../standing_instructions.md): the deploy and subagent rules in full
- [`.claude/settings.json`](../../.claude/settings.json): the hook configuration
