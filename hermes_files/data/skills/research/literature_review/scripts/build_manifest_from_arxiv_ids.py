#!/usr/bin/env python3
"""Build manifest.tsv rows from PDFs named by bare arXiv ID (e.g. 2306.14048v3.pdf).

Looks up real title/first-author/year via the arXiv API — never fabricates
metadata. A PDF whose filename has no arXiv ID, or whose ID can't be resolved,
is reported on stderr and left out of the manifest so it can be handled by hand
rather than silently getting an "Unknown" placeholder.

Usage:
  .venv/bin/python scripts/build_manifest_from_arxiv_ids.py <pdf_dir> >> manifest.tsv
"""
import re
import sys
from pathlib import Path

import arxiv

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")


def resolve(arxiv_id: str):
    search = arxiv.Search(id_list=[arxiv_id])
    result = next(arxiv.Client().results(search), None)
    if result is None:
        return None
    first_author = result.authors[0].name if result.authors else None
    if not first_author:
        return None
    return first_author, str(result.published.year), result.title


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <pdf_dir>", file=sys.stderr)
        return 1

    pdf_dir = Path(sys.argv[1]).expanduser().resolve()
    exit_code = 0

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        match = ARXIV_ID_RE.search(pdf_path.name)
        if not match:
            print(f"skip (no arXiv id in filename): {pdf_path.name}", file=sys.stderr)
            exit_code = 1
            continue

        resolved = resolve(match.group(1))
        if resolved is None:
            print(f"skip (arXiv lookup failed): {pdf_path.name}", file=sys.stderr)
            exit_code = 1
            continue

        first_author, year, title = resolved
        print(f"{pdf_path}\t{first_author}\t{year}\t{title}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
