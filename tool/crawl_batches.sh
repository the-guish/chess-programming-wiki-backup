#!/usr/bin/env bash
# Crawl in batches, committing and pushing content/ after each one so progress
# is never lost. Resumable: just run it again. Extra args go to `crawl`.
#
#   BATCH=500 BRANCH=main tool/crawl_batches.sh [--no-assets ...]
set -euo pipefail
cd "$(dirname "$0")/.."

BATCH=${BATCH:-500}
BRANCH=${BRANCH:-main}
TRAILER=${COMMIT_TRAILER:-}

pending() { python3 tool/cpw_scraper.py status | awk '$1 == "pending:" {print $2}'; }

push() {
    local delay=2
    for _ in 1 2 3 4 5; do
        git push -q origin "HEAD:$BRANCH" && return 0
        echo "push failed, retrying in ${delay}s" >&2
        sleep "$delay"; delay=$((delay * 2))
    done
    return 1
}

commit_batch() {
    git add content
    git diff --cached --quiet && return 0
    local files summary
    files=$(git diff --cached --name-only | wc -l)
    summary=$(python3 tool/cpw_scraper.py status | grep -v '^  failed' | tr -s ' \n' ' ')
    git commit -q -m "Mirror batch: $files files" -m "Crawl status:$summary" ${TRAILER:+-m "$TRAILER"}
    push
}

# Main passes skip earlier failures so the loop always drains; one final pass retries them.
while :; do
    python3 tool/cpw_scraper.py crawl --max-requests "$BATCH" --no-retry-failed "$@"
    commit_batch
    [ "$(pending)" = "" ] && break
done
python3 tool/cpw_scraper.py crawl "$@"
commit_batch
python3 tool/cpw_scraper.py status
