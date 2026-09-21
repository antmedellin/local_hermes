"""Discover papers for a literature review from a seed arXiv paper.

Run from the project root:
    .venv/bin/python scripts/discover_papers.py --seed 2502.00195

Reference list source, in order:
  1. documents/manifests/seed_references.txt if it exists (lines: year|title)
  2. otherwise the seed's arXiv HTML bibliography, saved to that file

Outputs in documents/manifests/:
  manifest.tsv        papers with a free PDF (path, first author, year, title, url)
  missing_pdfs.tsv    paywalled or not found
"""
import argparse
import difflib
import re
import sys
import time
from pathlib import Path

import arxiv
import requests
from lxml import html

API = "https://api.openalex.org/works"
MATCH = 0.85
ARXIV = arxiv.Client(delay_seconds=3)


def clean(t):
    return re.sub(r"[^A-Za-z0-9 \-]", " ", t).strip()


def similar(a, b):
    a = " ".join(clean(a).lower().split())
    b = " ".join(clean(b).lower().split())
    return difflib.SequenceMatcher(None, a, b).ratio()


def safe_name(title):
    return "".join(c for c in title if c.isalnum() or c in "_-")


def seed_info(arxiv_id):
    res = list(ARXIV.results(arxiv.Search(id_list=[arxiv_id])))
    if not res:
        sys.exit(f"Seed arXiv ID not found: {arxiv_id}")
    r = res[0]
    first = r.authors[0].name if r.authors else "Unknown"
    return r.title, r.published.year, first, f"https://arxiv.org/pdf/{arxiv_id}"


def refs_from_arxiv_html(arxiv_id):
    r = requests.get(f"https://arxiv.org/html/{arxiv_id}", timeout=60)
    if r.status_code != 200:
        return []
    doc = html.fromstring(r.content)
    refs = []
    for li in doc.xpath('//li[contains(@class,"ltx_bibitem")]'):
        text = " ".join(li.text_content().split())
        m = re.search(r"[\u201c\"](.+?)[\u201d\"]", text)
        y = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", text)
        if m and y:
            refs.append((int(y.group(1)), m.group(1).strip(" ,.")))
    return refs


def load_refs(refs_file, arxiv_id):
    if refs_file.exists():
        print(f"Using reference list: {refs_file}")
        out = []
        for line in refs_file.read_text(encoding="utf-8").splitlines():
            if "|" in line:
                y, t = line.split("|", 1)
                out.append((int(y), t.strip()))
        return out
    print("Reading references from the seed's arXiv HTML page...")
    refs = refs_from_arxiv_html(arxiv_id)
    if not refs:
        sys.exit("No references found automatically. Create "
                 f"{refs_file} by hand (one 'year|title' per line) and rerun.")
    refs_file.write_text("".join(f"{y}|{t}\n" for y, t in refs), encoding="utf-8")
    print(f"Saved {len(refs)} references to {refs_file}")
    return refs


def get(params):
    for attempt in range(6):
        r = requests.get(API, params=params, timeout=30)
        if r.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  OpenAlex busy, waiting {wait}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    sys.exit("OpenAlex kept rate limiting. Wait a few minutes and rerun.")


def openalex(year, title):
    data = get({"filter": f"title.search:{clean(title)}",
                "select": "title,publication_year,authorships,best_oa_location,locations",
                "per_page": 5})
    for w in data.get("results", []):
        y = w.get("publication_year") or 0
        if abs(y - year) > 2 or similar(w.get("title") or "", title) < MATCH:
            continue
        urls = []
        best = w.get("best_oa_location") or {}
        if best.get("pdf_url"):
            urls.append(best["pdf_url"])
        for loc in w.get("locations") or []:
            if loc and loc.get("pdf_url"):
                urls.append(loc["pdf_url"])
        auth = w.get("authorships") or []
        first = auth[0]["author"]["display_name"] if auth else "Unknown"
        return w["title"], y, first, (urls[0] if urls else "")
    return None


def arxiv_lookup(title):
    try:
        for r in ARXIV.results(arxiv.Search(query=f'ti:"{clean(title)}"', max_results=3)):
            if similar(r.title, title) >= MATCH:
                first = r.authors[0].name if r.authors else "Unknown"
                return r.title, r.published.year, first, r.pdf_url
    except Exception as e:
        print(f"  arXiv error: {e}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", required=True, help="seed arXiv ID, e.g. 2502.00195")
    args = ap.parse_args()

    man = Path.cwd() / "documents" / "manifests"
    if not man.parent.exists():
        sys.exit("Run this from the project root (the folder with documents/).")
    man.mkdir(parents=True, exist_ok=True)

    s_title, s_year, s_first, s_url = seed_info(args.seed)
    print(f"Seed: {s_title} ({s_first}, {s_year})")
    found = [(f"documents/renamed/{safe_name(s_title)}.pdf", s_first, s_year, s_title, s_url)]
    missing, notfound = [], []

    for year, title in load_refs(man / "seed_references.txt", args.seed):
        res = openalex(year, title)
        time.sleep(2)
        source = "OpenAlex"
        if not res or not res[3]:
            ax = arxiv_lookup(title)
            if ax:
                res, source = ax, "arXiv"
        if not res:
            notfound.append(f"{year}\tnot found\t{title}\n")
            print(f"NOT FOUND: {title}")
            continue
        t, y, first, url = res
        if url:
            found.append((f"documents/renamed/{safe_name(t)}.pdf", first, y, t, url))
            print(f"PDF ({source}): {t}")
        else:
            missing.append(f"{y}\t{first}\t{t}\n")
            print(f"PAYWALLED: {t}")

    with open(man / "manifest.tsv", "w", encoding="utf-8") as f:
        for p, a, y, t, u in found:
            f.write(f"{p}\t{a}\t{y}\t{t}\t{u}\n")
    with open(man / "missing_pdfs.tsv", "w", encoding="utf-8") as f:
        f.writelines(missing + notfound)

    print(f"\nWith free PDF (incl. seed): {len(found)}")
    print(f"Paywalled: {len(missing)}")
    print(f"Not found: {len(notfound)}")


if __name__ == "__main__":
    main()