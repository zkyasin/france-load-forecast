#!/usr/bin/env bash
# Commit a bundle to the data branch: latest/ holds the last one, archive/<date>/ each published
# one. Creates the branch on the first run. Usage: scripts/archive.sh <bundle directory>
set -euo pipefail

bundle=$1
day=$(jq -r .published "$bundle/meta.json")
worktree=$(mktemp -d)

if git fetch --quiet --depth 1 origin data 2>/dev/null; then
  git worktree add --quiet "$worktree" FETCH_HEAD
  git -C "$worktree" switch --quiet --force-create data
else
  git worktree add --quiet --detach "$worktree"
  git -C "$worktree" switch --quiet --orphan data
fi

rm -rf "$worktree/latest"
mkdir -p "$worktree/latest" "$worktree/archive/$day"
cp "$bundle"/*.json "$worktree/latest/"
cp "$bundle"/* "$worktree/archive/$day/"

git -C "$worktree" add --all
if git -C "$worktree" diff --cached --quiet; then
  echo "nothing new to publish for $day"
else
  git -C "$worktree" -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit --quiet --message "chore(data): publish $day"
  git -C "$worktree" push --quiet origin data
  echo "published $day"
fi
git worktree remove --force "$worktree"
