"""Verifier: round-trip checks, negative checks, and migrated-app execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from pqc_migrator.models import MigrationResult
from pqc_migrator.pqc import backends
from pqc_migrator.verifier import verify as verifier

KEM = "ML-KEM-512"
SIG = "ML-DSA-44"

pytestmark = pytest.mark.skipif(
    backends.available_backend() == backends.BACKEND_NONE,
    reason="no PQC backend installed",
)


def test_kem_checks_pass_for_a_supported_algorithm():
    results = verifier.verify_kem(KEM)
    assert results[f"kem_roundtrip[{KEM}]"]
    assert results[f"kem_rejects_foreign_key[{KEM}]"]


def test_signature_checks_pass_for_a_supported_algorithm():
    results = verifier.verify_signature(SIG)
    assert results[f"signature_roundtrip[{SIG}]"]
    assert results[f"signature_rejects_tampered_message[{SIG}]"]
    assert results[f"signature_rejects_wrong_key[{SIG}]"]


def test_unsupported_algorithm_is_reported_as_failure_not_success():
    if backends.available_backend() != backends.BACKEND_PUREPY:
        pytest.skip("SLH-DSA is available on the liboqs backend")
    results = verifier.verify_signature("SLH-DSA-SHA2-128s")
    assert not any(results.values())


def test_unknown_algorithm_never_silently_passes():
    results = verifier.verify_algorithms(["NOT-A-REAL-ALGORITHM"])
    assert results == {"unknown_algorithm[NOT-A-REAL-ALGORITHM]": False}


def test_verify_all_reports_the_active_backend():
    results = verifier.verify_all(algorithms=[KEM])
    backend = backends.available_backend()
    assert results[f"backend_available[{backend}]"] is True
    assert verifier.passed(results)
    assert verifier.summary(results).endswith("checks passed")


def test_summary_counts_failures():
    assert verifier.summary({"a": True, "b": False}) == "1/2 checks passed"
    assert not verifier.passed({"a": True, "b": False})


def test_migrated_app_execution_is_checked(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "main.py").write_text("print('ok')\n", encoding="utf-8")
    passed, output = verifier.verify_migrated_app(app)
    assert passed and output == "ok"


def test_failing_migrated_app_is_reported_as_failure(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "main.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
    passed, _ = verifier.verify_migrated_app(app)
    assert not passed


def test_manual_review_migrations_are_not_executed(tmp_path):
    """A file awaiting a protocol change must not be run and marked failed."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "main.py").write_text("raise RuntimeError('handshake incomplete')\n", encoding="utf-8")
    migration = MigrationResult(
        finding=None,
        original_file="handshake.py",
        migrated_file=str(app / "handshake.py"),
        changed=True,
        notes="needs protocol change",
        manual_review=True,
    )
    assert verifier.verify_migrations([migration]) == {}


def test_migrated_app_without_review_flag_is_executed(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "main.py").write_text("print('ran')\n", encoding="utf-8")
    migration = MigrationResult(
        finding=None,
        original_file="x.py",
        migrated_file=str(app / "x.py"),
        changed=True,
        notes="",
    )
    results = verifier.verify_migrations([migration])
    assert results == {f"migrated_app_runs[{Path(app).name}]": True}
