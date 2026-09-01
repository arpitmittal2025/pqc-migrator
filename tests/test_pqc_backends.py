"""PQC backends: real ML-KEM and ML-DSA round-trips through the unified interface."""

from __future__ import annotations

import pytest

from pqc_migrator.pqc import backends, benchmark

KEM = "ML-KEM-512"  # smallest parameter set keeps the suite fast
SIG = "ML-DSA-44"

pytestmark = pytest.mark.skipif(
    backends.available_backend() == backends.BACKEND_NONE,
    reason="no PQC backend installed",
)


def test_a_backend_is_detected():
    assert backends.available_backend() in (backends.BACKEND_LIBOQS, backends.BACKEND_PUREPY)


def test_backend_details_lists_supported_algorithms():
    details = backends.backend_details()
    assert KEM in details["kem_algorithms"]
    assert SIG in details["signature_algorithms"]


def test_standard_mapping_matches_fips_documents():
    assert backends.standard_for("ML-KEM-768") == "FIPS 203"
    assert backends.standard_for("ML-DSA-65") == "FIPS 204"
    assert backends.standard_for("SLH-DSA-SHA2-128s") == "FIPS 205"


def test_kem_roundtrip_recovers_the_shared_secret():
    public_key, secret_key = backends.kem_keypair(KEM)
    ciphertext, shared_secret = backends.kem_encapsulate(KEM, public_key)
    assert backends.kem_decapsulate(KEM, secret_key, ciphertext) == shared_secret
    assert len(shared_secret) == 32


def test_kem_key_and_ciphertext_sizes_match_fips_203():
    public_key, _ = backends.kem_keypair(KEM)
    ciphertext, _ = backends.kem_encapsulate(KEM, public_key)
    assert len(public_key) == 800  # ML-KEM-512 encapsulation key
    assert len(ciphertext) == 768  # ML-KEM-512 ciphertext


def test_kem_foreign_key_does_not_recover_the_secret():
    public_key, _ = backends.kem_keypair(KEM)
    ciphertext, shared_secret = backends.kem_encapsulate(KEM, public_key)
    _, other_secret = backends.kem_keypair(KEM)
    assert backends.kem_decapsulate(KEM, other_secret, ciphertext) != shared_secret


def test_signature_roundtrip_verifies():
    public_key, secret_key = backends.sig_keypair(SIG)
    signature = backends.sig_sign(SIG, secret_key, b"release-1.0")
    assert backends.sig_verify(SIG, public_key, b"release-1.0", signature)


def test_signature_rejects_tampering_and_wrong_keys():
    public_key, secret_key = backends.sig_keypair(SIG)
    signature = backends.sig_sign(SIG, secret_key, b"release-1.0")
    other_public, _ = backends.sig_keypair(SIG)
    assert not backends.sig_verify(SIG, public_key, b"release-1.1", signature)
    assert not backends.sig_verify(SIG, other_public, b"release-1.0", signature)


def test_unsupported_algorithm_raises_rather_than_faking_success():
    if backends.available_backend() != backends.BACKEND_PUREPY:
        pytest.skip("SLH-DSA is available on the liboqs backend")
    with pytest.raises(backends.UnsupportedAlgorithm):
        backends.sig_keypair("SLH-DSA-SHA2-128s")


def test_benchmark_reports_measured_timings_and_real_sizes():
    row = benchmark.benchmark_kem(KEM, runs=2)
    assert row["keygen_ms"] > 0 and row["op_ms"] > 0
    assert row["pubkey_bytes"] == 800
    assert row["sig_or_ct_bytes"] == 768
    assert row["standard"] == "FIPS 203"


def test_benchmark_includes_classical_baselines():
    table = benchmark.benchmark_all([KEM], runs=2)
    assert table["RSA-2048"]["kind"] == "classical"
    assert table["ECDSA-P256"]["kind"] == "classical"
    assert table[KEM]["kind"] == "pqc"
    # The headline comparison of the report: PQC keys are much larger.
    assert table[KEM]["pubkey_bytes"] > table["ECDSA-P256"]["pubkey_bytes"]
