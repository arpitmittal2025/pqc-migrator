"""Command line interface: scan | recommend | migrate | verify | report | run."""

from __future__ import annotations

from pathlib import Path

import sys

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .analyzer.static_analysis import analyze_project
from .context.context import AppContext, load_context
from .detector.scanner import scan_path
from .migrator.migrate import migrate_path, summarize
from .pqc import backends, benchmark as bench
from .recommender.recommend import algorithms_used, recommend_all
from .reporter import report as reporter
from .verifier import verify as verifier

# Windows consoles often default to cp1252, which cannot render rich's box
# drawing characters; switch the streams to UTF-8 before rich inspects them.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()

PURPOSE_COLOR = {"kem": "cyan", "key_exchange": "cyan", "signature": "magenta"}


def _load_context(target: str, level: int | None, scheme: str | None) -> AppContext:
    """Config file first, then CLI overrides."""
    context = load_context(target)
    if level is not None:
        context.security_level = max(1, min(5, level))
        context.source = f"{context.source} + --security-level"
    if scheme:
        context.prefer_signature_scheme = scheme
        context.source = f"{context.source} + --signature-scheme"
    return context


def _findings_table(findings) -> Table:
    table = Table(title="Classical crypto findings", header_style="bold")
    table.add_column("File", overflow="fold")
    table.add_column("Line", justify="right")
    table.add_column("Alg")
    table.add_column("Purpose")
    table.add_column("Construct")
    table.add_column("Library")
    for finding in findings:
        table.add_row(
            finding.file,
            str(finding.line),
            finding.algorithm.upper(),
            f"[{PURPOSE_COLOR.get(finding.purpose, 'white')}]{finding.purpose}[/]",
            finding.matched,
            finding.library,
        )
    return table


def _recommendation_table(recommendations) -> Table:
    table = Table(title="Recommended NIST PQC replacements", header_style="bold")
    table.add_column("Construct")
    table.add_column("Location", overflow="fold")
    table.add_column("PQC algorithm", style="bold green")
    table.add_column("Standard")
    table.add_column("Level", justify="right")
    for recommendation in recommendations:
        finding = recommendation.finding
        table.add_row(
            finding.matched,
            f"{finding.file}:{finding.line}",
            recommendation.pqc_algorithm,
            recommendation.nist_standard,
            str(recommendation.nist_level),
        )
    return table


def _verification_table(results: dict[str, bool]) -> Table:
    table = Table(title="Functional verification", header_style="bold")
    table.add_column("Check", overflow="fold")
    table.add_column("Result")
    for name, ok in results.items():
        table.add_row(name, "[green]PASS[/]" if ok else "[red]FAIL[/]")
    return table


def _benchmark_table(data: dict) -> Table:
    table = Table(title="Classical vs post-quantum", header_style="bold")
    table.add_column("Algorithm")
    table.add_column("Kind")
    table.add_column("Keygen ms", justify="right")
    table.add_column("Op")
    table.add_column("Op ms", justify="right")
    table.add_column("Pubkey B", justify="right")
    table.add_column("Sig/CT B", justify="right")
    for algorithm, row in data.items():
        if "error" in row:
            table.add_row(algorithm, "[red]error[/]", row["error"], "", "", "", "")
            continue
        style = "yellow" if row.get("kind") == "classical" else "green"
        table.add_row(
            f"[{style}]{algorithm}[/]",
            str(row.get("kind")),
            str(row.get("keygen_ms")),
            str(row.get("operation")),
            str(row.get("op_ms")),
            str(row.get("pubkey_bytes")),
            str(row.get("sig_or_ct_bytes")),
        )
    return table


security_level_option = click.option(
    "--security-level",
    type=click.IntRange(1, 5),
    default=None,
    help="Target NIST security category (overrides pqc.config.json).",
)
scheme_option = click.option(
    "--signature-scheme",
    type=click.Choice(["ML-DSA", "SLH-DSA"], case_sensitive=False),
    default=None,
    help="Preferred signature family.",
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="pqc-migrator")
def main() -> None:
    """AI-driven PQC migration framework: detect, recommend, migrate, verify, report."""


@main.command()
@click.argument("path", type=click.Path(exists=True))
def scan(path: str) -> None:
    """List quantum-vulnerable classical crypto in PATH."""
    findings = scan_path(path)
    if not findings:
        console.print("[green]No classical public-key crypto detected.[/]")
        return
    console.print(_findings_table(findings))
    console.print(f"[bold]{len(findings)}[/] finding(s) in {len({f.file for f in findings})} file(s).")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@security_level_option
@scheme_option
def recommend(path: str, security_level: int | None, signature_scheme: str | None) -> None:
    """Recommend a NIST PQC algorithm for every finding in PATH."""
    context = _load_context(path, security_level, signature_scheme)
    findings = scan_path(path)
    recommendations = recommend_all(findings, context)
    if not recommendations:
        console.print("[green]Nothing to migrate.[/]")
        return
    console.print(
        f"Context: level [bold]{context.security_level}[/], "
        f"signatures [bold]{context.prefer_signature_scheme}[/] "
        f"(source: {context.source})"
    )
    console.print(_recommendation_table(recommendations))


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("-o", "--output", "output", default="migrated", show_default=True,
              type=click.Path(), help="Directory for migrated copies.")
@security_level_option
@scheme_option
def migrate(path: str, output: str, security_level: int | None, signature_scheme: str | None) -> None:
    """Write migrated copies of PATH into the output directory."""
    context = _load_context(path, security_level, signature_scheme)
    findings = scan_path(path)
    recommendations = recommend_all(findings, context)
    results = migrate_path(path, output, recommendations, findings)
    stats = summarize(results)
    for result in results:
        marker = "[green]migrated[/]" if result.changed else "[yellow]unchanged[/]"
        label = result.finding.matched if result.finding else Path(result.original_file).name
        if result.manual_review:
            marker = "[yellow]needs review[/]"
        console.print(f"{marker} {label} -> {result.migrated_file}")
        if (not result.changed or result.manual_review) and result.finding:
            console.print(f"          [dim]{result.notes}[/]")
    console.print(
        f"\n[bold]{stats['migrated_findings']}/{stats['findings']}[/] findings migrated; "
        f"{stats['files_changed']} file(s) rewritten into [bold]{output}[/]."
    )


@main.command()
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--algorithm", "algorithms", multiple=True,
              help="Verify a specific algorithm (repeatable).")
@click.option("--migrated", "migrated_dir", type=click.Path(exists=True), default=None,
              help="Also execute migrated apps in this directory.")
def verify(path: str | None, algorithms: tuple[str, ...], migrated_dir: str | None) -> None:
    """Run real PQC round-trip checks (KEM encaps/decaps, sign/verify)."""
    details = backends.backend_details()
    console.print(f"Backend: [bold]{details['backend']}[/] — {details['note']}")

    targets = list(algorithms)
    if path and not targets:
        context = load_context(path)
        targets = algorithms_used(recommend_all(scan_path(path), context))
    results = verifier.verify_all(algorithms=targets or None)

    if migrated_dir:
        for app_dir in sorted(Path(migrated_dir).iterdir()):
            if (app_dir / "main.py").is_file():
                ok, output = verifier.verify_migrated_app(app_dir)
                results[f"migrated_app_runs[{app_dir.name}]"] = ok
                if not ok and output:
                    results[f"migrated_app_runs[{app_dir.name}] :: {output.splitlines()[-1][:120]}"] = False

    console.print(_verification_table(results))
    console.print(f"[bold]{verifier.summary(results)}[/]")
    if not verifier.passed(results):
        raise SystemExit(1)


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("-o", "--output", "output", default="reports", show_default=True,
              type=click.Path(), help="Directory for report.json / report.md / report.html.")
@click.option("--runs", default=bench.DEFAULT_RUNS, show_default=True,
              help="Benchmark repetitions per operation.")
@click.option("--no-benchmark", is_flag=True, help="Skip the benchmark section.")
@security_level_option
@scheme_option
def report(path: str, output: str, runs: int, no_benchmark: bool,
           security_level: int | None, signature_scheme: str | None) -> None:
    """Generate a full report (JSON + Markdown + HTML) for PATH."""
    context = _load_context(path, security_level, signature_scheme)
    findings = scan_path(path)
    recommendations = recommend_all(findings, context)
    algorithms = algorithms_used(recommendations)
    verification = verifier.verify_all(recommendations=recommendations)
    benchmark = {} if no_benchmark else bench.benchmark_all(algorithms, runs)
    document = reporter.build_report(
        target=path,
        findings=findings,
        recommendations=recommendations,
        verification=verification,
        benchmark=benchmark,
        analysis=analyze_project(path),
        context=context.to_dict(),
    )
    written = reporter.write_all(document, output)
    for kind, location in written.items():
        console.print(f"{kind}: [bold]{location}[/]")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("-o", "--output", "output", default="pqc_out", show_default=True,
              type=click.Path(), help="Root directory for migrated code and reports.")
@click.option("--runs", default=bench.DEFAULT_RUNS, show_default=True,
              help="Benchmark repetitions per operation.")
@click.option("--no-benchmark", is_flag=True, help="Skip the benchmark section.")
@security_level_option
@scheme_option
def run(path: str, output: str, runs: int, no_benchmark: bool,
        security_level: int | None, signature_scheme: str | None) -> None:
    """Full pipeline: scan -> recommend -> migrate -> verify -> report."""
    out_root = Path(output)
    migrated_dir = out_root / "migrated"
    reports_dir = out_root / "reports"

    details = backends.backend_details()
    console.rule("[bold]pqc-migrator")
    console.print(f"Target: [bold]{path}[/]  |  backend: [bold]{details['backend']}[/]")

    context = _load_context(path, security_level, signature_scheme)
    console.print(
        f"Context: level [bold]{context.security_level}[/], "
        f"signatures [bold]{context.prefer_signature_scheme}[/] (source: {context.source})\n"
    )

    console.rule("1. Scan")
    findings = scan_path(path)
    console.print(_findings_table(findings) if findings else "[green]No findings.[/]")

    console.rule("2. Recommend")
    recommendations = recommend_all(findings, context)
    if recommendations:
        console.print(_recommendation_table(recommendations))
    algorithms = algorithms_used(recommendations)

    console.rule("3. Migrate")
    migrations = migrate_path(path, migrated_dir, recommendations, findings)
    stats = summarize(migrations)
    console.print(
        f"{stats['migrated_findings']}/{stats['findings']} findings migrated, "
        f"{stats['files_changed']} file(s) rewritten into [bold]{migrated_dir}[/]"
    )
    for result in migrations:
        if result.manual_review:
            console.print(
                f"  [yellow]needs manual review[/] {result.migrated_file}: "
                "handshake must become encapsulate/decapsulate (not executed in verify)"
            )
        elif not result.changed and result.finding:
            console.print(f"  [yellow]skipped[/] {result.finding.matched}: {result.notes}")

    console.rule("4. Verify")
    verification = verifier.verify_all(
        recommendations=recommendations, migrations=migrations
    )
    console.print(_verification_table(verification))

    console.rule("5. Report")
    benchmark = {} if no_benchmark else bench.benchmark_all(algorithms, runs)
    if benchmark:
        console.print(_benchmark_table(benchmark))
    document = reporter.build_report(
        target=path,
        findings=findings,
        recommendations=recommendations,
        migrations=migrations,
        verification=verification,
        benchmark=benchmark,
        analysis=analyze_project(path),
        context=context.to_dict(),
    )
    written = reporter.write_all(document, reports_dir)
    for kind, location in written.items():
        console.print(f"{kind}: [bold]{location}[/]")

    console.rule("Done")
    console.print(f"Verification: [bold]{verifier.summary(verification)}[/]")
    if not verifier.passed(verification):
        raise SystemExit(1)


@main.command()
def backend() -> None:
    """Show which PQC backend is active and what it supports."""
    details = backends.backend_details()
    console.print(f"Backend: [bold]{details['backend']}[/] — {details['note']}")
    console.print(f"KEM:        {', '.join(details['kem_algorithms']) or 'none'}")
    console.print(f"Signatures: {', '.join(details['signature_algorithms']) or 'none'}")


if __name__ == "__main__":  # pragma: no cover
    main()
