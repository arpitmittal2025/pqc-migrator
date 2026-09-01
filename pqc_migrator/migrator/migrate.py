"""Apply rewrite rules and emit migrated copies of a project."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..detector.scanner import SKIP_DIRS, iter_python_files
from ..models import (
    PURPOSE_SIGNATURE,
    Finding,
    MigrationResult,
    Recommendation,
)
from . import rules as R

SHIM_SOURCE = Path(__file__).with_name("pqc_shim.py")
SHIM_FILENAME = "pqc_shim.py"

BANNER = """# --- migrated by pqc-migrator (rule-based, Project-I) ---
# rules applied: {rules}
# post-quantum algorithms: {algorithms}
# classical calls now resolve to {shim}, backed by NIST PQC primitives.
# TODO(project-II): LLM-assisted rewrite for constructs without a mechanical rule.
"""


def _relative_root(target: Path) -> Path:
    return target if target.is_dir() else target.parent


def _options_for_file(
    file_recommendations: list[Recommendation],
) -> R.RuleOptions:
    """Pick the algorithms this file should migrate to."""
    options = R.RuleOptions()
    for recommendation in file_recommendations:
        if recommendation.finding.purpose == PURPOSE_SIGNATURE:
            options.signature_algorithm = recommendation.pqc_algorithm
        else:
            options.kem_algorithm = recommendation.pqc_algorithm
    return options


def _group_by_file(items, key) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(str(Path(key(item))), []).append(item)
    return grouped


def _iter_all_files(root: Path) -> list[Path]:
    """Every file under ``root`` worth copying into the migrated tree."""
    if root.is_file():
        return [root]
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS or part.startswith(".") for part in path.parts):
            continue
        files.append(path)
    return files


def migrate_path(
    target: str | Path,
    output_dir: str | Path,
    recommendations: list[Recommendation] | None = None,
    findings: list[Finding] | None = None,
) -> list[MigrationResult]:
    """Write migrated copies of ``target`` into ``output_dir``.

    Returns one :class:`MigrationResult` per finding (plus one per file that had
    no findings but still needed copying), so nothing is reported as migrated
    unless a rule actually fired for it.
    """
    target_path = Path(target)
    root = _relative_root(target_path)
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    recommendations = recommendations or []
    if findings is None:
        findings = [r.finding for r in recommendations]

    recs_by_file = _group_by_file(recommendations, lambda r: r.finding.file)
    findings_by_file = _group_by_file(findings, lambda f: f.file)

    results: list[MigrationResult] = []
    shim_dirs: set[Path] = set()

    python_files = {p.resolve() for p in iter_python_files(target_path)}

    for source_file in _iter_all_files(root if target_path.is_dir() else target_path):
        relative = (
            source_file.relative_to(root)
            if target_path.is_dir()
            else Path(source_file.name)
        )
        destination = out_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        if source_file.resolve() not in python_files:
            shutil.copy2(source_file, destination)
            continue

        original = source_file.read_text(encoding="utf-8")
        file_key = str(source_file)
        file_findings = findings_by_file.get(file_key, [])
        options = _options_for_file(recs_by_file.get(file_key, []))

        migrated = original
        applied: list[str] = []
        fired: set[str] = set()
        covered: set[str] = set()
        for rule in R.RULES:
            migrated, hits = rule.apply(migrated, options)
            if hits:
                applied.append(f"{rule.name} (x{hits})")
                fired.add(rule.name)
                covered.update(rule.covers)

        needs_review = bool(fired & R.MANUAL_REVIEW_RULES)
        changed = migrated != original
        if changed:
            banner = BANNER.format(
                rules=", ".join(applied) or "none",
                algorithms=f"{options.kem_algorithm} / {options.signature_algorithm}",
                shim=R.SHIM_MODULE,
            )
            migrated = banner + migrated
            shim_dirs.add(destination.parent)

        destination.write_text(migrated, encoding="utf-8")

        if not file_findings:
            if changed:
                results.append(
                    MigrationResult(
                        finding=None,
                        original_file=file_key,
                        migrated_file=str(destination),
                        changed=True,
                        notes="Imports rewritten to the PQC shim.",
                        rules_applied=applied,
                        manual_review=needs_review,
                    )
                )
            continue

        for finding in file_findings:
            unsupported = R.UNSUPPORTED_PATTERNS.get(finding.matched)
            finding_changed = changed and (
                finding.matched in covered or finding.matched not in R.UNSUPPORTED_PATTERNS
            )
            if unsupported:
                notes = f"No rewrite rule for {finding.matched}: {unsupported}. Copied unchanged."
                finding_changed = False
            elif finding_changed:
                notes = (
                    f"{finding.matched} now resolves to "
                    f"{options.signature_algorithm if finding.purpose == PURPOSE_SIGNATURE else options.kem_algorithm}"
                    f" via {R.SHIM_MODULE}."
                )
                if needs_review:
                    notes += (
                        " Manual review required: the Diffie-Hellman round must be "
                        "restructured as encapsulate/decapsulate (see the TODO in "
                        "the migrated file)."
                    )
            else:
                notes = f"No rule fired for {finding.matched}; file copied unchanged."
            results.append(
                MigrationResult(
                    finding=finding,
                    original_file=file_key,
                    migrated_file=str(destination),
                    changed=finding_changed,
                    notes=notes,
                    rules_applied=applied,
                    manual_review=needs_review,
                )
            )

    for directory in shim_dirs | ({out_root} if shim_dirs else set()):
        shutil.copy2(SHIM_SOURCE, directory / SHIM_FILENAME)

    return results


def summarize(results: list[MigrationResult]) -> dict[str, int]:
    """Counts used by the CLI and the report."""
    files = {r.migrated_file for r in results}
    changed_files = {r.migrated_file for r in results if r.changed}
    return {
        "findings": len([r for r in results if r.finding is not None]),
        "migrated_findings": len([r for r in results if r.changed and r.finding]),
        "files_written": len(files),
        "files_changed": len(changed_files),
        "manual_review": len({r.migrated_file for r in results if r.manual_review}),
    }
