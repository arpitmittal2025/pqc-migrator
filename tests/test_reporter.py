"""Reporter and analyzer: report assembly, rendering, and the end-to-end CLI run."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pqc_migrator.analyzer.static_analysis import analyze_project
from pqc_migrator.context.context import AppContext
from pqc_migrator.detector.scanner import scan_path
from pqc_migrator.migrator.migrate import migrate_path
from pqc_migrator.recommender.recommend import algorithms_used, recommend_all
from pqc_migrator.reporter import report as reporter

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def build(sample: str, tmp_path: Path):
    source = SAMPLES / sample
    findings = scan_path(source)
    recommendations = recommend_all(findings, AppContext(security_level=3))
    migrations = migrate_path(source, tmp_path / "migrated", recommendations, findings)
    return reporter.build_report(
        target=str(source),
        findings=findings,
        recommendations=recommendations,
        migrations=migrations,
        verification={"kem_roundtrip[ML-KEM-768]": True, "example_failure": False},
        benchmark={
            "ML-KEM-768": {
                "kind": "pqc", "standard": "FIPS 203", "operation": "encapsulate",
                "keygen_ms": 1.0, "op_ms": 1.0, "pubkey_bytes": 1184,
                "sig_or_ct_bytes": 1088,
            }
        },
        analysis=analyze_project(source),
        context=AppContext(security_level=3).to_dict(),
    )


def test_analyzer_flags_files_and_libraries_importing_crypto():
    analysis = analyze_project(SAMPLES / "app_rsa")
    assert analysis["python_files"] == 3
    assert analysis["files_importing_crypto"] == 2
    assert "cryptography" in analysis["library_usage"]
    assert "cryptography" in analysis["vulnerable_dependencies"]


def test_summary_stats_count_findings_and_checks(tmp_path):
    report = build("app_rsa", tmp_path)
    stats = reporter.summary_stats(report)
    assert stats["findings"] == len(report.findings)
    assert stats["files_affected"] == 2
    assert stats["checks_run"] == 2 and stats["checks_passed"] == 1
    assert stats["all_checks_passed"] is False


def test_json_report_is_valid_and_complete(tmp_path):
    report = build("app_rsa", tmp_path)
    path = reporter.write_json(report, tmp_path / "report.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["target"].endswith("app_rsa")
    assert payload["backend"] in ("liboqs", "purepy")
    assert len(payload["findings"]) == len(report.findings)
    assert payload["recommendations"][0]["pqc_algorithm"] == "ML-KEM-768"
    assert payload["summary"]["findings"] == len(report.findings)
    assert "manual_review" in payload["migrations"][0]


def test_markdown_report_contains_every_section(tmp_path):
    markdown = reporter.render_markdown(build("app_rsa", tmp_path))
    for heading in (
        "# PQC Migration Report",
        "## 1. Findings",
        "## 2. Recommendations",
        "## 3. Migrations",
        "## 4. Verification",
        "## 5. Benchmark",
        "## 6. Dependency analysis",
    ):
        assert heading in markdown
    assert "ML-KEM-768" in markdown
    assert "PASS" in markdown and "FAIL" in markdown


def test_html_report_renders(tmp_path):
    html = reporter.render_html(build("app_rsa", tmp_path))
    assert "<!doctype html>" in html.lower()
    assert "PQC Migration Report" in html
    assert "ML-KEM-768" in html


def test_write_all_produces_three_files(tmp_path):
    written = reporter.write_all(build("app_rsa", tmp_path), tmp_path / "reports")
    assert set(written) == {"json", "markdown", "html"}
    for path in written.values():
        assert Path(path).is_file() and Path(path).stat().st_size > 0


def test_full_cli_pipeline_runs_on_the_rsa_sample(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "pqc_migrator.cli", "run", str(SAMPLES / "app_rsa"),
         "-o", str(tmp_path / "out"), "--runs", "2"],
        capture_output=True,
        text=True,
        timeout=600,
        encoding="utf-8",
        errors="replace",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (tmp_path / "out" / "reports" / "report.json").is_file()
    assert (tmp_path / "out" / "reports" / "report.md").is_file()
    assert (tmp_path / "out" / "reports" / "report.html").is_file()
    assert (tmp_path / "out" / "migrated" / "keygen.py").is_file()

    payload = json.loads((tmp_path / "out" / "reports" / "report.json").read_text(encoding="utf-8"))
    assert payload["summary"]["all_checks_passed"] is True
    assert algorithms_used([]) == []
