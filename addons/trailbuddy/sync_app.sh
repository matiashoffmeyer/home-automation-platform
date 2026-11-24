#!/usr/bin/env bash
# Copy the Trail Buddy app + server from golden-repo into this add-on folder,
# ready for an add-on rebuild. Run from anywhere:
#   addons/trailbuddy/sync_app.sh [golden-repo checkout or git URL]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-https://github.com/parent_a/golden-repo.git}"
TMP=""
if [ -d "$SRC/.git" ] || [ -f "$SRC/index.html" ]; then
  REPO="$SRC"
else
  TMP="$(mktemp -d)"; REPO="$TMP/golden-repo"
  git clone --depth 1 --branch main "$SRC" "$REPO"
fi
# Phones run the app shell from the service worker's cache and only fetch it again when
# sw.js changes: a changed shell under the same VERSION never reaches them (0.6.122-124,
# 2026-11-23: three releases stayed on the server only). Refuse that.
ver() { grep -o "const VERSION = '[^']*'" "$1/sw.js" 2>/dev/null || true; }
if [ -f "$HERE/app/sw.js" ] && [ "$(ver "$HERE/app")" = "$(ver "$REPO")" ]; then
  for f in index.html css js vendor manifest.webmanifest icons; do
    if ! diff -rq "$HERE/app/$f" "$REPO/$f" >/dev/null 2>&1; then
      echo "ERROR: $f changed but sw.js VERSION is still $(ver "$REPO") — bump it (and APP_VERSION in js/app.js) in golden-repo" >&2
      exit 1
    fi
  done
fi
rm -rf "$HERE/app"; mkdir -p "$HERE/app"
for f in index.html reset.html reset.js move sw.js manifest.webmanifest css js vendor data icons tiles watch; do
  cp -R "$REPO/$f" "$HERE/app/"
done
cp "$REPO/server/trailbuddy_server.py" "$REPO/server/trees.py" "$HERE/"
echo "Synced app $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?') into $HERE/app ($(du -sh "$HERE/app" | cut -f1))"
if [ -n "$TMP" ]; then rm -rf "$TMP"; fi
