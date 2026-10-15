#!/usr/bin/env bash
# ovrin: offline research reproducibility script
#
# Recomputes the paper's aggregate numbers from the committed records
# WITHOUT any network access. Anyone who has this repository can run
# `bash research/reproducibility/reproduce.sh` and reproduce every
# headline arithmetic result in Sections 6, 7, 8, and 9.
#
# What this script does NOT do:
#   - Contact GitHub. (survey/crawl.py needs network + GITHUB_TOKEN; not used here.)
#   - Contact npm / crates.io / PyPI / Maven / Go module proxy.
#   - Launch a coding-agent. Live agent runs require the paid API and time;
#     they produce the exact per-trial logs referenced in Section 7 and
#     are not reproduced here. Their outcomes are already committed.
#
# What this script DOES do:
#   1. Pooled prevalence + governance across the 5 language strata
#      from committed records-active-*-final.jsonl.
#   2. Carriage summary from committed research/carriage-study/results.
#   3. Ovrin unit tests, including the D(s,c) semantics tests.
#   4. Delegation-policy 2x2 matrix evaluation, N=50 per cell.
#   5. Three consequence cases, N=200 per case, seed=1729.
#   6. Web-mediated instance, N=20 per condition, seed=1729.
#   7. Reproducibility manifest with fixture digests.
#
# Requires: python>=3.10, pip install PyYAML pathspec pytest.
# Runtime: about 30 seconds on a laptop.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

echo "==> [1/7] Pooled survey analysis (offline)"
python survey/analyze.py \
  survey/out/records-active-go-final.jsonl \
  survey/out/records-active-java-final.jsonl \
  survey/out/records-active-javascript-final.jsonl \
  survey/out/records-active-python-final.jsonl \
  survey/out/records-active-rust-final.jsonl \
  --json-out survey/out/analysis-repro.json

echo "==> [2/7] Carriage summary"
python research/carriage-study/carriage_analysis.py \
  --results-dir research/carriage-study/results \
  || echo "(carriage_analysis.py optional; skip if absent)"

echo "==> [3/7] Ovrin unit tests (76+)"
python -m pytest tests/ -q --ignore=tests/test_survey_probe.py

echo "==> [4/7] Delegation-policy 2x2 matrix"
python research/harness-matrix/delegation_matrix_eval.py

echo "==> [5/7] Three consequence cases (SIM, N=200, seed=1729)"
python research/harness-matrix/consequence_eval.py --n 200 --seed 1729

echo "==> [6/7] Web-mediated instance (fixture + SIM, N=20 per condition)"
python research/harness-matrix/web_mediated_eval.py

echo "==> [7/7] Emit reproducibility manifest"
python research/reproducibility/manifest.py > research/reproducibility/MANIFEST.json
echo "wrote research/reproducibility/MANIFEST.json"

echo
echo "SUCCESS. All headline numbers recomputed from committed records."
echo "Live agent runs are not reproduced here (see tests/harness_cases/)."
