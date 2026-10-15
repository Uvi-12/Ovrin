# Editor integration

Copy `vscode-tasks.json` into your project's `.vscode/tasks.json` (or merge the
`tasks` array). Then **Terminal → Run Task → "Ovrin: scan instruction files"**.

Ovrin reports per *file* (an instruction file has no single offending line), so
the tasks surface the manifest in a terminal panel rather than as inline
squiggles. For CI annotations use the JSON manifest or the `enforce` SARIF
output, which GitHub code scanning renders directly.
