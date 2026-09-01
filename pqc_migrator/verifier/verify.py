"""Functional verification that the recommended PQC primitives really work.

Nothing here is mocked: every check runs the active backend's real
key generation, encapsulation/decapsulation and signing/verification.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..models import MigrationResult, Recommendation
from ..pqc import backends

DEFAULT_MESSAGE = b"pqc-migrator functional verification vector"


def verify_kem(algorithm: str) -> dict[str, bool]:
    """Encapsulate/decapsulate round-trip plus a wrong-key negative check."""
    results: dict[str, bool] = {}
    try:
        public_key, secret_key = backends.kem_keypair(algorithm)
        ciphertext, shared_secret = backends.kem_encapsulate(algorithm, public_key)
        recovered = backends.kem_decapsulate(algorithm, secret_key, ciphertext)
        results[f"kem_roundtrip[{algorithm}]"] = recovered == shared_secret

        # Implicit rejection: a foreign key must not recover the same secret.
        _, other_secret = backends.kem_keypair(algorithm)
        wrong = backends.kem_decapsulate(algorithm, other_secret, ciphertext)
        results[f"kem_rejects_foreign_key[{algorithm}]"] = wrong != shared_secret
    except Exception as exc:  # backend missing or algorithm unsupported
        results[f"kem_roundtrip[{algorithm}]"] = False
        results[f"kem_rejects_foreign_key[{algorithm}]"] = False
        results[f"kem_error[{algorithm}]: {type(exc).__name__}"] = False
    return results


def verify_signature(algorithm: str, message: bytes = DEFAULT_MESSAGE) -> dict[str, bool]:
    """Sign/verify round-trip plus tampered-message and wrong-key negatives."""
    results: dict[str, bool] = {}
    try:
        public_key, secret_key = backends.sig_keypair(algorithm)
        signature = backends.sig_sign(algorithm, secret_key, message)
        results[f"signature_roundtrip[{algorithm}]"] = backends.sig_verify(
            algorithm, public_key, message, signature
        )
        results[f"signature_rejects_tampered_message[{algorithm}]"] = not (
            backends.sig_verify(algorithm, public_key, message + b"!", signature)
        )
        other_public, _ = backends.sig_keypair(algorithm)
        results[f"signature_rejects_wrong_key[{algorithm}]"] = not (
            backends.sig_verify(algorithm, other_public, message, signature)
        )
    except Exception as exc:
        results[f"signature_roundtrip[{algorithm}]"] = False
        results[f"signature_rejects_tampered_message[{algorithm}]"] = False
        results[f"signature_error[{algorithm}]: {type(exc).__name__}"] = False
    return results


def verify_algorithms(algorithms: list[str]) -> dict[str, bool]:
    """Verify each algorithm using the check appropriate to its family."""
    results: dict[str, bool] = {}
    for algorithm in dict.fromkeys(algorithms):
        if algorithm in backends.KEM_ALGORITHMS:
            results.update(verify_kem(algorithm))
        elif algorithm in backends.SIG_ALGORITHMS:
            results.update(verify_signature(algorithm))
        else:
            results[f"unknown_algorithm[{algorithm}]"] = False
    return results


def verify_migrated_app(
    directory: str | Path, entrypoint: str = "main.py", timeout: int = 180
) -> tuple[bool, str]:
    """Execute a migrated sample app; success means it ran with exit code 0."""
    app_dir = Path(directory)
    script = app_dir / entrypoint
    if not script.is_file():
        return False, f"{script} not found"
    try:
        completed = subprocess.run(
            [sys.executable, entrypoint],
            cwd=str(app_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"{script} timed out after {timeout}s"
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def verify_migrations(
    migrations: list[MigrationResult], timeout: int = 180
) -> dict[str, bool]:
    """Run every migrated directory that has an executable entry point."""
    results: dict[str, bool] = {}
    # A file still awaiting a protocol change cannot run yet; executing it
    # would report a failure for a limitation the migration already declared.
    review_dirs = {
        str(Path(m.migrated_file).parent) for m in migrations if m.manual_review
    }
    directories = sorted(
        {str(Path(m.migrated_file).parent) for m in migrations if m.changed}
        - review_dirs
    )
    for directory in directories:
        if not (Path(directory) / "main.py").is_file():
            continue
        passed, output = verify_migrated_app(directory, timeout=timeout)
        label = f"migrated_app_runs[{Path(directory).name}]"
        results[label] = passed
        if not passed and output:
            first_line = output.splitlines()[-1][:160]
            results[f"{label} :: {first_line}"] = False
    return results


def verify_all(
    recommendations: list[Recommendation] | None = None,
    migrations: list[MigrationResult] | None = None,
    algorithms: list[str] | None = None,
) -> dict[str, bool]:
    """Full verification pass used by ``pqc-migrator verify`` and ``run``."""
    results: dict[str, bool] = {}
    backend = backends.available_backend()
    results[f"backend_available[{backend}]"] = backend != backends.BACKEND_NONE

    targets = list(algorithms or [])
    if recommendations:
        targets += [r.pqc_algorithm for r in recommendations]
    if not targets:
        targets = ["ML-KEM-768", "ML-DSA-65"]
    results.update(verify_algorithms(targets))

    if migrations:
        results.update(verify_migrations(migrations))
    return results


def passed(results: dict[str, bool]) -> bool:
    return all(results.values())


def summary(results: dict[str, bool]) -> str:
    total = len(results)
    ok = sum(1 for value in results.values() if value)
    return f"{ok}/{total} checks passed"
