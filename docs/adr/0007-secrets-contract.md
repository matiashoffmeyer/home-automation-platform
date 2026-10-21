# 7. Secrets are read through one module, checked by a static contract

- **Status:** accepted
- **Date:** 2026-10-20, extended 2026-10-21

## Context

Home Assistant reads secrets from `secrets.yaml` through `!secret <key>`.
Helper scripts need some of the same values: API tokens, the address of the
local instance, integration credentials. Over time ten scripts had their own
copy of a small parser for the file. A renamed key then broke some readers
and not others, and nothing listed which secrets a new installation needs.

Pattern scanners did not cover the gap either. Run over this repository's
history, gitleaks' default rules found none of the three kinds of credential
that had ever been committed: a password inside a camera URL, the id of a
link-shared spreadsheet, and the URL of a deployed web app that acts as its
own credential.

## Decision

1. **One reader.** Scripts read secrets only through `scripts/ha_secrets.py`.
   Only the modules listed as owners may name the secrets file.
2. **A tracked contract.** Every key the repository reads is listed with a
   harmless placeholder in `secrets.example.yaml`. The real values live only
   in the git-ignored `secrets.yaml` on the host.
3. **A static check.** `scripts/secrets_contract.py` collects every
   `!secret <key>` in tracked YAML and every `ha_secrets.get(<key>)` in Python,
   and fails on a key the example lacks or an example key nothing reads. A key
   that cannot be resolved statically is an error, because a reader of the
   code could not see which secret is used either. On the host, it also fails
   when a live secret value appears verbatim in any tracked or untracked file
   that is not ignored. It prints key names and paths, never values.
4. **Custom gitleaks rules.** `.gitleaks.toml` extends the default rules with
   four rules for the credential shapes this platform actually has: URL-embedded
   credentials, spreadsheet ids, web-app URLs and Home Assistant long-lived
   tokens. Each rule exists because it catches one of the historical cases.

## Consequences

- A new installation is set up by copying `secrets.example.yaml` and filling it
  in. CI and the offline validator ([ADR 5](0005-offline-validation.md)) run on
  the placeholders.
- The contract runs in pre-commit and CI without the host or the network.
  The live-value check runs only where the live file exists.
- Cleaning files does not clean history. Values committed before these
  checks existed remain in the private repository's history, which is why
  publication is a separate snapshot
  ([ADR 8](0008-publication-as-sanitized-snapshot.md)).
