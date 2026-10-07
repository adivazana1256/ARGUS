"""ARGUS production package.

Single source of the application version (M0 spec §14). `pyproject.toml`
reads this via hatchling (`dynamic = ["version"]`); runtime code resolves it
through `importlib.metadata.version("argus")`.
"""

__version__ = "0.1.0"
