#!/usr/bin/env bash
# Resume a paused run (after a token expiry, Ctrl-C, or crash). The orchestrator
# always skips completed trials, so resuming is just running again — this script
# exists so the intent is obvious. Set your API keys first, then:  ./resume.sh
set -euo pipefail
cd "$(dirname "$0")"
exec ./run.sh "$@"
