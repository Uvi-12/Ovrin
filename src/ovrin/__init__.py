"""Ovrin: inventory the instruction files your coding agent silently obeys.

AGENTS.md, CLAUDE.md, GEMINI.md, .cursorrules and their kin arrive through pull
requests like code, are reviewed like documentation, and are read by coding
agents as configuration. They have every property of a dependency and none of
the controls. Ovrin lists every one, records where it came from, whether
anyone reviews it, and which agents would load it.
"""
__version__ = "0.1.0"
__all__ = ["__version__"]
