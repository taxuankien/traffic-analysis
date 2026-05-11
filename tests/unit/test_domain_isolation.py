"""Verify the domain & application/ports layers don't leak heavy deps."""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
FORBIDDEN = {"cv2", "ultralytics", "supervision", "PyQt6", "torch"}


def _all_imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_domain_has_no_heavy_imports():
    for py in (ROOT / "src" / "domain").rglob("*.py"):
        leaked = _all_imports(py) & FORBIDDEN
        assert not leaked, f"{py.relative_to(ROOT)} imports {leaked}"


def test_ports_have_no_heavy_imports():
    for py in (ROOT / "src" / "application" / "ports").rglob("*.py"):
        leaked = _all_imports(py) & FORBIDDEN
        assert not leaked, f"{py.relative_to(ROOT)} imports {leaked}"
