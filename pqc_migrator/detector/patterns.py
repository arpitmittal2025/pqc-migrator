"""Signatures for quantum-vulnerable classical crypto across common Python libraries.

Each pattern is matched against the dotted name of an AST call/attribute
(e.g. ``rsa.generate_private_key``) and, as a fallback, against raw source text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import (
    ALG_DH,
    ALG_ECC,
    ALG_RSA,
    PURPOSE_KEM,
    PURPOSE_KEY_EXCHANGE,
    PURPOSE_SIGNATURE,
)

LIB_CRYPTOGRAPHY = "cryptography"
LIB_PYCRYPTODOME = "pycryptodome"
LIB_ECDSA = "ecdsa"
LIB_UNKNOWN = "unknown"

# Import roots -> library name, used to attribute a finding to a package.
IMPORT_LIBRARIES: dict[str, str] = {
    "cryptography": LIB_CRYPTOGRAPHY,
    "Crypto": LIB_PYCRYPTODOME,
    "Cryptodome": LIB_PYCRYPTODOME,
    "ecdsa": LIB_ECDSA,
}

# Third-party distributions that introduce classical public-key crypto.
VULNERABLE_DEPENDENCIES: dict[str, str] = {
    "cryptography": "RSA / ECDSA / DH primitives (hazmat asymmetric)",
    "Crypto": "PyCryptodome RSA, ECC and DH primitives",
    "Cryptodome": "PyCryptodome RSA, ECC and DH primitives",
    "ecdsa": "Pure-Python ECDSA signatures",
    "OpenSSL": "OpenSSL RSA/ECDSA key and certificate handling",
    "paramiko": "SSH host/user keys (RSA, ECDSA)",
    "jwt": "JWT signing with RS*/ES* algorithms",
    "jose": "JOSE/JWK signing with RS*/ES* algorithms",
}


@dataclass(frozen=True)
class CryptoPattern:
    """One detectable classical-crypto construct."""

    name: str  # the construct as it appears in code
    algorithm: str  # ALG_RSA | ALG_ECC | ALG_DH
    purpose: str  # PURPOSE_*
    library: str  # best-guess owning library
    description: str
    # Dotted suffixes that identify this construct in the AST.
    suffixes: tuple[str, ...] = field(default=())
    # Regex used by the text fallback scanner.
    regex: str = ""

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.regex or re.escape(self.name))


PATTERNS: tuple[CryptoPattern, ...] = (
    # ------------------------------------------------------------------ RSA
    CryptoPattern(
        name="rsa.generate_private_key",
        algorithm=ALG_RSA,
        purpose=PURPOSE_KEM,
        library=LIB_CRYPTOGRAPHY,
        description="RSA keypair generation (cryptography hazmat)",
        suffixes=("rsa.generate_private_key",),
        regex=r"\brsa\s*\.\s*generate_private_key\b",
    ),
    CryptoPattern(
        name="RSA.generate",
        algorithm=ALG_RSA,
        purpose=PURPOSE_KEM,
        library=LIB_PYCRYPTODOME,
        description="RSA keypair generation (PyCryptodome)",
        suffixes=("RSA.generate",),
        regex=r"\bRSA\s*\.\s*generate\b",
    ),
    CryptoPattern(
        name="padding.OAEP",
        algorithm=ALG_RSA,
        purpose=PURPOSE_KEM,
        library=LIB_CRYPTOGRAPHY,
        description="RSA-OAEP encryption padding (key transport)",
        suffixes=("padding.OAEP",),
        regex=r"\bpadding\s*\.\s*OAEP\b",
    ),
    CryptoPattern(
        name="PKCS1_OAEP.new",
        algorithm=ALG_RSA,
        purpose=PURPOSE_KEM,
        library=LIB_PYCRYPTODOME,
        description="RSA-OAEP cipher (PyCryptodome key transport)",
        suffixes=("PKCS1_OAEP.new",),
        regex=r"\bPKCS1_OAEP\b",
    ),
    CryptoPattern(
        name="padding.PSS",
        algorithm=ALG_RSA,
        purpose=PURPOSE_SIGNATURE,
        library=LIB_CRYPTOGRAPHY,
        description="RSA-PSS signature padding",
        suffixes=("padding.PSS",),
        regex=r"\bpadding\s*\.\s*PSS\b",
    ),
    CryptoPattern(
        name="padding.PKCS1v15",
        algorithm=ALG_RSA,
        purpose=PURPOSE_SIGNATURE,
        library=LIB_CRYPTOGRAPHY,
        description="PKCS#1 v1.5 signature padding",
        suffixes=("padding.PKCS1v15",),
        regex=r"\bpadding\s*\.\s*PKCS1v15\b",
    ),
    CryptoPattern(
        name="pkcs1_15.new",
        algorithm=ALG_RSA,
        purpose=PURPOSE_SIGNATURE,
        library=LIB_PYCRYPTODOME,
        description="PKCS#1 v1.5 signer (PyCryptodome)",
        suffixes=("pkcs1_15.new",),
        regex=r"\bpkcs1_15\s*\.\s*new\b",
    ),
    CryptoPattern(
        name="serialization.load_pem_private_key",
        algorithm=ALG_RSA,
        purpose=PURPOSE_KEM,
        library=LIB_CRYPTOGRAPHY,
        description="Loads a classical PEM private key",
        suffixes=("serialization.load_pem_private_key",),
        regex=r"\bload_pem_private_key\b",
    ),
    # ------------------------------------------------------------------ ECC
    CryptoPattern(
        name="ec.generate_private_key",
        algorithm=ALG_ECC,
        purpose=PURPOSE_SIGNATURE,
        library=LIB_CRYPTOGRAPHY,
        description="Elliptic-curve keypair generation",
        suffixes=("ec.generate_private_key",),
        regex=r"\bec\s*\.\s*generate_private_key\b",
    ),
    CryptoPattern(
        name="ec.ECDSA",
        algorithm=ALG_ECC,
        purpose=PURPOSE_SIGNATURE,
        library=LIB_CRYPTOGRAPHY,
        description="ECDSA signature algorithm",
        suffixes=("ec.ECDSA",),
        regex=r"\bec\s*\.\s*ECDSA\b",
    ),
    CryptoPattern(
        name="ec.SECP256R1",
        algorithm=ALG_ECC,
        purpose=PURPOSE_SIGNATURE,
        library=LIB_CRYPTOGRAPHY,
        description="NIST P-curve parameters",
        suffixes=("ec.SECP256R1", "ec.SECP384R1", "ec.SECP521R1"),
        regex=r"\bSECP(?:256R1|384R1|521R1)\b",
    ),
    CryptoPattern(
        name="ec.ECDH",
        algorithm=ALG_ECC,
        purpose=PURPOSE_KEY_EXCHANGE,
        library=LIB_CRYPTOGRAPHY,
        description="Elliptic-curve Diffie-Hellman key agreement",
        suffixes=("ec.ECDH",),
        regex=r"\bec\s*\.\s*ECDH\b",
    ),
    CryptoPattern(
        name="SigningKey.generate",
        algorithm=ALG_ECC,
        purpose=PURPOSE_SIGNATURE,
        library=LIB_ECDSA,
        description="ECDSA signing key (ecdsa package)",
        suffixes=("SigningKey.generate", "SigningKey.from_secret_exponent"),
        regex=r"\bSigningKey\s*\.\s*(?:generate|from_secret_exponent)\b",
    ),
    CryptoPattern(
        name="ECC.generate",
        algorithm=ALG_ECC,
        purpose=PURPOSE_SIGNATURE,
        library=LIB_PYCRYPTODOME,
        description="ECC keypair generation (PyCryptodome)",
        suffixes=("ECC.generate",),
        regex=r"\bECC\s*\.\s*generate\b",
    ),
    # ------------------------------------------------------------------- DH
    CryptoPattern(
        name="dh.generate_parameters",
        algorithm=ALG_DH,
        purpose=PURPOSE_KEY_EXCHANGE,
        library=LIB_CRYPTOGRAPHY,
        description="Finite-field Diffie-Hellman parameter generation",
        suffixes=("dh.generate_parameters",),
        regex=r"\bdh\s*\.\s*generate_parameters\b",
    ),
    CryptoPattern(
        name="dh.DHParameterNumbers",
        algorithm=ALG_DH,
        purpose=PURPOSE_KEY_EXCHANGE,
        library=LIB_CRYPTOGRAPHY,
        description="Diffie-Hellman parameter numbers",
        suffixes=("dh.DHParameterNumbers", "dh.DHPublicNumbers"),
        regex=r"\bdh\s*\.\s*DH(?:Parameter|Public|Private)Numbers\b",
    ),
    CryptoPattern(
        name="DiffieHellman",
        algorithm=ALG_DH,
        purpose=PURPOSE_KEY_EXCHANGE,
        library=LIB_UNKNOWN,
        description="Diffie-Hellman key agreement helper",
        suffixes=("DiffieHellman",),
        regex=r"\bDiffieHellman\b",
    ),
)

# Fast lookup: dotted suffix -> pattern.
SUFFIX_INDEX: dict[str, CryptoPattern] = {}
for _pattern in PATTERNS:
    for _suffix in _pattern.suffixes:
        SUFFIX_INDEX.setdefault(_suffix, _pattern)


def lookup(dotted: str) -> CryptoPattern | None:
    """Return the pattern matching a dotted call name, longest suffix first."""
    parts = dotted.split(".")
    for start in range(len(parts)):
        candidate = ".".join(parts[start:])
        if candidate in SUFFIX_INDEX:
            return SUFFIX_INDEX[candidate]
    return None


def by_algorithm(algorithm: str) -> tuple[CryptoPattern, ...]:
    return tuple(p for p in PATTERNS if p.algorithm == algorithm)
