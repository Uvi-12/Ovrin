#!/usr/bin/env bash
# A ~2-minute Ovrin walkthrough. Requires: ovrin installed (`pip install .`),
# git, and the [sign] extra for the last step (`pip install ".[sign]"`).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="${1:-/tmp/ovrin-demo}"
banner(){ printf '\n\033[1m== %s ==\033[0m\n\n' "$1"; }

banner "0. Build a demo repo with a seeded supply-chain layout"
bash "$HERE/build_demo_repo.sh" "$DEMO"
cd "$DEMO"

banner "1. Inventory what the agent would actually obey"
ovrin scan .

banner "2. CI gate: fail the build on any third-party instruction file"
if ovrin scan . --fail-on-third-party; then echo "exit=0 (clean)"; else echo "exit=$? (gate tripped — as intended)"; fi

banner "3. Emit an SBOM-aligned provenance manifest (SPDX 3.0)"
ovrin scan . -f spdx --no-timestamp -o demo.spdx.json
echo "wrote demo.spdx.json ($(wc -c < demo.spdx.json) bytes)"

banner "4. Enforce a delegation policy — block undelegated third-party authority"
ovrin enforce . --harness claude-code --policy "$HERE/authority-policy.yaml" -f sarif -o demo.sarif || true
echo "wrote demo.sarif"

banner "5. Sign the manifest so it is attestable (Ed25519)"
ovrin keygen --out-dir .ovrin-keys --force
ovrin scan . -f json --no-timestamp -o demo.manifest.json
ovrin sign demo.manifest.json --key .ovrin-keys/ovrin-signing.key -o demo.manifest.json.sig
ovrin verify demo.manifest.json --sig demo.manifest.json.sig --pub .ovrin-keys/ovrin-signing.pub
echo
echo "To record an asciinema cast:  asciinema rec -c 'bash $HERE/demo.sh' ovrin-demo.cast"
