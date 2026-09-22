#!/usr/bin/env python3
"""Rescan a paper corpus through LightRAG and retry failed documents."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INGEST_SCRIPT = SCRIPT_DIR / "document_ingest.py"


def collect_pdfs(paths: list[str]) -> list[Path]:
    pdfs: list[Path] = []

    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()

        if path.is_dir():
            pdfs.extend(sorted(candidate for candidate in path.rglob("*.pdf") if candidate.is_file()))
            continue

        if path.is_file() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
            continue

        raise FileNotFoundError(f"Not a PDF or directory: {raw_path}")

    unique_pdfs = sorted({pdf for pdf in pdfs})
    return unique_pdfs


def run_ingest(pdf_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INGEST_SCRIPT), str(pdf_path)],
        text=True,
        capture_output=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rescan a corpus through LightRAG and retry failures until each PDF completes."
    )
    parser.add_argument("paths", nargs="+", help="PDF file(s) or directory roots to rescan")
    parser.add_argument(
        "--retry",
        type=int,
        default=1,
        help="Number of retries for each failed PDF (default: 1)",
    )
    args = parser.parse_args()

    try:
        pdfs = collect_pdfs(args.paths)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1

    if not pdfs:
        print("No PDF files found.", file=sys.stderr)
        return 1

    failures: list[Path] = []

    for index, pdf_path in enumerate(pdfs, start=1):
        success = False

        for attempt in range(1, args.retry + 2):
            print(f"[{index}/{len(pdfs)}] Scanning {pdf_path} (attempt {attempt}/{args.retry + 1})")

            completed = run_ingest(pdf_path)

            if completed.stdout:
                print(completed.stdout, end="")

            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)

            if completed.returncode == 0:
                success = True
                break

            if attempt <= args.retry:
                print(f"Retrying failed scan for {pdf_path.name}...", file=sys.stderr)

        if not success:
            failures.append(pdf_path)

    print()
    print(f"Rescan complete. Success: {len(pdfs) - len(failures)} / {len(pdfs)}")

    if failures:
        print("Failed documents:", file=sys.stderr)

        for pdf_path in failures:
            print(f"- {pdf_path}", file=sys.stderr)

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())