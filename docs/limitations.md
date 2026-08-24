# Limitations

- Public repositories only. Enterprise practice may differ, and we say so rather than generalise past the data.
- Agent behaviour moves. Every row in the loading matrix is dated, and several are `documented` rather than `observed`. Re-run before citing.
- CODEOWNERS coverage is a proxy for review, not proof of it. We report `enforceable: null` where branch protection would decide, because the filesystem cannot.
- Package resolution is ecosystem-specific. npm resolves cleanly; others resolve partially. Coverage is reported per ecosystem.
- Discovery is filename-based. A project that loads instructions from an unusual filename via configuration is missed unless that pattern is added to `.aim.yml` or `formats.yaml`.
- The tool reads files. It does not execute agents, so a `loaded` verdict means "within discovery scope", not "observed being obeyed". Observation lives in `tests/harness_cases/`.
