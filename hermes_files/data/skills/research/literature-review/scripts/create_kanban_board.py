#!/usr/bin/env python3
"""Create the standard literature-review kanban board for a survey project.

Implements the Board Setup recipe from SKILL.md exactly: one parent card plus
one child card per phase, each carrying `--skill research/literature-review`
and pinned to a persistent, write-safe `--workspace dir:<path>` (never the
default `scratch` workspace -- see "Task Workspace" in SKILL.md). Run this
with the `hermes` CLI on PATH (inside the gateway container, where the
project directory is actually writable):

    .venv/bin/python scripts/create_kanban_board.py \\
        --topic "KV cache compression for long-context LLM inference" \\
        --workspace-dir /opt/ai_files/kv_paper \\
        --assignee default

Pass --corpus-done if discovery/download/ingest are already complete for this
project (e.g. papers were already ingested into LightRAG in a prior session)
-- those phase cards are still created, for an accurate board record, but are
immediately marked complete instead of left `ready` for a worker to redo.

Always run `hermes profile list` first and pass a real, confirmed profile
name via --assignee (see "Step 0" in SKILL.md) -- an unknown assignee makes
the dispatcher silently strand every card in `ready` forever.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

SKILL = "research/literature-review"


def phase_cards(topic: str, corpus_done: bool, target_pages: int, min_citations: int) -> list[tuple[str, str, bool]]:
    """Return (title, body, already_done) tuples for the standard phase cards."""

    return [
        (
            f"Set up project venv, folder structure, and copy skill scripts for '{topic}'",
            "Create the canonical literature-review project layout, .venv, and scripts/ "
            "copied from /opt/data/skills/research/literature-review/scripts/.",
            corpus_done,
        ),
        (
            f"Discover and record candidate papers for '{topic}'",
            "Record title, authors, year, venue/preprint source, DOI, URL, and PDF link "
            "for every candidate paper from a legitimate discovery source.",
            corpus_done,
        ),
        (
            "Download and rename PDFs into documents/downloads/ and documents/renamed/",
            "Rename each PDF to FirstAuthorLastName_Year_DocumentTitle.pdf using "
            "normalize_paper_filename.py, never fabricating author/year/title.",
            corpus_done,
        ),
        (
            "Ingest PDFs into LightRAG and rescan until fully processed",
            "Ingest every renamed PDF via document_ingest.py, then rescan with "
            "document_rescan.py until LightRAG reports full processing.",
            corpus_done,
        ),
        (
            f"Query LightRAG and draft the outline for '{topic}'",
            "Use document_rag_search.py to query themes and taxonomy candidates; write the "
            "section outline in writing/outlines/ before drafting prose.",
            False,
        ),
        (
            "Draft manuscript sections from LightRAG output",
            "Write writing/drafts/main.tex sections (introduction/scope, taxonomy, thematic "
            "sections). Cite only claims grounded in LightRAG query output and verified metadata.",
            False,
        ),
        (
            "Verify citations, populate bibliography, and compile the IEEE LaTeX template",
            f"Confirm every \\cite key resolves to a verified source and the bibliography has at "
            f"least {min_citations} verified citations. Lint the .bib with check_bib_math_escapes.py, "
            f"then compile with compile_latex.py.",
            False,
        ),
        (
            "Final technical review and smoke test",
            f"Run smoke_test.py and `compile_latex.py --target-pages {target_pages}` to confirm the "
            f"compiled PDF is exactly {target_pages} page(s) with no undefined references.",
            False,
        ),
    ]


def run_kanban(args: list[str], dry_run: bool, want_json: bool = False) -> dict:
    cmd = ["hermes", "kanban"] + args + (["--json"] if want_json else [])

    if dry_run:
        print("DRY-RUN:", " ".join(cmd))
        return {}

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        print(f"FAILED: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    if not want_json:
        return {"raw": result.stdout}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help="Survey topic (used in card titles)")
    parser.add_argument(
        "--workspace-dir",
        required=True,
        help="Absolute, write-safe project directory (e.g. /opt/ai_files/<project-slug>)",
    )
    parser.add_argument("--assignee", default="default", help="Confirmed kanban assignee/profile (see Step 0)")
    parser.add_argument(
        "--target-pages",
        type=int,
        default=5,
        help="Requested final page count, embedded in the review card body (skill default: 5)",
    )
    parser.add_argument(
        "--min-citations",
        type=int,
        default=15,
        help="Minimum verified citation count, embedded in the citation-verification card body (skill default: 15)",
    )
    parser.add_argument(
        "--corpus-done",
        action="store_true",
        help="Mark discovery/download/ingest phase cards as already complete",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print hermes kanban commands without running them")
    args = parser.parse_args()

    workspace = f"dir:{args.workspace_dir}"
    parent_title = f"Survey: {args.topic}"

    parent = run_kanban(
        ["create", parent_title, "--assignee", args.assignee, "--workspace", workspace, "--skill", SKILL],
        args.dry_run,
        want_json=True,
    )
    parent_id = parent.get("id") or parent.get("task_id")

    if not args.dry_run and not parent_id:
        print(f"Could not determine parent task id from response: {parent}", file=sys.stderr)
        return 1

    for title, body, already_done in phase_cards(args.topic, args.corpus_done, args.target_pages, args.min_citations):
        child = run_kanban(
            [
                "create", title,
                "--body", body,
                "--assignee", args.assignee,
                "--workspace", workspace,
                "--skill", SKILL,
            ],
            args.dry_run,
            want_json=True,
        )
        child_id = child.get("id") or child.get("task_id")

        if not args.dry_run and parent_id and child_id:
            run_kanban(["link", parent_id, child_id], args.dry_run)

        if already_done and not args.dry_run and child_id:
            run_kanban(
                ["complete", child_id, "--result", "Already satisfied by existing project state."],
                args.dry_run,
            )

    print("Kanban board created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
