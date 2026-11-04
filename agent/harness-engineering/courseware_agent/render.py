"""슬라이드 덱 목록 페이지(slides/index.html)."""
from __future__ import annotations

import html

CSS = """
:root{--bg:#ffffff;--fg:#2b3242;--muted:#7c8598;--accent:#2e74c6;--navy:#1e2a5c;--card:#f5f8fc;--line:#d9e0ec}
@media (prefers-color-scheme:dark){:root{--bg:#10131a;--fg:#e6e9ef;--muted:#9aa3b2;--accent:#7ca7ff;--navy:#c9d5ff;--card:#171b22;--line:#2a303a}}
*{box-sizing:border-box}body{margin:0 auto;max-width:1100px;padding:32px 16px;background:var(--bg);color:var(--fg);
font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
h1{color:var(--navy);margin:0 0 4px}p.sub{color:var(--muted);margin:0 0 24px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card img{width:100%;display:block;aspect-ratio:16/9;object-fit:cover;border-bottom:1px solid var(--line);background:#fff}
.card .body{padding:12px 14px}.card h2{font-size:16px;margin:0 0 6px;color:var(--navy)}
.card .meta{font-size:13px;color:var(--muted)}.card a{color:var(--accent);margin-right:10px;font-size:14px}
"""


def render_index_html(course_title: str, subtitle: str, rows: list[dict]) -> str:
    cards = []
    for r in rows:
        thumb = f'<img src="{html.escape(r["thumb"])}" alt="">' if r.get("thumb") else ""
        links = [f'<a href="{html.escape(r["pptx"])}">PPTX</a>']
        if r.get("pdf"):
            links.append(f'<a href="{html.escape(r["pdf"])}">PDF</a>')
        links.append(f'<a href="{html.escape(r["spec"])}">명세</a>')
        links.append(f'<a href="{html.escape(r["textbook"])}">교재</a>')
        cards.append(
            f'<div class="card">{thumb}<div class="body"><h2>{html.escape(r["title"])}</h2>'
            f'<div class="meta">슬라이드 {r["count"]}장 · 검토 {html.escape(str(r.get("score", "-")))}점</div>'
            f'<div>{"".join(links)}</div></div></div>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(course_title)}</title>
<style>{CSS}</style></head><body><h1>{html.escape(course_title)}</h1><p class="sub">{html.escape(subtitle)}</p>
<div class="grid">{''.join(cards)}</div></body></html>"""
