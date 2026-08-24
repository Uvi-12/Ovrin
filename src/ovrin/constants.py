"""Fixed values used across the scanner. One place, so nothing drifts."""

# Files larger than this are inventoried but not hashed in full. We never
# publish a hash of part of a file as if it were the whole file.
MAX_HASH_BYTES = 2 * 1024 * 1024

# Directories we do not descend into. These are scan-cost exclusions, not trust
# decisions. Vendor directories are handled in origin.py and are very much in
# scope.
SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox",
})

# Origin classes. A file is exactly one of these.
ORIGIN_CLASSES = (
    "repo",                 # tracked, in the project's own source tree
    "workspace",            # a declared monorepo workspace member
    "submodule",            # inside a path registered in .gitmodules
    "vendored",             # inside a committed third-party payload directory
    "installed-dependency", # resolved into a dependency tree (never committed)
    "untracked",            # on disk, not tracked by git
    "unknown",              # not a git repository; origin undecidable
)

# Reachability verdicts. What would a given harness do with this file.
VERDICTS = ("loaded", "ignored", "not-discovered", "unverified")

# Confidence in a harness rule. How we know.
CONFIDENCE = ("observed", "documented", "inferred", "unknown")

# How a format is consumed. Keeps a manually loaded CONVENTIONS.md from being
# counted as an auto-loaded instruction file.
ACTIVATION = ("native-auto", "configurable", "legacy", "manual", "unknown")
