"""Timing and size benchmarks: classical baselines vs the PQC replacements.

Every number in the report comes from this module actually running the
primitive on the machine generating the report -- there are no stored figures.
"""

from __future__ import annotations

import os
import statistics
import time
from typing import Any, Callable

from . import backends

DEFAULT_RUNS = 20
DEFAULT_KEYGEN_RUNS = 5
BENCH_MESSAGE = b"pqc-migrator benchmark message"


def _time_ms(func: Callable[[], Any], runs: int) -> tuple[float, Any]:
    """Median wall-clock milliseconds over ``runs`` calls, plus the last result."""
    samples: list[float] = []
    result: Any = None
    for _ in range(max(1, runs)):
        start = time.perf_counter()
        result = func()
        samples.append((time.perf_counter() - start) * 1000.0)
    return round(statistics.median(samples), 4), result


def benchmark_kem(algorithm: str, runs: int = DEFAULT_RUNS) -> dict[str, Any]:
    """Time ML-KEM keygen / encapsulation / decapsulation and record sizes."""
    keygen_ms, keypair = _time_ms(lambda: backends.kem_keypair(algorithm), runs)
    public_key, secret_key = keypair
    encaps_ms, encapsulated = _time_ms(
        lambda: backends.kem_encapsulate(algorithm, public_key), runs
    )
    ciphertext, shared_secret = encapsulated
    decaps_ms, _ = _time_ms(
        lambda: backends.kem_decapsulate(algorithm, secret_key, ciphertext), runs
    )
    return {
        "kind": "pqc",
        "family": "ML-KEM",
        "standard": backends.standard_for(algorithm),
        "nist_level": backends.NIST_LEVELS.get(algorithm),
        "operation": "encapsulate",
        "keygen_ms": keygen_ms,
        "op_ms": encaps_ms,
        "inverse_op_ms": decaps_ms,
        "pubkey_bytes": len(public_key),
        "secretkey_bytes": len(secret_key),
        "sig_or_ct_bytes": len(ciphertext),
        "shared_secret_bytes": len(shared_secret),
        "runs": runs,
    }


def benchmark_signature(algorithm: str, runs: int = DEFAULT_RUNS) -> dict[str, Any]:
    """Time signature keygen / sign / verify and record sizes."""
    keygen_ms, keypair = _time_ms(lambda: backends.sig_keypair(algorithm), runs)
    public_key, secret_key = keypair
    sign_ms, signature = _time_ms(
        lambda: backends.sig_sign(algorithm, secret_key, BENCH_MESSAGE), runs
    )
    verify_ms, _ = _time_ms(
        lambda: backends.sig_verify(algorithm, public_key, BENCH_MESSAGE, signature),
        runs,
    )
    return {
        "kind": "pqc",
        "family": algorithm.split("-")[0] + "-DSA" if "DSA" in algorithm else algorithm,
        "standard": backends.standard_for(algorithm),
        "nist_level": backends.NIST_LEVELS.get(algorithm),
        "operation": "sign",
        "keygen_ms": keygen_ms,
        "op_ms": sign_ms,
        "inverse_op_ms": verify_ms,
        "pubkey_bytes": len(public_key),
        "secretkey_bytes": len(secret_key),
        "sig_or_ct_bytes": len(signature),
        "runs": runs,
    }


# --------------------------------------------------------------------------
# Classical baselines (measured, not quoted)
# --------------------------------------------------------------------------

def benchmark_rsa(key_size: int = 2048, runs: int = DEFAULT_KEYGEN_RUNS) -> dict[str, Any]:
    """RSA-OAEP key transport baseline using the ``cryptography`` package."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    keygen_ms, private_key = _time_ms(
        lambda: rsa.generate_private_key(public_exponent=65537, key_size=key_size),
        max(1, min(runs, 5)),
    )
    public_key = private_key.public_key()
    oaep = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    )
    session_key = os.urandom(32)
    encrypt_ms, ciphertext = _time_ms(
        lambda: public_key.encrypt(session_key, oaep), DEFAULT_RUNS
    )
    decrypt_ms, _ = _time_ms(
        lambda: private_key.decrypt(ciphertext, oaep), DEFAULT_RUNS
    )
    pubkey_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "kind": "classical",
        "family": "RSA-OAEP",
        "standard": "PKCS#1 v2.2",
        "nist_level": None,
        "operation": "encrypt",
        "keygen_ms": keygen_ms,
        "op_ms": encrypt_ms,
        "inverse_op_ms": decrypt_ms,
        "pubkey_bytes": len(pubkey_der),
        "secretkey_bytes": None,
        "sig_or_ct_bytes": len(ciphertext),
        "runs": DEFAULT_RUNS,
        "note": "quantum-vulnerable (Shor)",
    }


def benchmark_ecdsa(runs: int = DEFAULT_RUNS) -> dict[str, Any]:
    """ECDSA over P-256 signature baseline."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    keygen_ms, private_key = _time_ms(
        lambda: ec.generate_private_key(ec.SECP256R1()), runs
    )
    public_key = private_key.public_key()
    sign_ms, signature = _time_ms(
        lambda: private_key.sign(BENCH_MESSAGE, ec.ECDSA(hashes.SHA256())), runs
    )
    verify_ms, _ = _time_ms(
        lambda: public_key.verify(signature, BENCH_MESSAGE, ec.ECDSA(hashes.SHA256())),
        runs,
    )
    pubkey_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "kind": "classical",
        "family": "ECDSA-P256",
        "standard": "FIPS 186-5",
        "nist_level": None,
        "operation": "sign",
        "keygen_ms": keygen_ms,
        "op_ms": sign_ms,
        "inverse_op_ms": verify_ms,
        "pubkey_bytes": len(pubkey_der),
        "secretkey_bytes": None,
        "sig_or_ct_bytes": len(signature),
        "runs": runs,
        "note": "quantum-vulnerable (Shor)",
    }


def benchmark_algorithms(
    algorithms: list[str], runs: int = DEFAULT_RUNS
) -> dict[str, dict[str, Any]]:
    """Benchmark the PQC algorithms the recommender selected."""
    results: dict[str, dict[str, Any]] = {}
    for algorithm in dict.fromkeys(algorithms):
        try:
            if algorithm in backends.KEM_ALGORITHMS:
                results[algorithm] = benchmark_kem(algorithm, runs)
            elif algorithm in backends.SIG_ALGORITHMS:
                results[algorithm] = benchmark_signature(algorithm, runs)
        except Exception as exc:
            results[algorithm] = {"kind": "pqc", "error": f"{type(exc).__name__}: {exc}"}
    return results


def benchmark_all(
    algorithms: list[str] | None = None,
    runs: int = DEFAULT_RUNS,
    include_classical: bool = True,
) -> dict[str, dict[str, Any]]:
    """Full benchmark table: PQC algorithms plus classical baselines."""
    algorithms = algorithms or ["ML-KEM-768", "ML-DSA-65"]
    results = benchmark_algorithms(algorithms, runs)
    if include_classical:
        try:
            results["RSA-2048"] = benchmark_rsa()
            results["ECDSA-P256"] = benchmark_ecdsa(runs)
        except Exception as exc:  # pragma: no cover - cryptography always present
            results["classical_error"] = {"error": f"{type(exc).__name__}: {exc}"}
    return results


def comparison_rows(benchmark: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the benchmark dict into report-friendly rows."""
    rows = []
    for algorithm, data in benchmark.items():
        if "error" in data:
            rows.append({"algorithm": algorithm, "error": data["error"]})
            continue
        rows.append(
            {
                "algorithm": algorithm,
                "kind": data.get("kind"),
                "standard": data.get("standard"),
                "operation": data.get("operation"),
                "keygen_ms": data.get("keygen_ms"),
                "op_ms": data.get("op_ms"),
                "inverse_op_ms": data.get("inverse_op_ms"),
                "pubkey_bytes": data.get("pubkey_bytes"),
                "sig_or_ct_bytes": data.get("sig_or_ct_bytes"),
            }
        )
    return rows
