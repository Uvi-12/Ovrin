#!/bin/bash
# RQ3-A day run: npm, cargo, python, maven — sequential, 180s cap, resumable.
set -u
cd "$(dirname "$0")/../.." || exit 1
echo "=== RQ3-A day run started: $(date) ==="
echo "host disk before: $(df -h / | tail -1 | awk '{print $4}') free"

run_eco () {
  local eco="$1" sample="$2"
  echo ""
  echo "########## $eco : started $(date) ##########"
  python3 research/rq3/drive.py \
    --sample "survey/out/$sample" \
    --ecosystem "$eco" \
    --out "research/rq3/results/rq3-$eco.jsonl" \
    --timeout 180
  echo "########## $eco : finished $(date) ##########"
  echo "host disk now: $(df -h / | tail -1 | awk '{print $4}') free"
  docker volume prune -f >/dev/null 2>&1
}

run_eco npm    sample-active-javascript.json
run_eco cargo  sample-active-rust.json
run_eco python sample-active-python.json
run_eco maven  sample-active-java.json

echo ""
echo "=== ALL DONE: $(date) ==="
for e in npm cargo python maven; do
  n=$(wc -l < "research/rq3/results/rq3-$e.jsonl" 2>/dev/null || echo 0)
  echo "  rq3-$e.jsonl: $n records"
done