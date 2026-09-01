"""Migrator: rewrite rules, migrated output, and honest reporting of what changed."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from pqc_migrator.context.context import AppContext
from pqc_migrator.detector.scanner import scan_path
from pqc_migrator.migrator import rules as R
from pqc_migrator.migrator.migrate import migrate_path, summarize
from pqc_migrator.recommender.recommend import recommend_all

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def run_pipeline(sample: str, out_dir: Path, level: int = 3):
    source = SAMPLES / sample
    findings = scan_path(source)
    recommendations = recommend_all(findings, AppContext(security_level=level))
    results = migrate_path(source, out_dir, recommendations, findings)
    return findings, results


def test_replace_call_handles_nested_parentheses():
    source = "key = ec.generate_private_key(ec.SECP256R1())\n"
    out, hits = R.replace_call(source, "ec.generate_private_key", 'algorithm="ML-DSA-65"')
    assert hits == 1
    assert out.strip() == 'key = ec.generate_private_key(algorithm="ML-DSA-65")'


def test_import_rule_only_rewrites_shimmed_names():
    shimmed, hits = R._rule_imports(
        "from cryptography.hazmat.primitives.asymmetric import rsa\n", R.RuleOptions()
    )
    assert hits == 1 and "from pqc_shim import rsa" in shimmed

    untouched, hits = R._rule_imports(
        "from cryptography.hazmat.primitives.kdf.hkdf import HKDF\n", R.RuleOptions()
    )
    assert hits == 0 and "cryptography" in untouched


def test_rsa_sample_is_rewritten_to_ml_kem(tmp_path):
    findings, results = run_pipeline("app_rsa", tmp_path / "migrated")
    migrated = (tmp_path / "migrated" / "keygen.py").read_text(encoding="utf-8")

    assert 'rsa.generate_private_key(algorithm="ML-KEM-768")' in migrated
    assert "from pqc_shim import rsa" in migrated
    code = [line for line in migrated.splitlines() if not line.startswith("#")]
    assert not any("cryptography" in line for line in code)
    assert all(r.changed for r in results if r.finding)
    assert summarize(results)["migrated_findings"] == len(findings)


def test_ecdsa_sample_is_rewritten_to_ml_dsa(tmp_path):
    _, results = run_pipeline("app_ecdsa", tmp_path / "migrated")
    migrated = (tmp_path / "migrated" / "signer.py").read_text(encoding="utf-8")

    assert 'ec.generate_private_key(algorithm="ML-DSA-65")' in migrated
    assert "from pqc_shim import ec" in migrated
    assert all(r.changed for r in results if r.finding)


def test_originals_are_never_modified(tmp_path):
    before = (SAMPLES / "app_rsa" / "keygen.py").read_text(encoding="utf-8")
    run_pipeline("app_rsa", tmp_path / "migrated")
    assert (SAMPLES / "app_rsa" / "keygen.py").read_text(encoding="utf-8") == before


def test_migration_writes_the_runtime_shim_next_to_the_code(tmp_path):
    run_pipeline("app_rsa", tmp_path / "migrated")
    assert (tmp_path / "migrated" / "pqc_shim.py").is_file()


def test_banner_records_the_rules_that_fired(tmp_path):
    run_pipeline("app_rsa", tmp_path / "migrated")
    migrated = (tmp_path / "migrated" / "keygen.py").read_text(encoding="utf-8")
    assert "migrated by pqc-migrator" in migrated
    assert "rsa-keygen-to-ml-kem" in migrated
    assert "TODO(project-II)" in migrated


def test_dh_exchange_is_flagged_for_manual_review(tmp_path):
    _, results = run_pipeline("app_dh", tmp_path / "migrated")
    migrated = (tmp_path / "migrated" / "handshake.py").read_text(encoding="utf-8")

    assert 'dh.generate_parameters(algorithm="ML-KEM-768")' in migrated
    assert "TODO(pqc-migrator): DH exchange" in migrated
    assert any(r.manual_review for r in results)
    assert summarize(results)["manual_review"] == 1


def test_unsupported_pattern_is_reported_as_unmigrated(tmp_path):
    project = tmp_path / "legacy"
    project.mkdir()
    (project / "app.py").write_text(
        "from Crypto.PublicKey import RSA\n\nkey = RSA.generate(2048)\n", encoding="utf-8"
    )
    findings = scan_path(project)
    results = migrate_path(
        project, tmp_path / "out", recommend_all(findings, AppContext()), findings
    )
    assert results and not any(r.changed for r in results)
    assert "No rewrite rule" in results[0].notes


def test_migrated_rsa_app_runs_with_real_pqc(tmp_path):
    run_pipeline("app_rsa", tmp_path / "migrated")
    completed = subprocess.run(
        [sys.executable, "main.py"],
        cwd=str(tmp_path / "migrated"),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert "session key established" in completed.stdout


def test_migrated_ecdsa_app_runs_with_real_pqc(tmp_path):
    run_pipeline("app_ecdsa", tmp_path / "migrated")
    completed = subprocess.run(
        [sys.executable, "main.py"],
        cwd=str(tmp_path / "migrated"),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert "signature valid: True" in completed.stdout


def test_shim_key_serialisation_roundtrips(tmp_path):
    """The migrated keygen module can still save and load a private key."""
    run_pipeline("app_rsa", tmp_path / "migrated")
    script = tmp_path / "migrated" / "check_serialisation.py"
    script.write_text(
        "from keygen import generate_keypair, save_private_key, load_private_key\n"
        "from secure_channel import wrap_session_key, unwrap_session_key\n"
        "private_key, public_key = generate_keypair()\n"
        "save_private_key(private_key, 'key.bin')\n"
        "restored = load_private_key('key.bin')\n"
        "blob = wrap_session_key(public_key, b'0' * 32)\n"
        "assert unwrap_session_key(restored, blob) == b'0' * 32\n"
        "print('serialisation ok')\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, script.name],
        cwd=str(tmp_path / "migrated"),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert "serialisation ok" in completed.stdout
