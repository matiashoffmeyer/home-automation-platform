# Architecture decision records

Each record states one decision: the context that forced it, what was
decided, and what it costs. The records are short. Where a longer account
exists, with incidents and measurements, it is in the Danish design notes
listed under *Further reading*.

| # | Decision | Date |
|---|---|---|
| [1](0001-tunable-values-in-git.md) | Tunable values are snapshotted to git and seed a fresh install | 2026-06-17 |
| [2](0002-presence-behind-health-gates.md) | Presence is read through health gates and sustained anchors | 2026-05-01 |
| [3](0003-room-modes-and-manual-override.md) | Each room is Auto, Manual or Off, and a person's action wins | 2026-04-11 |
| [4](0004-lamp-ownership-registry.md) | Contested lamps have an ownership registry and a generated owner sensor | 2026-10-04 |
| [5](0005-offline-validation.md) | Configuration is validated offline by Home Assistant's own code | 2026-10-04 |
| [6](0006-agent-guardrails-as-hooks.md) | Rules that protect the house or the budget run as hooks | 2026-10-04 |
| [7](0007-secrets-contract.md) | Secrets are read through one module, checked by a static contract | 2026-10-20 |
| [8](0008-publication-as-sanitized-snapshot.md) | Publication is a sanitized single-commit snapshot | 2026-10-21 |

Records are numbered in the order they were written down, which is not
always the order in which the decisions were first made. A record is not
edited once a later decision replaces it. The new record says what it
supersedes, and the old one is marked `superseded`.
