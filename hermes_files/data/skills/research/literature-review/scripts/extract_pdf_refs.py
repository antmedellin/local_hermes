#!/usr/bin/env python3
"""Pull the References section out of a PDF and write one reference per line.

Usage: extract_pdf_refs.py <paper.pdf> [--out documents/manifests/references_raw.txt]

Run from the project root. A worker then turns each line into year|title
for seed_references.txt.

How entries are split: it reads each line's position on the page. In most
reference lists the first line of an entry starts at the column's left edge
and the following lines are indented (hanging indent). Two-column layouts
are handled column by column. Numbered lists ([1], 1.) are also detected.
"""
import argparse
import re
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    sys.exit("pymupdf is missing. Add pymupdf to requirements.txt and rerun setup_project.sh")

HEADING = re.compile(
    r"^\s*(\d+\.?\s*)?(references|bibliography|works cited|literature cited|reference list)\s*$",
    re.I,
)
SECTION_END = re.compile(r"^\s*(appendix|appendices|supplementary material|acknowledg)", re.I)
NUMBERED = re.compile(r"^\s*(\[\d{1,3}\]|\d{1,3}\.)\s+")
MARGIN_BAND = 0.06   # top/bottom share of the page treated as running header/footer
INDENT_TOL = 2.5     # points; a line starting within this of the column edge starts an entry


def page_lines(doc):
    """Every text line as (page, column, y, x, text), in reading order."""
    out = []
    for pno, page in enumerate(doc):
        w, h = page.rect.width, page.rect.height
        mid = w / 2
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"]).strip()
                if not text:
                    continue
                x0, y0, x1, _ = line["bbox"]
                if y0 < h * MARGIN_BAND or y0 > h * (1 - MARGIN_BAND):
                    continue
                col = 1 if x0 >= mid - 5 else 0
                out.append((pno, col, round(y0, 1), round(x0, 1), text))
    out.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return out


def reference_lines(lines):
    start = None
    for i, (_, _, _, _, text) in enumerate(lines):
        if HEADING.match(text):
            start = i  # last match wins, so a table-of-contents mention is skipped
    if start is None:
        sys.exit("No References heading found. Write seed_references.txt by hand (year|title per line).")
    section = []
    for line in lines[start + 1:]:
        if SECTION_END.match(line[4]):
            break
        section.append(line)
    return section


def join(current, text):
    if not current:
        return text
    if current.endswith("-") and not current.endswith(" -"):
        return current[:-1] + text
    return current + " " + text


def split_references(section):
    numbered = sum(bool(NUMBERED.match(t[4])) for t in section) >= 3

    # Left edge of each (page, column) group
    edges = {}
    for pno, col, _, x, _ in section:
        key = (pno, col)
        edges[key] = min(edges.get(key, x), x)

    refs, current = [], ""
    for pno, col, _, x, text in section:
        if numbered:
            starts_new = bool(NUMBERED.match(text))
            text = NUMBERED.sub("", text) if starts_new else text
        else:
            starts_new = x <= edges[(pno, col)] + INDENT_TOL
        if starts_new and current:
            refs.append(current)
            current = text
        else:
            current = join(current, text)
    if current:
        refs.append(current)
    return [r for r in refs if len(r) > 20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default="documents/manifests/references_raw.txt")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_file():
        sys.exit(f"PDF not found: {pdf}")

    doc = pymupdf.open(str(pdf))
    lines = page_lines(doc)
    if sum(len(t[4]) for t in lines) < 500:
        sys.exit("This PDF has almost no text (likely scanned or printed to PDF). Get the publisher's PDF.")

    refs = split_references(reference_lines(lines))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(refs) + "\n", encoding="utf-8")

    print(f"Wrote {len(refs)} references to {out}")
    if len(refs) < 5:
        print("WARNING: fewer than 5 references found. Check references_raw.txt against the PDF.")


if __name__ == "__main__":
    main()