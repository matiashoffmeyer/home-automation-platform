#!/usr/bin/env bash
# Development tools: the pinned versions in requirements-dev.txt plus gitleaks,
# installed into .cache/dev-venv, and the git hooks into .git/hooks.
#
#   bash scripts/dev_setup.sh              tools + git hooks
#   bash scripts/dev_setup.sh --no-hooks   tools only (what `make setup` and CI run)
#
# Home Assistant OS has no make, so on the production host this script is the
# entry point. The venv lives under .cache/ because git ignores that directory
# and Home Assistant backups leave it out (the Supervisor excludes .cache/*):
# about 200 MB of tooling costs no backup space. It is rebuilt when
# requirements-dev.txt changes or its interpreter is gone, for example after an
# add-on update replaced the Python it was built with.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

VENV=.cache/dev-venv
GITLEAKS_VERSION=8.30.1
# From gitleaks_${GITLEAKS_VERSION}_checksums.txt on the GitHub release.
GITLEAKS_SHA256_linux_x64=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
GITLEAKS_SHA256_linux_arm64=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080

want="$(sha256sum requirements-dev.txt | cut -d' ' -f1)"
stamp="$VENV/.requirements-dev.sha256"
if "$VENV/bin/python" -c '' 2>/dev/null && [ "$(cat "$stamp" 2>/dev/null)" = "$want" ]; then
    echo "dev tools up to date in $VENV"
else
    rm -rf "$VENV"
    if command -v uv >/dev/null 2>&1; then
        uv venv -q --python python3 "$VENV"
        uv pip install -q --python "$VENV/bin/python" -r requirements-dev.txt
    else
        python3 -m venv "$VENV"
        "$VENV/bin/python" -m pip install -q --disable-pip-version-check -r requirements-dev.txt
    fi
    echo "$want" >"$stamp"
    echo "dev tools installed in $VENV"
fi

# gitleaks is a Go binary, not a Python package: download the release and check
# it against the pinned checksum before it lands in the venv.
if [ "$("$VENV/bin/gitleaks" version 2>/dev/null)" != "$GITLEAKS_VERSION" ]; then
    case "$(uname -s)-$(uname -m)" in
        Linux-x86_64) arch=x64 sha=$GITLEAKS_SHA256_linux_x64 ;;
        Linux-aarch64 | Linux-arm64) arch=arm64 sha=$GITLEAKS_SHA256_linux_arm64 ;;
        *) arch="" sha="" ;;
    esac
    if [ -z "$arch" ]; then
        echo "gitleaks: no pinned build for $(uname -s)-$(uname -m); install gitleaks $GITLEAKS_VERSION on PATH" >&2
    else
        tarball="gitleaks_${GITLEAKS_VERSION}_linux_${arch}.tar.gz"
        tmp="$(mktemp -d)"
        trap 'rm -rf "$tmp"' EXIT
        curl -fsSL -o "$tmp/$tarball" \
            "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${tarball}"
        echo "$sha  $tmp/$tarball" | sha256sum -c - >/dev/null
        tar -xzf "$tmp/$tarball" -C "$tmp" gitleaks
        install -m 755 "$tmp/gitleaks" "$VENV/bin/gitleaks"
        echo "gitleaks $GITLEAKS_VERSION installed in $VENV/bin (checksum verified)"
    fi
fi

if [ "${1:-}" != "--no-hooks" ]; then
    hooks="$(git rev-parse --git-path hooks)"
    install -m 755 scripts/pre-commit-hook.sh "$hooks/pre-commit"
    install -m 755 scripts/pre-push-hook.sh "$hooks/pre-push"
    echo "git hooks installed: pre-commit, pre-push"
fi
