#!/usr/bin/env python3
"""Compile an IEEE-style survey draft and verify its final page count.

Runs the full pdflatex -> bibtex -> pdflatex -> pdflatex cycle from the
directory containing the .tex file, using absolute binary paths (`which`
can report "not found" inside minimal containers even when the binaries
are installed and on PATH -- see references/phase5-paper-drafting.md).
After each pdflatex pass, greps the log for any error ("^!") or unresolved
reference/citation ("undefined") and fails fast instead of compiling three
more times against a broken .tex file. On success, reports the actual page
count parsed from the pdflatex log (never estimated from word count) and
exits non-zero if it does not match --target-pages.

Usage:
    .venv/bin/python scripts/compile_latex.py writing/drafts/main.tex --target-pages 5
    .venv/bin/python scripts/compile_latex.py writing/drafts/main.tex  # no page check
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

BINARY_FALLBACKS = {
    "pdflatex": ["/usr/bin/pdflatex"],
    "bibtex": ["/usr/bin/bibtex"],
}

PAGE_COUNT_RE = re.compile(r"Output written on \S+\.pdf \((\d+) pages?")


def resolve_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found

    for candidate in BINARY_FALLBACKS.get(name, []):
        if Path(candidate).exists():
            return candidate

    print(
        f"Could not locate '{name}' via PATH or known fallback paths "
        f"{BINARY_FALLBACKS.get(name, [])}. Install the LaTeX toolchain "
        f"(see references/phase5-paper-drafting.md).",
        file=sys.stderr,
    )
    sys.exit(1)


def run(binary: str, args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        [binary] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout + result.stderr


def check_log_for_errors(log: str, label: str) -> list[str]:
    problems: list[str] = []

    for line in log.splitlines():
        if line.startswith("!"):
            problems.append(f"[{label}] LaTeX error: {line}")
        if "undefined" in line.lower() and ("reference" in line.lower() or "citation" in line.lower()):
            problems.append(f"[{label}] {line.strip()}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tex_path", type=Path, help="Path to the .tex file to compile")
    parser.add_argument("--target-pages", type=int, default=None, help="Expected final page count")
    args = parser.parse_args()

    tex_path = args.tex_path.resolve()
    if not tex_path.exists():
        print(f"No such file: {tex_path}", file=sys.stderr)
        return 1

    tex_dir = tex_path.parent
    tex_stem = tex_path.stem

    pdflatex = resolve_binary("pdflatex")
    bibtex = resolve_binary("bibtex")
    pdflatex_args = ["-interaction=nonstopmode", tex_path.name]

    all_problems: list[str] = []
    last_log = ""

    for label in ("pdflatex#1", "bibtex", "pdflatex#2", "pdflatex#3"):
        if label == "bibtex":
            log = run(bibtex, [tex_stem], tex_dir)
        else:
            log = run(pdflatex, pdflatex_args, tex_dir)
            last_log = log

        all_problems.extend(check_log_for_errors(log, label))

    if all_problems:
        print("Compile failed:")
        for problem in all_problems:
            print(f"- {problem}")
        return 1

    match = PAGE_COUNT_RE.search(last_log)
    if not match:
        print("Compile succeeded but could not parse the final page count from the log.", file=sys.stderr)
        return 1

    page_count = int(match.group(1))
    print(f"Compile succeeded: {tex_stem}.pdf has {page_count} page(s).")

    if args.target_pages is not None and page_count != args.target_pages:
        print(
            f"Page count mismatch: expected {args.target_pages}, got {page_count}. "
            f"Add or remove a whole subsection (not sentence-level edits) and recompile.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
