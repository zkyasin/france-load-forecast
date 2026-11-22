#!/usr/bin/env bash
# Copy the bundles published on the data branch into public/data, without the real-time
# snapshots, and list the publication dates, oldest first, in public/data/archive.json.
set -euo pipefail
cd "$(dirname "$0")/.."

# A shallow clone, as in CI, fetches the last commit only. A full clone keeps its full history.
if [[ $(git rev-parse --is-shallow-repository) == true ]]; then
  git fetch --quiet --depth 1 origin data
else
  git fetch --quiet origin data
fi
rm -rf public/data
mkdir -p public/data
git -C .. archive FETCH_HEAD latest archive ':(exclude)*.parquet' | tar -x -f - -C public/data
ls public/data/archive | jq --raw-input --null-input --compact-output '[inputs]' \
  >public/data/archive.json
