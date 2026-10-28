"""Pipeline engine shared by the local dev server and the Vercel functions.

Keeping this separate means the code exercised locally is exactly the code that
runs in production; the HTTP handlers do nothing but parse and serialise.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pqc_migrator.analyzer.static_analysis import analyze_project  # noqa: E402
from pqc_migrator.context.context import AppContext  # noqa: E402
from pqc_migrator.detector.scanner import scan_source  # noqa: E402
from pqc_migrator.migrator.migrate import migrate_path, summarize  # noqa: E402
from pqc_migrator.pqc import backends, benchmark as bench  # noqa: E402
from pqc_migrator.recommender.recommend import (  # noqa: E402
    algorithms_used,
    recommend_all,
)
from pqc_migrator.verifier import verify as verifier  # noqa: E402

SAMPLES_DIR = ROOT / "samples"
BENCH_RUNS = 5
MAX_SOURCE_BYTES = 120_000

# Executing migrated output is the strongest evidence the pipeline works, but
# running code that arrived over HTTP would be a remote-execution hole. It is
# therefore done only for the sample applications shipped with the project.
TRUSTED_SAMPLES = {"app_rsa", "app_ecdsa", "app_dh"}


def _read_sample(name: str) -> dict[str, str]:
    directory = SAMPLES_DIR / name
    if not directory.is_dir():
        raise ValueError(f"unknown sample: {name}")
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(directory.iterdir())
        if path.suffix in (".py", ".json")
    }


def list_samples() -> dict:
    """Sample applications offered in the UI."""
    described = {
        "app_rsa": {
            "title": "RSA key transport",
            "blurb": "Wraps a session key with RSA-OAEP across two modules.",
            "expect": "4 findings → ML-KEM-768 (FIPS 203)",
        },
        "app_ecdsa": {
            "title": "ECDSA release signing",
            "blurb": "Signs release artifacts with ECDSA over P-256, with its own pqc.config.json.",
            "expect": "4 findings → ML-DSA-65 (FIPS 204)",
        },
        "app_dh": {
            "title": "Diffie-Hellman handshake",
            "blurb": "Finite-field DH key agreement. Demonstrates the case that cannot be fully automated.",
            "expect": "1 finding → ML-KEM-768, flagged for manual review",
        },
    }
    out = []
    for name, meta in described.items():
        try:
            files = _read_sample(name)
        except ValueError:
            continue
        out.append({"id": name, **meta, "files": files})
    return {"samples": out}


def backend_info() -> dict:
    details = backends.backend_details()
    return {
        "backend": details["backend"],
        "note": details["note"],
        "kem": list(details["kem_algorithms"]),
        "signature": list(details["signature_algorithms"]),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


def _write_project(directory: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        safe = Path(name).name  # never let a path escape the sandbox
        if not safe:
            continue
        (directory / safe).write_text(text, encoding="utf-8")


def _execute_migrated(directory: Path, timeout: int = 25) -> tuple[bool, str]:
    """Run a migrated sample app with the framework importable."""
    import os
    import subprocess

    entry = directory / "main.py"
    if not entry.is_file():
        return False, "no main.py"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    try:
        completed = subprocess.run(
            [sys.executable, "main.py"],
            cwd=str(directory), env=environment,
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as exc:  # subprocess unavailable in some sandboxes
        return False, f"{type(exc).__name__}: {exc}"
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def run_pipeline(
    files: dict[str, str],
    *,
    security_level: int = 3,
    signature_scheme: str = "ML-DSA",
    sample: str | None = None,
    run_benchmark: bool = True,
) -> dict:
    """Detect, recommend, migrate, verify and benchmark one small project."""
    started = time.perf_counter()

    files = {k: v for k, v in files.items() if isinstance(v, str)}
    if not files:
        raise ValueError("no source files supplied")
    total = sum(len(v.encode("utf-8")) for v in files.values())
    if total > MAX_SOURCE_BYTES:
        raise ValueError(f"source too large ({total} bytes; limit {MAX_SOURCE_BYTES})")

    context = AppContext(
        security_level=max(1, min(5, int(security_level))),
        prefer_signature_scheme=(
            "SLH-DSA" if str(signature_scheme).upper() == "SLH-DSA" else "ML-DSA"
        ),
        source="request",
    )

    workspace = Path(tempfile.mkdtemp(prefix="pqcweb_"))
    try:
        source_dir = workspace / "src"
        source_dir.mkdir()
        _write_project(source_dir, files)

        # ---------------------------------------------------------- detect
        findings = []
        for path in sorted(source_dir.glob("*.py")):
            findings.extend(
                scan_source(path.read_text(encoding="utf-8"), path.name)
            )
        findings.sort(key=lambda f: (f.file, f.line, f.matched))

        # ------------------------------------------------------ recommend
        recommendations = recommend_all(findings, context)
        algorithms = algorithms_used(recommendations)

        # -------------------------------------------------------- migrate
        # migrate_path reads findings by file path, so re-scan through it.
        from pqc_migrator.detector.scanner import scan_path

        disk_findings = scan_path(source_dir)
        disk_recommendations = recommend_all(disk_findings, context)
        out_dir = workspace / "migrated"
        migrations = migrate_path(
            source_dir, out_dir, disk_recommendations, disk_findings
        )
        stats = summarize(migrations)

        migrated_files = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(out_dir.glob("*.py"))
            if path.name != "pqc_shim.py"
        }

        # --------------------------------------------------------- verify
        verification = verifier.verify_all(
            recommendations=disk_recommendations or recommendations
        )
        execution = {"attempted": False, "passed": False, "output": "",
                     "reason": "Execution runs only for the bundled samples."}
        if sample in TRUSTED_SAMPLES and stats.get("files_changed"):
            needs_review = any(m.manual_review for m in migrations)
            if needs_review:
                execution["reason"] = (
                    "Skipped: this migration is flagged for manual review, so the "
                    "framework does not claim it runs."
                )
            else:
                passed, output = _execute_migrated(out_dir)
                execution = {"attempted": True, "passed": passed,
                             "output": output[-1500:], "reason": ""}
                verification[f"migrated_app_runs[{sample}]"] = passed

        # ------------------------------------------------------ benchmark
        benchmark = {}
        if run_benchmark:
            benchmark = bench.benchmark_all(algorithms or None, runs=BENCH_RUNS)

        analysis = analyze_project(source_dir)
        analysis.pop("imports_by_file", None)
        analysis["crypto_files"] = {
            Path(k).name: v for k, v in analysis.get("crypto_files", {}).items()
        }

        return {
            "ok": True,
            "backend": backend_info(),
            "context": context.to_dict(),
            "findings": [f.to_dict() | {"file": Path(f.file).name} for f in findings],
            "recommendations": [
                r.to_dict() | {"finding": r.finding.to_dict() | {"file": Path(r.finding.file).name}}
                for r in recommendations
            ],
            "migrations": [
                m.to_dict() | {
                    "original_file": Path(m.original_file).name,
                    "migrated_file": Path(m.migrated_file).name,
                }
                for m in migrations
            ],
            "stats": stats,
            "migrated_files": migrated_files,
            "verification": verification,
            "execution": execution,
            "benchmark": benchmark,
            "analysis": analysis,
            "algorithms": algorithms,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def handle(payload: dict) -> dict:
    """Dispatch a request body to the right operation."""
    action = payload.get("action", "analyze")
    if action == "samples":
        return list_samples()
    if action == "backend":
        return backend_info()

    sample = payload.get("sample")
    if sample:
        files = _read_sample(str(sample))
    else:
        code = payload.get("code") or ""
        if not code.strip():
            raise ValueError("paste some Python, or choose a sample")
        files = {str(payload.get("filename") or "app.py"): code}

    return run_pipeline(
        files,
        security_level=payload.get("security_level", 3),
        signature_scheme=payload.get("signature_scheme", "ML-DSA"),
        sample=str(sample) if sample else None,
        run_benchmark=bool(payload.get("benchmark", True)),
    )


def handle_json(raw: bytes | str) -> tuple[int, dict]:
    """Parse, dispatch and map errors to status codes."""
    try:
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            raise ValueError("body must be a JSON object")
    except json.JSONDecodeError as exc:
        return 400, {"ok": False, "error": f"invalid JSON: {exc}"}

    try:
        return 200, handle(payload)
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except Exception as exc:  # surface the reason rather than a blank 500
        return 500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
