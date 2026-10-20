"""Render the paper Markdown into a typeset, shareable HTML page.

Run:  python paper/build_paper.py
"""

from __future__ import annotations

from pathlib import Path

import markdown

HERE = Path(__file__).parent
SOURCE = HERE / "pqc_migrator_paper.md"
OUTPUT = HERE / "pqc_migrator_paper.html"

TEMPLATE = """<title>Verified Post-Quantum Migration</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2\
?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&\
family=IBM+Plex+Sans:wght@400;500;600&\
family=IBM+Plex+Mono:wght@400&display=swap">
<style>
  :root {{
    --ground: #fbfaf8; --surface: #ffffff; --ink: #16171a; --ink-soft: #4d5158;
    --ink-faint: #81858d; --rule: #e0ddd7; --accent: #7a2f20; --accent-soft: #f6eae6;
    --mark: #f4f2ee;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --ground: #15161a; --surface: #1c1e23; --ink: #e9e8e4; --ink-soft: #a9adb4;
      --ink-faint: #7d828a; --rule: #2e3137; --accent: #e08a72; --accent-soft: #2b1d19;
      --mark: #22252a;
    }}
  }}
  :root[data-theme="dark"] {{
    --ground: #15161a; --surface: #1c1e23; --ink: #e9e8e4; --ink-soft: #a9adb4;
    --ink-faint: #7d828a; --rule: #2e3137; --accent: #e08a72; --accent-soft: #2b1d19;
    --mark: #22252a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0 1.25rem 6rem; background: var(--ground); color: var(--ink);
    font-family: "Source Serif 4", Georgia, serif; font-size: 17px; line-height: 1.68;
    -webkit-font-smoothing: antialiased;
  }}
  .paper {{ max-width: 48rem; margin: 0 auto; }}
  h1 {{
    font-family: "Source Serif 4", Georgia, serif; font-weight: 600;
    font-size: clamp(1.75rem, 4.2vw, 2.4rem); line-height: 1.18; letter-spacing: -.015em;
    margin: 3.5rem 0 1.25rem; text-wrap: balance;
  }}
  h2 {{
    font-family: "IBM Plex Sans", system-ui, sans-serif; font-weight: 600;
    font-size: .82rem; text-transform: uppercase; letter-spacing: .1em;
    color: var(--accent); margin: 3rem 0 .9rem; padding-bottom: .4rem;
    border-bottom: 1px solid var(--rule);
  }}
  h3 {{
    font-family: "IBM Plex Sans", system-ui, sans-serif; font-weight: 600;
    font-size: 1.02rem; margin: 2rem 0 .5rem; letter-spacing: -.005em;
  }}
  p {{ margin: 0 0 1.05rem; }}
  strong {{ font-weight: 600; }}
  em {{ font-style: italic; }}
  hr {{ border: none; border-top: 1px solid var(--rule); margin: 2.5rem 0; }}
  a {{ color: var(--accent); }}
  ul, ol {{ padding-left: 1.4rem; margin: 0 0 1.05rem; }}
  li {{ margin-bottom: .45rem; }}
  blockquote {{
    margin: 1.4rem 0; padding: .85rem 1.1rem; background: var(--accent-soft);
    border-left: 3px solid var(--accent); border-radius: 0 5px 5px 0;
    font-family: "IBM Plex Sans", system-ui, sans-serif; font-size: .88rem;
    color: var(--ink-soft);
  }}
  blockquote p {{ margin: 0; }}
  blockquote p + p {{ margin-top: .5rem; }}
  code {{
    font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace;
    font-size: .84em; background: var(--mark); padding: .1em .35em; border-radius: 3px;
  }}
  pre {{
    background: var(--surface); border: 1px solid var(--rule); border-radius: 7px;
    padding: 1rem 1.15rem; overflow-x: auto; margin: 0 0 1.3rem;
  }}
  pre code {{ background: none; padding: 0; font-size: .82rem; line-height: 1.55; }}
  .table-wrap {{
    overflow-x: auto; margin: 0 0 1.5rem; border: 1px solid var(--rule);
    border-radius: 7px; background: var(--surface);
  }}
  table {{ border-collapse: collapse; width: 100%; font-size: .87rem;
           font-family: "IBM Plex Sans", system-ui, sans-serif; }}
  th, td {{ text-align: left; padding: .55rem .8rem; border-bottom: 1px solid var(--rule);
            vertical-align: top; }}
  th {{ font-weight: 600; font-size: .74rem; text-transform: uppercase;
        letter-spacing: .06em; color: var(--ink-soft); background: var(--mark);
        white-space: nowrap; }}
  td {{ font-variant-numeric: tabular-nums; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  h1 + p {{ color: var(--ink-soft); }}
  @media print {{
    body {{ background: #fff; color: #000; font-size: 10.5pt; padding: 0; }}
    .paper {{ max-width: none; }}
    h2 {{ color: #000; }}
  }}
</style>
<article class="paper">
{body}
</article>
"""


def build() -> Path:
    text = SOURCE.read_text(encoding="utf-8")
    html = markdown.markdown(
        text, extensions=["tables", "fenced_code", "sane_lists", "attr_list"]
    )
    html = html.replace("<table>", '<div class="table-wrap"><table>')
    html = html.replace("</table>", "</table></div>")
    OUTPUT.write_text(TEMPLATE.format(body=html), encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size:,} bytes)")
