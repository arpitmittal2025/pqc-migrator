"""Core data models shared by every stage of the pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Algorithm identifiers used by the detector / recommender.
ALG_RSA = "rsa"
ALG_ECC = "ecc"
ALG_DH = "dh"

# Purposes a finding can serve.
PURPOSE_KEM = "kem"
PURPOSE_SIGNATURE = "signature"
PURPOSE_KEY_EXCHANGE = "key_exchange"


@dataclass
class Finding:
    """One occurrence of quantum-vulnerable classical cryptography."""

    file: str
    line: int
    algorithm: str  # "rsa" | "ecc" | "dh"
    purpose: str  # "kem" | "signature" | "key_exchange"
    matched: str  # the construct matched, e.g. "rsa.generate_private_key"
    library: str  # "cryptography" | "pycryptodome" | "ecdsa" | "unknown"
    snippet: str = ""  # source line, for the report
    detector: str = "ast"  # "ast" | "regex"

    def key(self) -> tuple[str, int, str]:
        """Identity used to de-duplicate AST and regex hits."""
        return (self.file, self.line, self.matched)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Recommendation:
    """The NIST PQC replacement proposed for a finding."""

    finding: Finding
    pqc_algorithm: str  # e.g. "ML-KEM-768"
    nist_standard: str  # e.g. "FIPS 203"
    nist_level: int  # 1..5
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding": self.finding.to_dict(),
            "pqc_algorithm": self.pqc_algorithm,
            "nist_standard": self.nist_standard,
            "nist_level": self.nist_level,
            "rationale": self.rationale,
        }


@dataclass
class MigrationResult:
    """Outcome of applying rewrite rules to a single source file."""

    finding: Finding | None
    original_file: str
    migrated_file: str
    changed: bool
    notes: str
    rules_applied: list[str] = field(default_factory=list)
    # True when a rule fired but the construct still needs a human protocol
    # change (e.g. DH's symmetric agreement has no drop-in KEM equivalent).
    manual_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding": self.finding.to_dict() if self.finding else None,
            "original_file": self.original_file,
            "migrated_file": self.migrated_file,
            "changed": self.changed,
            "notes": self.notes,
            "rules_applied": list(self.rules_applied),
            "manual_review": self.manual_review,
        }


@dataclass
class Report:
    """Everything the reporter needs to render JSON / Markdown / HTML."""

    target: str = ""
    backend: str = ""
    findings: list[Finding] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    migrations: list[MigrationResult] = field(default_factory=list)
    verification: dict[str, bool] = field(default_factory=dict)
    benchmark: dict[str, dict[str, Any]] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "backend": self.backend,
            "generated_at": self.generated_at,
            "context": self.context,
            "findings": [f.to_dict() for f in self.findings],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "migrations": [m.to_dict() for m in self.migrations],
            "verification": self.verification,
            "benchmark": self.benchmark,
            "analysis": self.analysis,
        }
