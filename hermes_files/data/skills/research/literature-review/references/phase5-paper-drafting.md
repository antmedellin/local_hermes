# Phase 5: Survey Drafting

**Goal**: Write a complete, publication-ready literature review or survey paper.

## Context Management for Large Projects

Large survey projects can exceed the agent's context window. Manage them proactively.

### What to Load Into Context

| Drafting Task | Load Into Context | Do Not Load |
|---------------|------------------|-------------|
| Writing Introduction | contribution statement, 15+ relevant paper abstracts | all literature notes |
| Writing Survey Sections | themed citation notes, taxonomy outline, relevant LightRAG output | raw PDFs for unrelated themes |
| Writing Open Problems | comparison table, gaps summary, contradictions between papers | full corpus |
| Revision pass | full paper draft, specific change requests | everything else |

### Principles

- `experiment_log.md` is the primary context bridge when the survey is grounded in empirical work.
- Use the kanban board as the primary work queue.
- Only spawn a specialized sub-agent when a card is isolated enough to hand off cleanly.
- Summarize, don't include raw files.
- For very large projects, create a `context/` directory with compressed summaries:

```text
context/
  contribution.md
  corpus_summary.md
  literature_map.md
  figure_inventory.md
```

## Survey Narrative

The single most critical insight is that a survey is not a list of papers. It is an organizing argument.

### Three Pillars

| Pillar | Description | Test |
|--------|-------------|------|
| The What | The taxonomy or synthesis you provide | Can you state it in one sentence? |
| The Why | Why the organization matters | Does it reveal patterns individual papers do not? |
| The So What | Why the survey is useful | Does it help readers navigate the field? |

If you cannot state the survey's contribution in one sentence, the draft is not ready.

## Survey Workflow

1. Define the survey scope and contribution.
2. Build and deduplicate the local corpus.
3. Import the corpus into LightRAG.
4. Query LightRAG to extract themes, contrasts, and open problems.
5. Draft the taxonomy or organizing framework.
6. Draft the thematic survey sections.
7. Draft the comparative analysis.
8. Draft limitations and open problems.
9. Draft the conclusion.
10. Run the smoke test and fix any failures.

## Survey Structure

Default structure:

- Introduction and scope
- Taxonomy or organizing framework
- Thematic survey sections
- Comparative analysis
- Open problems and limitations
- Conclusion

## Writing Rules

- Keep the narrative synthesis-first.
- Prefer tables and taxonomies when they reduce repetition.
- State scope boundaries clearly.
- Identify gaps, disagreements, and trends across the literature.
- Cite every factual claim that depends on prior work.

## Environment Setup

Always create and use a virtual environment inside the project folder.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install arxiv semanticscholar requests habanero numpy scipy matplotlib SciencePlots
```

Use the local venv for every project command that runs Python code:

```bash
.venv/bin/python scripts/document_rag_search.py "<query>"
.venv/bin/python scripts/document_rescan.py documents/downloads/
.venv/bin/python scripts/normalize_paper_filename.py --first-author "<Author>" --year 2026 --title "<Title>" paper.pdf
.venv/bin/python scripts/smoke_test.py
```

## LaTeX Setup

Install the host LaTeX dependencies before compiling the template. The practical minimum is `latexmk`, `texlive-latex-recommended`, `texlive-latex-extra`, `texlive-fonts-recommended`, `texlive-science`, `ghostscript`, and `bibtex`. There is no `bibtex-base` package — `bibtex` itself ships inside `texlive-latex-recommended`; do not add it to the install list or the whole `apt-get install` fails on that one bad name. Before installing, check whether the packages are already present (`apt-get install` is fast and idempotent, so just run it — a stack rebuilt from the repo's Dockerfile often already has TeX Live baked in, and the install command reports `is already the newest version` instead of downloading anything).

**`which` can lie inside a container.** `which pdflatex`/`bibtex`/`latexmk` can report "not found" via `bash -lc` even when the binaries are installed and on `PATH`, because `pdflatex` is a symlink (`/usr/bin/pdflatex -> pdftex`) and some minimal container images don't ship a `which` binary at all. Confirm with `ls -la /usr/bin/pdflatex /usr/bin/bibtex /usr/bin/latexmk` and then just invoke the absolute path (`/usr/bin/pdflatex -interaction=nonstopmode main.tex`) — don't conclude LaTeX is missing and reinstall based on `which` alone.

**Never hand-escape `$` inside a `.bib` title field.** Writing `title={H\$_2\$O: ...}` or `\$L_2\$` to get subscript math renders correctly as *math* but breaks the moment `ieeetr`/similar `.bst` styles emit that title inside a `{\em ...}` text run in the reference list — you get `! Missing $ inserted.` followed by `! LaTeX Error: Command \itshape invalid in math mode.` and `! Extra }, or forgotten \endgroup.`, all pointing at `main.bbl`, not `main.tex`, which makes the real cause (the `.bib` file) easy to miss. Use plain unescaped `$_2$` (BibTeX copies the title field verbatim, so real math delimiters are fine) or `\textsubscript{2}` instead.

**`\url{}` in a `.bib` entry needs `\usepackage{url}` (or `hyperref`) in the main document**, even though the template's default packages don't include it — a `@misc` citation for a web source (e.g. a leaderboard page) with `howpublished={\url{https://...}}` will fail with `! Undefined control sequence.` at the `\url` inside `main.bbl` otherwise.

**Hitting an exact page-count target is iterative, not a one-shot estimate.** After the first clean compile, check the actual page count with `grep -o 'Output written on main.pdf ([0-9]* pages' <pdflatex.log>` (the log line, not a guess from word count) and add or remove whole subsections — not sentence-level edits — to move by roughly a full page per subsection in a two-column IEEE conference layout. Recompile the full `pdflatex -> bibtex -> pdflatex -> pdflatex` cycle after every content change, since bibtex must rerun whenever citations move pages/citation keys change, and check the log for `^!` (any error) and `undefined` (unresolved citations/refs) each time, not just the page count.

Full recompile cycle, using absolute paths per the `which` gotcha above:

```bash
/usr/bin/pdflatex -interaction=nonstopmode main.tex
/usr/bin/bibtex main
/usr/bin/pdflatex -interaction=nonstopmode main.tex
/usr/bin/pdflatex -interaction=nonstopmode main.tex
```

## Running Project Scripts From Outside the Container

When the project's `.venv` and `scripts/` live inside a mounted volume (e.g. `/opt/ai_files/<project>` inside the `gateway` container, host-mapped from `hermes_files/ai_files/<project>`), and you are driving the workflow from outside the container (host shell, another agent), invoke the venv interpreter with its in-container absolute path through `docker compose exec -T gateway`, not a locally-installed Python:

```bash
docker compose exec -T gateway /opt/ai_files/<project>/.venv/bin/python /opt/ai_files/<project>/scripts/document_rag_search.py "<query>"
```

The `-T` flag is required for non-interactive/scripted calls (no pseudo-TTY) — omitting it fails with "the input device is not a TTY" when run from a script or subagent rather than an interactive terminal. `docker compose exec` resolves the service name (`gateway`) to whichever container actually implements it, so this works even if `docker ps` shows a container name that doesn't literally match the service name in `docker-compose.yml`.

## Board Workflow

Use the kanban board for survey work:

- Parent cards: corpus building, taxonomy, drafting, bibliography, verification.
- Child cards: search, download, rename, ingest, rescan, outline, related work, figures, final review.
- Roles: Corpus Curator, LightRAG Ingestor, Survey Writer, Citation Verifier, Template Maintainer, Build Checker, Reviewer Response Owner.
- Statuses: not started, in progress, blocked, needs review, done.

Rules:

- Assign each card to exactly one role.
- Split cross-functional work into child cards.
- When a card is blocked, create a blocker card with the dependency and owner.
- When a card finishes and creates more work, create follow-up cards immediately.
- When a branch is unproductive, create a decision card for rerun, expansion, reframing, or stop.
- Use specialized sub-agents only for a child card that is isolated enough to hand off cleanly.

## Smoke Test

Run the smoke test before treating the skill as ready:

```bash
.venv/bin/python scripts/smoke_test.py
```

The smoke test should confirm:

- required files exist
- the project venv can import the base Python dependencies
- the scripts are syntactically valid
- the template uses BibTeX and does not rely on an inline bibliography block
- the bibliography contains the template reference entries

## Reference Files

- [references/checklists.md](references/checklists.md)
- [references/experiment-patterns.md](references/experiment-patterns.md)
- [references/sources.md](references/sources.md)
- [templates/README.md](templates/README.md)
- [templates/IEEE_Conference_Template/IEEE.bib](templates/IEEE_Conference_Template/IEEE.bib)
