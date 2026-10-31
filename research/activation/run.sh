#!/usr/bin/env bash
# Ovrin Lab — install dependencies and run the full pipeline. Safe to re-run:
# it resumes from where a previous run stopped (nothing is re-done).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "need python3 (set PYTHON=...)"; exit 1; }

# 1. isolated environment + dependencies
if [ ! -d .venv ]; then
  echo "[setup] creating .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -q --upgrade pip >/dev/null 2>&1 || true
python -m pip install -q -r requirements.txt

# 2. auth status. Drop an optional keys.env next to this script (it is only
# sourced, never committed — see .gitignore) to set env vars automatically.
if [ -f keys.env ]; then
  echo "[keys] sourcing keys.env"
  set -a; . ./keys.env; set +a
fi
echo "[auth]"
# Claude Code / Codex authenticate via your SUBSCRIPTION LOGIN, not a key:
#   claude  -> run 'claude' then /login once (Claude Max)
#   codex   -> run 'codex login' once (ChatGPT plan)
# so an (unset) env key for these is normal. Gemini uses GEMINI_API_KEY.
for c in claude codex gemini ollama; do
  if command -v "$c" >/dev/null 2>&1; then echo "       $c = on PATH"; else echo "       $c = (not installed)"; fi
done
for k in ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY; do
  if [ -n "${!k:-}" ]; then echo "       $k = set"; fi
done
[ -n "${GEMINI_API_KEY:-}" ] || echo "       note: GEMINI_API_KEY unset — the gemini agent will fail auth if enabled"

# 3. run (auto-resumes). Pass extra flags through, e.g.:  ./run.sh --only activation
echo "[run]"
exec python -m lab.cli --config config.yaml "$@"
