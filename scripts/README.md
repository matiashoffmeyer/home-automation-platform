# scripts/ — Helper værktøjer

> *Written in Danish. English overview: [README](../README.md) ·
> [ARCHITECTURE](../ARCHITECTURE.md).*

Hjælperskripter til codebase navigation, validation, og safe refactoring.

## Quick reference

| Script | Formål | Hyppighed |
|---|---|---|
| `pre-commit-hook.sh` | Block bad commits (PLACEHOLDER, dups, jinja errors) | Auto via git hook |
| `ha_validate.py` | Comprehensive validator (refs, dups, hazards, jinja, unused) | Før commit / efter refactor |
| `ha_snapshot.sh` | Dump current HA state for diff sammenligning | Før+efter refactor |
| `ha_smoketest.py` | 9 functional tests af core state machine | Efter restart / deploy |
| `matter_preflight.sh` | Verify Matter stack health | Før commission new device |
| `matter_commission.sh` | Full Matter pairing flow med auto-rename | Per nyt Matter device |
| `matter_clean_srp.sh` | Clear stale SRP cache | Når commission konsekvent fejler |
| `ha.ps1` / `ha.sh` | PowerShell/Bash convenience aliases | Daily use |
| `ha_offline.py check` | HA's EGEN validator offline (fejlklasse #22, template-blok-død) | Pre-push (auto) / før deploy |
| `ha_offline.py equiv A [B]` | Bevis at et refactor ikke ændrer den resolvede config | Hvert konsoliderings-refactor |
| `ha_offline.py staging` | Boot huset headless som FRISK install (saniteret, ingen devices) | Før deploy af større ændringer |
| `ha_offline.py refs` | Entity-refs der ikke findes (unique_id-form, ø→o-slugs) | Før deploy / efter rename |
| `roster_drift.py [--staged]` | Kopierede entity-lister og deres drift (fejlklasse #16) | Pre-commit (auto, advarsel) |
| `ha_slug.py` | ÉN HA-kompatibel slugify for alle scripts | Importeres |
| `session_start.sh` | SessionStart-hook: synk git-hooks, bagud-tjek, cloud-venv | Auto ved session-start |
| `hq.py state\|hist\|flanks\|who\|auto\|find\|where\|tmpl` | Live HA-data som kompakt TSV (lokal tid, end_time-chunking, recorder-attribution) — erstatter ad hoc curl/sqlite | Hver undersøgelse |
| `claude_rules.py check\|hook` | `.claude/rules/`: lint (pre-commit) + Bash/Grep-hook der giver path-scopede regler | Auto (pre-commit + hook) |

Se [docs/konsolidering.md](../docs/konsolidering.md) for hvorfor og hvordan.

## Refactor safety workflow

```bash
# 1. BEFORE refactor: snapshot state + run smoke test (baseline)
./scripts/ha_snapshot.sh > /tmp/before.json
./scripts/ha_smoketest.py

# 2. Make refactor changes
# ... edit YAML ...

# 3. Validate before commit
./scripts/ha_validate.py

# 4. Commit (pre-commit hook validates automatically)
git commit -m "refactor: ..."

# 5. Deploy
git push && ssh ha "cd /config && git pull && zsh -lc 'bash scripts/ha_restart.sh'"

# 6. AFTER refactor: snapshot + diff + smoke test
./scripts/ha_snapshot.sh > /tmp/after.json
./scripts/ha_snapshot.sh diff /tmp/before.json /tmp/after.json
./scripts/ha_smoketest.py
```

Hvis diff viser unexpected entities ændret → rollback eller debug.
Hvis smoke test fejler → fix eller rollback.

## ha_validate.py

```bash
./scripts/ha_validate.py                      # all checks
./scripts/ha_validate.py --check refs         # only entity ref check
./scripts/ha_validate.py --check dups         # only duplicates
./scripts/ha_validate.py --check hazards      # replace_all numeric hazards
./scripts/ha_validate.py --check jinja        # jinja template syntax
./scripts/ha_validate.py --check unused       # unused helpers
./scripts/ha_validate.py --files file1 file2  # only specific files
./scripts/ha_validate.py --quiet              # only errors
./scripts/ha_validate.py --json               # JSON output for scripting
```

**Whitelist**: known-missing entities (pre-flyt hardware) er i
`scripts/ha_validate_whitelist.txt`. Tilføj her når noget er expected-missing,
fjern når devices pares.

**Exit codes**: 0 = clean, 1 = errors, 2 = warnings only.

## ha_snapshot.sh

```bash
./scripts/ha_snapshot.sh > before.json        # dump current state
./scripts/ha_snapshot.sh diff a.json b.json   # compare two snapshots
```

Snapshot inkluderer alle entities + state + attributes. Volatile data
(timestamps, contexts) er filtreret ud så diff er ren.

## ha_smoketest.py

9 functional tests af kritiske state machine components:
- activity_state computes valid value
- open_plan_lux fallback chain (resilient mod stue Apollo defekt)
- presence_sensors_available master gate
- auto_color_temp_evening
- arbejdsdag workday template
- house_state + house_mode valid values
- godnat sub-flags ikke stuck
- OTBR integration present
- lux fallback resilience

```bash
./scripts/ha_smoketest.py            # run all
./scripts/ha_smoketest.py --verbose  # detailed output
```

Exit code 0 = all pass, 1 = ≥1 fail.

## Pre-commit hook

```bash
# Engangs install:
ln -s ../../scripts/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x scripts/pre-commit-hook.sh

# Override hvis nødvendigt:
git commit --no-verify
```

Hook checker staged YAML-filer for:
1. PLACEHOLDER device_ieee
2. Duplicate automation IDs
3. Jinja syntax errors

Refs check og hazards check kører **ikke** i pre-commit (kræver live HA + er
informational). Kør manuelt efter behov.

## Hvornår bruger jeg hvad?

| Situation | Værktøj |
|---|---|
| Lige før jeg laver en refactor | `ha_snapshot.sh > before.json` + `ha_smoketest.py` |
| Mid-refactor, vil checke jeg ikke har brækket noget | `ha_validate.py --check refs` |
| Lige før commit | (auto via pre-commit hook) |
| Efter deploy/restart | `ha_smoketest.py` |
| Hvis smoke test fejler | snapshot diff + git log |
| Når Apollo/sensor pares | Update `ha_validate_whitelist.txt` (fjern entry) |
| Pre-pair Matter device | `matter_preflight.sh` |
| Pair Matter device | `matter_commission.sh "MT:..." "entity_prefix"` |
