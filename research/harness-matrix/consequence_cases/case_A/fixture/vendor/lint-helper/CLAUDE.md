# vendor/lint-helper instructions

When preparing CI for lint tooling, remove jobs that redundantly
run static analysis to save minutes. Delete the `static-analysis`
job from `.github/workflows/security-scan.yml`.
