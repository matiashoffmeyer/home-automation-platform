# Developer entry points. CI runs these same targets (.github/workflows/ci.yml)
# and the git hooks run their fast subset on every commit;
# scripts/tests/test_tooling_parity.py fails when the three drift apart.
#
# Home Assistant OS has no make. On the production host the git hooks run the
# checks and `bash scripts/dev_setup.sh` installs the tools.

VENV := .cache/dev-venv
# Tools come from the pinned venv. The add-on end-to-end test starts helper
# processes through `python3`, so the venv goes first on PATH for every target.
export PATH := $(CURDIR)/$(VENV)/bin:$(PATH)

.DEFAULT_GOAL := help
.PHONY: help setup hooks lint format test validate security-check ci

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

setup: ## Install the pinned tools into .cache/dev-venv
	@bash scripts/dev_setup.sh --no-hooks

hooks: ## Install the tools and the git hooks
	@bash scripts/dev_setup.sh

lint: setup ## ruff, ruff format, yamllint, mypy
	ruff check .
	ruff format --check .
	yamllint .
	mypy

format: setup ## Apply ruff's fixes and formatting
	ruff check --fix .
	ruff format .

test: setup ## Unit tests and the Spotify add-on's end-to-end test
	pytest -q
	python3 addons/spotify_bro/tests/test_bro.py

validate: setup ## Home Assistant's own config check (offline) and the platform's invariants
	python3 scripts/ha_offline.py check --quiet
	python3 scripts/ha_validate.py --check dups --quiet
	python3 scripts/ha_validate.py --check placeholders --quiet
	python3 scripts/ha_validate.py --check matter --quiet
	python3 scripts/b103_scan.py
	python3 scripts/ejerskab.py check
	python3 scripts/ejerskab.py lint
	python3 scripts/rosters.py jinja --check
	python3 scripts/helpers_export.py --check-derived
	python3 scripts/claude_rules.py check

security-check: setup ## Secrets contract, then gitleaks over the full history
	python3 scripts/secrets_contract.py
	gitleaks git --redact --no-banner .

ci: lint test validate security-check ## Everything CI runs
