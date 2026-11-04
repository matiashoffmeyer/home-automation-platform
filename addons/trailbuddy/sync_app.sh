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
rm -rf "$HERE/app"; mkdir -p "$HERE/app"
for f in index.html sw.js manifest.webmanifest css js vendor data icons tiles watch; do
  cp -R "$REPO/$f" "$HERE/app/"
done
cp "$REPO/server/trailbuddy_server.py" "$HERE/"
echo "Synced app $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?') into $HERE/app ($(du -sh "$HERE/app" | cut -f1))"
if [ -n "$TMP" ]; then rm -rf "$TMP"; fi
