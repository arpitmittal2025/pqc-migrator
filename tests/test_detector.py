"""Detector: AST matching, purpose classification, library attribution, regex fallback."""

from __future__ import annotations

from pathlib import Path

from pqc_migrator.detector import patterns
from pqc_migrator.detector.scanner import dotted_name, scan_path, scan_source

SAMPLES = Path(__file__).resolve().parents[1] / "samples"

RSA_ENCRYPT_SOURCE = """
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
blob = key.public_key().encrypt(
    b"secret",
    padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                 algorithm=hashes.SHA256(), label=None),
)
"""

RSA_SIGN_SOURCE = """
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
sig = key.sign(b"msg", padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
               salt_length=32), hashes.SHA256())
"""

PYCRYPTODOME_SOURCE = """
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP

key = RSA.generate(2048)
cipher = PKCS1_OAEP.new(key)
"""


def test_dotted_name_flattens_attribute_chains():
    import ast

    call = ast.parse("a.b.c(1)").body[0].value
    assert dotted_name(call.func) == "a.b.c"


def test_detects_rsa_encryption_as_kem():
    findings = scan_source(RSA_ENCRYPT_SOURCE, "enc.py")
    matched = {f.matched for f in findings}
    assert "rsa.generate_private_key" in matched
    assert "padding.OAEP" in matched
    assert all(f.algorithm == "rsa" for f in findings)
    assert {f.purpose for f in findings} == {"kem"}


def test_rsa_keygen_reclassified_as_signature_when_only_signing():
    findings = scan_source(RSA_SIGN_SOURCE, "sign.py")
    keygen = next(f for f in findings if f.matched == "rsa.generate_private_key")
    assert keygen.purpose == "signature"


def test_library_attribution_uses_imports():
    findings = scan_source(PYCRYPTODOME_SOURCE, "legacy.py")
    assert {f.library for f in findings} == {"pycryptodome"}
    assert {f.matched for f in findings} >= {"RSA.generate", "PKCS1_OAEP.new"}


def test_regex_fallback_catches_unparsable_files():
    broken = "def oops(\nkey = rsa.generate_private_key(key_size=2048)\n"
    findings = scan_source(broken, "broken.py")
    assert findings, "regex fallback should still report a finding"
    assert all(f.detector == "regex" for f in findings)


def test_findings_are_not_duplicated_across_detectors():
    findings = scan_source(RSA_ENCRYPT_SOURCE, "enc.py")
    keys = [f.key() for f in findings]
    assert len(keys) == len(set(keys))


def test_scans_all_three_sample_apps():
    rsa_findings = scan_path(SAMPLES / "app_rsa")
    ecdsa_findings = scan_path(SAMPLES / "app_ecdsa")
    dh_findings = scan_path(SAMPLES / "app_dh")

    assert {f.algorithm for f in rsa_findings} == {"rsa"}
    assert {f.algorithm for f in ecdsa_findings} == {"ecc"}
    assert {f.algorithm for f in dh_findings} == {"dh"}
    assert {f.purpose for f in ecdsa_findings} == {"signature"}
    assert {f.purpose for f in dh_findings} == {"key_exchange"}


def test_pattern_lookup_matches_longest_suffix():
    assert patterns.lookup("cryptography.rsa.generate_private_key") is not None
    assert patterns.lookup("json.dumps") is None


def test_line_numbers_and_snippets_are_populated():
    findings = scan_source(RSA_ENCRYPT_SOURCE, "enc.py")
    keygen = next(f for f in findings if f.matched == "rsa.generate_private_key")
    assert keygen.line == 5
    assert "generate_private_key" in keygen.snippet
