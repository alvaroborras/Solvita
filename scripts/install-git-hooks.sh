#!/usr/bin/env bash
# One-shot installer: symlink scripts/git-hooks/* into .git/hooks/.
# Re-run safely; existing symlinks pointing into this repo are replaced.

set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOOKS_SRC="$ROOT/scripts/git-hooks"
HOOKS_DST="$ROOT/.git/hooks"

if [ ! -d "$HOOKS_DST" ]; then
  echo "ERROR: $HOOKS_DST not found. Are you in a git checkout?" >&2
  exit 1
fi

for src in "$HOOKS_SRC"/*; do
  name="$(basename "$src")"
  dst="$HOOKS_DST/$name"
  ln -sfv "../../scripts/git-hooks/$name" "$dst"
done

echo "✓ Installed Solvita git hooks into $HOOKS_DST"
