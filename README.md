# PQC Migrator

**Find quantum-vulnerable cryptography in Python, replace it with the NIST post-quantum
standards, and prove the result still works by running it.**

Shor's algorithm breaks RSA, ECC and Diffie–Hellman. NIST standardised the replacements in
August 2024 — ML-KEM (FIPS 203), ML-DSA (FIPS 204) and SLH-DSA (FIPS 205). The algorithms are
settled; migrating the enormous body of existing code is not. This project automates that
migration end to end for Python, and verifies its own output by executing it.

> **Live demo:** paste Python or pick a sample, and watch the five stages run.
> **Project-I, BCSE497J**, School of Computer Science and Engineering, VIT.

---

## What it does

| Stage | What happens |
| --- | --- |
| **1 · Detect** | Parses every `.py` file into an abstract syntax tree and matches it against a pattern index covering RSA, ECC and Diffie–Hellman across `cryptography`, PyCryptodome and `ecdsa`. Resolves aliased imports; falls back to a regex sweep only for files that will not parse. |
| **2 · Classify** | Infers what each key is actually *for* — key encapsulation, key exchange or signature — from how it is used elsewhere in the module. An RSA key that only signs is a signature key, not a transport key. |
| **3 · Recommend** | Purpose picks the family, a configurable NIST category picks the parameter set, and strength signals in the original code (`key_size=4096`, `SECP521R1`) can raise it. Every decision carries a written justification. |
| **4 · Migrate** | Rewrite rules produce migrated **copies** — originals are never touched. Classical calls are redirected to a compatibility shim that keeps the classical object model while running real ML-KEM / ML-DSA underneath. |
| **5 · Verify** | Round-trip *and* negative tests (tampered message, wrong key, foreign decapsulation key), then **executes the migrated program**. |
| **6 · Report** | JSON, Markdown and HTML, including a benchmark measured at report time — no stored numbers. |

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -e ".[dev]"
pqc-migrator run samples/app_rsa -o pqc_out/app_rsa
```

Other commands:

```bash
pqc-migrator scan       samples            # list findings
pqc-migrator recommend  samples/app_ecdsa  # findings + recommended algorithm
pqc-migrator migrate    samples/app_rsa -o out
pqc-migrator verify     samples/app_rsa
pqc-migrator report     samples/app_dh -o reports
pqc-migrator backend                       # which PQC backend is active
pytest -q                                  # 70 tests
```

Useful flags: `--security-level 1..5`, `--signature-scheme ML-DSA|SLH-DSA`, `--runs N`.

## The web app

```bash
python dev_server.py        # http://127.0.0.1:8000
```

A single page that runs the whole pipeline in the browser: findings table, recommendations
with rationale, a before/after diff of the rewritten source, verification checks and a live
benchmark. Deployed on Vercel as a Python serverless function (`api/analyze.py`) plus static
assets in `public/`.

**Pasted code is analysed and rewritten but never executed.** Only the three bundled samples
are run, so the public endpoint cannot be used to execute arbitrary code.

## Results

Detection was evaluated on a purpose-built benchmark of 29 Python modules containing 38
expert-annotated sites — 18 in-scope modules, 5 deliberately adversarial, and 6 clean modules
that contain no vulnerable cryptography at all.

| Metric | Value |
| --- | --- |
| Precision (all flags) | **1.000** |
| Recall, in scope (31 sites) | **1.000** |
| Purpose classification accuracy | **1.000** |
| False alarms on 6 clean modules | **0** |
| Recall, extended adversarial set (7 sites) | **0.000** |

That last row is the honest and most informative result: it marks exactly where syntactic
analysis stops — cryptography selected by a string parameter (`jwt.encode(..., algorithm="RS256")`),
reached through wrapper libraries (paramiko, pyOpenSSL), or hidden behind dynamic dispatch.

Building the benchmark was not just measurement; it changed the detector. The first run
scored precision 0.871 / recall 0.964, and attributing each error exposed three genuine
defects — the regex fallback firing inside docstrings, aliased imports being invisible, and
EC keys used for agreement being misclassified as signing keys. All are fixed, and the
benchmark now runs inside the test suite so the numbers cannot regress unnoticed.

```bash
python evaluation/build_corpus.py && python evaluation/evaluate.py
```

### Cost of migration

Measured on the machine generating the report, medians over repeated runs:

| Scheme | Keygen (ms) | Primary op (ms) | Public key (B) | Sig / CT (B) |
| --- | --- | --- | --- | --- |
| ML-KEM-768 | 3.12 | encapsulate 3.54 | 1,184 | 1,088 |
| RSA-2048 | 33.71 | encrypt 0.02 | 294 | 256 |
| ML-DSA-65 | 7.60 | sign 34.72 | 1,952 | 3,309 |
| ECDSA P-256 | 0.014 | sign 0.032 | 91 | 71 |

Post-quantum key generation is roughly **11× faster** than RSA-2048, but keys are **4× larger**
and ML-DSA signatures **46× larger** than ECDSA. The real cost of migrating is bandwidth and
storage, not computation. Sizes are fixed by the standards; timings depend on the active
backend (the pure-Python one is far slower than liboqs).

## A limitation we do not paper over

Diffie–Hellman is **symmetric** — both parties derive the same secret from one exchange. A KEM
is directional: one side encapsulates, the other decapsulates. No compatibility shim can hide
that, because the surrounding protocol must change. The tool therefore migrates DH parameter
generation, annotates each `.exchange()` site with the restructuring required, marks the file
**manual review**, and refuses to execute it or report it as migrated.

Run `samples/app_dh` and you will see 3/5 checks rather than 5/5. That is the correct answer.

## Layout

```
pqc_migrator/          the framework
  detector/            patterns.py, scanner.py        — AST analysis
  recommender/         recommend.py                   — rule + scoring engine
  migrator/            rules.py, migrate.py, pqc_shim.py
  pqc/                 backends.py, benchmark.py      — liboqs | kyber-py/dilithium-py
  verifier/            verify.py
  reporter/            report.py + HTML template
  optimizer/           stub — Project-II
api/                   Vercel serverless function
public/                the web app
samples/               app_rsa, app_ecdsa, app_dh
evaluation/            labelled benchmark + harness
tests/                 70 tests
```

## Scope

Migration is **rule-based** in this phase. Constructs no rule matches are copied unchanged and
reported as unmigrated — never as a success. LLM-assisted rewriting of code the rules cannot
match is Project-II, and the `TODO(project-II)` markers show where it plugs in. The critical
design point is that the verification stage does not move: model-generated code would face the
same round-trip tests and execution requirement as rule-generated code.

Python only. The optimisation module is a defined interface with no implementation.

## Team

| | |
| --- | --- |
| Arpit Mittal | 23BCI0044 |
| Priyanshu Sen | 23BCT0040 |
| Vedansh Trivedi | 23BCT0056 |

Guide: **Badrinath N**, Associate Professor Grade 2, School of Computer Science and
Engineering, VIT. Team ID 20106UG02.

## References

1. NIST, *Module-Lattice-Based Key-Encapsulation Mechanism Standard*, FIPS 203, Aug. 2024.
2. NIST, *Module-Lattice-Based Digital Signature Standard*, FIPS 204, Aug. 2024.
3. NIST, *Stateless Hash-Based Digital Signature Standard*, FIPS 205, Aug. 2024.
4. P. W. Shor, "Polynomial-time algorithms for prime factorization and discrete logarithms on a
   quantum computer," *SIAM Journal on Computing*, vol. 26, no. 5, 1997.
