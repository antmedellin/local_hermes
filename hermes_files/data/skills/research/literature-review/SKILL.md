---
name: literature-review
title: Literature Review and Survey Papers
description: "Discover, download, normalize, ingest, query, and synthesize research papers into survey and literature review manuscripts backed by LightRAG citations."
version: 2.0.0
author: Hermes Agent
license: MIT
dependencies: [arxiv, semanticscholar, requests, habanero, numpy, scipy, matplotlib, SciencePlots]
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, papers, literature, rag, lightrag, knowledge-graph, survey, literature-review, paper-writing]
    category: research
    related_skills: [arxiv, lightrag, research-paper-writing]
    requires_toolsets: [terminal, files, kanban]
---

# Literature Review and Survey Research Skill

Use this skill only for literature reviews, survey papers, tutorials, and related synthesis-first research writing.

This skill is not a general paper-writing pipeline.

## Default Outcome

Unless the user specifies otherwise, produce a 5-page literature review or survey draft with 15+ verified citations in the IEEE-style template used by this skill.

## Core Principles

1. Build a local corpus before writing.
2. Use LightRAG as the persistent source of truth.
3. Never invent citations from memory.
4. Write only from LightRAG query output and verified source metadata.
5. Keep the manuscript organized by themes, methods, or open problems rather than paper-by-paper summaries.
6. Keep the board explicit: one parent task, clear child tasks, one owner per task.


## Project Isolation Rules

Every literature review MUST be executed inside a newly created project directory.

Never reuse an existing project directory unless the user explicitly identifies it.

### Required Behavior

1. Generate a project slug from the research topic.

Example:

Topic:
"Event Camera Based Metrology"

Project folder:
event-camera-based-metrology

2. Create a timestamped project root.

Example:

projects/
  20260921_event-camera-based-metrology/

3. All work for the survey MUST occur within that directory.

4. Never read:
   - previous survey folders
   - previous manifests
   - previous download directories
   - previous draft folders
   - previous bibliography files

unless the user explicitly requests continuation of an existing project.

5. Before creating the project, verify that the target directory does not already exist.

If it exists:

- create a new directory with a numeric suffix

Example:

20260921_event-camera-based-metrology
20260921_event-camera-based-metrology-2
20260921_event-camera-based-metrology-3

6. Store the project directory path in the parent kanban card description.

All child tasks must use that exact path.

### Continuation Mode

Only continue an existing survey if the user explicitly provides:

- a project path
- a project name

Examples:

"Continue the event camera survey"
"Open project 20260921_event-camera-based-metrology"

Otherwise always create a new project.


## Canonical Project Layout

Create this structure inside the project folder:

```text
project/
  .venv/
  documents/
    downloads/
    renamed/
    processed/
    manifests/
  notes/
    literature/
    synthesis/
    experiments/
  writing/
    outlines/
    drafts/
    figures/
    tables/
  bibliography/
    references.bib
  templates/
  scripts/
```

## Project Environment

Always create and use a virtual environment inside the project folder, and always copy this skill's own scripts into the project (the canonical layout's `scripts/` folder does not populate itself):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install arxiv semanticscholar requests habanero numpy scipy matplotlib SciencePlots
test -x .venv/bin/python || echo "BROKEN VENV: .venv/bin/python missing/not executable — recreate with python3 -m venv .venv, do not try to work around a missing interpreter"
cp /opt/data/skills/research/literature-review/scripts/*.py scripts/
```

This skill's scripts live at `/opt/data/skills/research/literature-review/scripts/` on disk (that's what `scripts/document_ingest.py` etc. resolve to in this doc) — they are never auto-copied into a new project folder, so a project's `scripts/` directory is empty until you run the `cp` above. If a script "goes missing" partway through a task, re-run the `cp`; do not write a substitute script from scratch and do not search other directories for it.

Use the venv interpreter when running project scripts. `.venv/bin/python` **is** the interpreter — invoke it directly, never prefix it with another `python3`/`python` (`python3 .venv/bin/python script.py` runs the venv's *binary* as a text script and crashes with `SyntaxError: source code cannot contain null bytes`). Before running anything, confirm `.venv/bin/python` actually exists and runs (`.venv/bin/python --version`) — a venv created by copying/rsyncing another environment can end up missing the interpreter binary entirely while still having `pip`/site-packages; the fix is to recreate the venv with `python3 -m venv .venv`, never to invoke a system/global `python3` "just this once".

```bash
.venv/bin/python scripts/document_rag_search.py "<query>"
.venv/bin/python scripts/document_rescan.py documents/downloads/
.venv/bin/python scripts/normalize_paper_filename.py --first-author "<Author>" --year 2026 --title "<Title>" paper.pdf
.venv/bin/python scripts/smoke_test.py
```

### Script signatures (do not guess flags — these are exhaustive)

Two of the four scripts only operate on **one PDF per invocation**; loop over them instead of searching for a `--dir`/batch flag that does not exist:

| Script | Args | Batch? |
|---|---|---|
| `normalize_paper_filename.py` | positional `pdf_path`, required `--first-author`, `--year`, `--title`, optional `--dry-run` | No — one call per PDF |
| `document_ingest.py` | positional `<path/to/paper.pdf>` only | No — one call per PDF |
| `document_rescan.py` | positional `paths` (one or more files or directory roots) | Yes — pass a whole directory |
| `document_rag_search.py` | positional free-text `query`, optional `--mode`, `--json` | N/A (read-only query) |
| `build_manifest_from_arxiv_ids.py` | positional `<pdf_dir>` — prints manifest rows to stdout | Yes — one pass over a directory |

`normalize_paper_filename.py` needs the first author, year, and title as literal strings — it cannot infer them from the PDF, and **you must never fabricate them** (no `"Unknown"` author, no year guessed from an arXiv-ID prefix, no filename-as-title). If the source PDFs are already named by bare arXiv ID (e.g. `2306.14048v3.pdf`, which is what raw downloads/leaderboard exports look like), resolve the real metadata with `build_manifest_from_arxiv_ids.py` — it queries the arXiv API via the `arxiv` package (already in Project Environment) and skips (reporting on stderr, never guessing) any file it can't resolve:

```bash
.venv/bin/python scripts/build_manifest_from_arxiv_ids.py /opt/ai_files/kv_paper > documents/manifests/manifest.tsv
```

For sources that aren't on arXiv, build the manifest by hand from the Discovery phase's recorded title/authors/year — still never a placeholder. Once you have a manifest (from either path), drive the rename + ingest loop from it, e.g.:

```bash
# manifest.tsv: one line per paper — "path<TAB>first_author<TAB>year<TAB>title"
while IFS=$'\t' read -r path author year title; do
  renamed=$(.venv/bin/python scripts/normalize_paper_filename.py --first-author "$author" --year "$year" --title "$title" "$path")
  mv "$path" "$renamed"
  .venv/bin/python scripts/document_ingest.py "$renamed"
done < manifest.tsv
.venv/bin/python scripts/document_rescan.py documents/renamed/
```

Never use `python3 -c "..."` one-liners or the `execute_code` tool for corpus/manifest logic — both are blocked by this install's guardrails for autonomous kanban workers and the call will just fail. Any one-off logic (parsing filenames, building a manifest, checking installed packages) goes in a real file under `scripts/`, run via `.venv/bin/python scripts/<name>.py` through `terminal`, same as every other script here.

Install LaTeX dependencies on the host system before compiling the template. The practical minimum is `latexmk`, `texlive-latex-recommended`, `texlive-latex-extra`, `texlive-fonts-recommended`, `texlive-science`, `ghostscript`, and `bibtex`. If those packages are not available individually, install a full TeX Live distribution. See `references/phase5-paper-drafting.md` for container-specific gotchas (a lying `which`, `.bib` math-escaping errors, `\url` needing `usepackage{url}`, and the iterative page-count-check loop for hitting an exact length target). Before compiling, run `.venv/bin/python scripts/check_bib_math_escapes.py bibliography/references.bib` to catch the escaped-dollar mistake before it produces confusing `main.bbl` errors; then run `.venv/bin/python scripts/compile_latex.py writing/drafts/main.tex --target-pages 5` (or whatever length was requested) to compile and verify the page count in one step instead of manually cycling `pdflatex`/`bibtex`.

If a manifest's `build_manifest_from_arxiv_ids.py` pass leaves some PDFs unresolved (reported as `Unknown_<year>_<id>.pdf` under `documents/renamed/`), don't re-run discovery/download for those — resolve their real title/authors/year by hand (e.g. from the arXiv ID itself, cross-checked against a search) and rename them directly per the manifest format; a handful of well-known, unambiguous papers (e.g. a field-defining method already discussed elsewhere in the corpus) don't need a fresh API round-trip to confirm.

## Corpus Workflow

Follow this loop for every survey project:

1. Discover papers from legitimate sources.
2. Record title, authors, year, venue or preprint source, DOI, URL, and any accessible PDF link.
3. Download every paper you plan to cite.
4. Rename each PDF to `FirstAuthorLastName_Year_DocumentTitle.pdf`.
5. Import the PDFs into LightRAG.
6. Rescan until LightRAG reports every document is fully processed.
7. Query LightRAG for synthesis and related-work drafts.
8. Write the survey from LightRAG results and verified source metadata only.

### Discovery Sources

Use any legitimate source that improves coverage:

- arXiv
- Semantic Scholar
- Crossref
- OpenAlex
- PubMed / PubMed Central
- IEEE Xplore
- ACM Digital Library
- Springer
- publisher pages
- university repositories
- author pages

### Dynamic Pages (JS-rendered dashboards, leaderboards)

`web_extract` only sees the raw/pre-hydration HTML, so JS-heavy pages (Gradio/Streamlit Spaces, React dashboards) can come back as an empty shell (e.g. a "Refreshing" placeholder). For those, use `browser_navigate` to the URL followed by `browser_snapshot` instead of retrying `web_extract`. Do not use `browser_exec`/Browser Use mode for this — it drives the page through model-written Python and has no API for reading the accessibility tree, so it hallucinates non-existent helper modules. Set `browser.backend: "off"` in config.yaml so the model gets the discrete `browser_navigate`/`browser_snapshot`/`browser_click` tools directly.

Per-item detail panels (e.g. a leaderboard where clicking a method/model card reveals its paper link) require one `browser_click` + `browser_snapshot` per item, not a single snapshot of the whole page. Gradio panels also lag by one render cycle: the snapshot returned immediately after a click can still show the *previous* selection's details. If a panel looks stale, call `browser_snapshot` again (or click the next item and read the previous item's result from that response) before recording the link. If all you need from the page is the method/model roster or taxonomy (not every individual paper link), a single `browser_navigate` + `browser_snapshot` of the default tab is enough — don't click through every card just to confirm the roster.

### Access Fallbacks

If a source is blocked or incomplete:

1. Preserve whatever metadata you already have.
2. Search by title.
3. Search by title plus first author.
4. Search by DOI.
5. Search for a legal open-access copy.
6. Continue until you have either the paper or enough metadata to identify it cleanly.

## LightRAG Usage

Use LightRAG as the persistent research store for the survey.

LightRAG URL:

```text
http://local-hermes-lightrag-1:9621
```

Rules:

- Query LightRAG before drafting related work or synthesis sections.
- Use the citations returned by the query response.
- Do not copy unsupported claims from raw notes into the paper.
- If ingestion fails, rescan the corpus before writing continues.

## Writing Rules

### Survey Structure

Default survey structure:

1. Introduction and scope
2. Taxonomy or organizing framework
3. Thematic survey sections
4. Comparative analysis
5. Open problems and limitations
6. Conclusion

### Writing Constraints

- Keep the narrative synthesis-first.
- Prefer tables and taxonomies when they reduce repetition.
- State scope boundaries clearly.
- Identify gaps, disagreements, and trends across the literature.
- Keep citations grounded in the verified corpus.

### Related Work Drafting

- Load only the citation notes and relevant LightRAG output for the current section.
- Summarize works by theme, not by publication order.
- Cite every factual claim that depends on prior work.

### Default Length and Citation Target

- Default length: 5 pages.
- Default citation floor: 15 verified citations.

## Kanban Workflow

Use the kanban board as the primary task controller.

`kanban_*` tools (e.g. `kanban_create`) are opt-in: they only exist in the schema for dispatcher-spawned workers, or for a profile that explicitly lists `kanban` in its toolsets (`all`/`*` does not enable it). If `kanban_create` calls have no visible effect, run `hermes tools enable kanban` and `/reset` before continuing.

### Step 0: confirm the assignee before creating anything

The dispatcher **silently fails on unknown assignee names** — a task assigned to a profile that doesn't exist just sits in `ready` forever with nothing polling it ("This task has been ready for Nm but nothing has claimed it"). Never invent an assignee name (e.g. a plausible-sounding role like `development-lead`).

1. Run `hermes profile list` (or check `kanban_list` for assignees already in use) before creating the first card.
2. On a single-profile install (no extra profiles beyond `default`), assign **every** card to `default`. Do not invent per-role profile names unless those profiles actually exist on this machine.
3. If dedicated worker profiles genuinely exist, only use exactly those names.

### Task Workspace

On Docker installs, `write_file`/`patch` are hard-restricted to `HERMES_WRITE_SAFE_ROOT`. A kanban task's default `scratch` workspace lives under `$HERMES_HOME/kanban/workspaces/<id>/` — if that path is outside the write-safe root, every write in the task silently fails, the worker can't create the Canonical Project Layout at all, and it degrades to dumping one flat file wherever it *can* write. Before creating the parent card, confirm the workspace will actually be writable:

- Pin an explicit, persistent workspace with `--workspace dir:<absolute path under a writable root>` (e.g. `dir:/opt/ai_files/<project-slug>`) instead of relying on the default `scratch` workspace. This also means the project survives task completion instead of being deleted.
- If `write_file` calls still return `Write denied: ... is outside HERMES_WRITE_SAFE_ROOT`, that's an infrastructure problem, not a task problem — flag it back to the user rather than routing around it by writing loose files outside the project folder.

### Board Setup

Keep it flat and concrete — this matters more on smaller/local models, which lose track of abstract multi-step task bodies. Each card should describe **one action**, not a numbered list of phases:

Prefer running `.venv/bin/python scripts/create_kanban_board.py --topic "<topic>" --workspace-dir <path> --assignee <confirmed profile> [--corpus-done]` over creating cards one at a time by hand — it implements the exact recipe below, always links children to the parent, and (with `--corpus-done`) marks the discovery/download/ingest cards complete in one pass when the corpus was already built in a prior session, keeping the board an accurate record instead of leaving stale `ready` cards for already-finished work. The manual recipe it encodes:

1. Create one parent card for the survey (title = the survey topic, assignee = confirmed per Step 0, `--workspace dir:<path>` per Task Workspace above, `--skill research/literature-review` so the worker gets this skill's full text injected instead of having to rediscover it mid-task via trial-and-error `skill_view` calls on guessed names like `research` or `mlops/research` — the skill name is always the full `<category>/<name>` path shown by `skills_list`, never the category alone).
2. Create one child card per phase, each linked to the parent with `kanban_link`, each with a single concrete deliverable, each also carrying `--skill research/literature-review`:
   - "Set up project venv, folder structure, and copy this skill's scripts/ at `<project_dir>` (see Project Environment)"
   - "Discover and record candidate papers for `<topic>`"
   - "Download and rename PDFs into `documents/downloads/`"
   - "Ingest PDFs into LightRAG and rescan until fully processed"
   - "Query LightRAG and draft the outline"
   - "Draft manuscript sections from LightRAG output"
   - "Verify citations and compile the bibliography"
   - "Final technical review and smoke test"
3. A card's own worker **can** call `kanban_create` to spawn further child/follow-up cards mid-task (e.g. the ingest card discovers a corrupt PDF and spawns a "re-download paper X" card) — this is expected and encouraged. What must never happen is cramming multiple phases' worth of steps into a single card's body instead of creating separate cards.

### Assignees

On a single-profile install, every card's assignee is the confirmed profile from Step 0 (usually `default`) — do not fabricate role names. Only introduce named assignees (e.g. `Corpus Curator`, `LightRAG Ingestor`, `Survey Writer`) if the user has actually created those profiles (`hermes profile list` shows them); otherwise route all cards to the same confirmed profile.

### Statuses

Use these statuses only:

- not started
- in progress
- blocked
- needs review
- done

### Task Rules

- Assign each card to exactly one confirmed profile (Step 0).
- One action per card — split multi-step descriptions into separate child cards instead of listing steps in the body.
- If a claimed task's own body already contains multiple numbered phases (e.g. a legacy task created before this card was split up), the first action is to `kanban_create` one child per phase and `kanban_link` them to the current task, then work only the first child — never execute every phase inline in one run just because they're listed in one body.
- When a card is blocked, create a blocker card with the dependency and owner.
- When a card finishes and creates more work, create follow-up cards immediately (see Board Setup #3).
- When a branch is unproductive, create a decision card for rerun, expansion, reframing, or stop.
- Use specialized sub-agents only for a child card that is isolated enough to hand off cleanly.


## Survey Draft Smoke Test

The skill is test-ready when these checks pass:

1. The project venv exists, `.venv/bin/python --version` runs successfully, and can import the base Python dependencies.
2. `scripts/` contains all five scripts copied from this skill's own `scripts/` directory (not just leftover logs).
3. The paper-renaming script works on a sample PDF path.
4. The rescan script can enumerate PDFs without crashing.
5. The query script can call LightRAG or fails with a clear error.
6. The IEEE-style template compiles with BibTeX using the local bibliography file.
7. The checklist stays survey-only and contains no venue-specific sections.

## Reference Files

- [references/checklists.md](references/checklists.md) - universal survey checklist
- [references/phase5-paper-drafting.md](references/phase5-paper-drafting.md) - survey drafting workflow
- [references/experiment-patterns.md](references/experiment-patterns.md) - corpus and analysis patterns
- [templates/README.md](templates/README.md) - IEEE-style survey template usage
- [templates/IEEE_Conference_Template/IEEE.bib](templates/IEEE_Conference_Template/IEEE.bib) - bibliography file

## Scripts

- [scripts/document_ingest.py](scripts/document_ingest.py) - upload a PDF to LightRAG
- [scripts/document_rag_search.py](scripts/document_rag_search.py) - query LightRAG and preserve citations
- [scripts/document_rescan.py](scripts/document_rescan.py) - rescan a corpus and retry failures
- [scripts/normalize_paper_filename.py](scripts/normalize_paper_filename.py) - rename PDFs into the canonical pattern
- [scripts/build_manifest_from_arxiv_ids.py](scripts/build_manifest_from_arxiv_ids.py) - resolve bare-arXiv-ID PDFs into a rename/ingest manifest
- [scripts/create_kanban_board.py](scripts/create_kanban_board.py) - create the standard parent + phase-card kanban board for a survey project
- [scripts/check_bib_math_escapes.py](scripts/check_bib_math_escapes.py) - lint a `.bib` file for escaped-dollar math that breaks BibTeX styles
- [scripts/compile_latex.py](scripts/compile_latex.py) - run the full pdflatex/bibtex cycle and verify the final page count
- [scripts/smoke_test.py](scripts/smoke_test.py) - verify the local survey workflow
