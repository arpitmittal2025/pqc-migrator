"""Measure detection precision, recall and purpose-classification accuracy.

A detection is counted at (file, line, algorithm) granularity: the question
being asked is "did the tool flag the right line and attribute it to the right
classical algorithm family?". Several constructs on one line (for example
``ec.generate_private_key(ec.SECP256R1())``) therefore count once, so a tool is
neither rewarded nor punished for how finely it splits a single site.

Ground-truth sites carry a scope:

* ``core``     -- RSA / ECC / DH reached directly through the libraries this
                  prototype targets (cryptography, PyCryptodome, ecdsa). This is
                  the stated scope, and the headline recall is measured here.
* ``extended`` -- genuinely quantum-vulnerable usage reached through wrapper
                  libraries, a string parameter, dynamic dispatch or dataflow
                  indirection. Reported separately as a coverage limit.

Precision is reported over every flag the tool raises, against sites of either
scope, so finding an extended site is never penalised.

Run:  python evaluation/evaluate.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pqc_migrator.detector.scanner import scan_path

EVAL_DIR = Path(__file__).parent
CORPUS_DIR = EVAL_DIR / "corpus"
LABELS_FILE = EVAL_DIR / "labels.json"
RESULTS_FILE = EVAL_DIR / "results.json"

Site = tuple[str, int, str]


def _relative(path: str) -> str:
    return Path(path).resolve().relative_to(CORPUS_DIR.resolve()).as_posix()


def _div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return _div(2 * precision * recall, precision + recall)


def evaluate() -> dict:
    manifest = json.loads(LABELS_FILE.read_text(encoding="utf-8"))

    core: set[Site] = set()
    extended: set[Site] = set()
    purpose_of: dict[Site, str] = {}
    for label in manifest["labels"]:
        site: Site = (label["file"], label["line"], label["algorithm"])
        (core if label["scope"] == "core" else extended).add(site)
        purpose_of[site] = label["purpose"]
    expected_all = core | extended

    findings = scan_path(CORPUS_DIR)
    detected: set[Site] = set()
    detected_purpose: dict[Site, str] = {}
    per_file: dict[str, int] = defaultdict(int)
    for finding in findings:
        site = (_relative(finding.file), finding.line, finding.algorithm)
        detected.add(site)
        detected_purpose.setdefault(site, finding.purpose)
        per_file[site[0]] += 1

    legitimate = detected & expected_all
    spurious = detected - expected_all
    core_found = core & detected
    core_missed = core - detected
    extended_found = extended & detected
    extended_missed = extended - detected

    precision = _div(len(legitimate), len(detected))
    core_recall = _div(len(core_found), len(core))
    extended_recall = _div(len(extended_found), len(extended))

    per_algorithm: dict[str, dict] = {}
    for algorithm in sorted({site[2] for site in core}):
        tp = len({s for s in core_found if s[2] == algorithm})
        fn = len({s for s in core_missed if s[2] == algorithm})
        fp = len({s for s in spurious if s[2] == algorithm})
        p = _div(tp, tp + fp)
        r = _div(tp, tp + fn)
        per_algorithm[algorithm] = {
            "sites": tp + fn,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(_f1(p, r), 4),
        }

    purpose_correct = sum(
        1 for site in core_found if detected_purpose.get(site) == purpose_of[site]
    )
    purpose_errors = [
        {
            "file": s[0], "line": s[1], "algorithm": s[2],
            "expected": purpose_of[s], "detected": detected_purpose.get(s),
        }
        for s in sorted(core_found)
        if detected_purpose.get(s) != purpose_of[s]
    ]

    clean_files = set(manifest["negative_files"])
    noisy_clean = sorted(f for f in clean_files if per_file.get(f, 0) > 0)

    results = {
        "corpus": {
            "files": len(manifest["files"]),
            "in_scope_files": len(manifest["positive_files"]),
            "extended_files": len(manifest["extended_files"]),
            "clean_files": len(manifest["negative_files"]),
            "core_sites": len(core),
            "extended_sites": len(extended),
            "flags_raised": len(detected),
            "raw_findings": len(findings),
        },
        "headline": {
            "precision": round(precision, 4),
            "recall_in_scope": round(core_recall, 4),
            "f1_in_scope": round(_f1(precision, core_recall), 4),
            "recall_extended": round(extended_recall, 4),
            "legitimate_flags": len(legitimate),
            "spurious_flags": len(spurious),
            "in_scope_missed": len(core_missed),
            "extended_missed": len(extended_missed),
        },
        "per_algorithm": per_algorithm,
        "purpose_classification": {
            "evaluated_on": len(core_found),
            "correct": purpose_correct,
            "accuracy": round(_div(purpose_correct, len(core_found)), 4),
            "errors": purpose_errors,
        },
        "clean_files": {
            "total": len(clean_files),
            "with_false_alarms": len(noisy_clean),
            "files": noisy_clean,
        },
        "missed_in_scope": [
            {"file": f, "line": l, "algorithm": a} for f, l, a in sorted(core_missed)
        ],
        "missed_extended": [
            {"file": f, "line": l, "algorithm": a} for f, l, a in sorted(extended_missed)
        ],
        "spurious": [
            {"file": f, "line": l, "algorithm": a} for f, l, a in sorted(spurious)
        ],
    }
    RESULTS_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def _print(results: dict) -> None:
    corpus, head = results["corpus"], results["headline"]
    print("=" * 66)
    print("DETECTION BENCHMARK")
    print("=" * 66)
    print(
        f"corpus : {corpus['files']} files = "
        f"{corpus['in_scope_files']} in-scope + {corpus['extended_files']} extended "
        f"+ {corpus['clean_files']} clean"
    )
    print(
        f"sites  : {corpus['core_sites']} in-scope, {corpus['extended_sites']} extended; "
        f"{corpus['flags_raised']} flags raised"
    )
    print()
    print(f"  precision            : {head['precision']:.3f}  "
          f"({head['legitimate_flags']} legitimate / {corpus['flags_raised']} flags, "
          f"{head['spurious_flags']} spurious)")
    print(f"  recall (in scope)    : {head['recall_in_scope']:.3f}  "
          f"({head['in_scope_missed']} missed of {corpus['core_sites']})")
    print(f"  F1     (in scope)    : {head['f1_in_scope']:.3f}")
    print(f"  recall (extended)    : {head['recall_extended']:.3f}  "
          f"({head['extended_missed']} missed of {corpus['extended_sites']})")
    print()
    print("per algorithm (in scope):")
    for algorithm, m in results["per_algorithm"].items():
        print(f"  {algorithm:<4} n={m['sites']:<3} precision {m['precision']:.3f}  "
              f"recall {m['recall']:.3f}  F1 {m['f1']:.3f}")
    purpose = results["purpose_classification"]
    print()
    print(f"purpose classification: {purpose['correct']}/{purpose['evaluated_on']} "
          f"= {purpose['accuracy']:.3f}")
    for error in purpose["errors"]:
        print(f"  {error['file']}:{error['line']} expected {error['expected']}, "
              f"got {error['detected']}")
    clean = results["clean_files"]
    print()
    print(f"clean files with false alarms: {clean['with_false_alarms']}/{clean['total']}")
    for group, title in (("missed_in_scope", "missed (in scope)"),
                         ("missed_extended", "missed (extended)"),
                         ("spurious", "spurious flags")):
        if results[group]:
            print()
            print(f"{title}:")
            for site in results[group]:
                print(f"  {site['file']}:{site['line']} ({site['algorithm']})")
    print()
    print(f"written to {RESULTS_FILE}")


if __name__ == "__main__":
    _print(evaluate())
