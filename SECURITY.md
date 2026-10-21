# Security

## Reporting a vulnerability

Please report security problems privately through GitHub's
**Report a vulnerability** button on the repository's Security tab, not in a
public issue. Include the file, the commit and what an attacker could do. You
can expect an answer within a week.

Only the latest commit is maintained.

## Scope

This repository is the configuration and tooling of a single home. It runs
inside a local Home Assistant installation and is not a hosted service. The
reports that matter most are:

- a credential, token or personal identifier that reached the published files;
- a script that could leak a secret, for example by printing it or writing it
  to a tracked file;
- an automation that a remote party could trigger to unlock, disarm or
  otherwise act on the home;
- a CI workflow that could be abused, for example through untrusted input.

## How secrets are handled

- Real secrets live only in `secrets.yaml` on the host, which git ignores.
  [`secrets.example.yaml`](secrets.example.yaml) lists every key the code reads,
  with a placeholder value.
- Scripts read secrets through one module, `scripts/ha_secrets.py`.
  `scripts/secrets_contract.py` checks statically that the code and the
  example agree, and, on the host, that no live value appears in a tracked
  file ([ADR 7](docs/adr/0007-secrets-contract.md)).
- [gitleaks](https://github.com/gitleaks/gitleaks) scans the full history in
  CI (`make security-check`) and staged changes through
  [pre-commit](.pre-commit-config.yaml), with [custom rules](.gitleaks.toml)
  for the credential shapes this platform uses.
- CI has a read-only token and actions pinned to commit SHAs.
- This repository is a sanitized snapshot of a private working repository.
  Personal names are replaced by roles, device identifiers are pseudonymized,
  and the private history is not published
  ([ADR 8](docs/adr/0008-publication-as-sanitized-snapshot.md)).
