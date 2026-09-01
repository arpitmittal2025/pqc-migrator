"""Project-level static analysis: which files and dependencies pull in classical crypto."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ..detector.patterns import IMPORT_LIBRARIES, VULNERABLE_DEPENDENCIES
from ..detector.scanner import iter_python_files

REQUIREMENT_FILES = ("requirements.txt", "requirements-dev.txt", "pyproject.toml")
_REQ_LINE = re.compile(r"^\s*['\"]?([A-Za-z0-9_.\-]+)")

# Distribution name -> import root, for requirement parsing.
DISTRIBUTION_ROOTS = {
    "cryptography": "cryptography",
    "pycryptodome": "Crypto",
    "pycryptodomex": "Cryptodome",
    "ecdsa": "ecdsa",
    "pyopenssl": "OpenSSL",
    "paramiko": "paramiko",
    "pyjwt": "jwt",
    "python-jose": "jose",
}


def file_imports(path: Path) -> list[str]:
    """Top-level module names imported by a Python file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return sorted(modules)


def _crypto_roots(modules: list[str]) -> list[str]:
    roots = {m.split(".")[0] for m in modules}
    return sorted(roots & (set(IMPORT_LIBRARIES) | set(VULNERABLE_DEPENDENCIES)))


def declared_dependencies(root: Path) -> dict[str, str]:
    """Requirement-file entries that ship classical public-key crypto."""
    flagged: dict[str, str] = {}
    for name in REQUIREMENT_FILES:
        manifest = root / name
        if not manifest.is_file():
            continue
        try:
            text = manifest.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            match = _REQ_LINE.match(line)
            if not match:
                continue
            distribution = match.group(1).lower()
            import_root = DISTRIBUTION_ROOTS.get(distribution)
            if import_root and import_root in VULNERABLE_DEPENDENCIES:
                flagged[distribution] = (
                    f"{VULNERABLE_DEPENDENCIES[import_root]} (declared in {name})"
                )
    return flagged


def analyze_project(path: str | Path) -> dict[str, Any]:
    """Walk the project and summarise where classical crypto enters it."""
    target = Path(path)
    root = target if target.is_dir() else target.parent
    python_files = iter_python_files(target)

    imports_by_file: dict[str, list[str]] = {}
    crypto_files: dict[str, list[str]] = {}
    library_usage: dict[str, int] = {}

    for file_path in python_files:
        modules = file_imports(file_path)
        imports_by_file[str(file_path)] = modules
        roots = _crypto_roots(modules)
        if roots:
            crypto_files[str(file_path)] = roots
            for item in roots:
                library_usage[item] = library_usage.get(item, 0) + 1

    return {
        "root": str(root),
        "python_files": len(python_files),
        "files_importing_crypto": len(crypto_files),
        "imports_by_file": imports_by_file,
        "crypto_files": crypto_files,
        "library_usage": dict(sorted(library_usage.items())),
        "vulnerable_dependencies": {
            name: VULNERABLE_DEPENDENCIES[name]
            for name in sorted(library_usage)
            if name in VULNERABLE_DEPENDENCIES
        },
        "declared_dependencies": declared_dependencies(root),
    }
