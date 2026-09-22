"""Download the PDFs listed in documents/manifests/manifest.tsv.

Run from the project root:
    .venv/bin/python scripts/download_papers.py

- Skips files that already exist (safe to rerun)
- Rejects responses that are not real PDFs (e.g. HTML login pages)
"""
import csv
import sys
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (literature-review downloader)"}


def main():
    root = Path.cwd()
    manifest = root / "documents" / "manifests" / "manifest.tsv"
    if not manifest.exists():
        sys.exit(f"No manifest at {manifest}. Run from the project root after discover_papers.py.")

    ok = skipped = failed = 0
    with open(manifest, newline="", encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 5:
                continue
            target, url = root / row[0], row[4]
            if target.exists() and target.stat().st_size > 0:
                print(f"exists  {target.name}")
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                r = requests.get(url, timeout=60, headers=HEADERS)
                r.raise_for_status()
                if not r.content.startswith(b"%PDF"):
                    raise ValueError("response is not a PDF (probably a web page)")
                target.write_bytes(r.content)
                print(f"saved   {target.name}")
                ok += 1
            except Exception as e:
                print(f"FAILED  {row[3]}: {e}")
                failed += 1

    print(f"\nDownloaded: {ok}   Already had: {skipped}   Failed: {failed}")


if __name__ == "__main__":
    main()