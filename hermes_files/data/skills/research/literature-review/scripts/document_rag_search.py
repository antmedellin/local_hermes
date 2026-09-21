#!/usr/bin/env python3
"""LightRAG search script for Hermes skill integration."""

import argparse
import json
import sys
import urllib.request


LIGHTRAG_URL = "http://local-hermes-lightrag-1:9621/query"


def search(query: str, mode: str = "hybrid") -> dict:
    payload = json.dumps(
        {
            "query": query,
            "mode": mode,
            "only_need_context": True,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        LIGHTRAG_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_citations(result: dict) -> list[str]:
    citation_keys = ("citations", "references", "source_nodes", "sources")

    for key in citation_keys:
        value = result.get(key)

        if not value:
            continue

        if isinstance(value, dict):
            return [f"{k}: {v}" for k, v in value.items()]

        if isinstance(value, list):
            citations = []

            for item in value:
                if isinstance(item, dict):
                    title = item.get("title") or item.get("name") or item.get("paper_title")
                    citation = item.get("citation") or item.get("reference") or item.get("source")
                    doi = item.get("doi") or item.get("DOI")
                    url = item.get("url") or item.get("link")

                    parts = [part for part in (title, citation, doi, url) if part]
                    citations.append(" | ".join(parts) if parts else json.dumps(item, ensure_ascii=True))
                else:
                    citations.append(str(item))

            return citations

        return [str(value)]

    return []


def format_result(result: dict, show_json: bool = False) -> str:
    if show_json:
        return json.dumps(result, indent=2, ensure_ascii=True)

    response_text = result.get("response") or result.get("data") or result.get("answer") or str(result)
    lines = [str(response_text)]

    citations = extract_citations(result)

    if citations:
        lines.append("")
        lines.append("Citations:")

        for citation in citations:
            lines.append(f"- {citation}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Query LightRAG and preserve citations from the response.")
    parser.add_argument("query", nargs="*", help="Query text to send to LightRAG")
    parser.add_argument("--mode", default="hybrid", help="LightRAG query mode (default: hybrid)")
    parser.add_argument("--json", action="store_true", help="Print the raw LightRAG response as JSON")
    args = parser.parse_args()

    query = " ".join(args.query).strip()

    if not query:
        print("Usage: document_rag_search.py <query>", file=sys.stderr)
        return 1

    try:
        result = search(query, mode=args.mode)
    except Exception as error:
        print(f"LightRAG query failed: {error}", file=sys.stderr)
        return 1

    print(format_result(result, show_json=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())