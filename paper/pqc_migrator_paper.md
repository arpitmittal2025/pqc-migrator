# From Detection to Verified Replacement: An End-to-End Framework for Post-Quantum Cryptographic Migration of Python Codebases

**Priyanshu Sen** (23BCT0040), **Vedansh Trivedi** (23BCT0056), **Arpit Mittal** (23BCI0044)
School of Computer Science and Engineering, Vellore Institute of Technology, Vellore, India
Team ID: 20106UG02

> *Insert faculty guide's name, designation and affiliation here before submission.*

---

## Abstract

Public-key cryptography based on integer factorisation and discrete logarithms underpins
the confidentiality and authenticity guarantees of practically all deployed software, and
all of it falls to a sufficiently capable quantum computer. The National Institute of
Standards and Technology closed the algorithmic side of this problem in 2024 by
standardising ML-KEM, ML-DSA and SLH-DSA, but the engineering side remains open: an
organisation holding a large codebase still has no systematic way to locate its
vulnerable cryptography, decide what each occurrence should become, change it, and
convince itself that the result still works. Existing efforts treat these as separate
concerns — discovery tools that stop at an inventory, guidance documents that describe
crypto-agility without prescribing a path, and code-transformation experiments that
produce patches nobody has executed.

This paper presents a framework that joins them into one pipeline: static detection of
quantum-vulnerable primitives, context-sensitive selection of a NIST replacement,
rule-based source rewriting onto a compatibility layer, functional verification of the
rewritten program, and automated reporting with measured cost figures. We evaluate the
detector on a purpose-built labelled benchmark of 29 Python modules containing 38
annotated cryptographic sites, and report precision of 1.00 and recall of 1.00 over the
31 sites within the prototype's stated scope, with no false alarms across six
cryptographically clean modules. On a deliberately adversarial set of seven sites reached
through wrapper libraries, string parameters and dynamic dispatch, recall is 0.00, which
delimits exactly where purely syntactic analysis stops being sufficient. Applied to three
sample applications, the pipeline migrated nine of nine detected sites and the rewritten
RSA and ECDSA applications executed successfully under real ML-KEM and ML-DSA. Measured
on our hardware, migration leaves key generation faster but inflates transmitted material
substantially: ML-KEM-768 public keys are 4.0× the size of RSA-2048's, and ML-DSA-65
signatures are 46.6× an ECDSA P-256 signature.

**Index Terms** — post-quantum cryptography, software migration, static analysis,
ML-KEM, ML-DSA, crypto-agility, program verification

---

## I. Introduction

### A. The problem is no longer which algorithm, but how to get there

For three decades the security of digital infrastructure has rested on a small number of
public-key constructions — RSA, elliptic-curve cryptography, and Diffie–Hellman — whose
hardness assumptions are specific to classical computation. Shor demonstrated in 1994
that a quantum computer able to maintain sufficient coherent operations solves both
integer factorisation and the discrete logarithm problem in polynomial time [11]. Every
one of those constructions therefore has a known expiry date; what remains uncertain is
only the date itself.

That uncertainty does not make the problem distant. Encrypted traffic captured today can
be stored and decrypted once the capability exists, an attack pattern usually described
as *harvest-now, decrypt-later* [9]. Any data whose confidentiality must outlive the arrival
of cryptographically relevant quantum hardware — medical records, identity databases,
state communications, long-lived financial instruments — is therefore already exposed,
regardless of how strong today's cryptography is against today's adversaries.

NIST completed the standardisation response in August 2024, publishing FIPS 203 (ML-KEM,
for key encapsulation) [1], FIPS 204 (ML-DSA, for digital signatures) [2] and FIPS 205
(SLH-DSA, a stateless hash-based signature scheme) [3]. High-quality implementations
followed quickly. The algorithmic question is, for practical purposes, settled.

The engineering question is not. An organisation that wishes to act on this guidance
confronts a different task entirely: finding every place its software performs
quantum-vulnerable cryptography, determining what each of those places is actually *for*,
selecting an appropriate replacement, modifying code that was often written years earlier
by people who have left, and establishing that the modified system still behaves
correctly. None of that is addressed by publishing an algorithm specification.

### B. Why this is harder than a find-and-replace

Three properties of real codebases make cryptographic migration resistant to mechanical
treatment.

*Cryptographic usage is diffuse.* Key generation, serialisation, encryption and signing
are rarely colocated. A single logical operation — establishing a session key — may touch
a key-management module, a transport module and a configuration file, each written in a
different style.

*Intent is not recorded.* A line reading `rsa.generate_private_key(...)` does not say
whether the resulting key will encrypt a session secret or sign a release artifact. The
distinction is decisive, because a key-encapsulation mechanism and a signature scheme are
not interchangeable; substituting one for the other produces code that fails, or worse,
code that appears to work while providing no meaningful guarantee.

*Replacement is not substitution.* The post-quantum primitives differ structurally from
what they replace. RSA encrypts a short message directly; ML-KEM encapsulates a shared
secret and leaves the payload to a symmetric cipher. Diffie–Hellman is symmetric, with
both parties deriving the same secret simultaneously; a KEM is directional. These are not
API differences that an adapter can hide — in the Diffie–Hellman case the surrounding
protocol itself must change.

A migration approach that ignores any of these produces either an incomplete inventory or
a patch that nobody can trust.

### C. Contributions

This paper describes the design, implementation and evaluation of a framework that treats
migration as a single pipeline rather than a collection of tools. Specifically:

1. **A purpose-aware detector.** Abstract-syntax-tree analysis locates quantum-vulnerable
   primitives in Python source and classifies each occurrence by the role it plays — key
   encapsulation, key exchange, or signature — using evidence drawn from the rest of the
   enclosing module.
2. **A context-sensitive recommendation engine.** Each finding is mapped to a specific
   NIST parameter set using the detected purpose, a configurable target security
   category, and strength signals recovered from the classical parameters, with a written
   justification attached to every decision.
3. **Rewriting onto a compatibility layer.** Source transformations redirect classical
   calls to a shim that preserves the classical object model while performing ML-KEM or
   ML-DSA operations underneath, keeping the rewrites local and auditable.
4. **Verification as a pipeline stage, not an afterthought.** The framework runs
   round-trip and negative cryptographic tests and then executes the migrated program.
   Nothing is reported as migrated unless a rule actually fired, and nothing is reported
   as working unless it ran.
5. **A labelled detection benchmark and measured results.** We publish a 29-module corpus
   with 38 expert-annotated cryptographic sites, partitioned into in-scope and
   deliberately adversarial subsets, together with the measured precision, recall and
   purpose-classification accuracy of our detector on it.

We are explicit about what this prototype does not yet do. Migration is driven by
mechanical rules; the generative-model component that would handle code our rules cannot
match is designed for but not implemented, and is discussed as future work rather than
claimed as a result.

---

## II. Background

### A. What quantum computation actually breaks

It is worth being precise, because the threat is often stated too broadly. Shor's
algorithm attacks problems with hidden periodic structure, which covers factorisation and
discrete logarithms and therefore RSA, finite-field Diffie–Hellman, and all elliptic-curve
schemes including ECDSA, ECDH, Ed25519 and X25519. Symmetric primitives are affected only
by Grover's quadratic speedup, which is answered by increasing key lengths; AES-256 and
SHA-384 remain appropriate. Consequently the migration problem is confined to public-key
cryptography — a smaller target than "all cryptography", but one that is embedded far more
deeply in application logic.

### B. The standardised replacements

**ML-KEM** (FIPS 203) is a module-lattice key-encapsulation mechanism, defined at three
parameter sets corresponding to NIST security categories 1, 3 and 5. It does not encrypt
arbitrary messages. It produces a ciphertext and a shared secret, with the payload
protected by a symmetric cipher keyed from that secret.

**ML-DSA** (FIPS 204) is a module-lattice signature scheme at categories 2, 3 and 5. It
is a drop-in replacement for ECDSA or RSA-PSS at the level of the operation, though not
at the level of message size.

**SLH-DSA** (FIPS 205) is a stateless hash-based signature scheme whose security rests
only on hash-function assumptions. Its conservative security comes at the cost of large
signatures and slow signing, making it appropriate for infrequent, long-lived signatures
such as firmware and root certificates.

Table I gives the sizes we measured for every parameter set, alongside the classical
baselines. These are not quoted figures; they are byte lengths produced by the
implementations our framework drives.

**TABLE I. MEASURED KEY AND OUTPUT SIZES (BYTES)**

| Scheme | Category | Public key | Secret key | Ciphertext / signature |
|---|---|---|---|---|
| ML-KEM-512 | 1 | 800 | 1,632 | 768 |
| ML-KEM-768 | 3 | 1,184 | 2,400 | 1,088 |
| ML-KEM-1024 | 5 | 1,568 | 3,168 | 1,568 |
| ML-DSA-44 | 2 | 1,312 | 2,560 | 2,420 |
| ML-DSA-65 | 3 | 1,952 | 4,032 | 3,309 |
| ML-DSA-87 | 5 | 2,592 | 4,896 | 4,627 |
| RSA-2048 (classical) | — | 294 | — | 256 |
| ECDSA P-256 (classical) | — | 91 | — | 71 |

Classical public keys are given in DER SubjectPublicKeyInfo encoding; ECDSA signature
length varies by one or two bytes between runs because DER encodes variable-length
integers.

### C. Crypto-agility and why it does not solve this

The standard architectural advice is crypto-agility: isolate cryptographic operations
behind an interface so that algorithms can be swapped without touching application code.
The advice is sound and we follow it in our own design. It is also, for the installed base,
unhelpful. Systems that were written with crypto-agility in mind are precisely the systems
that do not have a migration problem. The code that needs migrating is the code that
hard-wired its primitives, and recommending that it should have been written differently
does not move it forward.

---

## III. Related Work and Research Gap

Existing work clusters into four groups, each of which solves part of the problem.

**Cryptographic discovery.** Tools and guidance exist for producing a cryptographic bill
of materials — an inventory of where cryptography appears in a system. NIST's National
Cybersecurity Center of Excellence identifies discovery as the necessary first step of any
migration programme [4]. Inventory, however, is where these efforts stop. Knowing that
line 42 calls RSA does not indicate what should replace it, and produces no code.

**Standards and migration guidance.** NIST's preparatory guidance [7] and national
directives such as CNSA 2.0 establish timelines and set crypto-agility as an objective.
These documents are, by design, prescriptive about goals and silent about implementation.
They tell an organisation that it must migrate, not how to migrate a specific repository.

**Post-quantum implementations.** The Open Quantum Safe project and its liboqs library
[10] made the new primitives broadly available well before standardisation concluded, and
pure-Python implementations now exist for ML-KEM and ML-DSA [5], [6]. This work supplies
the destination of a migration without addressing the journey.

**Language models for code transformation.** A growing literature applies large language
models to source-to-source transformation tasks [8]. Results are encouraging on isolated
functions, and uniformly carry the same caveat: the output requires human verification,
because a plausible-looking patch and a correct one are indistinguishable without
execution. Applied naively to cryptographic code, where a silent failure may produce
something that runs but protects nothing, this caveat is disqualifying rather than
cautionary.

**The gap.** No existing system connects these pieces. Discovery tools do not recommend;
guidance does not transform; implementations do not migrate; transformation research does
not verify. The framework described here is an attempt to close that loop, and the
verification stage in particular is what distinguishes it: the correctness of a migrated
cryptographic system is established by running it, not by inspecting the diff.

> *Note for submission: replace the bracketed citations in this section with the specific
> papers from your literature survey, and expand the LLM paragraph with the two or three
> most relevant recent works you identified.*

---

## IV. Framework Design

### A. Pipeline structure

The framework is organised as six stages, each a separate module communicating through
explicit data structures:

```
source tree
    │
    ├─▶ (1) Detection        → list[Finding]
    ├─▶ (2) Static analysis  → import and dependency map
    ├─▶ (3) Context          → target security category, scheme preference
    ├─▶ (4) Recommendation   → list[Recommendation]
    ├─▶ (5) Migration        → migrated source tree + list[MigrationResult]
    ├─▶ (6) Verification     → check name → pass/fail
    └─▶ (7) Reporting        → JSON, Markdown, HTML + measured benchmark
```

Four record types carry state between stages. A `Finding` records a located occurrence
(file, line, algorithm family, purpose, the matched construct, and the owning library). A
`Recommendation` pairs a finding with a chosen parameter set, the governing FIPS document,
the security category, and a human-readable justification. A `MigrationResult` records
what happened to one finding, including the specific rules that fired and whether human
attention is still required. A `Report` aggregates all of the above with verification
outcomes and benchmark measurements.

Keeping these types explicit matters for a reason beyond tidiness: it makes it structurally
impossible for the reporting stage to claim an outcome that an earlier stage did not
produce.

### B. Detection

Detection is primarily syntactic but not textual. Each module is parsed into an abstract
syntax tree; call and attribute nodes are flattened into dotted names and matched against
a pattern index covering RSA, elliptic-curve and Diffie–Hellman constructs across the
`cryptography`, PyCryptodome and `ecdsa` libraries.

Two refinements proved necessary in practice.

*Alias resolution.* A module may import a primitive under another name. Matching the
written name alone misses `from ... import rsa as asym_rsa` entirely. The detector
therefore records the import table for each module and, when a dotted name does not match
directly, re-resolves its root through that table before retrying the lookup. This also
handles importing a function directly rather than its module.

*Scope of the textual fallback.* A regular-expression sweep handles modules that fail to
parse, which a purely AST-based analyser would otherwise skip in silence. An early version
ran this sweep on every module as a second opinion. Evaluation showed this to be a mistake:
on parseable files it contributed no detections the AST pass had missed, while matching
crypto names inside docstrings, string constants and import statements. The sweep is now a
genuine fallback, used only when parsing fails.

### C. Purpose classification

The detector assigns each finding one of three purposes — `kem`, `key_exchange`, or
`signature` — because the recommendation depends on it entirely.

Most constructs determine their own purpose: OAEP padding indicates key transport, PSS
padding indicates signing, `ECDH` indicates agreement. Key *generation* does not. The
pattern table must assign `rsa.generate_private_key` and `ec.generate_private_key` some
default, but the true purpose is a property of the surrounding module.

The detector therefore performs a second pass over each module's findings and reassigns
generation sites based on how the key is subsequently used: an RSA key in a module that
only signs is reclassified as a signature key, and an elliptic-curve key in a module that
only performs agreement is reclassified as key exchange. Both rules were added in response
to misclassifications surfaced by the benchmark described in Section VI.

### D. Recommendation

Recommendation combines three inputs. The *purpose* selects the family: key encapsulation
and key exchange map to ML-KEM, signatures to ML-DSA, or to SLH-DSA where a deployment
explicitly prefers hash-based signatures. The *target security category*, read from an
optional `pqc.config.json` beside the code or defaulting to category 3, selects the
parameter set. Finally, a *scoring pass* raises the target when the classical parameters
imply a stronger requirement than the configured default — an RSA modulus of 4096 bits or
a P-521 curve both push the recommendation to category 5.

Every recommendation carries a justification string naming the construct, the reason the
family was chosen, the resulting category, and any scoring signals that applied. This is
not cosmetic: a migration proposal that a security engineer cannot audit is a migration
proposal that will not be accepted.

### E. Migration and the compatibility layer

Migration never modifies the input. It writes a transformed copy of the source tree,
leaving the original untouched, which makes the entire stage trivially reversible.

Transformations are small, independent, auditable rules. Imports of supported
`cryptography` names are redirected to a shim module; RSA, EC and DH generation calls have
their argument lists replaced with the chosen algorithm identifier. Each rewritten file is
prefixed with a header recording which rules fired and which algorithms were selected.

The shim is what keeps the rewrites small. It exposes objects shaped like their classical
counterparts — `generate_private_key`, `public_key()`, `encrypt`/`decrypt`,
`sign`/`verify`, `private_bytes` — so that call sites need not change, while the operations
underneath are post-quantum. Classical arguments that have no post-quantum meaning, such
as padding modes and hash selections for signature schemes that handle their own hashing,
are accepted and ignored.

The one case where this strategy legitimately fails is instructive. RSA key transport maps
cleanly onto ML-KEM: the shim encapsulates to the recipient's key and protects the payload
with AES-256-GCM under the resulting shared secret, preserving `encrypt`/`decrypt`
semantics. Diffie–Hellman does not map cleanly, because its symmetry is essential — both
parties derive the same secret from one exchange, whereas a KEM requires one party to
encapsulate and the other to decapsulate. No adapter can hide this; the protocol must
change. The framework therefore migrates DH parameter generation, annotates each exchange
site with the required restructuring, marks the file as requiring manual review, and
declines to execute it during verification. It does not report the file as successfully
migrated.

We regard this behaviour as a design result rather than a shortcoming. A migration tool
that silently produced something plausible here would be considerably more dangerous than
one that stops and says so.

### F. Backend abstraction

All post-quantum operations pass through a single interface exposing key generation,
encapsulation, decapsulation, signing and verification. Two backends implement it: liboqs
where available, and pure-Python ML-KEM and ML-DSA otherwise. Selection is automatic and
overridable. Requesting an algorithm the active backend cannot provide — SLH-DSA on the
pure-Python backend — raises an explicit error rather than silently substituting a
different scheme.

### G. Verification

The verification stage asks two separate questions.

*Do the primitives work?* For each recommended algorithm the framework performs a full
round trip and the corresponding negative tests: that a KEM's shared secret survives
encapsulation and decapsulation, and that decapsulating with a foreign key does not
recover it; that a signature verifies, and that a tampered message and a wrong public key
are both rejected.

The negative tests carry most of the evidential weight. A verification stage that only
confirms successful paths cannot distinguish working cryptography from a stub that returns
success.

*Does the migrated program work?* The framework executes each migrated application and
records its exit status. This is the strongest available evidence that a transformation
preserved behaviour, and it is what we mean by verified replacement as opposed to proposed
replacement.

### H. Reporting

The final stage emits JSON, Markdown and HTML containing findings, recommendations with
justifications, migration outcomes, verification results, dependency analysis, and a
benchmark measured at report time on the machine generating the report. No performance
figure in the output is stored or inherited from literature.

---

## V. Implementation

The prototype is approximately 3,200 lines of Python across 26 modules, with 700 lines of
tests. It is installable as a package and driven by a single command-line interface
exposing each stage individually (`scan`, `recommend`, `migrate`, `verify`, `report`) and a
composite `run` command that executes the whole pipeline.

Post-quantum operations are provided by `kyber-py` 1.2.0 (ML-KEM) and `dilithium-py` 1.4.0
(ML-DSA) [5], [6], with liboqs supported as the preferred backend. Classical cryptography
in the sample applications and the classical benchmark baselines use PyCA `cryptography`
50.0.1. Detection relies on the Python standard library's `ast` module. The test suite
comprises 70 tests executing in approximately 3.5 seconds.

Three deliberately small sample applications accompany the framework: an RSA-OAEP session-key
transport service, an ECDSA release-signing service, and a finite-field Diffie–Hellman
handshake. They are intentionally idiomatic rather than contrived, and serve as the
end-to-end demonstration targets in Section VI-C.

---

## VI. Evaluation

We address four questions. **RQ1:** how accurately does the detector locate
quantum-vulnerable cryptography? **RQ2:** does it correctly infer what that cryptography is
for? **RQ3:** does the pipeline produce migrated code that actually runs? **RQ4:** what does
migration cost?

All measurements were taken on an Intel 12th-generation x86-64 laptop running Windows 11
and CPython 3.11.9, using the pure-Python backend.

### A. RQ1: Detection accuracy

**Benchmark construction.** No standard benchmark exists for this task, so we built one.
It comprises 29 Python modules in three groups: 18 *in-scope* modules using RSA, ECC or
Diffie–Hellman directly through the three targeted libraries; 5 *extended* modules in which
genuinely vulnerable cryptography is reached indirectly; and 6 *clean* modules containing
no vulnerable public-key cryptography at all. The clean group is essential — a detector
evaluated only on positive cases cannot be shown to be precise.

Ground truth is embedded in the corpus itself. Every line a cryptographer would flag
carries a trailing annotation naming the expected algorithm family, purpose and scope.
Because the detector's AST pass ignores comments and its fallback strips them, the labels
cannot influence the measurement. The corpus contains 38 annotated sites: 31 in scope and 7
extended.

**Scoring.** A detection is counted at (file, line, algorithm family) granularity, so a tool
is neither rewarded nor penalised for how finely it decomposes a single site —
`ec.generate_private_key(ec.SECP256R1())` counts once. Precision is computed over every
flag raised against sites of either scope, so detecting an extended site is never
penalised. Recall is reported separately for each scope.

**Results.** Table II reports the outcome.

**TABLE II. DETECTION PERFORMANCE**

| Metric | Value |
|---|---|
| Flags raised | 31 |
| Precision (all flags) | **1.000** |
| Recall, in-scope (31 sites) | **1.000** |
| F1, in-scope | **1.000** |
| Recall, extended (7 sites) | **0.000** |
| Clean modules with false alarms | 0 of 6 |

**TABLE III. IN-SCOPE PERFORMANCE BY ALGORITHM FAMILY**

| Family | Sites | Precision | Recall | F1 |
|---|---|---|---|---|
| RSA | 15 | 1.000 | 1.000 | 1.000 |
| ECC | 14 | 1.000 | 1.000 | 1.000 |
| Diffie–Hellman | 2 | 1.000 | 1.000 | 1.000 |

Within its stated scope the detector missed nothing and raised no false alarms, including
on modules specifically constructed to mislead it: one containing identifiers such as
`ECDSALogFormatter` and `generate_private_key_id` that resemble cryptography without being
cryptography, and one whose docstrings and string constants discuss `rsa.generate_private_key`
and `dh.generate_parameters` without calling them.

These numbers should be read with Section VII-A in mind. The benchmark was authored by the
same team that built the detector, and it is small. It establishes that the pattern index,
alias resolution and purpose refinement behave as designed on idiomatic code; it does not
establish that detection is a solved problem.

**The extended set is the informative result.** Recall of 0.000 across all seven
adversarial sites is not a defect to be apologised for but a measurement of where syntactic
analysis ends. The seven misses fall into three categories:

- *Algorithm selected by a value, not an API* — `jwt.encode(claims, key, algorithm="RS256")`
  performs RSA signing, but nothing in the call graph names RSA. Detecting it requires
  reasoning about the semantics of a library's string parameters.
- *Cryptography behind a wrapper library* — `paramiko.RSAKey.generate(2048)` and pyOpenSSL's
  `generate_key(crypto.TYPE_RSA, 2048)` are vulnerable but belong to libraries outside the
  prototype's declared scope. These are addressable by extending the pattern index, and are
  the cheapest of the three to fix.
- *Indirection and dynamic dispatch* — `getattr(rsa, FACTORY)` and a call through a
  module-level alias bound earlier both defeat name-based matching. Closing these requires
  dataflow analysis, or the semantic reasoning that motivates the model-assisted component
  discussed in Section VIII.

**Defects surfaced by the benchmark.** Building the benchmark was not merely a measurement
exercise; it changed the detector. The first run produced precision 0.871 and recall 0.964,
and attributing each error identified three genuine defects: the textual fallback firing on
string literals and import lines (four false positives), aliased imports being invisible
(one false negative), and elliptic-curve keys used for agreement being misclassified as
signing keys. Alias resolution, restricting the fallback to unparseable files, and the
elliptic-curve purpose refinement described in Section IV-C all originate here. A coverage
gap in Ed25519 and X25519 — elliptic-curve schemes equally broken by Shor — was also closed.
The results in Table II are post-fix, and the benchmark now runs as part of the test suite
so that the reported figures cannot regress unnoticed.

### B. RQ2: Purpose classification

Purpose was evaluated on the 31 correctly located in-scope sites against the expert
annotation. All 31 were classified correctly (accuracy 1.000), including the two cases the
per-module refinement exists for: an RSA key used exclusively for PSS signing, and an
elliptic-curve key used exclusively for ECDH agreement. Before the refinement described in
Section IV-C, the latter was classified as a signature key, which would have produced an
ML-DSA recommendation for a key-exchange site — a recommendation that is not merely
suboptimal but unusable.

### C. RQ3: End-to-end migration

Table IV summarises the complete pipeline applied to the three sample applications.

**TABLE IV. END-TO-END PIPELINE RESULTS**

| Application | Sites | Recommendation | Migrated | Manual review | Verification |
|---|---|---|---|---|---|
| RSA key transport | 4 (2 files) | ML-KEM-768, FIPS 203 | 4 / 4 | 0 | 4 / 4 passed |
| ECDSA signing | 4 (1 file) | ML-DSA-65, FIPS 204 | 4 / 4 | 0 | 5 / 5 passed |
| DH handshake | 1 (1 file) | ML-KEM-768, FIPS 203 | 1 / 1 | 1 | 3 / 3 passed |

Two observations matter more than the counts.

First, the two applications whose migrations completed were **executed** after rewriting,
and both ran successfully under real post-quantum cryptography — the RSA application
established a session key through ML-KEM encapsulation, and the ECDSA application produced
and verified an ML-DSA signature. This is the distinction between a patch and a verified
migration.

Second, the two applications received *different* recommendations from *different* FIPS
standards, derived from the purpose classification rather than from any per-project
configuration, and the ECDSA project's security parameters were additionally read from its
own configuration file. The pipeline is not specialised to a single example.

The Diffie–Hellman case behaves as designed and as described in Section IV-E: parameter
generation migrated, the exchange site annotated, the file marked for manual review, and
excluded from execution. Its three verification checks cover the backend and the ML-KEM
primitives, not the application, and the report states this rather than inflating the
result.

### D. RQ4: The cost of migration

Table V reports medians over 20 iterations per operation.

**TABLE V. MEASURED PERFORMANCE, CLASSICAL VERSUS POST-QUANTUM**

| Scheme | Keygen (ms) | Primary op (ms) | Inverse op (ms) | Public key (B) | Output (B) |
|---|---|---|---|---|---|
| ML-KEM-768 | 3.12 | encapsulate 3.54 | decapsulate 5.15 | 1,184 | 1,088 |
| RSA-2048 | 33.71 | encrypt 0.02 | decrypt 0.49 | 294 | 256 |
| ML-DSA-65 | 7.60 | sign 34.72 | verify 10.19 | 1,952 | 3,309 |
| ECDSA P-256 | 0.014 | sign 0.032 | verify 0.069 | 91 | 71 |

**Size is the real cost, and it is structural.** ML-KEM-768 public keys are 4.03× RSA-2048's
and its ciphertexts 4.25×; ML-DSA-65 signatures are 46.6× an ECDSA P-256 signature and its
public keys 21.4×. These ratios are fixed by the standards and are independent of
implementation. For a protocol that transmits a certificate chain or signs many small
messages, this is the dominant migration consideration — not computation.

**Timing figures are implementation-bound and should be read with care.** ML-KEM-768 key
generation is 10.8× faster than RSA-2048 key generation, a genuine and
implementation-independent structural advantage, since lattice key generation involves no
prime search. The ML-DSA signing figure of 34.72 ms, however, reflects a pure-Python
implementation; optimised native implementations perform the same operation in well under a
millisecond. We report the number we measured rather than one we would prefer, and we
identify it as a property of the backend rather than of ML-DSA.

RSA key generation also exhibits noticeable run-to-run variance (we observed 29–43 ms
across runs) because it searches randomly for primes. This is one reason the framework
measures at report time rather than shipping a table of constants.

---

## VII. Discussion

### A. Threats to validity

**Internal.** The benchmark was constructed by the authors of the detector. Despite labelling
by cryptographic role rather than by what the tool outputs, and despite deliberately
including adversarial and clean modules, a self-authored benchmark cannot exclude the
possibility that the corpus reflects assumptions already embedded in the implementation.
Independent evaluation is required before the in-scope figures should be treated as
characteristic.

**External.** Thirty-eight annotated sites across twenty-nine modules is small, and the
modules are short and self-contained. Production codebases are larger, less idiomatic, and
contain cryptography reached through layers of internal abstraction that our extended set
only gestures at. The in-scope results should be read as establishing correct behaviour on
clear cases, not as a projection of field performance.

**Construct.** Executing a migrated program establishes that it runs and that its
cryptographic round trips succeed. It does not establish that the migrated system's security
properties match the original's in a protocol sense — key lifetimes, session binding and
authentication context are outside what execution can confirm.

### B. Limitations

The prototype handles Python only. Migration rules cover the `cryptography` library;
PyCryptodome and `ecdsa` usage is detected and reported honestly as unmigrated rather than
silently skipped. The optimisation stage specified in the architecture exists as an
interface with no implementation. SLH-DSA is recommended where requested but requires the
liboqs backend to execute. Most significantly, migration is purely rule-driven: code whose
shape no rule matches is copied unchanged and reported as such.

---

## VIII. Conclusion and Future Work

Post-quantum migration is frequently discussed as a cryptographic problem. It is better
understood as a software-engineering problem with a cryptographic correctness criterion. The
algorithms exist and are standardised; what is missing is a reliable way to get a specific
body of existing code from where it is to where it must be, with evidence that nothing broke
along the way.

This paper described a framework that treats that transition as a single verified pipeline —
detection, purpose inference, context-sensitive recommendation, rule-based rewriting,
functional verification and reporting. On a purpose-built labelled benchmark the detector
achieved precision 1.00 and recall 1.00 over 31 in-scope sites with perfect purpose
classification and no false alarms on clean modules, while recording recall of 0.00 on a
deliberately adversarial set that marks the boundary of syntactic analysis. Applied end to
end, the pipeline migrated nine of nine detected sites across three applications, and the two
applications it migrated completely were executed successfully under real ML-KEM and ML-DSA.

Three directions follow directly from the measurements rather than from speculation.

**Model-assisted transformation for what rules cannot reach.** The extended-set results
quantify the need precisely: seven sites, in three distinct categories, that name-based
matching cannot see. A language model is a plausible instrument for two of them — semantic
parameters and wrapper libraries — and the framework is already structured to accommodate it,
with the rule engine attempted first and the model invoked only on what remains. The critical
design point is that the verification stage does not move: model-generated code would be
subject to exactly the same round-trip tests and execution requirement as rule-generated code,
which converts the usual objection to generative code transformation into a tractable one.

**Protocol-level restructuring.** The Diffie–Hellman case needs more than a better rewrite
rule; it needs the surrounding protocol to be restructured into an encapsulate/decapsulate
exchange. This is a program-transformation problem over control flow, not a substitution.

**Broader coverage and independent evaluation.** Extending the pattern index to wrapper
libraries is inexpensive and would close part of the extended set immediately. Extending
beyond Python requires per-language parsing but no architectural change. Most importantly,
the framework needs to be run against real repositories with independently established ground
truth before any claim about field effectiveness is justified.

The artifacts described here — the framework, the three sample applications, the labelled
benchmark and the evaluation harness — are available in the project repository so that the
reported numbers can be reproduced.

---

## References

> *Entries are ordered most-recent first. Verify every one against the published source
> before submission, and renumber if you add references from your own survey.*

[1] National Institute of Standards and Technology, *Module-Lattice-Based Key-Encapsulation
Mechanism Standard*, FIPS 203, Aug. 2024.

[2] National Institute of Standards and Technology, *Module-Lattice-Based Digital Signature
Standard*, FIPS 204, Aug. 2024.

[3] National Institute of Standards and Technology, *Stateless Hash-Based Digital Signature
Standard*, FIPS 205, Aug. 2024.

[4] National Cybersecurity Center of Excellence, *Migration to Post-Quantum Cryptography*,
NIST SP 1800-38, National Institute of Standards and Technology. Confirm the volume and
revision date you cite.

[5] G. Pope, "kyber-py: A pure-Python implementation of ML-KEM (FIPS 203)," software
repository, version 1.2.0.

[6] G. Pope, "dilithium-py: A pure-Python implementation of ML-DSA (FIPS 204)," software
repository, version 1.4.0.

[7] W. Barker, W. Polk, and M. Souppaya, *Getting Ready for Post-Quantum Cryptography:
Exploring Challenges Associated with Adopting and Using Post-Quantum Cryptographic
Algorithms*, NIST Cybersecurity White Paper, 2021.

[8] M. Chen et al., "Evaluating large language models trained on code," arXiv:2107.03374,
2021.

[9] M. Mosca, "Cybersecurity in an era with quantum computers: Will we be ready?," *IEEE
Security & Privacy*, vol. 16, no. 5, pp. 38-41, 2018.

[10] D. Stebila and M. Mosca, "Post-quantum key exchange for the Internet and the Open
Quantum Safe project," in *Selected Areas in Cryptography (SAC 2016)*, LNCS vol. 10532,
pp. 14-37.

[11] P. W. Shor, "Polynomial-time algorithms for prime factorization and discrete logarithms
on a quantum computer," *SIAM Journal on Computing*, vol. 26, no. 5, pp. 1484-1509, 1997.
