#!/usr/bin/env bash
# Populates ./docs/ with the current contents of the `pages` branch (if it
# exists on the remote), so the pipeline can see previously-published
# episodes - needed for feed continuity and for publish.py's retention
# pruning to work correctly. Safe to run even if the branch doesn't exist
# yet (first-ever publish) - docs/ is just left as-is.
#
# This does NOT create a local branch or worktree - it just untars the
# remote branch's tree into docs/, decoupled from git entirely. See
# scripts/publish_pages_branch.sh for how docs/ gets published back.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${PAGES_BRANCH:-pages}"
REMOTE="${PAGES_REMOTE:-origin}"
DOCS_DIR="$REPO_ROOT/docs"

mkdir -p "$DOCS_DIR"
cd "$REPO_ROOT"

if git fetch "$REMOTE" "$BRANCH" 2>/dev/null; then
  git archive FETCH_HEAD | tar -x -C "$DOCS_DIR"
  echo "Fetched existing '$BRANCH' branch content into docs/ ($(find "$DOCS_DIR" -name '*.mp3' | wc -l | tr -d ' ') episode(s))"
else
  echo "No existing '$BRANCH' branch on $REMOTE yet - starting fresh (first publish)."
fi
