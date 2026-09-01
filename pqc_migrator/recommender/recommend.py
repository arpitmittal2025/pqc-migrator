"""Rule + scoring engine: Finding + AppContext -> NIST PQC Recommendation."""

from __future__ import annotations

import re

from ..context.context import AppContext
from ..models import (
    PURPOSE_KEM,
    PURPOSE_KEY_EXCHANGE,
    PURPOSE_SIGNATURE,
    Finding,
    Recommendation,
)
from ..pqc.backends import standard_for

# NIST category -> concrete parameter set.
KEM_BY_LEVEL: dict[int, str] = {
    1: "ML-KEM-512",
    2: "ML-KEM-512",
    3: "ML-KEM-768",
    4: "ML-KEM-768",
    5: "ML-KEM-1024",
}

ML_DSA_BY_LEVEL: dict[int, str] = {
    1: "ML-DSA-44",
    2: "ML-DSA-44",
    3: "ML-DSA-65",
    4: "ML-DSA-65",
    5: "ML-DSA-87",
}

SLH_DSA_BY_LEVEL: dict[int, str] = {
    1: "SLH-DSA-SHA2-128s",
    2: "SLH-DSA-SHA2-128s",
    3: "SLH-DSA-SHA2-192s",
    4: "SLH-DSA-SHA2-192s",
    5: "SLH-DSA-SHA2-256s",
}

CLASSICAL_LABEL: dict[str, str] = {
    "rsa": "RSA",
    "ecc": "ECC/ECDSA",
    "dh": "Diffie-Hellman",
}

# Strength hints read out of the matched source line. Each entry raises the
# floor of the recommended NIST category.
STRENGTH_HINTS: tuple[tuple[str, int, str], ...] = (
    (r"key_size\s*=\s*(?:4096|8192)", 5, "RSA key size >= 4096 bits"),
    (r"key_size\s*=\s*3072", 3, "RSA key size 3072 bits"),
    (r"SECP521R1", 5, "curve P-521"),
    (r"SECP384R1", 4, "curve P-384"),
    (r"SECP256R1", 3, "curve P-256"),
)


def _score_level(finding: Finding, base_level: int) -> tuple[int, list[str]]:
    """Raise the target category when the classical parameters imply more strength."""
    level = base_level
    reasons: list[str] = []
    haystack = f"{finding.snippet} {finding.matched}"
    for regex, implied, label in STRENGTH_HINTS:
        if re.search(regex, haystack, re.IGNORECASE) and implied > level:
            level = implied
            reasons.append(f"{label} implies NIST level {implied}")
    return min(5, level), reasons


def recommend(finding: Finding, context: AppContext | None = None) -> Recommendation:
    """Pick the NIST PQC replacement for a single finding."""
    context = context or AppContext()
    level, score_reasons = _score_level(finding, context.security_level)

    if finding.purpose in (PURPOSE_KEM, PURPOSE_KEY_EXCHANGE):
        algorithm = KEM_BY_LEVEL[level]
        family = "a key-encapsulation mechanism"
    elif finding.purpose == PURPOSE_SIGNATURE:
        if context.prefer_signature_scheme == "SLH-DSA":
            algorithm = SLH_DSA_BY_LEVEL[level]
            family = "a stateless hash-based signature scheme"
        else:
            algorithm = ML_DSA_BY_LEVEL[level]
            family = "a lattice-based signature scheme"
    else:  # pragma: no cover - purposes are constrained by the detector
        algorithm = KEM_BY_LEVEL[level]
        family = "a key-encapsulation mechanism"

    classical = CLASSICAL_LABEL.get(finding.algorithm, finding.algorithm.upper())
    rationale_parts = [
        f"{classical} ({finding.matched}) is broken by Shor's algorithm on a "
        f"cryptographically relevant quantum computer",
        f"the construct is used for '{finding.purpose}', so it needs {family}",
        f"{algorithm} targets NIST category {level}",
    ]
    rationale_parts.extend(score_reasons)
    if context.source != "defaults":
        rationale_parts.append(f"context from {context.source}")

    return Recommendation(
        finding=finding,
        pqc_algorithm=algorithm,
        nist_standard=standard_for(algorithm),
        nist_level=level,
        rationale="; ".join(rationale_parts) + ".",
    )


def recommend_all(
    findings: list[Finding], context: AppContext | None = None
) -> list[Recommendation]:
    """Recommend a replacement for every finding."""
    return [recommend(finding, context) for finding in findings]


def algorithms_used(recommendations: list[Recommendation]) -> list[str]:
    """Distinct PQC algorithms across recommendations, in first-seen order."""
    seen: list[str] = []
    for recommendation in recommendations:
        if recommendation.pqc_algorithm not in seen:
            seen.append(recommendation.pqc_algorithm)
    return seen
