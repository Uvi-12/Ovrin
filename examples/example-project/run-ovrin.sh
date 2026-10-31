#!/usr/bin/env bash
# Run Ovrin end to end on an example repository: scan, CI gate, SPDX manifest,
# policy enforcement, and signature verification.
# Requires: ovrin installed (pip install ".[sign]") and git.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-/tmp/ovrin-example}"
banner(){ printf '\n\033[1m== %s ==\033[0m\n\n' "$1"; }

banner "0. Build an example repository with a seeded supply-chain layout"
bash "$HERE/build-example-repo.sh" "$DEST"
cd "$DEST"

banner "1. Inventory what the agent would actually obey"
ovrin scan .

banner "2. CI gate: fail the build on any third-party instruction file"
if ovrin scan . --fail-on-third-party; then echo "exit=0 (clean)"; else echo "exit=$? (gate tripped — as intended)"; fi

banner "3. Emit an SBOM-aligned provenance manifest (SPDX 3.0)"
ovrin scan . -f spdx --no-timestamp -o example.spdx.json
echo "wrote example.spdx.json ($(wc -c < example.spdx.json) bytes)"

banner "4. Enforce a delegation policy — block undelegated third-party authority"
ovrin enforce . --harness claude-code --policy "$HERE/authority-policy.yaml" -f sarif -o example.sarif || true
echo "wrote example.sarif"

banner "5. Sign the manifest so it is attestable (Ed25519)"
ovrin keygen --out-dir .ovrin-keys --force
ovrin scan . -f json --no-timestamp -o example.manifest.json
ovrin sign example.manifest.json --key .ovrin-keys/ovrin-signing.key -o example.manifest.json.sig
ovrin verify example.manifest.json --sig example.manifest.json.sig --pub .ovrin-keys/ovrin-signing.pub
echo

