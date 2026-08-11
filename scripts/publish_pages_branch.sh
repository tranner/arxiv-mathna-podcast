#!/usr/bin/env bash
# Publishes ./docs/ to a dedicated `pages` branch as a single squashed
# (orphan, parentless) commit, REPLACING the branch's prior history every
# time rather than adding to it. This is what keeps that branch - which
# holds binary mp3s - from growing without bound: git repo size stays
# roughly proportional to the current episode retention window
# (EPISODE_RETENTION_DAYS in config.py), not to how many episodes have
# EVER been published. `main` never touches docs/ at all (see .gitignore).
#
# This only touches the `pages` branch ref and (optionally) origin - it
# does not read or modify the current checkout's working directory, index,
# or whatever branch you have checked out.
#
# Usage:
#   bash scripts/publish_pages_branch.sh          # update local 'pages' branch only
#   bash scripts/publish_pages_branch.sh --push    # also force-push to origin (used by CI)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$REPO_ROOT/docs"
BRANCH="${PAGES_BRANCH:-pages}"
REMOTE="${PAGES_REMOTE:-origin}"
DO_PUSH=0
[ "${1:-}" = "--push" ] && DO_PUSH=1

if [ ! -d "$DOCS_DIR" ] || [ -z "$(ls -A "$DOCS_DIR" 2>/dev/null)" ]; then
  echo "docs/ is empty or missing - nothing to publish. Run the pipeline first (see main.py)." >&2
  exit 1
fi

cd "$REPO_ROOT"

TMP_INDEX="$(mktemp -u)"  # -u: just reserve a name, don't create the file -
                          # git treats a *missing* index file as "start
                          # empty", but a zero-byte existing file as a
                          # corrupt index and refuses to read it.
trap 'rm -f "$TMP_INDEX"' EXIT

# Build the tree/commit against a scratch index + a work tree pointed at
# docs/, so this never touches the real index or working directory of
# whatever branch is currently checked out.
COMMIT=$(
  GIT_INDEX_FILE="$TMP_INDEX" GIT_WORK_TREE="$DOCS_DIR" git add -A -- . >&2
  TREE=$(GIT_INDEX_FILE="$TMP_INDEX" git write-tree)
  git commit-tree "$TREE" -m "Publish episodes ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
)

git branch -f "$BRANCH" "$COMMIT"
echo "Updated local branch '$BRANCH' -> $COMMIT (orphan commit, no parent - old history superseded)"
echo "  $(git show --stat --format='' "$BRANCH" | tail -1)"

if [ "$DO_PUSH" = "1" ]; then
  git push --force "$REMOTE" "$BRANCH:refs/heads/$BRANCH"
  echo "Force-pushed '$BRANCH' to $REMOTE"
else
  echo ""
  echo "Not pushed. Inspect with:   git log $BRANCH -1 --stat"
  echo "Push it yourself with:      git push --force $REMOTE $BRANCH"
fi
