"""Assemble the Report object and render it as JSON, Markdown and HTML."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import Finding, MigrationResult, Recommendation, Report
from ..pqc import backends

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "report.html.j2"


def build_report(
    target: str,
    findings: list[Finding] | None = None,
    recommendations: list[Recommendation] | None = None,
    migrations: list[MigrationResult] | None = None,
    verification: dict[str, bool] | None = None,
    benchmark: dict[str, dict[str, Any]] | None = None,
    analysis: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> Report:
    return Report(
        target=str(target),
        backend=backends.available_backend(),
        findings=findings or [],
        recommendations=recommendations or [],
        migrations=migrations or [],
        verification=verification or {},
        benchmark=benchmark or {},
        analysis=analysis or {},
        context=context or {},
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )


def summary_stats(report: Report) -> dict[str, Any]:
    """Headline numbers shown at the top of every rendering."""
    by_algorithm: dict[str, int] = {}
    for finding in report.findings:
        by_algorithm[finding.algorithm] = by_algorithm.get(finding.algorithm, 0) + 1
    checks = report.verification
    return {
        "findings": len(report.findings),
        "files_affected": len({f.file for f in report.findings}),
        "by_algorithm": dict(sorted(by_algorithm.items())),
        "recommendations": len(report.recommendations),
        "migrated": len([m for m in report.migrations if m.changed]),
        "manual_review": len([m for m in report.migrations if m.manual_review]),
        "not_migrated": len([m for m in report.migrations if not m.changed and m.finding]),
        "checks_run": len(checks),
        "checks_passed": sum(1 for value in checks.values() if value),
        "all_checks_passed": bool(checks) and all(checks.values()),
    }


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------

def write_json(report: Report, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["summary"] = summary_stats(report)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_none_\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join("" if c is None else str(c) for c in row) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(report: Report) -> str:
    stats = summary_stats(report)
    parts: list[str] = []
    parts.append("# PQC Migration Report\n")
    parts.append(
        f"- **Target:** `{report.target}`\n"
        f"- **Generated:** {report.generated_at}\n"
        f"- **PQC backend:** `{report.backend}`\n"
        f"- **Findings:** {stats['findings']} across {stats['files_affected']} file(s)\n"
        f"- **Migrated findings:** {stats['migrated']} "
        f"(unmigrated: {stats['not_migrated']})\n"
        f"- **Verification:** {stats['checks_passed']}/{stats['checks_run']} checks passed\n"
    )
    if report.context:
        parts.append(
            "\n## Application context\n\n"
            f"- Security level: **{report.context.get('security_level')}**\n"
            f"- Preferred signature scheme: **{report.context.get('prefer_signature_scheme')}**\n"
            f"- Source: `{report.context.get('source')}`\n"
        )
        if report.context.get("notes"):
            parts.append(f"- Notes: {report.context['notes']}\n")

    parts.append("\n## 1. Findings\n\n")
    parts.append(
        _table(
            ["File", "Line", "Algorithm", "Purpose", "Construct", "Library", "Detector"],
            [
                [f.file, f.line, f.algorithm.upper(), f.purpose, f"`{f.matched}`", f.library, f.detector]
                for f in report.findings
            ],
        )
    )

    parts.append("\n## 2. Recommendations\n\n")
    parts.append(
        _table(
            ["Construct", "File:Line", "PQC algorithm", "Standard", "NIST level"],
            [
                [
                    f"`{r.finding.matched}`",
                    f"{r.finding.file}:{r.finding.line}",
                    f"**{r.pqc_algorithm}**",
                    r.nist_standard,
                    r.nist_level,
                ]
                for r in report.recommendations
            ],
        )
    )
    if report.recommendations:
        parts.append("\n<details><summary>Rationale per finding</summary>\n\n")
        for recommendation in report.recommendations:
            parts.append(
                f"- `{recommendation.finding.matched}` "
                f"({recommendation.finding.file}:{recommendation.finding.line}) → "
                f"**{recommendation.pqc_algorithm}** — {recommendation.rationale}\n"
            )
        parts.append("\n</details>\n")

    parts.append("\n## 3. Migrations\n\n")
    parts.append(
        _table(
            ["Original", "Migrated", "Changed", "Manual review", "Rules applied", "Notes"],
            [
                [
                    m.original_file,
                    m.migrated_file,
                    "yes" if m.changed else "no",
                    "yes" if m.manual_review else "no",
                    ", ".join(m.rules_applied) or "-",
                    m.notes,
                ]
                for m in report.migrations
            ],
        )
    )

    parts.append("\n## 4. Verification\n\n")
    parts.append(
        _table(
            ["Check", "Result"],
            [[f"`{name}`", "PASS" if ok else "FAIL"] for name, ok in report.verification.items()],
        )
    )

    parts.append("\n## 5. Benchmark: classical vs PQC\n\n")
    rows = []
    for algorithm, data in report.benchmark.items():
        if "error" in data:
            rows.append([algorithm, "error", data["error"], "", "", "", ""])
            continue
        rows.append(
            [
                algorithm,
                data.get("kind"),
                data.get("standard"),
                data.get("keygen_ms"),
                f"{data.get('operation')}: {data.get('op_ms')}",
                data.get("pubkey_bytes"),
                data.get("sig_or_ct_bytes"),
            ]
        )
    parts.append(
        _table(
            ["Algorithm", "Kind", "Standard", "Keygen (ms)", "Primary op (ms)", "Public key (B)", "Sig/CT (B)"],
            rows,
        )
    )
    parts.append(
        "\n_Timings are medians measured on this machine with the "
        f"`{report.backend}` backend; sizes are exact byte lengths._\n"
    )

    if report.analysis:
        parts.append("\n## 6. Dependency analysis\n\n")
        parts.append(
            f"- Python files scanned: {report.analysis.get('python_files')}\n"
            f"- Files importing crypto libraries: {report.analysis.get('files_importing_crypto')}\n"
        )
        parts.append(
            _table(
                ["Library", "Why it matters"],
                [[k, v] for k, v in report.analysis.get("vulnerable_dependencies", {}).items()],
            )
        )

    parts.append(
        "\n---\n\n_Migration in this phase is rule-based (Project-I). "
        "LLM-assisted rewriting of arbitrary code is Project-II._\n"
    )
    return "".join(parts)


def write_markdown(report: Report, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_markdown(report), encoding="utf-8")
    return destination


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def render_html(report: Report) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = environment.get_template(TEMPLATE_NAME)
    return template.render(report=report, stats=summary_stats(report))


def write_html(report: Report, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_html(report), encoding="utf-8")
    return destination


def write_all(report: Report, out_dir: str | Path) -> dict[str, str]:
    """Write report.json, report.md and report.html into ``out_dir``."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written = {
        "json": str(write_json(report, directory / "report.json")),
        "markdown": str(write_markdown(report, directory / "report.md")),
    }
    try:
        written["html"] = str(write_html(report, directory / "report.html"))
    except Exception as exc:  # jinja2 missing or template error
        written["html_error"] = f"{type(exc).__name__}: {exc}"
    return written
