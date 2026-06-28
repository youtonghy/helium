#!/bin/bash
# quilt-fix: Push to target patch in a disposable quilt worktree, refresh it,
# and normalize quilt's source-tree-prefixed paths back to a/b style.
# Usage: bash quilt-fix.sh <patch-name>
#   patch-name = relative path in patches/ (e.g. inox-patchset/modify-default-prefs.patch)
# Environment:
#   HELIUM_QUILT_SRC = source tree to operate on (default: codex_tmp/patchwork_src)

set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$SCRIPT_DIR/.." && pwd)
SRC="${HELIUM_QUILT_SRC:-$REPO/codex_tmp/patchwork_src}"
TARGET_PATCH="${1:-}"

if [ -z "$TARGET_PATCH" ]; then
    echo "Usage: $0 <patch-name>"
    exit 1
fi

if [ ! -d "$SRC" ]; then
    echo "Source tree not found: $SRC" >&2
    echo "Set HELIUM_QUILT_SRC or create codex_tmp/patchwork_src first." >&2
    exit 1
fi

cd "$SRC"
source "$REPO/devutils/set_quilt_vars.sh"

echo "→ Pushing to $TARGET_PATCH ..."
quilt push "$TARGET_PATCH" 2>&1 | tail -5

echo "→ Refreshing ..."
quilt refresh

PATCH_FILE="$REPO/patches/$TARGET_PATCH"
SRC_BASENAME=$(basename "$SRC")

# Fix path prefixes and remove quilt artifacts
python3 -c "
import re

with open('$PATCH_FILE', 'r') as f:
    content = f.read()

# Normalize quilt paths from the active source tree back to a/b prefixes.
source_root = re.escape('$SRC_BASENAME')
content = re.sub(rf'^--- {source_root}\.orig/', '--- a/', content, flags=re.MULTILINE)
content = re.sub(rf'^--- {source_root}/', '--- a/', content, flags=re.MULTILINE)
content = re.sub(rf'^\+\+\+ {source_root}/', '+++ b/', content, flags=re.MULTILINE)

# Remove Index: lines and following === separator lines
lines = content.split('\n')
out = []
skip_eq = False
for line in lines:
    if line.startswith('Index: '):
        skip_eq = True
        continue
    if skip_eq and line.startswith('==='):
        skip_eq = False
        continue
    skip_eq = False
    out.append(line)

with open('$PATCH_FILE', 'w') as f:
    f.write('\n'.join(out))
"

echo "→ Cleaning up ..."
find "$SRC" -name '*.orig' -delete 2>/dev/null || true

echo "✓ Fixed: $TARGET_PATCH"
