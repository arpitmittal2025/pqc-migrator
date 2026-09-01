# pqc-migrator — AI-Driven PQC Migration & Optimization Framework

Detects classical public-key cryptography (RSA, ECC/ECDSA, Diffie–Hellman) in Python
source, recommends the right NIST post-quantum replacement, rewrites the code,
**runs the migrated code to prove the PQC actually works**, and generates a report
with a measured classical-vs-PQC benchmark — all from one CLI.

This is the Project-I build: migration is **rule-based**. LLM-assisted rewriting of
arbitrary code, non-Python languages, and the optimization pass are Project-II
(`pqc_migrator/optimizer/optimize.py` is an explicit stub, not a fake implementation).

---

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
pqc-migrator run samples/app_rsa -o pqc_out/app_rsa
```

That single command scans, recommends, migrates, verifies and reports. Output lands in
`pqc_out/app_rsa/migrated/` (runnable migrated code) and `pqc_out/app_rsa/reports/`
(`report.json`, `report.md`, `report.html`).

## CLI

```bash
pqc-migrator scan       samples/app_rsa            # list findings
pqc-migrator recommend  samples/app_ecdsa          # findings + recommended PQC algorithm
pqc-migrator migrate    samples/app_rsa -o out     # write migrated copies
pqc-migrator verify     samples/app_rsa            # real KEM / signature round-trips
pqc-migrator report     samples/app_dh  -o reports # JSON + Markdown + HTML
pqc-migrator run        samples/app_rsa -o pqc_out # the whole pipeline
pqc-migrator backend                               # which PQC backend is active
```

Useful flags: `--security-level 1..5`, `--signature-scheme ML-DSA|SLH-DSA`,
`--runs N` (benchmark repetitions), `--no-benchmark`.

## Pipeline

| Stage | Module | What it does |
| --- | --- | --- |
| Detect | `detector/scanner.py` | AST walk over every `.py` file, matching the constructs in `detector/patterns.py`; a regex sweep catches what the AST cannot parse. Classifies each hit as `kem`, `key_exchange` or `signature`, and attributes it to a library using the file's imports. |
| Analyze | `analyzer/static_analysis.py` | Project walk: import map per file, which files pull in crypto libraries, which declared dependencies introduce classical crypto. |
| Context | `context/context.py` | Reads `pqc.config.json` (security level, preferred signature family) or falls back to documented defaults (level 3, ML-DSA). |
| Recommend | `recommender/recommend.py` | Rule + scoring engine: purpose picks the family, the security level picks the parameter set, and classical strength hints (`key_size=4096`, `SECP521R1`, …) raise the target category. Emits a rationale per finding. |
| Migrate | `migrator/` | Text/AST rewrite rules produce migrated **copies**; originals are never touched. Classical calls are pointed at `pqc_shim.py`, a drop-in module whose objects keep the classical shape (`generate_private_key`, `encrypt`/`decrypt`, `sign`/`verify`) but run ML-KEM / ML-DSA underneath. |
| Verify | `verifier/verify.py` | Real encaps/decaps and sign/verify round-trips, plus negative checks (tampered message, wrong key, foreign decapsulation key), plus **executing the migrated app**. |
| Report | `reporter/report.py` | `report.json`, `report.md` and a themed `report.html`, including the benchmark. |

### Algorithm mapping

| Purpose | Family | Level 1–2 | Level 3–4 | Level 5 |
| --- | --- | --- | --- | --- |
| `kem`, `key_exchange` | ML-KEM (FIPS 203) | ML-KEM-512 | ML-KEM-768 | ML-KEM-1024 |
| `signature` | ML-DSA (FIPS 204) | ML-DSA-44 | ML-DSA-65 | ML-DSA-87 |
| `signature`, hash-based requested | SLH-DSA (FIPS 205) | SLH-DSA-SHA2-128s | SLH-DSA-SHA2-192s | SLH-DSA-SHA2-256s |

## PQC backend

All PQC goes through `pqc/backends.py`, so nothing else in the codebase knows which
implementation is installed:

- **`liboqs`** (import name `oqs`) — preferred; provides ML-KEM, ML-DSA and SLH-DSA.
- **`purepy`** — `kyber-py` + `dilithium-py` fallback; ML-KEM and ML-DSA only. Asking
  for SLH-DSA here raises `UnsupportedAlgorithm` rather than quietly substituting
  something else.

Selection is automatic; `PQC_MIGRATOR_BACKEND=liboqs|purepy` forces one. Check with
`pqc-migrator backend`.

## What the migration actually produces

`samples/app_rsa/keygen.py` before:

```python
from cryptography.hazmat.primitives.asymmetric import rsa

private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
```

after `pqc-migrator migrate`:

```python
# --- migrated by pqc-migrator (rule-based, Project-I) ---
# rules applied: cryptography-imports-to-shim (x2), rsa-keygen-to-ml-kem (x1)
# post-quantum algorithms: ML-KEM-768 / ML-DSA-65
from pqc_shim import rsa

private_key = rsa.generate_private_key(algorithm="ML-KEM-768")
```

RSA-OAEP key transport becomes ML-KEM encapsulation with the payload under AES-256-GCM,
so `public_key.encrypt(...)` / `private_key.decrypt(...)` keep working at the call site.
The migrated `app_rsa` and `app_ecdsa` apps both run and are executed during `verify`.

### Known limitation: Diffie–Hellman

Diffie–Hellman's *symmetric* agreement has no drop-in KEM equivalent — one side must
encapsulate and the other decapsulate. The migrator rewrites parameter generation to
ML-KEM, then **annotates** each `.exchange()` site with a TODO and marks the file
`manual_review` in the report. It is not executed during verification and is never
reported as a successful migration. `pqc_shim.kem_handshake()` provides the correct
replacement primitive for the rewrite.

## Benchmark

Measured by `pqc/benchmark.py` at report time — no stored figures. Example run on the
development machine (Python 3.11, `purepy` backend, medians of 20 runs; the pure-Python
backend is far slower than liboqs, so treat the timings as relative, not absolute):

| Algorithm | Kind | Keygen (ms) | Primary op (ms) | Public key (B) | Sig/CT (B) |
| --- | --- | --- | --- | --- | --- |
| ML-KEM-768 | pqc | 2.47 | encapsulate 3.33 | 1184 | 1088 |
| ML-DSA-65 | pqc | 8.13 | sign 47.88 | 1952 | 3309 |
| RSA-2048 | classical | 43.10 | encrypt 0.02 | 294 | 256 |
| ECDSA-P256 | classical | 0.02 | sign 0.02 | 91 | 71 |

The headline trade-off is size: ML-KEM-768 public keys are ~4× RSA-2048's and ML-DSA-65
signatures are ~47× an ECDSA-P256 signature. **Re-run the tool and use its numbers** in
any write-up rather than copying this table.

## Configuration

Drop a `pqc.config.json` beside the code (see `samples/app_ecdsa/`):

```json
{
  "security_level": 3,
  "prefer_signature_scheme": "ML-DSA",
  "notes": "Release signing service; long-lived verification keys."
}
```

## Tests

```bash
pytest
```

60 tests cover detection (including the regex fallback and purpose reclassification),
recommendation and scoring, the real PQC round-trips, the rewrite rules, execution of
the migrated apps, verification behaviour, and the full CLI pipeline.

## Layout

```
pqc_migrator/
├── cli.py                     scan | recommend | migrate | verify | report | run | backend
├── models.py                  Finding, Recommendation, MigrationResult, Report
├── detector/                  patterns.py, scanner.py
├── analyzer/static_analysis.py
├── context/context.py
├── recommender/recommend.py
├── migrator/                  rules.py, migrate.py, pqc_shim.py (runtime shim)
├── pqc/                       backends.py, benchmark.py
├── verifier/verify.py
├── reporter/                  report.py, templates/report.html.j2
└── optimizer/optimize.py      stub (Project-II)
samples/                       app_rsa, app_ecdsa, app_dh
tests/
```

## Scope and honesty

- Migration is rule-based; constructs without a rule are copied unchanged and reported
  as unmigrated, never as a success. `# TODO(project-II): LLM-assisted rewrite` marks
  where the model-driven pass belongs.
- PyCryptodome and the `ecdsa` package are **detected** but have no rewrite rules yet.
- Only Python is supported.
- No optimization pass exists in this build.
