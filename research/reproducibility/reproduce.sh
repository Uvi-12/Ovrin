#!/usr/bin/env bash
# Reproduce the survey numbers from the committed seed.
# Requires GITHUB_TOKEN in the environment.
set -euo pipefail
python survey/crawl.py --seed survey/out/seed-active.jsonl \
    --out survey/out/records-active.jsonl --history
python survey/analyze.py survey/out/records-active.jsonl
