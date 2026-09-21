#!/usr/bin/env python3
"""Lint a .bib file for escaped-dollar math that breaks BibTeX styles.

Writing title={H\\$_2\\$O: ...} (a literal backslash-escaped dollar sign) instead
of title={H$_2$O: ...} compiles fine as long as BibTeX never needs to render the
title as plain text -- but the moment a .bst style (e.g. ieeetr) wraps a title in
a text run like {\\em ...}, the escaped "\\$" survives verbatim into main.bbl and
produces a chain of confusing errors that all point at main.bbl, not the .bib
file itself: "! Missing $ inserted.", "! LaTeX Error: Command \\itshape invalid
in math mode.", "! Extra }, or forgotten \\endgroup." Run this before compiling
to catch the mistake at its actual source.

Usage:
    .venv/bin/python scripts/check_bib_math_escapes.py bibliography/references.bib
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Matches a literal backslash immediately followed by a dollar sign, e.g. \$
ESCAPED_DOLLAR = re.compile(r"\\\$")


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    for lineno, line in enumerate(lines, start=1):
        if ESCAPED_DOLLAR.search(line):
            errors.append(
                f"{path}:{lineno}: escaped dollar sign (\\$) found -- use a plain "
                f"$...$ math delimiter instead, or \\textsubscript{{}}/\\textsuperscript{{}}: {line.strip()!r}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bib_path", type=Path, help="Path to the .bib file to lint")
    args = parser.parse_args()

    if not args.bib_path.exists():
        print(f"No such file: {args.bib_path}", file=sys.stderr)
        return 1

    errors = check_file(args.bib_path)

    if errors:
        print("Bibliography math-escape check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {args.bib_path} has no escaped-dollar math issues.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
