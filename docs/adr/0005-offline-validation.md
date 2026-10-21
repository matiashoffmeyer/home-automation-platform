# 5. Configuration is validated offline by Home Assistant's own code

- **Status:** accepted
- **Date:** 2026-10-04

## Context

Home Assistant disables an automation that fails validation. A single invalid
template in its actions is enough, and nothing warns at commit, deploy or
reload: the automation shows as `unavailable` and never runs. One invalid
template sensor can likewise take down the whole `template:` block of its
file. These defects were found after deploy, if at all.

The built-in `ha core check` had been dropped earlier because of an upstream
bug in 2026.4 (`check_config` did not set up the trigger helper). Custom
linters checked syntax and conventions but not what Home Assistant itself
accepts.

Refactoring raised a second question. The repository held the same entity
lists in many files (25 lists, 152 copies). Consolidating them was the
obvious fix, but each edit risked changing behaviour, and there was no proof
that it had not.

## Decision

`scripts/ha_offline.py` installs the production version of Home Assistant
(pinned in `scripts/ha_offline_version.txt`) in a local virtual environment
and runs its own code against the repository. Secrets come from the
placeholders in `secrets.example.yaml`; `.storage` and devices are never
used.

| Command | Purpose |
|---|---|
| `check` | Home Assistant's own configuration check, with the log classified into errors and known noise |
| `equiv REV_A [REV_B]` | diff of the *resolved* configuration, after `!include` and package merging |
| `staging` | boot the house headless as a fresh install |
| `refs` | entity references that do not exist |

`check` runs in the pre-push hook and in CI. A refactor is declared either
structural, in which case `equiv` must be empty, or a behaviour change, in
which case the `equiv` diff is reviewed as the change.

## Consequences

- Replayed against seven earlier incidents, `check` would have caught five
  before commit. The two misses were semantic: a folded Jinja `if` that
  rendered the string `"false"`, and a service that exists only on the
  production host.
- The roster consolidation could be done in batches with an empty `equiv` as
  proof. The lists now live in `rosters/` and are included where they are
  used.
- A Home Assistant upgrade can be tested before it is installed
  (`--version <new>`).
- The first run builds a virtual environment of about 1 GB, and the pinned
  version must be kept equal to production by hand.
- After deploy, `./scripts/ha_health.sh deploy` remains necessary. Offline
  validation cannot see integrations or services that exist only on the host.

## Further reading

The design notes are in Danish.

- [`docs/konsolidering.md`](../konsolidering.md): the evidence from the commit history, the incident replay and the staging review
