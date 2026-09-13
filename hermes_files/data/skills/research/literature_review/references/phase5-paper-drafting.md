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

Install the host LaTeX dependencies before compiling the template. The practical minimum is `latexmk`, `texlive-latex-recommended`, `texlive-latex-extra`, `texlive-fonts-recommended`, `texlive-science`, `ghostscript`, and `bibtex`.

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
