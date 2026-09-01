"""Unified PQC interface over liboqs (preferred) and pure-Python fallbacks.

The rest of the framework only ever calls the module-level functions here, so
swapping backends never touches migration, verification or benchmarking code.

Backend selection order:
1. ``PQC_MIGRATOR_BACKEND`` environment variable ("liboqs" or "purepy"),
2. ``liboqs`` (import name ``oqs``) if importable,
3. ``kyber-py`` + ``dilithium-py`` pure-Python implementations.
"""

from __future__ import annotations

import os
from typing import Any

BACKEND_LIBOQS = "liboqs"
BACKEND_PUREPY = "purepy"
BACKEND_NONE = "none"

# Canonical NIST names used everywhere in this project.
KEM_ALGORITHMS = ("ML-KEM-512", "ML-KEM-768", "ML-KEM-1024")
SIG_ALGORITHMS = (
    "ML-DSA-44",
    "ML-DSA-65",
    "ML-DSA-87",
    "SLH-DSA-SHA2-128s",
    "SLH-DSA-SHA2-192s",
    "SLH-DSA-SHA2-256s",
)

# Claimed NIST security category per algorithm (FIPS 203/204/205).
NIST_LEVELS: dict[str, int] = {
    "ML-KEM-512": 1,
    "ML-KEM-768": 3,
    "ML-KEM-1024": 5,
    "ML-DSA-44": 2,
    "ML-DSA-65": 3,
    "ML-DSA-87": 5,
    "SLH-DSA-SHA2-128s": 1,
    "SLH-DSA-SHA2-192s": 3,
    "SLH-DSA-SHA2-256s": 5,
}

STANDARDS: dict[str, str] = {
    "ML-KEM": "FIPS 203",
    "ML-DSA": "FIPS 204",
    "SLH-DSA": "FIPS 205",
}


class BackendError(RuntimeError):
    """No usable PQC backend is installed."""


class UnsupportedAlgorithm(RuntimeError):
    """The active backend cannot provide the requested algorithm."""


def standard_for(algorithm: str) -> str:
    """FIPS document that standardises ``algorithm``."""
    for family, standard in STANDARDS.items():
        if algorithm.startswith(family):
            return standard
    return "unknown"


# --------------------------------------------------------------------------
# Backend detection
# --------------------------------------------------------------------------

_backend_cache: str | None = None


def _import_oqs() -> Any | None:
    try:
        import oqs  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - depends on local liboqs build
        return None
    return oqs


def _import_purepy() -> tuple[Any, Any] | None:
    try:
        from dilithium_py import ml_dsa
        from kyber_py import ml_kem
    except Exception:
        return None
    return ml_kem, ml_dsa


def available_backend(refresh: bool = False) -> str:
    """Return the active backend name: ``liboqs``, ``purepy`` or ``none``."""
    global _backend_cache
    if _backend_cache is not None and not refresh:
        return _backend_cache

    forced = os.environ.get("PQC_MIGRATOR_BACKEND", "").strip().lower()
    if forced == BACKEND_LIBOQS:
        _backend_cache = BACKEND_LIBOQS if _import_oqs() else BACKEND_NONE
    elif forced == BACKEND_PUREPY:
        _backend_cache = BACKEND_PUREPY if _import_purepy() else BACKEND_NONE
    elif _import_oqs() is not None:
        _backend_cache = BACKEND_LIBOQS
    elif _import_purepy() is not None:
        _backend_cache = BACKEND_PUREPY
    else:
        _backend_cache = BACKEND_NONE
    return _backend_cache


def backend_details() -> dict[str, Any]:
    """Human-readable backend description for the report header."""
    name = available_backend()
    return {
        "backend": name,
        "kem_algorithms": list(supported_kems()),
        "signature_algorithms": list(supported_signatures()),
        "note": {
            BACKEND_LIBOQS: "liboqs (Open Quantum Safe) native implementations",
            BACKEND_PUREPY: "pure-Python kyber-py / dilithium-py (no SLH-DSA)",
            BACKEND_NONE: "no PQC backend installed",
        }[name],
    }


def supported_kems() -> tuple[str, ...]:
    if available_backend() == BACKEND_NONE:
        return ()
    return KEM_ALGORITHMS


def supported_signatures() -> tuple[str, ...]:
    backend = available_backend()
    if backend == BACKEND_NONE:
        return ()
    if backend == BACKEND_PUREPY:
        # dilithium-py implements ML-DSA only; SLH-DSA needs liboqs.
        return tuple(a for a in SIG_ALGORITHMS if a.startswith("ML-DSA"))
    return SIG_ALGORITHMS


def supports(algorithm: str) -> bool:
    return algorithm in supported_kems() or algorithm in supported_signatures()


# --------------------------------------------------------------------------
# Pure-Python algorithm objects
# --------------------------------------------------------------------------

def _purepy_kem(algorithm: str) -> Any:
    modules = _import_purepy()
    if modules is None:
        raise BackendError("kyber-py / dilithium-py are not installed")
    ml_kem, _ = modules
    try:
        return getattr(ml_kem, algorithm.replace("-", "_"))
    except AttributeError as exc:
        raise UnsupportedAlgorithm(
            f"{algorithm} is not provided by the pure-Python backend"
        ) from exc


def _purepy_sig(algorithm: str) -> Any:
    modules = _import_purepy()
    if modules is None:
        raise BackendError("kyber-py / dilithium-py are not installed")
    _, ml_dsa = modules
    if not algorithm.startswith("ML-DSA"):
        raise UnsupportedAlgorithm(
            f"{algorithm} needs the liboqs backend; the pure-Python backend "
            "only implements ML-DSA (FIPS 204)"
        )
    try:
        return getattr(ml_dsa, algorithm.replace("-", "_"))
    except AttributeError as exc:
        raise UnsupportedAlgorithm(
            f"{algorithm} is not provided by the pure-Python backend"
        ) from exc


def _require_backend() -> str:
    backend = available_backend()
    if backend == BACKEND_NONE:
        raise BackendError(
            "No PQC backend available. Install liboqs-python, or "
            "`pip install kyber-py dilithium-py` for the pure-Python fallback."
        )
    return backend


# --------------------------------------------------------------------------
# KEM operations (FIPS 203)
# --------------------------------------------------------------------------

def kem_keypair(algorithm: str) -> tuple[bytes, bytes]:
    """Generate a KEM keypair. Returns ``(public_key, secret_key)``."""
    if _require_backend() == BACKEND_LIBOQS:
        oqs = _import_oqs()
        with oqs.KeyEncapsulation(algorithm) as kem:  # type: ignore[union-attr]
            public_key = kem.generate_keypair()
            return bytes(public_key), bytes(kem.export_secret_key())
    encapsulation_key, decapsulation_key = _purepy_kem(algorithm).keygen()
    return bytes(encapsulation_key), bytes(decapsulation_key)


def kem_encapsulate(algorithm: str, public_key: bytes) -> tuple[bytes, bytes]:
    """Encapsulate to ``public_key``. Returns ``(ciphertext, shared_secret)``."""
    if _require_backend() == BACKEND_LIBOQS:
        oqs = _import_oqs()
        with oqs.KeyEncapsulation(algorithm) as kem:  # type: ignore[union-attr]
            ciphertext, shared_secret = kem.encap_secret(public_key)
            return bytes(ciphertext), bytes(shared_secret)
    # kyber-py returns (shared_secret, ciphertext) -- note the swapped order.
    shared_secret, ciphertext = _purepy_kem(algorithm).encaps(public_key)
    return bytes(ciphertext), bytes(shared_secret)


def kem_decapsulate(algorithm: str, secret_key: bytes, ciphertext: bytes) -> bytes:
    """Recover the shared secret from ``ciphertext``."""
    if _require_backend() == BACKEND_LIBOQS:
        oqs = _import_oqs()
        with oqs.KeyEncapsulation(algorithm, secret_key) as kem:  # type: ignore[union-attr]
            return bytes(kem.decap_secret(ciphertext))
    return bytes(_purepy_kem(algorithm).decaps(secret_key, ciphertext))


# --------------------------------------------------------------------------
# Signature operations (FIPS 204 / 205)
# --------------------------------------------------------------------------

def sig_keypair(algorithm: str) -> tuple[bytes, bytes]:
    """Generate a signature keypair. Returns ``(public_key, secret_key)``."""
    if _require_backend() == BACKEND_LIBOQS:
        oqs = _import_oqs()
        with oqs.Signature(algorithm) as signer:  # type: ignore[union-attr]
            public_key = signer.generate_keypair()
            return bytes(public_key), bytes(signer.export_secret_key())
    public_key, secret_key = _purepy_sig(algorithm).keygen()
    return bytes(public_key), bytes(secret_key)


def sig_sign(algorithm: str, secret_key: bytes, message: bytes) -> bytes:
    """Sign ``message`` with ``secret_key``."""
    if _require_backend() == BACKEND_LIBOQS:
        oqs = _import_oqs()
        with oqs.Signature(algorithm, secret_key) as signer:  # type: ignore[union-attr]
            return bytes(signer.sign(message))
    return bytes(_purepy_sig(algorithm).sign(secret_key, message))


def sig_verify(
    algorithm: str, public_key: bytes, message: bytes, signature: bytes
) -> bool:
    """Verify ``signature`` over ``message``. Returns False on any rejection."""
    if _require_backend() == BACKEND_LIBOQS:
        oqs = _import_oqs()
        with oqs.Signature(algorithm) as verifier:  # type: ignore[union-attr]
            try:
                return bool(verifier.verify(message, signature, public_key))
            except Exception:
                return False
    try:
        return bool(_purepy_sig(algorithm).verify(public_key, message, signature))
    except Exception:
        return False
