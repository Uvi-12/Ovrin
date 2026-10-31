"""Ovrin: inventory the configuration your coding agent obeys and runs.

AGENTS.md, CLAUDE.md, GEMINI.md, .cursorrules and their kin arrive through pull
requests like code, are reviewed like documentation, and are read by coding
agents as configuration. .mcp.json servers and settings hooks go further and
make the agent run code. All of them have every property of a dependency and
none of the controls. Ovrin lists every one, records where it came from,
whether anyone reviews it, which agents would load it, and what it can do.
"""
__version__ = "0.2.0"
__all__ = ["__version__"]
