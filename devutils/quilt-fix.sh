#!/bin/bash
# quilt-fix: Push to target patch in a disposable quilt worktree, refresh it,
# and normalize quilt's source-tree-prefixed paths back to a/b style.
# Usage: bash quilt-fix.sh <patch-name>
#   patch-name = relative path in patches/ (e.g. inox-patchset/modify-default-prefs.patch)
# Environment:
#   NITROUS_QUILT_SRC (fallback HELIUM_QUILT_SRC) = source tree
#   (default: codex_tmp/patchwork_src)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$SCRIPT_DIR/.." && pwd)
SRC="${NITROUS_QUILT_SRC:-${HELIUM_QUILT_SRC:-$REPO/codex_tmp/patchwork_src}}"
TARGET_PATCH="${1:-}"

if [ -z "$TARGET_PATCH" ]; then
    echo "Usage: $0 <patch-name>"
    exit 1
fi

if [ ! -d "$SRC" ]; then
    echo "Source tree not found: $SRC" >&2
    echo "Set NITROUS_QUILT_SRC (or HELIUM_QUILT_SRC) or create codex_tmp/patchwork_src first." >&2
    exit 1
fi

cd "$SRC"
source "$REPO/devutils/set_quilt_vars.sh"

CURRENT_TOP=$(command quilt --quiltrc - top 2>/dev/null || true)
if [ "$CURRENT_TOP" != "$TARGET_PATCH" ]; then
    echo "→ Pushing to $TARGET_PATCH ..."
    set +e
    PUSH_OUTPUT=$(command quilt --quiltrc - push "$TARGET_PATCH" 2>&1)
    PUSH_STATUS=$?
    set -e
    printf '%s\n' "$PUSH_OUTPUT" | tail -5
    if [ "$PUSH_STATUS" -ne 0 ]; then
        exit "$PUSH_STATUS"
    fi
else
    echo "→ Target patch is already on top."
fi

TOP_PATCH=$(command quilt --quiltrc - top)
if [ "$TOP_PATCH" != "$TARGET_PATCH" ]; then
    echo "error: quilt top is $TOP_PATCH; expected $TARGET_PATCH" >&2
    exit 1
fi

echo "→ Refreshing ..."
command quilt --quiltrc - refresh "$TARGET_PATCH"

PATCH_FILE="$REPO/patches/$TARGET_PATCH"
SRC_BASENAME=$(basename "$SRC")

# Fix path prefixes and remove quilt artifacts
python3 - "$PATCH_FILE" "$SRC_BASENAME" <<'PY'
import re
import sys

patch_file, source_basename = sys.argv[1:]
with open(patch_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Normalize quilt paths from the active source tree back to a/b prefixes.
source_root = re.escape(source_basename)
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

with open(patch_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
PY

echo "→ Cleaning up ..."
find "$SRC" -name '*.orig' -delete 2>/dev/null || true

echo "✓ Fixed: $TARGET_PATCH"
