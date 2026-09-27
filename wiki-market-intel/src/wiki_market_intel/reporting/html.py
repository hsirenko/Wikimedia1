"""HTML report (spec §25, "a polished visual report"): the Markdown report as one self-contained page.

The reports use a small, fixed Markdown subset (headings, pipe tables, bullet lists, block
quotes, images, bold, italics, code), so a short converter covers it without a new
dependency. Charts are embedded as data URIs: the file can be emailed or opened offline.
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

CSS = """
:root { --bg:#fbfaf7; --surface:#ffffff; --ink:#1f1e1c; --ink2:#52514e; --muted:#898781; --line:#e1e0d9;
        --accent:#2a78d6; --zebra:#f4f3ee; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg:#161615; --surface:#1f1e1c; --ink:#ecebe6; --ink2:#c3c2b7; --muted:#9a9890;
        --line:#3a3936; --accent:#6ea8ec; --zebra:#262523; }
}
:root[data-theme="dark"] { --bg:#161615; --surface:#1f1e1c; --ink:#ecebe6; --ink2:#c3c2b7; --muted:#9a9890;
        --line:#3a3936; --accent:#6ea8ec; --zebra:#262523; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 1.7rem; line-height:1.25; margin: 0 0 6px; }
h2 { font-size: 1.2rem; margin: 40px 0 12px; padding-top: 16px; border-top: 1px solid var(--line); }
h3 { font-size: 1rem; margin: 24px 0 8px; color: var(--ink2); }
p, li { color: var(--ink); }
.meta { color: var(--muted); font-size: .85rem; margin: 0 0 8px; }
ul { padding-left: 1.2rem; }
li { margin: 4px 0; }
code { font: .85em ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--zebra); padding: 1px 5px;
       border-radius: 4px; overflow-wrap: anywhere; }
blockquote { margin: 12px 0; padding: 8px 14px; border-left: 3px solid var(--accent); background: var(--surface);
             color: var(--ink2); }
.table { overflow-x: auto; margin: 12px 0; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: .88rem; }
th, td { padding: 7px 10px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); }
th { color: var(--ink2); font-weight: 600; background: var(--zebra); }
tr:last-child td { border-bottom: 0; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
figure { margin: 16px 0; padding: 12px; background: #ffffff; border: 1px solid var(--line); border-radius: 8px; }
figure img { display: block; width: 100%; height: auto; }
footer { margin-top: 48px; color: var(--muted); font-size: .8rem; }
"""

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])_(?!\s)(.+?)(?<!\s)_(?![\w])")
_IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")


def _inline(text: str) -> str:
    codes: list[str] = []

    def keep(m: re.Match) -> str:
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = _INLINE_CODE.sub(keep, text)
    text = html.escape(text, quote=False)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table(lines: list[str]) -> str:
    header, spec, body = _cells(lines[0]), _cells(lines[1]), [_cells(l) for l in lines[2:]]
    right = [s.endswith(":") for s in spec]

    def cell(tag: str, text: str, i: int) -> str:
        cls = ' class="num"' if i < len(right) and right[i] else ""
        return f"<{tag}{cls}>{_inline(text)}</{tag}>"

    head = "".join(cell("th", h, i) for i, h in enumerate(header))
    rows = "".join("<tr>" + "".join(cell("td", c, i) for i, c in enumerate(r)) + "</tr>" for r in body)
    return f'<div class="table"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def markdown_to_html(md: str, image=lambda src: src) -> str:
    """Body HTML for the report Markdown subset. `image(src)` maps an image path to its URL."""
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
        elif stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(_table(block) if len(block) >= 2 else f"<p>{_inline(block[0])}</p>")
        elif stripped.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(f"<li>{_inline(lines[i].strip()[2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
        elif stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + " ".join(_inline(q) for q in quote if q) + "</blockquote>")
        elif _IMAGE.match(stripped):
            alt, src = _IMAGE.match(stripped).groups()
            out.append(f'<figure><img src="{html.escape(image(src))}" alt="{html.escape(alt)}"></figure>')
            i += 1
        elif stripped.startswith("_") and stripped.endswith("_") and len(stripped) > 2:
            out.append(f'<p class="meta">{_inline(stripped[1:-1])}</p>')
            i += 1
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||- |>|!\[)", lines[i].strip()):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)


def _data_uri(path: Path) -> str | None:
    if not path.is_file():
        return None
    kind = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg"}.get(path.suffix.lower(), "image/png")
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def page(md: str, base_dir: Path, lang: str = "en", footer: str = "") -> str:
    """A complete, self-contained HTML page. Images next to the report are embedded."""
    body = markdown_to_html(md, image=lambda src: _data_uri(Path(base_dir) / src) or src)
    first = re.search(r"^#\s+(.*)$", md, flags=re.MULTILINE)
    title = html.escape(first.group(1).strip() if first else "Wikipedia market intelligence report")
    foot = f"<footer>{html.escape(footer)}</footer>" if footer else ""
    return (f'<!doctype html>\n<html lang="{html.escape(lang)}">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{title}</title>\n'
            f"<style>{CSS}</style>\n</head>\n<body>\n<main>\n{body}\n{foot}\n</main>\n</body>\n</html>\n")


def write(md_path: Path, lang: str = "en", footer: str = "") -> Path:
    """report.md -> report.html in the same folder."""
    md_path = Path(md_path)
    out = md_path.with_suffix(".html")
    out.write_text(page(md_path.read_text("utf-8"), md_path.parent, lang, footer), "utf-8")
    return out
