# Limitations

- Public repositories only. Enterprise practice may differ, and we say so rather than generalise past the data.
- Agent behaviour moves. Every row in the loading matrix is dated, and several are `documented` rather than `observed`. Re-run before citing.
- CODEOWNERS coverage is a proxy for review, not proof of it. We report `enforceable: null` where branch protection would decide, because the filesystem cannot.
- Package resolution is ecosystem-specific. npm resolves cleanly; others resolve partially. Coverage is reported per ecosystem.
- Discovery is filename-based. A project that loads instructions from an unusual filename via configuration is missed unless that pattern is added to `formats.yaml`.
- The tool reads files. It does not execute agents, so a `loaded` verdict means "within discovery scope", not "observed being obeyed". Observation lives in `tests/harness_cases/`.
- Executing configuration is read as data and never run. A `loaded` verdict for an `.mcp.json` server or a settings hook means the agent reads the file when launched at the repository root. Some agents ask the user to approve project MCP servers before starting them; the scanner cannot see that choice, so it reports what the file would do, not whether someone clicked approve.
- Dependency-code detection is path-based. A hook or server command that runs a path inside `vendor/`, `node_modules/`, or a submodule is flagged. A command that fetches a package from a registry (`npx`, `uvx`) is reported as process execution, and as `floating_version` when the version can move, but the fetched package is not resolved. A path assembled at runtime from variables is not followed.
- User-scope and managed settings (`~/.claude`, `~/.gemini`, `~/.codex/config.toml`, enterprise policy files) live outside the repository and are out of scope. They can add or override executing configuration the manifest does not show.
