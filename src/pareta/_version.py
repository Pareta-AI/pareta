"""Single source of truth for the package version.

Kept in sync with pyproject.toml's [project].version. When we wire the
OpenAPI-generated types + CI release (SDK_PLAN §10/§12), the tag drives both.
"""

__version__ = "1.1.1"
