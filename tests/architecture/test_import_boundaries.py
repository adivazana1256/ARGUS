"""Architecture / import-boundary enforcement (M0 spec §7.4, §1.1).

A small AST-based checker walks every production module under ``src/argus`` and
asserts the dependency direction defined in ``docs/ARCHITECTURE.md`` §17 and the
M0 foundation spec §1.1.  It is deliberately zero-dependency (stdlib ``ast`` +
``pathlib``) rather than pulling in ``import-linter`` — the ruleset is small and
owning it keeps it transparent and extensible (M0 spec §7.4, §18 decision E).

The checker is a pure function over source text, so the negative controls feed
it *synthetic* in-test source (strings / ``tmp_path`` files) to prove it flags a
forbidden import — **no real forbidden import is ever added to src/argus**
(M0 spec §7.4 negative-control strategy).

Dependency matrix (``source layer -> forbidden target layers``), derived from
``docs/ARCHITECTURE.md`` §17 (inner layers never import outer) and M0 §1.1
(config/observability are cross-cutting and import no layer; nothing imports
spikes):

    domain          -> application, api, infrastructure, observability, config, spikes
    application      -> api, infrastructure, spikes
    config           -> domain, application, api, infrastructure, observability, spikes
    observability    -> domain, application, api, infrastructure, spikes
                         (observability may import config)
    api              -> infrastructure, spikes
    infrastructure   -> spikes
    <argus root>     -> spikes   (e.g. main.py)

Only argus-internal layer dependencies and ``spikes`` are governed here.
Standard-library and third-party imports (os, fastapi, pydantic, ...) are
ignored by design — framework-purity rules are a separate concern.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
ARGUS_ROOT_LAYER = "<argus-root>"

# source layer -> forbidden target layers. Extend by adding a layer key (and
# listing it as a forbidden target where other layers must not reach it).
FORBIDDEN: dict[str, frozenset[str]] = {
    "domain": frozenset(
        {"application", "api", "infrastructure", "observability", "config", "spikes"}
    ),
    "application": frozenset({"api", "infrastructure", "spikes"}),
    "config": frozenset(
        {"domain", "application", "api", "infrastructure", "observability", "spikes"}
    ),
    "observability": frozenset(
        {"domain", "application", "api", "infrastructure", "spikes"}
    ),
    "api": frozenset({"infrastructure", "spikes"}),
    "infrastructure": frozenset({"spikes"}),
    ARGUS_ROOT_LAYER: frozenset({"spikes"}),
}
# Any layer not explicitly listed still must never import spikes.
_DEFAULT_FORBIDDEN = frozenset({"spikes"})


@dataclass(frozen=True)
class Violation:
    source_module: str
    source_file: str
    line: int
    imported: str
    target_layer: str

    @property
    def message(self) -> str:
        return (
            f"{self.source_file}:{self.line}: {self.source_module} imports "
            f"'{self.imported}' (layer '{self.target_layer}') — forbidden by the "
            f"ARGUS dependency matrix."
        )


def _target_layer(module: str) -> str | None:
    """Layer that an absolute dotted module belongs to, or None if external."""
    parts = module.split(".")
    if parts[0] == "spikes":
        return "spikes"
    if parts[0] != "argus":
        return None  # stdlib / third-party — ignored by design
    if len(parts) == 1:
        return ARGUS_ROOT_LAYER  # bare `import argus`
    return parts[1]


def _resolve_relative(
    module: str | None, level: int, package_parts: tuple[str, ...]
) -> str | None:
    """Resolve a relative import to an absolute dotted module.

    ``level`` 1 is the module's own package; each extra level climbs one parent
    (matching Python's import semantics). Returns None if it climbs past root.
    """
    if level == 0:
        return module
    keep = len(package_parts) - (level - 1)
    if keep <= 0:
        return None
    base = list(package_parts[:keep])
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def check_source(
    source: str,
    *,
    source_layer: str,
    package_parts: tuple[str, ...],
    source_module: str = "<source>",
    source_file: str = "<source>",
) -> list[Violation]:
    """Return every import in ``source`` that violates the dependency matrix.

    Pure function: no filesystem access, no import execution. ``package_parts``
    is the dotted package the source lives in (e.g. ``("argus", "api")``), used
    to resolve relative imports deterministically.
    """
    forbidden = FORBIDDEN.get(source_layer, _DEFAULT_FORBIDDEN)
    violations: list[Violation] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        resolved: list[str] = []
        if isinstance(node, ast.Import):
            resolved = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            abs_mod = _resolve_relative(node.module, node.level, package_parts)
            if abs_mod is not None:
                resolved = [abs_mod]
        else:
            continue
        for module in resolved:
            layer = _target_layer(module)
            if layer is not None and layer in forbidden:
                violations.append(
                    Violation(
                        source_module=source_module,
                        source_file=source_file,
                        line=node.lineno,
                        imported=module,
                        target_layer=layer,
                    )
                )
    return violations


def _package_parts(path: Path) -> tuple[str, ...]:
    return path.parent.relative_to(SRC_ROOT).parts


def _source_layer(package_parts: tuple[str, ...]) -> str:
    # package_parts[0] == "argus"; a file directly under argus/ (e.g. main.py,
    # the root __init__) is the argus root, otherwise the layer is parts[1].
    if len(package_parts) <= 1:
        return ARGUS_ROOT_LAYER
    return package_parts[1]


def _source_module(path: Path) -> str:
    parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def check_tree(root: Path = SRC_ROOT) -> list[Violation]:
    """Run the checker over the real ``src/argus/**`` tree (positive control)."""
    violations: list[Violation] = []
    for path in sorted((root / "argus").rglob("*.py")):
        package_parts = _package_parts(path)
        violations.extend(
            check_source(
                path.read_text(encoding="utf-8"),
                source_layer=_source_layer(package_parts),
                package_parts=package_parts,
                source_module=_source_module(path),
                source_file=str(path.relative_to(SRC_ROOT.parent)),
            )
        )
    return violations


# --------------------------------------------------------------------------- #
# Positive control: the real tree must be clean.
# --------------------------------------------------------------------------- #


def test_real_source_tree_has_no_violations() -> None:
    violations = check_tree()
    assert violations == [], "\n".join(v.message for v in violations)


# --------------------------------------------------------------------------- #
# Negative controls: synthetic in-test source only — src/argus is never touched.
# --------------------------------------------------------------------------- #


def test_import_from_spikes_is_flagged() -> None:
    violations = check_source(
        "import spikes.orchestration.graph\n",
        source_layer="domain",
        package_parts=("argus", "domain"),
        source_module="argus.domain.thing",
    )
    assert [v.target_layer for v in violations] == ["spikes"]


def test_from_spikes_import_is_flagged_for_any_layer() -> None:
    # infrastructure may import frameworks, but never spikes.
    violations = check_source(
        "from spikes.orchestration import graph\n",
        source_layer="infrastructure",
        package_parts=("argus", "infrastructure"),
    )
    assert [v.imported for v in violations] == ["spikes.orchestration"]


def test_forbidden_layer_dependency_is_flagged() -> None:
    # application must not reach outward into api.
    violations = check_source(
        "from argus.api.app import create_app\n",
        source_layer="application",
        package_parts=("argus", "application"),
    )
    assert [v.target_layer for v in violations] == ["api"]


def test_domain_importing_infrastructure_is_flagged() -> None:
    violations = check_source(
        "import argus.infrastructure.db\n",
        source_layer="domain",
        package_parts=("argus", "domain"),
    )
    assert [v.target_layer for v in violations] == ["infrastructure"]


def test_allowed_dependency_passes() -> None:
    # observability -> config is explicitly allowed (cross-cutting may use config).
    assert (
        check_source(
            "from argus.config import Settings\n",
            source_layer="observability",
            package_parts=("argus", "observability"),
        )
        == []
    )


def test_allowed_api_to_application_passes() -> None:
    # api -> application / domain is the normal delivery direction.
    assert (
        check_source(
            "from argus.application.investigate import run\n"
            "from argus.domain.ioc import Ioc\n",
            source_layer="api",
            package_parts=("argus", "api"),
        )
        == []
    )


def test_relative_forbidden_import_is_resolved_and_flagged() -> None:
    # `from ..api import router` inside domain resolves to argus.api -> forbidden.
    violations = check_source(
        "from ..api import router\n",
        source_layer="domain",
        package_parts=("argus", "domain"),
    )
    assert [(v.imported, v.target_layer) for v in violations] == [("argus.api", "api")]


def test_relative_allowed_import_passes() -> None:
    # `from ..config import Settings` inside api resolves to argus.config -> allowed.
    assert (
        check_source(
            "from ..config import Settings\n",
            source_layer="api",
            package_parts=("argus", "api"),
        )
        == []
    )


def test_relative_same_layer_import_passes() -> None:
    # `from . import errors` inside api stays in api -> allowed.
    assert (
        check_source(
            "from . import errors\n",
            source_layer="api",
            package_parts=("argus", "api"),
        )
        == []
    )


def test_stdlib_and_thirdparty_imports_are_ignored() -> None:
    source = (
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "import fastapi\n"
        "from pydantic import BaseModel\n"
        "import structlog\n"
    )
    assert (
        check_source(source, source_layer="domain", package_parts=("argus", "domain"))
        == []
    )


def test_checker_resolves_against_a_real_file(tmp_path: Path) -> None:
    # Prove the file-walking path works end to end on a synthetic tree, without
    # importing the module or touching src/argus.
    module = tmp_path / "argus" / "domain" / "thing.py"
    module.parent.mkdir(parents=True)
    module.write_text("import spikes.foo\n", encoding="utf-8")
    violations = check_source(
        module.read_text(encoding="utf-8"),
        source_layer="domain",
        package_parts=("argus", "domain"),
        source_module="argus.domain.thing",
        source_file="src/argus/domain/thing.py",
    )
    assert len(violations) == 1


def test_violation_message_is_actionable() -> None:
    (violation,) = check_source(
        "import spikes.foo\n",
        source_layer="domain",
        package_parts=("argus", "domain"),
        source_module="argus.domain.thing",
        source_file="src/argus/domain/thing.py",
    )
    msg = violation.message
    assert "src/argus/domain/thing.py" in msg  # source file
    assert "argus.domain.thing" in msg  # source module
    assert "spikes.foo" in msg  # forbidden target
    assert "spikes" in msg  # offending layer
