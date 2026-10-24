"""Generate the report's figures as PNGs.

Diagrams are drawn rather than hand-sketched so they stay consistent with the
implementation, and the result charts are plotted from the measured numbers in
evaluation/paper_data.json and evaluation/results.json.

Run:  python report/make_diagrams.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).parent
FIGURES = HERE / "figures"
FIGURES.mkdir(exist_ok=True)
DATA = HERE.parent / "evaluation"

INK = "#1b1f24"
EDGE = "#44506a"
FILL = "#eef2f8"
ACCENT = "#1f4e79"
ACCENT_FILL = "#dce8f5"
WARN_FILL = "#fbeedd"
PQC = "#1f4e79"
CLASSICAL = "#b07d3a"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "savefig.dpi": 220,
    "savefig.bbox": "tight",
    "figure.facecolor": "white",
})


def box(ax, x, y, w, h, text, *, fill=FILL, edge=EDGE, size=8.5, bold=False, radius=0.02):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.004,rounding_size={radius}",
        linewidth=1.0, edgecolor=edge, facecolor=fill))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=size, color=INK, fontweight="bold" if bold else "normal",
            linespacing=1.4)


def arrow(ax, start, end, *, style="-|>", colour=EDGE, dashed=False, rad=0.0):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle=style, mutation_scale=11, linewidth=1.0,
        color=colour, linestyle="--" if dashed else "-",
        connectionstyle=f"arc3,rad={rad}", shrinkA=1, shrinkB=1))


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    return fig, ax


def save(fig, name):
    path = FIGURES / name
    fig.savefig(path)
    plt.close(fig)
    print(f"  {name}")


# --------------------------------------------------------------------- 4.1
def architecture():
    fig, ax = canvas(7.4, 4.6)
    box(ax, 0.02, 0.855, 0.19, 0.10, "Target Python\nproject", fill="#ffffff", bold=True)
    box(ax, 0.02, 0.455, 0.19, 0.095, "pqc.config.json\n(optional)", fill="#ffffff")
    box(ax, 0.02, 0.055, 0.19, 0.10, "Migrated\nsource tree", fill="#ffffff", bold=True)

    stages = [
        ("1. Detector\nAST + regex fallback", 0.715),
        ("2. Static Analyzer\nimports, dependencies", 0.595),
        ("3. Context Loader\nsecurity level, scheme", 0.455),
        ("4. Recommender\nrule + scoring engine", 0.335),
        ("5. Migrator\nrewrite rules + shim", 0.215),
        ("6. Verifier\nround-trip + execution", 0.065),
    ]
    for label, y in stages:
        box(ax, 0.25, y, 0.38, 0.092, label, fill=ACCENT_FILL, edge=ACCENT, size=8.2)

    for i in range(len(stages) - 1):
        arrow(ax, (0.44, stages[i][1]), (0.44, stages[i + 1][1] + 0.092))

    arrow(ax, (0.115, 0.855), (0.30, 0.807))
    arrow(ax, (0.21, 0.502), (0.25, 0.501))
    arrow(ax, (0.30, 0.215), (0.115, 0.155))

    box(ax, 0.68, 0.45, 0.30, 0.30,
        "PQC Backend Abstraction\n\nliboqs\nkyber-py / dilithium-py\n\n"
        "ML-KEM (FIPS 203)\nML-DSA (FIPS 204)",
        fill="#f3f0e8", edge="#8a7a52", size=7.8)
    arrow(ax, (0.63, 0.261), (0.70, 0.50), dashed=True, rad=0.20)
    arrow(ax, (0.63, 0.111), (0.72, 0.46), dashed=True, rad=0.14)

    box(ax, 0.68, 0.055, 0.30, 0.26,
        "7. Reporter\n\nreport.json\nreport.md\nreport.html\n\n+ measured benchmark",
        fill=WARN_FILL, edge="#9a7340", size=7.8)
    arrow(ax, (0.63, 0.090), (0.68, 0.150))
    save(fig, "fig_4_1_architecture.png")


# --------------------------------------------------------------------- 4.2
def dfd_level0():
    fig, ax = canvas(6.4, 2.3)
    box(ax, 0.02, 0.38, 0.17, 0.24, "Developer /\nSecurity\nEngineer", fill="#ffffff", bold=True)
    ax.add_patch(Circle((0.5, 0.5), 0.14, facecolor=ACCENT_FILL, edgecolor=ACCENT, linewidth=1.1))
    ax.text(0.5, 0.5, "0\nPQC Migration\nFramework", ha="center", va="center",
            fontsize=8.5, color=INK, linespacing=1.4)
    box(ax, 0.80, 0.56, 0.18, 0.18, "Migrated\ncode", fill="#ffffff")
    box(ax, 0.80, 0.26, 0.18, 0.18, "Migration\nreport", fill="#ffffff")

    arrow(ax, (0.19, 0.55), (0.36, 0.55)); ax.text(0.27, 0.60, "source path", fontsize=7.5, ha="center")
    arrow(ax, (0.19, 0.45), (0.36, 0.45)); ax.text(0.27, 0.38, "config", fontsize=7.5, ha="center")
    arrow(ax, (0.64, 0.56), (0.80, 0.63))
    arrow(ax, (0.64, 0.44), (0.80, 0.37))
    save(fig, "fig_4_2_dfd_level0.png")


def dfd_level1():
    fig, ax = canvas(7.2, 2.6)
    nodes = [
        ("1.0\nDetect", 0.06), ("2.0\nRecommend", 0.25),
        ("3.0\nMigrate", 0.44), ("4.0\nVerify", 0.63), ("5.0\nReport", 0.82),
    ]
    for label, x in nodes:
        ax.add_patch(Circle((x + 0.07, 0.62), 0.072, facecolor=ACCENT_FILL,
                            edgecolor=ACCENT, linewidth=1.0))
        ax.text(x + 0.07, 0.62, label, ha="center", va="center", fontsize=7.8, linespacing=1.4)
    for i in range(len(nodes) - 1):
        arrow(ax, (nodes[i][1] + 0.142, 0.62), (nodes[i + 1][1] + 0.0, 0.62))
    labels = ["findings", "recommend-\nations", "migration\nresults", "check\nresults"]
    for i, text in enumerate(labels):
        ax.text(nodes[i][1] + 0.175, 0.78, text, fontsize=7, ha="center", linespacing=1.3)

    for x, text in ((0.06, "D1  Pattern index"), (0.44, "D2  Rewrite rules"),
                    (0.63, "D3  PQC backend")):
        box(ax, x, 0.17, 0.26, 0.10, text, fill="#f3f0e8", edge="#8a7a52", size=7.8)
        arrow(ax, (x + 0.13, 0.27), (x + 0.11, 0.55), dashed=True)
    save(fig, "fig_4_3_dfd_level1.png")


def use_case():
    fig, ax = canvas(6.4, 4.0)
    ax.add_patch(FancyBboxPatch((0.26, 0.04), 0.52, 0.92,
                 boxstyle="round,pad=0.004,rounding_size=0.01",
                 linewidth=1.0, edgecolor=EDGE, facecolor="#fafbfd"))
    ax.text(0.52, 0.92, "PQC Migration Framework", ha="center", fontsize=9, fontweight="bold")

    cases = ["Scan project for\nclassical crypto", "Recommend NIST\nPQC algorithm",
             "Migrate source\ncode", "Verify PQC\nround-trips",
             "Execute migrated\napplication", "Generate migration\nreport"]
    ys = [0.80, 0.665, 0.53, 0.395, 0.26, 0.125]
    for label, y in zip(cases, ys):
        ax.add_patch(FancyBboxPatch((0.32, y - 0.045), 0.40, 0.09,
                     boxstyle="round,pad=0.003,rounding_size=0.045",
                     linewidth=0.9, edgecolor=ACCENT, facecolor=ACCENT_FILL))
        ax.text(0.52, y, label, ha="center", va="center", fontsize=8, linespacing=1.35)

    def actor(x, y, name):
        ax.add_patch(Circle((x, y + 0.055), 0.016, fill=False, edgecolor=INK, linewidth=1.0))
        ax.plot([x, x], [y + 0.039, y - 0.005], color=INK, linewidth=1.0)
        ax.plot([x - 0.025, x + 0.025], [y + 0.028, y + 0.028], color=INK, linewidth=1.0)
        ax.plot([x, x - 0.022], [y - 0.005, y - 0.045], color=INK, linewidth=1.0)
        ax.plot([x, x + 0.022], [y - 0.005, y - 0.045], color=INK, linewidth=1.0)
        ax.text(x, y - 0.075, name, ha="center", fontsize=8, linespacing=1.3)

    actor(0.11, 0.62, "Developer")
    actor(0.11, 0.25, "Security\nEngineer")
    actor(0.90, 0.33, "PQC\nBackend")

    for y in ys[:4]:
        arrow(ax, (0.145, 0.62), (0.32, y), colour="#6b7484")
    for y in ys[3:]:
        arrow(ax, (0.145, 0.25), (0.32, y), colour="#6b7484")
    for y in (ys[1], ys[3], ys[4]):
        arrow(ax, (0.865, 0.33), (0.72, y), colour="#6b7484", dashed=True)
    save(fig, "fig_4_4_use_case.png")


def class_diagram():
    fig, ax = canvas(7.2, 4.4)

    def cls(x, y, w, h, title, body):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                     boxstyle="square,pad=0.003", linewidth=1.0,
                     edgecolor=EDGE, facecolor="#ffffff"))
        ax.add_patch(FancyBboxPatch((x, y + h - 0.062), w, 0.062,
                     boxstyle="square,pad=0.003", linewidth=1.0,
                     edgecolor=EDGE, facecolor=ACCENT_FILL))
        ax.text(x + w / 2, y + h - 0.031, title, ha="center", va="center",
                fontsize=8.2, fontweight="bold")
        ax.text(x + 0.012, y + h - 0.078, body, ha="left", va="top",
                fontsize=7.2, linespacing=1.55, family="monospace")

    cls(0.02, 0.60, 0.27, 0.33, "Finding",
        "+ file: str\n+ line: int\n+ algorithm: str\n+ purpose: str\n"
        "+ matched: str\n+ library: str\n+ detector: str")
    cls(0.36, 0.60, 0.29, 0.33, "Recommendation",
        "+ finding: Finding\n+ pqc_algorithm: str\n+ nist_standard: str\n"
        "+ nist_level: int\n+ rationale: str")
    cls(0.70, 0.60, 0.28, 0.33, "MigrationResult",
        "+ finding: Finding\n+ migrated_file: str\n+ changed: bool\n"
        "+ manual_review: bool\n+ rules_applied: list")
    cls(0.36, 0.30, 0.29, 0.22, "Report",
        "+ findings: list\n+ recommendations: list\n+ migrations: list\n"
        "+ verification: dict\n+ benchmark: dict")
    cls(0.02, 0.05, 0.27, 0.19, "Scanner",
        "+ scan_path()\n+ scan_source()\n- _refine_purpose()")
    cls(0.36, 0.05, 0.29, 0.19, "Migrator",
        "+ migrate_path()\n+ summarize()\n- apply_rules()")
    cls(0.70, 0.05, 0.28, 0.19, "PQCBackend",
        "+ kem_keypair()\n+ kem_encapsulate()\n+ sig_sign()\n+ sig_verify()")

    arrow(ax, (0.29, 0.76), (0.36, 0.76), style="-|>")
    arrow(ax, (0.65, 0.76), (0.70, 0.76), style="-|>")
    arrow(ax, (0.50, 0.60), (0.50, 0.52), style="-|>")
    arrow(ax, (0.16, 0.24), (0.16, 0.60), style="-|>", dashed=True)
    arrow(ax, (0.50, 0.24), (0.50, 0.30), style="-|>", dashed=True)
    arrow(ax, (0.84, 0.24), (0.84, 0.60), style="-|>", dashed=True)
    save(fig, "fig_4_5_class.png")


def sequence_diagram():
    fig, ax = canvas(7.2, 4.6)
    actors = ["User\n(CLI)", "Detector", "Recommender", "Migrator", "Verifier", "Reporter"]
    xs = [0.07, 0.24, 0.41, 0.58, 0.75, 0.93]
    for name, x in zip(actors, xs):
        box(ax, x - 0.065, 0.90, 0.13, 0.075, name, fill=ACCENT_FILL, edge=ACCENT, size=7.8)
        ax.plot([x, x], [0.90, 0.06], color="#9aa3b2", linewidth=0.8, linestyle=(0, (4, 3)))

    steps = [
        (0, 1, "run(path)", 0.845),
        (1, 0, "list[Finding]", 0.785),
        (0, 2, "recommend(findings, context)", 0.725),
        (2, 0, "list[Recommendation]", 0.665),
        (0, 3, "migrate(recommendations)", 0.605),
        (3, 3, "apply rewrite rules, copy tree", 0.545),
        (3, 0, "list[MigrationResult]", 0.485),
        (0, 4, "verify(recommendations, migrations)", 0.425),
        (4, 4, "KEM / signature round-trips", 0.365),
        (4, 4, "execute migrated application", 0.305),
        (4, 0, "dict[check -> pass/fail]", 0.245),
        (0, 5, "build_report(...)", 0.185),
        (5, 0, "report.json / .md / .html", 0.125),
    ]
    for src, dst, label, y in steps:
        if src == dst:
            x = xs[src]
            ax.add_patch(FancyBboxPatch((x, y - 0.018), 0.055, 0.036,
                         boxstyle="square,pad=0", linewidth=0.9,
                         edgecolor=EDGE, facecolor="none"))
            arrow(ax, (x + 0.055, y + 0.016), (x + 0.004, y - 0.016))
            ax.text(x + 0.07, y, label, fontsize=7.2, va="center")
        else:
            back = dst < src
            arrow(ax, (xs[src], y), (xs[dst], y), dashed=back)
            ax.text((xs[src] + xs[dst]) / 2, y + 0.016, label,
                    fontsize=7.2, ha="center", style="italic" if back else "normal")
    save(fig, "fig_4_6_sequence.png")


# --------------------------------------------------------------------- 7.x
def size_chart():
    bench = json.loads((DATA / "paper_data.json").read_text(encoding="utf-8"))["bench"]
    labels = ["RSA-2048\n(classical)", "ML-KEM-768\n(PQC)", "ECDSA-P256\n(classical)", "ML-DSA-65\n(PQC)"]
    keys = ["RSA-2048", "ML-KEM-768", "ECDSA-P256", "ML-DSA-65"]
    pub = [bench[k]["pubkey_bytes"] for k in keys]
    out = [bench[k]["sig_or_ct_bytes"] for k in keys]
    colours = [CLASSICAL, PQC, CLASSICAL, PQC]

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9))
    for ax, values, title in ((axes[0], pub, "Public key size"),
                              (axes[1], out, "Ciphertext / signature size")):
        bars = ax.bar(labels, values, color=colours, edgecolor="#2b3340", linewidth=0.7, width=0.62)
        ax.set_title(title, fontsize=9.5, pad=8)
        ax.set_ylabel("bytes", fontsize=8.5)
        ax.tick_params(labelsize=7.6)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.6)
        ax.set_axisbelow(True)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value * 1.02, f"{value:,}",
                    ha="center", va="bottom", fontsize=7.6)
        ax.set_ylim(0, max(values) * 1.18)
    fig.tight_layout()
    save(fig, "fig_7_1_sizes.png")


def timing_chart():
    bench = json.loads((DATA / "paper_data.json").read_text(encoding="utf-8"))["bench"]
    keys = ["RSA-2048", "ML-KEM-768", "ECDSA-P256", "ML-DSA-65"]
    labels = ["RSA-2048", "ML-KEM-768", "ECDSA-P256", "ML-DSA-65"]
    keygen = [bench[k]["keygen_ms"] for k in keys]
    op = [bench[k]["op_ms"] for k in keys]

    fig, ax = plt.subplots(figsize=(6.6, 2.9))
    x = range(len(labels))
    ax.bar([i - 0.19 for i in x], keygen, width=0.37, label="key generation",
           color=ACCENT, edgecolor="#2b3340", linewidth=0.7)
    ax.bar([i + 0.19 for i in x], op, width=0.37, label="primary operation",
           color="#9db8d6", edgecolor="#2b3340", linewidth=0.7)
    ax.set_yscale("log")
    ax.set_ylabel("milliseconds (log scale)", fontsize=8.5)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=8)
    ax.tick_params(labelsize=7.6)
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    for i, (a, b) in enumerate(zip(keygen, op)):
        ax.text(i - 0.19, a * 1.12, f"{a:g}", ha="center", fontsize=7)
        ax.text(i + 0.19, b * 1.12, f"{b:g}", ha="center", fontsize=7)
    fig.tight_layout()
    save(fig, "fig_7_2_timing.png")


if __name__ == "__main__":
    print("writing figures:")
    architecture()
    dfd_level0()
    dfd_level1()
    use_case()
    class_diagram()
    sequence_diagram()
    size_chart()
    timing_chart()
    print(f"-> {FIGURES}")
