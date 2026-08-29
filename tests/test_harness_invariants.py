"""Harness invariants — mechanical anti-bypass checks (not virtual/filler tests)."""

from __future__ import annotations

import ast
from pathlib import Path

from models import content_filename

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _py_files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_const(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _request_json_write_calls(tree: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, method) for request_json(METHOD, ...) where METHOD is a write verb."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) != "request_json":
            continue
        if not node.args:
            continue
        method = _string_const(node.args[0])
        if method and method.upper() in WRITE_METHODS:
            found.append((node.lineno, method.upper()))
    return found


def test_write_http_confined_to_mutate():
    violations: list[str] = []
    for path in _py_files_under(SRC):
        rel = path.relative_to(SRC)
        parts = rel.parts
        if parts[0] == "tests":
            continue
        if rel.as_posix() == "http_client.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, method in _request_json_write_calls(tree):
            if parts[0] != "mutate":
                violations.append(f"{rel}:{lineno} request_json({method!r})")
    assert not violations, "non-GET request_json must live under src/mutate/\n" + "\n".join(
        violations
    )


def test_gate_files_present():
    required = [
        ROOT / "ruff.toml",
        ROOT / ".github" / "workflows" / "harness-gate.yml",
        ROOT / "tests" / "test_harness_invariants.py",
        ROOT / "HARNESS.md",
        ROOT / "Makefile",
        ROOT / "docs" / "harness" / "python" / "invariants.md",
        ROOT / "docs" / "harness" / "frontend" / "README.md",
        ROOT / "docs" / "harness" / "build" / "gate.md",
        ROOT / "docs" / "harness" / "config" / "inventory.md",
        ROOT / "docs" / "harness" / "anti-bypass.md",
        ROOT / "docs" / "harness" / "verify.md",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    assert not missing, f"harness gate files missing: {missing}"


def test_ruff_select_not_gutted():
    text = (ROOT / "ruff.toml").read_text(encoding="utf-8")
    # Minimal parse — avoid tomllib (3.11+) / extra deps on 3.10 CI images.
    import re

    m = re.search(r"(?m)^select\s*=\s*\[([^\]]*)\]", text)
    assert m, "ruff.toml must define lint.select = [...]"
    items = [x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()]
    assert items, "ruff.toml lint.select must be non-empty (do not gut the linter)"


def test_content_filename_ascii_for_business_ids():
    name = content_filename("answer", "456", "123")
    assert name == "answer_123_456.md"
    assert name.isascii()
    assert "中文" not in name
    # Callers must pass ASCII zhihu ids; Chinese belongs in title/body only.
    polluted = content_filename("answer", "你好", "1")
    assert not polluted.isascii(), "non-ASCII ids produce non-ASCII names — never pass Chinese as zhihu_id"


def test_makefile_defines_gate_target():
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "\ngate:" in mk or mk.startswith("gate:") or "\ngate:\n" in mk or "gate:" in mk
    assert "ruff check src" in mk
    assert "pytest" in mk
