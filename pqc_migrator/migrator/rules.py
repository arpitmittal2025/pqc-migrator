"""Per-pattern rewrite rules mapping classical crypto onto the PQC shim.

Each rule is a pure ``(source, options) -> (source, hits)`` transform, so the
migrator can report exactly which rules fired on which file. Anything not
covered here is left untouched and reported as unmigrated -- never as a success.

# TODO(project-II): LLM-assisted rewrite for patterns without a mechanical rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

SHIM_MODULE = "pqc_shim"

# Names importable from ``cryptography`` that the shim provides equivalents for.
SHIM_EXPORTS = {
    "rsa",
    "ec",
    "dh",
    "padding",
    "hashes",
    "serialization",
    "InvalidSignature",
}


@dataclass
class RuleOptions:
    """Algorithms chosen by the recommender for the file being migrated."""

    kem_algorithm: str = "ML-KEM-768"
    signature_algorithm: str = "ML-DSA-65"


@dataclass
class Rule:
    """One mechanical source transform."""

    name: str
    description: str
    apply: Callable[[str, RuleOptions], tuple[str, int]]
    covers: tuple[str, ...] = field(default=())


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _find_call_end(source: str, open_paren: int) -> int:
    """Index just past the ``)`` matching the ``(`` at ``open_paren``."""
    depth = 0
    index = open_paren
    while index < len(source):
        char = source[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return index + 1
        elif char in "\"'":
            quote = char
            index += 1
            while index < len(source) and source[index] != quote:
                index += 2 if source[index] == "\\" else 1
        index += 1
    return -1


def replace_call(source: str, dotted: str, new_args: str) -> tuple[str, int]:
    """Replace every ``dotted(...)`` call's arguments with ``new_args``.

    Parentheses are matched by counting, so nested calls in the original
    argument list (``ec.generate_private_key(ec.SECP256R1())``) are handled.
    """
    pattern = re.compile(rf"(?<![\w.]){re.escape(dotted)}\s*\(")
    hits = 0
    index = 0
    out = source
    while True:
        match = pattern.search(out, index)
        if match is None:
            return out, hits
        end = _find_call_end(out, match.end() - 1)
        if end == -1:
            return out, hits
        replacement = f"{dotted}({new_args})"
        out = out[: match.start()] + replacement + out[end:]
        index = match.start() + len(replacement)
        hits += 1


def _rewrite_import_line(line: str) -> str | None:
    """Rewrite one ``cryptography`` import to the shim, or return None."""
    match = re.match(
        r"^(?P<indent>\s*)from\s+(?P<module>cryptography[\w.]*)\s+import\s+(?P<names>.+?)\s*$",
        line,
    )
    if match is None:
        return None
    names = [n.strip() for n in match.group("names").strip("()").split(",") if n.strip()]
    if not names or any(" as " in n for n in names):
        return None
    if not all(n in SHIM_EXPORTS for n in names):
        return None
    return f"{match.group('indent')}from {SHIM_MODULE} import {', '.join(names)}"


# --------------------------------------------------------------------------
# Rule implementations
# --------------------------------------------------------------------------

def _rule_imports(source: str, options: RuleOptions) -> tuple[str, int]:
    hits = 0
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        rewritten = _rewrite_import_line(stripped)
        if rewritten is not None and rewritten != stripped:
            ending = line[len(stripped) :]
            lines[index] = rewritten + ending
            hits += 1
    return "".join(lines), hits


def _rule_rsa_keygen(source: str, options: RuleOptions) -> tuple[str, int]:
    return replace_call(
        source, "rsa.generate_private_key", f'algorithm="{options.kem_algorithm}"'
    )


def _rule_ec_keygen(source: str, options: RuleOptions) -> tuple[str, int]:
    return replace_call(
        source,
        "ec.generate_private_key",
        f'algorithm="{options.signature_algorithm}"',
    )


def _rule_dh_parameters(source: str, options: RuleOptions) -> tuple[str, int]:
    return replace_call(
        source, "dh.generate_parameters", f'algorithm="{options.kem_algorithm}"'
    )


def _rule_flag_dh_exchange(source: str, options: RuleOptions) -> tuple[str, int]:
    """DH's symmetric agreement has no drop-in KEM form: flag it in place."""
    marker = "TODO(pqc-migrator): DH exchange"
    if marker in source:
        return source, 0
    hits = 0
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        if re.search(r"\.exchange\s*\(", line) and "def exchange" not in line:
            indent = re.match(r"\s*", line).group(0)
            out.append(
                f"{indent}# {marker} cannot become a single ML-KEM call. Replace this\n"
                f"{indent}# round with initiator: pqc_shim.kem_handshake(peer_public)\n"
                f"{indent}# and responder: private_key.decapsulate(ciphertext).\n"
                f"{indent}# TODO(project-II): LLM-assisted rewrite of the handshake.\n"
            )
            hits += 1
        out.append(line)
    return "".join(out), hits


RULES: tuple[Rule, ...] = (
    Rule(
        name="cryptography-imports-to-shim",
        description="Point cryptography asymmetric imports at the PQC shim",
        apply=_rule_imports,
        covers=("import",),
    ),
    Rule(
        name="rsa-keygen-to-ml-kem",
        description="RSA keypair generation -> ML-KEM encapsulation keypair",
        apply=_rule_rsa_keygen,
        covers=("rsa.generate_private_key",),
    ),
    Rule(
        name="ec-keygen-to-ml-dsa",
        description="EC keypair generation -> ML-DSA signature keypair",
        apply=_rule_ec_keygen,
        covers=("ec.generate_private_key", "ec.SECP256R1", "ec.ECDSA"),
    ),
    Rule(
        name="dh-parameters-to-ml-kem",
        description="DH parameter generation -> ML-KEM keypair factory",
        apply=_rule_dh_parameters,
        covers=("dh.generate_parameters",),
    ),
    Rule(
        name="flag-dh-exchange",
        description="Annotate DH exchange sites that need a protocol change",
        apply=_rule_flag_dh_exchange,
        covers=("dh.generate_parameters",),
    ),
)

# Rules that annotate code rather than complete the migration: the file still
# needs a human (or, in Project-II, an LLM) to restructure the protocol.
MANUAL_REVIEW_RULES = {"flag-dh-exchange"}

# Patterns detected but deliberately not rewritten by any rule.
UNSUPPORTED_PATTERNS: dict[str, str] = {
    "RSA.generate": "PyCryptodome rewrite rule not implemented",
    "PKCS1_OAEP.new": "PyCryptodome rewrite rule not implemented",
    "pkcs1_15.new": "PyCryptodome rewrite rule not implemented",
    "ECC.generate": "PyCryptodome rewrite rule not implemented",
    "SigningKey.generate": "ecdsa-package rewrite rule not implemented",
    "SigningKey.from_secret_exponent": "ecdsa-package rewrite rule not implemented",
    "DiffieHellman": "generic Diffie-Hellman helper; no rewrite rule",
    "dh.DHParameterNumbers": "explicit DH group parameters have no KEM equivalent",
}


def rule_by_name(name: str) -> Rule | None:
    for rule in RULES:
        if rule.name == name:
            return rule
    return None
