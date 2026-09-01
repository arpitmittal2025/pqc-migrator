# CLAUDE.md — AI-Driven PQC Migration & Optimization Framework

> This file is the build brief. It targets a **Project-I (60–70%) implementation**:
> a working end-to-end pipeline that detects classical crypto in Python code,
> recommends NIST post-quantum algorithms, migrates the code, verifies the
> migrated crypto actually works, and generates a report. Optimization,
> multi-language support, and LLM-driven migration are **out of scope** (Project-II).

## 0. How to work on this repo
- Language: **Python 3.11+**. Keep it a clean, installable package with a CLI.
- Build **incrementally, module by module**, in the order in Section 7.
- After each module: add unit tests and make sure `pytest` passes before moving on.
- Prefer standard library + a few well-known packages (Section 3). Don't add heavy deps.
- Every module must be runnable and demoable on the sample codebases in `samples/`.
- Write real, honest code — no stubbed results pretending to be real output.

## 1. Goal
Automate the migration of classical public-key cryptography (RSA, ECC/ECDSA,
Diffie–Hellman) in Python source code to NIST-standardized Post-Quantum
Cryptography (ML-KEM / ML-DSA / SLH-DSA), with detection → recommendation →
migration → verification → reporting, driven from a single CLI.

## 2. Scope for this build (~65%)
IN SCOPE (must work end-to-end and be demoable):
- Detect RSA, ECC/ECDSA, and Diffie–Hellman usage in Python code.
- Static/dependency scan across a project folder.
- Lightweight application-context input (security level, KEM vs signature need).
- Rule + scoring recommendation engine → NIST PQC algorithm per finding.
- Rule-based code migration for supported patterns (produces migrated copies).
- Functional verification: PQC KEM encaps/decaps round-trip and sign/verify round-trip.
- Report generation: JSON + Markdown/HTML, with a small benchmark
  (timings and key/signature sizes: classical vs PQC).

OUT OF SCOPE (leave clear TODOs, do not implement):
- LLM/AI-model-driven migration of arbitrary code (rules only for now).
- Languages other than Python.
- Optimization/refactoring pass (stub module only).
- Production deployment, GUI beyond the CLI (optional Streamlit later).

## 3. Tech stack
- Python 3.11+, packaged with `pyproject.toml`.
- CLI: `click` (or `argparse`).
- Classical crypto in the sample "legacy" code: `cryptography` (real RSA/ECC).
- **Real PQC (primary):** `liboqs-python` (import name `oqs`) for ML-KEM / ML-DSA / SLH-DSA.
- **Real PQC (fallback if liboqs is hard to build):** pure-Python `kyber-py` (ML-KEM)
  and `dilithium-py` (ML-DSA). Abstract PQC behind a `pqc/backends.py` interface so the
  rest of the code doesn't care which backend is active. Auto-detect at runtime.
- Testing: `pytest`. Reports: `jinja2` for HTML (optional), `rich` for pretty CLI output.

## 4. Repository structure
```
pqc-migrator/
├── pyproject.toml
├── README.md
├── CLAUDE.md                     # this file
├── pqc_migrator/
│   ├── __init__.py
│   ├── cli.py                    # `pqc-migrator scan|recommend|migrate|verify|report|run`
│   ├── models.py                 # dataclasses: Finding, Recommendation, MigrationResult, Report
│   ├── detector/
│   │   ├── __init__.py
│   │   ├── patterns.py           # signatures for RSA/ECC/DH across libs
│   │   └── scanner.py            # AST + regex scan → list[Finding]
│   ├── analyzer/
│   │   └── static_analysis.py    # project walk, imports, dependency map
│   ├── context/
│   │   └── context.py            # load/infer security level + purpose (KEM vs signature)
│   ├── recommender/
│   │   └── recommend.py          # Finding + context → Recommendation (NIST algo + level)
│   ├── migrator/
│   │   ├── rules.py              # per-pattern rewrite rules
│   │   └── migrate.py            # apply rules → migrated file copies + MigrationResult
│   ├── pqc/
│   │   ├── backends.py           # unified interface over liboqs / kyber-py / dilithium-py
│   │   └── benchmark.py          # timings + key/signature sizes, classical vs PQC
│   ├── verifier/
│   │   └── verify.py             # KEM round-trip + sign/verify round-trip checks
│   └── reporter/
│       ├── report.py             # build Report, write JSON + Markdown/HTML
│       └── templates/report.html.j2
├── samples/
│   ├── app_rsa/                  # a mini codebase using RSA (encryption/keygen)
│   ├── app_ecdsa/               # a mini codebase using ECDSA signatures
│   └── app_dh/                   # a mini codebase using Diffie–Hellman
└── tests/
    ├── test_detector.py
    ├── test_recommender.py
    ├── test_migrator.py
    ├── test_pqc_backends.py
    └── test_verifier.py
```

## 5. Data models (pqc_migrator/models.py)
```python
@dataclass
class Finding:
    file: str
    line: int
    algorithm: str          # "rsa" | "ecc" | "dh"
    purpose: str            # "kem" | "signature" | "key_exchange"
    matched: str            # the construct matched
    library: str            # "cryptography" | "pycryptodome" | "unknown"

@dataclass
class Recommendation:
    finding: Finding
    pqc_algorithm: str      # e.g. "ML-KEM-768"
    nist_standard: str      # e.g. "FIPS 203"
    nist_level: int         # 1..5
    rationale: str

@dataclass
class MigrationResult:
    finding: Finding
    original_file: str
    migrated_file: str      # path to migrated copy
    changed: bool
    notes: str

@dataclass
class Report:
    findings: list[Finding]
    recommendations: list[Recommendation]
    migrations: list[MigrationResult]
    verification: dict      # test name -> pass/fail
    benchmark: dict         # algo -> {keygen_ms, op_ms, pubkey_bytes, sig_or_ct_bytes}
```

## 6. Module specifications
### 6.1 Detector (detector/scanner.py)
- Parse each `.py` file with `ast`; walk calls/attributes/imports.
- Match patterns in `patterns.py`, e.g.:
  - RSA: `rsa.generate_private_key`, `RSA.generate`, `PKCS1_OAEP`, `padding.OAEP`
  - ECC: `ec.generate_private_key`, `SECP256R1`, `ECDSA`, `SigningKey` (ecdsa lib)
  - DH:  `dh.generate_parameters`, `DiffieHellman`
- Classify `purpose`: RSA-encrypt/DH → `kem`/`key_exchange`; RSA-sign/ECDSA → `signature`.
- Return `list[Finding]` with file, line, matched text, library.
- Also keep a regex fallback for cases AST misses.

### 6.2 Analyzer (analyzer/static_analysis.py)
- Walk the target project directory (skip venv/.git).
- Build a map: file → imported modules; flag files importing crypto libs.
- Summarize which third-party dependencies introduce vulnerable crypto.

### 6.3 Context (context/context.py)
- Read an optional `pqc.config.json` (security_level, prefer_signature_scheme).
- If absent, infer: default nist_level=3; purpose from the finding.

### 6.4 Recommender (recommender/recommend.py)
Mapping (parameterise by nist_level):
- purpose kem / key_exchange  → **ML-KEM** (FIPS 203): L1→ML-KEM-512, L3→ML-KEM-768, L5→ML-KEM-1024
- purpose signature           → **ML-DSA** (FIPS 204): L2→ML-DSA-44, L3→ML-DSA-65, L5→ML-DSA-87
- if config requests hash-based signatures → **SLH-DSA** (FIPS 205)
- Return `Recommendation` with rationale string.

### 6.5 Migrator (migrator/migrate.py + rules.py)
- For each finding with a supported rule, produce a migrated copy under `migrated/`.
- Rules are text/AST transforms mapping a classical pattern to the PQC backend call,
  e.g. `cryptography` RSA keygen → `pqc.backends.kem_keypair("ML-KEM-768")`.
- Unsupported patterns: copy file unchanged, set `changed=False`, add a TODO note.
- Never claim a migration succeeded if no rule applied.

### 6.6 PQC backend (pqc/backends.py)
Unified functions the rest of the code calls (backend picked at runtime):
```python
def available_backend() -> str: ...        # "liboqs" | "purepy"
def kem_keypair(alg): ...                   # -> (public_key, secret_key)
def kem_encapsulate(alg, public_key): ...   # -> (ciphertext, shared_secret)
def kem_decapsulate(alg, secret_key, ct): ... # -> shared_secret
def sig_keypair(alg): ...
def sig_sign(alg, secret_key, msg): ...
def sig_verify(alg, public_key, msg, sig): ...
```
- Try `import oqs` first; else use kyber-py/dilithium-py. Map algorithm names per backend.

### 6.7 Verifier (verifier/verify.py)
- KEM check: keypair → encapsulate → decapsulate; assert shared secrets match.
- Signature check: keypair → sign(msg) → verify; assert True, and a tampered msg → False.
- Return dict of test name → pass/fail; used in the report.

### 6.8 Benchmark (pqc/benchmark.py)
- Time keygen and the primary op (encaps or sign) over N runs.
- Record public-key size and ciphertext/signature size.
- Compare against the classical scheme's sizes (RSA-2048, ECDSA-P256) for the report.

### 6.9 Reporter (reporter/report.py)
- Assemble `Report`; write `report.json` and `report.md` (and `report.html` via jinja2).
- Sections: findings table, recommendations, migrations, verification results, benchmark.

## 7. Build order (do these as sequential milestones)
1. Project skeleton + `pyproject.toml` + models + CLI stub + one sample app (RSA).
2. Detector + tests (scan sample, get findings).
3. PQC backends + tests (real ML-KEM/ML-DSA round-trips pass).
4. Recommender + tests.
5. Verifier + benchmark + tests.
6. Migrator + rules + tests (migrate RSA sample to ML-KEM).
7. Reporter (JSON + Markdown/HTML).
8. Analyzer + context.
9. `pqc-migrator run` = full pipeline on a sample, end to end.
10. Add ECDSA and DH samples + rules; polish README with usage + screenshots.

## 8. CLI (target UX)
```
pqc-migrator scan       <path>        # list findings
pqc-migrator recommend  <path>        # findings + recommended PQC
pqc-migrator migrate    <path> -o out # write migrated copies
pqc-migrator verify                    # run PQC round-trip checks
pqc-migrator report     <path> -o rep # full report (json/md/html)
pqc-migrator run        <path>         # scan→recommend→migrate→verify→report
```

## 9. Acceptance criteria (what "done for 60–70%" means)
- `pqc-migrator run samples/app_rsa` executes the whole pipeline without errors.
- Detector finds the RSA/ECC/DH usages in all three sample apps.
- Recommender returns correct NIST algorithms for each.
- At least the RSA→ML-KEM migration produces a migrated file whose PQC round-trip
  passes in the verifier.
- A report (JSON + Markdown/HTML) is generated with findings, recommendations,
  verification results, and a classical-vs-PQC size/timing benchmark.
- `pytest` passes for all implemented modules.

## 10. Notes / honesty
- The "AI-assisted" migration is **rule-based** in this phase; LLM-driven migration is
  Project-II. Keep a `# TODO(project-II): LLM-assisted rewrite` marker where relevant.
- All results in the final academic report/PPT must be the **actual** numbers this tool
  produces — replace any placeholder figures once the tool runs.
