"""AST-first scanner that turns Python source into :class:`Finding` objects.

The AST walk is the primary detector; a regex sweep runs afterwards and only
contributes hits the AST missed (unparsable files, string-embedded code, etc.).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from ..models import (
    ALG_ECC,
    ALG_RSA,
    PURPOSE_KEM,
    PURPOSE_KEY_EXCHANGE,
    PURPOSE_SIGNATURE,
    Finding,
)
from . import patterns as P

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "build",
    "dist",
    "site-packages",
}


def iter_python_files(root: str | os.PathLike[str]) -> list[Path]:
    """Yield every ``.py`` file under ``root``, skipping vendored/tooling dirs."""
    root_path = Path(root)
    if root_path.is_file():
        return [root_path] if root_path.suffix == ".py" else []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in sorted(filenames):
            if name.endswith(".py"):
                found.append(Path(dirpath) / name)
    return sorted(found)


def dotted_name(node: ast.AST) -> str:
    """Flatten an attribute/name chain into ``a.b.c``; empty string if not one."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    elif isinstance(current, ast.Call):
        # e.g. parameters.generate_private_key() chained off a call
        inner = dotted_name(current.func)
        if inner:
            parts.append(inner)
    else:
        return ""
    return ".".join(reversed(parts))


class _ImportCollector(ast.NodeVisitor):
    """Maps local aliases to the module path they came from."""

    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}
        self.modules: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.aliases[local] = alias.name
            self.modules.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            self.aliases[local] = f"{module}.{alias.name}" if module else alias.name
        if module:
            self.modules.add(module)
        self.generic_visit(node)


def _library_for(dotted: str, aliases: dict[str, str], fallback: str) -> str:
    """Attribute a matched construct to a library using the file's imports."""
    root = dotted.split(".")[0]
    origin = aliases.get(root, "")
    origin_root = origin.split(".")[0]
    if origin_root in P.IMPORT_LIBRARIES:
        return P.IMPORT_LIBRARIES[origin_root]
    if root in P.IMPORT_LIBRARIES:
        return P.IMPORT_LIBRARIES[root]
    return fallback


class _CryptoVisitor(ast.NodeVisitor):
    """Collects pattern hits from calls and bare attribute references."""

    def __init__(self, file: str, lines: list[str], aliases: dict[str, str]) -> None:
        self.file = file
        self.lines = lines
        self.aliases = aliases
        self.findings: list[Finding] = []
        self._seen: set[tuple[str, int, str]] = set()

    def _canonical(self, dotted: str) -> str:
        """Expand a local alias back to the module it was imported from.

        ``from ...asymmetric import rsa as asym_rsa`` makes ``asym_rsa.x``
        equivalent to ``cryptography...asymmetric.rsa.x``; without this the
        renamed import would be invisible to the pattern index.
        """
        root, _, rest = dotted.partition(".")
        origin = self.aliases.get(root)
        if not origin:
            return ""
        return f"{origin}.{rest}" if rest else origin

    def _record(self, node: ast.AST, dotted: str) -> None:
        pattern = P.lookup(dotted)
        if pattern is None:
            canonical = self._canonical(dotted)
            pattern = P.lookup(canonical) if canonical else None
        if pattern is None:
            return
        line = getattr(node, "lineno", 0)
        key = (self.file, line, pattern.name)
        if key in self._seen:
            return
        self._seen.add(key)
        self.findings.append(
            Finding(
                file=self.file,
                line=line,
                algorithm=pattern.algorithm,
                purpose=pattern.purpose,
                matched=pattern.name,
                library=_library_for(dotted, self.aliases, pattern.library),
                snippet=self.lines[line - 1].strip() if 0 < line <= len(self.lines) else "",
                detector="ast",
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        dotted = dotted_name(node.func)
        if dotted:
            self._record(node, dotted)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        dotted = dotted_name(node)
        if dotted:
            self._record(node, dotted)
        self.generic_visit(node)


def _refine_ecc_purpose(file_findings: list[Finding]) -> None:
    """An EC key used only for agreement is key exchange, not signing.

    The pattern table has to pick one default purpose for
    ``ec.generate_private_key``; the surrounding file decides the real one.
    """
    ecc = [f for f in file_findings if f.algorithm == ALG_ECC]
    if not ecc:
        return
    agrees = any(f.purpose == PURPOSE_KEY_EXCHANGE for f in ecc)
    signs = any(f.matched in {"ec.ECDSA", "Ed25519PrivateKey.generate"} for f in ecc)
    if agrees and not signs:
        for finding in ecc:
            if finding.matched in {"ec.generate_private_key", "ec.SECP256R1",
                                   "ec.SECP384R1", "ec.SECP521R1"}:
                finding.purpose = PURPOSE_KEY_EXCHANGE


def _refine_rsa_purpose(findings: list[Finding]) -> None:
    """RSA keygen is purpose-neutral; decide per file from how the key is used.

    A file that only ever signs with its RSA key needs ML-DSA, not ML-KEM.
    """
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.file, []).append(finding)

    for file_findings in by_file.values():
        _refine_ecc_purpose(file_findings)
        rsa_findings = [f for f in file_findings if f.algorithm == ALG_RSA]
        if not rsa_findings:
            continue
        signs = any(f.purpose == PURPOSE_SIGNATURE for f in rsa_findings)
        encrypts = any(
            f.purpose == PURPOSE_KEM and f.matched in {"padding.OAEP", "PKCS1_OAEP.new"}
            for f in rsa_findings
        )
        if signs and not encrypts:
            for finding in rsa_findings:
                if finding.matched in {
                    "rsa.generate_private_key",
                    "RSA.generate",
                    "serialization.load_pem_private_key",
                }:
                    finding.purpose = PURPOSE_SIGNATURE


def _regex_findings(
    file: str, lines: list[str], aliases: dict[str, str], seen: set[tuple[str, int, str]]
) -> list[Finding]:
    """Text fallback for anything the AST walk could not reach."""
    findings: list[Finding] = []
    for pattern in P.PATTERNS:
        regex = pattern.compiled()
        for index, line in enumerate(lines, start=1):
            code = line.split("#", 1)[0]
            if not regex.search(code):
                continue
            key = (file, index, pattern.name)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                Finding(
                    file=file,
                    line=index,
                    algorithm=pattern.algorithm,
                    purpose=pattern.purpose,
                    matched=pattern.name,
                    library=_library_for(pattern.name, aliases, pattern.library),
                    snippet=line.strip(),
                    detector="regex",
                )
            )
    return findings


def scan_source(source: str, file: str = "<string>") -> list[Finding]:
    """Scan a source string; used by tests and by :func:`scan_file`."""
    lines = source.splitlines()
    aliases: dict[str, str] = {}
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None

    if tree is not None:
        collector = _ImportCollector()
        collector.visit(tree)
        aliases = collector.aliases
        visitor = _CryptoVisitor(file, lines, aliases)
        visitor.visit(tree)
        findings.extend(visitor.findings)
        seen |= visitor._seen
    else:
        # Fallback only. On a file that parses, the AST walk is authoritative;
        # running the regex sweep as well only matched crypto names appearing
        # in docstrings, string constants and import statements.
        findings.extend(_regex_findings(file, lines, aliases, seen))
    _refine_rsa_purpose(findings)
    findings.sort(key=lambda f: (f.file, f.line, f.matched))
    return findings


def scan_file(path: str | os.PathLike[str]) -> list[Finding]:
    """Scan a single Python file."""
    file_path = Path(path)
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_source(source, str(file_path))


def scan_path(path: str | os.PathLike[str]) -> list[Finding]:
    """Scan a file or an entire project directory."""
    findings: list[Finding] = []
    for file_path in iter_python_files(path):
        findings.extend(scan_file(file_path))
    return findings
