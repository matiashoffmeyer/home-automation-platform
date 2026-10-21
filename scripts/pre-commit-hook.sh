#!/usr/bin/env bash
# =============================================================================
# Pre-commit hook — Phase 0+4 fra refactor-plan
# =============================================================================
# Catcher de pitfalls vi har ramt over de sidste 6 audit-runder FØR de
# lander i prod. Kører automatisk ved hver `git commit`.
#
# Checks (i prioriteret rækkefølge):
#   1. PLACEHOLDER device_ieee (G3 — fra audit-runde 9)
#   2. Broken entity references (validator)
#   3. Duplicate automation IDs (validator)
#   4. Replace_all hazards (transition: 60 vs 600 — vi brød HA boot 2026-04-29)
#   5. Jinja syntax errors (validator)
#   0c. Roster-drift (advarsel): rettet liste med tvillinger (roster_drift.py)
#   0d. custom_templates/rosters.jinja passer til rosters/ (rosters.py jinja --check)
#   0h. secrets-kontrakten: nøgler ↔ secrets.example.yaml, ingen live credential i git
#   0i. ruff + yamllint på stagede filer; hooks/Makefile/CI i trit (test_tooling_parity)
#   (HA's egen validator kører i pre-PUSH: scripts/ha_offline.py check)
#
# Bruger ./scripts/ha_validate.py som engine. Kun staged YAML-filer scannes.
#
# Installation (engangs, også ruff/yamllint i .cache/dev-venv):
#   bash scripts/dev_setup.sh
#
# Override hvis nødvendigt: `git commit --no-verify` (IKKE anbefalet).
# =============================================================================

set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Python fra dev-venv'et (pinnet PyYAML) når det virker, ellers systemets: en
# clone uden globalt PyYAML kan så også køre tjekkene (scripts/dev_setup.sh).
if "$REPO_ROOT/.cache/dev-venv/bin/python" -c 'import yaml' 2>/dev/null; then
    PATH="$REPO_ROOT/.cache/dev-venv/bin:$PATH"
fi

# === Check 0: unikke backlog-ID'er (user-spec 2026-10-04) ===
# Kører kun når BACKLOG.md eller arkivet er staged — derfor FØR yaml-exit'en.
if git diff --cached --name-only | grep -qE '^(BACKLOG\.md|docs/backlog_archive\.md)$'; then
    if [ -f "$REPO_ROOT/scripts/backlog_ids.py" ]; then
        (cd "$REPO_ROOT" && python3 scripts/backlog_ids.py --staged) || {
            echo "❌ COMMIT BLOKERET: se backlog-ID-fejlene ovenfor." >&2
            exit 1
        }
    fi
fi

# === Check 0b: lys-ejerskab (2026-10-04, user-spec "lint blokerer") ===
# En skriver til en lampe med register i ejerskab/ skal stå i registret, og de
# genererede filer skal passe til det. Kører kun når noget relevant er staged.
if git diff --cached --name-only | grep -qE '^(automations|packages|script_pkg|ejerskab)/.*\.yaml$|^scripts/ejerskab\.py$'; then
    if [ -f "$REPO_ROOT/scripts/ejerskab.py" ]; then
        (cd "$REPO_ROOT" && python3 scripts/ejerskab.py check && python3 scripts/ejerskab.py lint) || {
            echo "❌ COMMIT BLOKERET: lys-ejerskab (se ovenfor). Registret: ejerskab/<lampe>.yaml," >&2
            echo "   kontrakten: docs/auto/ejerskab/<lampe>.md." >&2
            exit 1
        }
    fi
fi

# === Check 0d: fresh-install-filen passer til snapshottet (P1-hærdning) ===
# HA læser config_snapshots/fresh_install/input_number.yaml ved HVER start. Den
# skal være præcis det helpers_export.py afleder af helper_values.yaml — en
# håndrettet eller halvt-merget fil blokeres her (gen-afled med --derive).
# --staged: det er det STAGEDE par der committes; arbejdstræet kan være
# konsistent mens kun helper_values.yaml er staged (review 10-04).
if git diff --cached --name-only | grep -qE '^config_snapshots/|^scripts/helpers_export\.py$'; then
    if [ -f "$REPO_ROOT/scripts/helpers_export.py" ]; then
        (cd "$REPO_ROOT" && python3 scripts/helpers_export.py --check-derived --staged) || {
            echo "❌ COMMIT BLOKERET: fresh-install-filen passer ikke til snapshottet (se ovenfor)." >&2
            exit 1
        }
    fi
fi

# === Check 0e: hq.py-tests (2026-10-05) ===
# Live-data-CLI'et lukker UTC/DST-, end_time- og context-fælderne; testene
# (offline, < 1 s) beviser det ved hver ændring af scriptet eller fixturen.
if git diff --cached --name-only | grep -qE '^scripts/(hq\.py|tests/)'; then
    (cd "$REPO_ROOT" && python3 -m unittest discover -q -s scripts/tests -p 'test_hq*.py') || {
        echo "❌ COMMIT BLOKERET: hq.py-tests fejler (se ovenfor)." >&2
        exit 1
    }
fi

# === Check 0f: path-scopede Claude-regler (2026-10-05) ===
# En regel uden paths loades i HVER session; en glob der ikke rammer noget
# (omdøbt fil) gør reglen tavst død; en regel uden index-linje i CLAUDE.md
# findes ikke for en session der kun bruger hq.py.
if git diff --cached --name-only | grep -qE '^(\.claude/rules/|CLAUDE\.md$|scripts/claude_rules\.py$)'; then
    (cd "$REPO_ROOT" && python3 scripts/claude_rules.py check) || {
        echo "❌ COMMIT BLOKERET: .claude/rules/ (se ovenfor)." >&2
        exit 1
    }
fi

# === Check 0d: rosters.jinja afledt af rosters/ (konsolidering 2026-10-10) ===
# Jinja-kopierne importerer listerne fra custom_templates/rosters.jinja. Står
# den ikke ens med rosters/*.yaml, ser templates og YAML to forskellige huse.
if git diff --cached --name-only | grep -qE '^(rosters/|custom_templates/rosters\.jinja$|scripts/rosters\.py$)'; then
    (cd "$REPO_ROOT" && python3 scripts/rosters.py jinja --check) || {
        echo "❌ COMMIT BLOKERET: kør python3 scripts/rosters.py jinja og stage custom_templates/rosters.jinja." >&2
        exit 1
    }
fi

# === Check 0g: dashboards parser som YAML (2026-10-11) ===
# Et ucitert `name: Weekend: godnat …` er ugyldig YAML: HA viser så kun
# "mapping values are not allowed here", og HELE Indstillinger-siden kan ikke
# åbnes. ha_offline check læser ikke dashboards — derfor dette tjek.
DASH=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '^dashboards/.*\.ya?ml$' || true)
if [ -n "$DASH" ]; then
    (cd "$REPO_ROOT" && python3 - $DASH <<'PYEOF'
import sys, subprocess, yaml
class L(yaml.SafeLoader): pass
L.add_multi_constructor('!', lambda l, s, n: None)
bad = 0
for f in sys.argv[1:]:
    txt = subprocess.run(["git", "show", f":{f}"], capture_output=True, text=True).stdout
    try:
        yaml.load(txt, Loader=L)
    except yaml.YAMLError as e:
        bad += 1
        print(f"❌ {f}: {e}".replace("\n", " "), file=sys.stderr)
sys.exit(1 if bad else 0)
PYEOF
    ) || {
        echo "❌ COMMIT BLOKERET: dashboard er ugyldig YAML (citér værdier med ': ' i — fx name: 'A: b')." >&2
        exit 1
    }
fi

# === Check 0c: roster-drift (konsolidering 2026-10-04, fejlklasse #16) ===
# Rettede du en entity-liste der står ordret andre steder, nævnes tvillingerne
# — med den GAMLE version. Kun advarsel: et bevidst forskelligt par er lovligt.
if git diff --cached --name-only | grep -qE '^(automations|packages|script_pkg)/.*\.yaml$'; then
    if [ -f "$REPO_ROOT/scripts/roster_drift.py" ]; then
        (cd "$REPO_ROOT" && python3 scripts/roster_drift.py --staged) || true
    fi
fi

# === Check 0h: secrets-kontrakten (2026-10-20) ===
# Hver nøgle koden læser (!secret i YAML, ha_secrets.get() i Python) skal stå i
# secrets.example.yaml, kun scripts/ha_secrets.py må læse secrets.yaml, og ingen
# live credential må stå i en fil git kan se. Printer kun nøgle-navne (~1,5 s).
if git diff --cached --name-only | grep -qE '\.(py|ya?ml|sh)$'; then
    (cd "$REPO_ROOT" && python3 scripts/secrets_contract.py) || {
        echo "❌ COMMIT BLOKERET: secrets-kontrakten (se ovenfor). Ny nøgle → secrets.example.yaml" >&2
        echo "   med en pladsholder; læs den via scripts/ha_secrets.py." >&2
        exit 1
    }
    if git diff --cached --name-only | grep -qE '^scripts/(ha_secrets|secrets_contract)\.py$|^scripts/tests/test_ha_secrets'; then
        (cd "$REPO_ROOT" && python3 -m unittest discover -q -s scripts/tests -p 'test_ha_secrets*.py') || {
            echo "❌ COMMIT BLOKERET: ha_secrets-tests fejler (se ovenfor)." >&2
            exit 1
        }
    fi
fi

# === Check 0i: ruff + yamllint (2026-10-21) ===
# Samme værktøjer og versioner som `make lint`/CI, fra dev-venv'et som
# scripts/dev_setup.sh bygger i .cache/ (HA's backup springer .cache/ over).
# Mangler det, ADVARES der højt men blokeres ikke: en add-on-opdatering kan
# tage venv'ets python med sig, og huset skal stadig kunne committe.
# NB lint ser arbejdstræets fil, ikke den stagede blob. Under pre-commit-
# frameworket (PRE_COMMIT=1) kører dets egne ruff/yamllint-hooks i stedet.
DEV_BIN="$REPO_ROOT/.cache/dev-venv/bin"
dev_tool() {
    [ -x "$DEV_BIN/$1" ] && "$DEV_BIN/$1" --version >/dev/null 2>&1 && echo "$DEV_BIN/$1"
}
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '\.py$' || true)
STAGED_YML=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '\.ya?ml$' || true)
if [ -n "${PRE_COMMIT:-}" ]; then
    STAGED_PY="" STAGED_YML=""
fi
if [ -n "$STAGED_PY" ]; then
    if RUFF=$(dev_tool ruff); then
        (cd "$REPO_ROOT" && "$RUFF" check --force-exclude $STAGED_PY \
            && "$RUFF" format --check --force-exclude $STAGED_PY) || {
            echo "❌ COMMIT BLOKERET: ruff (se ovenfor). Ret: $RUFF check --fix <fil> && $RUFF format <fil>" >&2
            exit 1
        }
    else
        echo "⚠️  ⚠️  ruff mangler — Python-lint SPRUNGET OVER. Byg værktøjerne: bash scripts/dev_setup.sh" >&2
    fi
fi
if [ -n "$STAGED_YML" ]; then
    if YAMLLINT=$(dev_tool yamllint); then
        (cd "$REPO_ROOT" && "$YAMLLINT" $STAGED_YML) || {
            echo "❌ COMMIT BLOKERET: yamllint (se ovenfor). Booleans er true/false; states citeres (\"on\")." >&2
            exit 1
        }
    else
        echo "⚠️  ⚠️  yamllint mangler — YAML-lint SPRUNGET OVER. Byg værktøjerne: bash scripts/dev_setup.sh" >&2
    fi
fi
# Hooks, Makefile, CI og versions-pins skal følges ad (scripts/tests/test_tooling_parity.py).
if git diff --cached --name-only | grep -qE '^(Makefile|\.pre-commit-config\.yaml|requirements-dev\.txt|pyproject\.toml|\.github/workflows/|scripts/(pre-commit-hook|pre-push-hook|dev_setup)\.sh|scripts/tests/test_tooling_parity)'; then
    (cd "$REPO_ROOT" && python3 -m unittest discover -q -s scripts/tests -p 'test_tooling_parity.py') || {
        echo "❌ COMMIT BLOKERET: hooks, Makefile og CI er ude af trit (se ovenfor)." >&2
        exit 1
    }
fi

# Kun tjek staged YAML-filer
STAGED_YAML=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '\.(yaml|yml)$' || true)

if [ -z "$STAGED_YAML" ]; then
    exit 0
fi

# === Check 1: PLACEHOLDER device_ieee (legacy hard check) ===
PLACEHOLDER_PATTERN='device_ieee:.*PLACEHOLDER'
XXXX_PATTERN='device_ieee:.*"xx:xx'
ZERO_IEEE='device_ieee:.*"00:00:00:00:00:00:00:00"'

PLACEHOLDER_HITS=$(echo "$STAGED_YAML" | xargs grep -l -E "$PLACEHOLDER_PATTERN|$XXXX_PATTERN" 2>/dev/null || true)

if [ -n "$PLACEHOLDER_HITS" ]; then
    echo "" >&2
    echo "❌ COMMIT BLOKERET: device_ieee PLACEHOLDER detekteret" >&2
    for f in $PLACEHOLDER_HITS; do
        echo "  $f:" >&2
        grep -nE "$PLACEHOLDER_PATTERN|$XXXX_PATTERN" "$f" | sed 's/^/    /' >&2
    done
    echo "" >&2
    echo "Erstat PLACEHOLDER med faktisk IEEE eller \"00:00:00:00:00:00:00:00\" (fake)." >&2
    exit 1
fi

# Soft warning for fake-IEEE
ZERO_HITS=$(echo "$STAGED_YAML" | xargs grep -l -E "$ZERO_IEEE" 2>/dev/null || true)
if [ -n "$ZERO_HITS" ]; then
    echo "ℹ️  Note: fake device_ieee (00:00:..) i $(echo "$ZERO_HITS" | wc -l) fil(er). Husk parring." >&2
fi

# === Check 2-5: Comprehensive validator ===
# Kører ha_validate.py for de yaml-filer der staged. Bug der allerede er i
# main koden bliver IKKE blokeret (kun nye bugs i denne commit).
if [ -f "$REPO_ROOT/scripts/ha_validate.py" ]; then
    if command -v python3 >/dev/null 2>&1; then
        cd "$REPO_ROOT"
        # Run validator on staged files only — checks they don't introduce new bugs
        # Skip 'refs' check in pre-commit (requires HA_TOKEN + live HA, slow + flaky)
        # Skip 'unused' check (informational only, would block too many commits)
        VALIDATOR_OUT=$(python3 scripts/ha_validate.py --files $STAGED_YAML --check dups --quiet 2>&1) || {
            echo "" >&2
            echo "❌ COMMIT BLOKERET: validator fandt errors:" >&2
            echo "$VALIDATOR_OUT" >&2
            echo "" >&2
            echo "Run: python3 scripts/ha_validate.py for full report" >&2
            exit 1
        }
        # Matter-lys uden continue_on_error (2026-10-07): CHIP-timeout aborterer
        # ellers hele scriptet. Blokerer — reglen stod før kun i CLAUDE.md, og
        # 11 kald (inkl. røgalarmens fuldt-lys) manglede den.
        MATTER_OUT=$(python3 scripts/ha_validate.py --files $STAGED_YAML --check matter --quiet 2>&1) || {
            echo "" >&2
            echo "❌ COMMIT BLOKERET:" >&2
            echo "$MATTER_OUT" >&2
            echo "Tilføj 'continue_on_error: true' på kaldet (søskende-nøgle til action/service)." >&2
            exit 1
        }
        # B103 (2026-10-07): to: uden from: på en template-entity fyrer falsk ved
        # template.reload. Scanner hele arbejdstræet (~1 s, libyaml); bevidste
        # undtagelser står i ALLOWLIST i scripts/b103_scan.py med begrundelse.
        if echo "$STAGED_YAML" | grep -qE '^(automations|packages)/'; then
            B103_OUT=$(python3 scripts/b103_scan.py 2>&1) || {
                echo "" >&2
                echo "❌ COMMIT BLOKERET: state-trigger med to: uden from: på en template-entity" >&2
                echo "$B103_OUT" | grep -v '^template-entities' >&2
                echo "Tilføj from: (eller not_from: [unknown, unavailable]). Er flanken selve" >&2
                echo "beviset, så allowlist id'et i scripts/b103_scan.py med et HVORFOR." >&2
                exit 1
            }
        fi
        # Hazards as warning only (don't block commit, just inform)
        python3 scripts/ha_validate.py --files $STAGED_YAML --check hazards --quiet 2>&1 || true
        python3 scripts/ha_validate.py --files $STAGED_YAML --check jinja --quiet 2>&1 || {
            echo "" >&2
            echo "⚠  Jinja syntax warnings — fix før deploy hvis kritisk" >&2
        }
    fi
fi

exit 0
