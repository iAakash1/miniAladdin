#!/usr/bin/env bash
#
# Capture the /quant screenshots in docs/screenshots/quant/.
#
# Two things have to be temporarily changed to photograph this page, and both
# are reverted by a trap so the working tree is never left holding them:
#
#   1. `/quant` is auth-gated like the rest of the terminal. Signing in from a
#      script would mean handling credentials, so the route is made public for
#      the duration instead. The page's data comes from the FastAPI backend
#      either way, so the render is identical to the authenticated one.
#   2. Sections are native <details> and default to collapsed. Headless Chrome
#      screenshots before any JS the caller supplies, so they are opened in the
#      source for the capture.
#
# Neither change is ever committed: `git checkout` runs on EXIT, including on
# failure or interrupt. Verify with `git status` afterwards.
#
# Usage:
#   scripts/docs/capture_quant_screenshots.sh            # assumes servers are up
#
# Requires: backend on :8000, `npm run dev` on :3000, Google Chrome.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PROXY="dashboard/src/proxy.ts"
VIEW="dashboard/src/components/terminal/QuantResearchView.tsx"
OUT="docs/screenshots/quant"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Restore from copies taken before the edits, NOT with `git checkout`.
#
# The first version of this script used `git checkout -- "$PROXY" "$VIEW"`. The
# view is a new, untracked file, so git failed on the whole pathspec and
# restored NEITHER — and the `|| true` swallowed it. The working tree was left
# with `/quant` publicly routable, which is the exact failure this trap exists
# to prevent. Byte-for-byte copies do not care whether a file is tracked.
BACKUP="$(mktemp -d)"
cp "$PROXY" "$BACKUP/proxy.ts"
cp "$VIEW" "$BACKUP/view.tsx"

restore() {
  local failed=0
  cp "$BACKUP/proxy.ts" "$PROXY" || failed=1
  cp "$BACKUP/view.tsx" "$VIEW" || failed=1
  rm -rf "$BACKUP"
  if [ "$failed" -ne 0 ]; then
    echo "!! RESTORE FAILED — check $PROXY for a public /quant route before committing" >&2
    return 1
  fi
  # Prove it, rather than announcing it.
  if grep -q "'/quant" "$PROXY"; then
    echo "!! $PROXY still routes /quant publicly — restore did not take" >&2
    return 1
  fi
  echo "restored $PROXY and $VIEW (verified: /quant is auth-gated again)"
}
trap restore EXIT INT TERM

[ -x "$CHROME" ] || { echo "Google Chrome not found at $CHROME"; exit 1; }
curl -sf -o /dev/null "http://127.0.0.1:8000/api/quant/status" \
  || { echo "backend not up on :8000"; exit 1; }

mkdir -p "$OUT"

python3 - "$PROXY" "$VIEW" <<'PY'
import sys
from pathlib import Path

proxy, view = Path(sys.argv[1]), Path(sys.argv[2])

s = proxy.read_text()
s = s.replace("  '/sitemap.xml',", "  '/quant(.*)',\n  '/sitemap.xml',")
proxy.write_text(s)

v = view.read_text()
for section in ("ablation", "integrity", "regimes", "costs", "overfit", "provenance"):
    idx = v.index(f'id="{section}"')
    close = v.index(">", v.index("summary=", idx))
    v = v[:close] + "\n              defaultOpen\n            " + v[close:]
view.write_text(v)
print("capture mode applied")
PY

echo "waiting for the dev server to recompile…"
sleep 10
curl -sf -o /dev/null "http://localhost:3000/quant" || { echo "/quant not reachable"; exit 1; }

# Headless Chrome occasionally hangs when invoked repeatedly against the same
# profile, so each shot gets a throwaway user-data-dir and a hard time limit.
# A hung capture must not take the whole script — and the restore trap — with it.
shot() {  # name, width, height
  local profile; profile="$(mktemp -d)"
  local ok=0
  ( "$CHROME" --headless --disable-gpu --hide-scrollbars \
      --user-data-dir="$profile" --no-first-run --no-default-browser-check \
      --window-size="$2,$3" --screenshot="$OUT/$1" \
      --virtual-time-budget=11000 "http://localhost:3000/quant" 2>/dev/null ) &
  local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge 90 ]; then
      kill -9 "$pid" 2>/dev/null || true
      echo "  $1  TIMED OUT after ${waited}s — previous capture left in place" >&2
      break
    fi
    sleep 2; waited=$((waited + 2))
  done
  wait "$pid" 2>/dev/null && ok=1 || true
  rm -rf "$profile"
  [ "$ok" -eq 1 ] && echo "  $1  (${2}x${3})"
  return 0
}

shot "01-quant-research-full-LOCAL.png"        1440 3900
shot "02-deployment-status-holdout-LOCAL.png"  1440 900
shot "03-quant-mobile-LOCAL.png"                430 1400

echo "captured into $OUT"
