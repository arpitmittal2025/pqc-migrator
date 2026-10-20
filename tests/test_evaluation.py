"""The detection benchmark, and the detector behaviour it drove."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pqc_migrator.detector.scanner import scan_source

EVAL_DIR = Path(__file__).resolve().parents[1] / "evaluation"
sys.path.insert(0, str(EVAL_DIR))


# --------------------------------------------------------------------------
# Detector behaviour the benchmark exposed
# --------------------------------------------------------------------------

def test_aliased_import_is_resolved():
    """A renamed import used to be invisible to the pattern index."""
    source = (
        "from cryptography.hazmat.primitives.asymmetric import rsa as asym_rsa\n"
        "key = asym_rsa.generate_private_key(public_exponent=65537, key_size=2048)\n"
    )
    findings = scan_source(source, "aliased.py")
    assert [f.matched for f in findings] == ["rsa.generate_private_key"]
    assert findings[0].library == "cryptography"


def test_from_import_of_the_function_itself_is_resolved():
    source = (
        "from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key\n"
        "key = generate_private_key(public_exponent=65537, key_size=2048)\n"
    )
    assert [f.matched for f in scan_source(source, "direct.py")] == [
        "rsa.generate_private_key"
    ]


def test_crypto_names_in_strings_are_not_flagged():
    """The regex sweep used to fire on docstrings and string constants."""
    source = (
        '"""Replace rsa.generate_private_key with ML-KEM."""\n'
        'NOTE = "we used ec.generate_private_key and dh.generate_parameters"\n'
        "# dh.generate_parameters was the old group\n"
    )
    assert scan_source(source, "docs.py") == []


def test_regex_fallback_still_covers_unparsable_files():
    source = "def broken(\n    key = rsa.generate_private_key(key_size=2048)\n"
    findings = scan_source(source, "broken.py")
    assert findings and all(f.detector == "regex" for f in findings)


def test_ed25519_is_detected_as_vulnerable_signature():
    source = (
        "from cryptography.hazmat.primitives.asymmetric import ed25519\n"
        "key = ed25519.Ed25519PrivateKey.generate()\n"
    )
    findings = scan_source(source, "eddsa.py")
    assert [(f.algorithm, f.purpose) for f in findings] == [("ecc", "signature")]


def test_x25519_is_detected_as_key_exchange():
    source = (
        "from cryptography.hazmat.primitives.asymmetric import x25519\n"
        "key = x25519.X25519PrivateKey.generate()\n"
    )
    findings = scan_source(source, "xdh.py")
    assert [(f.algorithm, f.purpose) for f in findings] == [("ecc", "key_exchange")]


def test_ec_key_used_only_for_agreement_is_key_exchange():
    """An EC key feeding ECDH is key exchange, not signing."""
    source = (
        "from cryptography.hazmat.primitives.asymmetric import ec\n"
        "key = ec.generate_private_key(ec.SECP256R1())\n"
        "shared = key.exchange(ec.ECDH(), peer)\n"
    )
    assert {f.purpose for f in scan_source(source, "ecdh.py")} == {"key_exchange"}


def test_ec_key_used_for_signing_stays_signature():
    source = (
        "from cryptography.hazmat.primitives import hashes\n"
        "from cryptography.hazmat.primitives.asymmetric import ec\n"
        "key = ec.generate_private_key(ec.SECP256R1())\n"
        "sig = key.sign(data, ec.ECDSA(hashes.SHA256()))\n"
    )
    assert {f.purpose for f in scan_source(source, "ecdsa.py")} == {"signature"}


# --------------------------------------------------------------------------
# The benchmark itself must stay reproducible
# --------------------------------------------------------------------------

def test_benchmark_reproduces_the_reported_scores():
    """Guards the numbers quoted in the paper against silent regression."""
    build_corpus = pytest.importorskip("build_corpus")
    evaluate = pytest.importorskip("evaluate")

    manifest = build_corpus.build()
    assert manifest["labels"], "corpus must carry ground-truth labels"

    results = evaluate.evaluate()
    head = results["headline"]
    assert head["precision"] == 1.0
    assert head["recall_in_scope"] == 1.0
    assert results["purpose_classification"]["accuracy"] == 1.0
    assert results["clean_files"]["with_false_alarms"] == 0
    # The extended set is adversarial by construction and is expected to fail.
    assert head["recall_extended"] < 1.0


def test_clean_files_produce_no_findings():
    import build_corpus

    build_corpus.build()
    for name in ("n01_symmetric_only.py", "n05_plain_application.py",
                 "n06_modern_symmetric.py"):
        source = (EVAL_DIR / "corpus" / name).read_text(encoding="utf-8")
        assert scan_source(source, name) == [], f"{name} should be clean"
