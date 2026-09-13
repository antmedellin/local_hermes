#!/usr/bin/env python3
"""Rename a downloaded paper to the first-author/year/title convention."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def sanitize_component(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


def extract_last_name(first_author: str) -> str:
    author = first_author.strip()

    if "," in author:
        return sanitize_component(author.split(",", 1)[0])

    parts = [part for part in author.split() if part]
    if not parts:
        raise ValueError("First author name is empty.")

    return sanitize_component(parts[-1])


def build_target_name(first_author: str, year: str, title: str) -> str:
    last_name = extract_last_name(first_author)
    year_component = sanitize_component(str(year))
    title_component = sanitize_component(title)

    if not year_component:
        raise ValueError("Year is empty after sanitization.")

    if not title_component:
        raise ValueError("Title is empty after sanitization.")

    return f"{last_name}_{year_component}_{title_component}.pdf"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rename a downloaded paper to FirstAuthorLastName_Year_DocumentTitle.pdf."
    )
    parser.add_argument("pdf_path", help="Path to the downloaded PDF to rename")
    parser.add_argument("--first-author", required=True, help="First author name")
    parser.add_argument("--year", required=True, help="Publication year")
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument("--dry-run", action="store_true", help="Print the rename target without changing files")
    args = parser.parse_args()

    source_path = Path(args.pdf_path).expanduser().resolve()

    if not source_path.is_file():
        print(f"File does not exist: {source_path}", file=sys.stderr)
        return 1

    if source_path.suffix.lower() != ".pdf":
        print("Only PDF files can be renamed by this utility.", file=sys.stderr)
        return 1

    target_name = build_target_name(args.first_author, args.year, args.title)
    target_path = source_path.with_name(target_name)

    print(target_path)

    if args.dry_run:
        return 0

    if target_path.exists() and target_path != source_path:
        print(f"Target already exists: {target_path}", file=sys.stderr)
        return 1

    source_path.rename(target_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())