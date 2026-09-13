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

Always create and use a virtual environment inside the project folder.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install arxiv semanticscholar requests habanero numpy scipy matplotlib SciencePlots
```

Use the venv interpreter when running project scripts:

```bash
.venv/bin/python scripts/document_rag_search.py "<query>"
.venv/bin/python scripts/document_rescan.py documents/downloads/
.venv/bin/python scripts/normalize_paper_filename.py --first-author "<Author>" --year 2026 --title "<Title>" paper.pdf
.venv/bin/python scripts/smoke_test.py
```

Install LaTeX dependencies on the host system before compiling the template. The practical minimum is `latexmk`, `texlive-latex-recommended`, `texlive-latex-extra`, `texlive-fonts-recommended`, `texlive-science`, `ghostscript`, and `bibtex`. If those packages are not available individually, install a full TeX Live distribution.

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

### Board Setup

Create:

- one parent card for the survey
- parent cards for corpus building, synthesis, drafting, bibliography, and verification
- child cards for search, download, rename, ingest, rescan, outline, related work, figures, and final review

### Assignees

Create role-based assignees at the start of the project:

- Corpus Curator
- LightRAG Ingestor
- Survey Writer
- Citation Verifier
- Template Maintainer
- Build Checker
- Reviewer Response Owner

### Statuses

Use these statuses only:

- not started
- in progress
- blocked
- needs review
- done

### Task Rules

- Assign each card to exactly one role.
- Split cross-functional work into child cards.
- When a card is blocked, create a blocker card with the dependency and owner.
- When a card finishes and creates more work, create follow-up cards immediately.
- When a branch is unproductive, create a decision card for rerun, expansion, reframing, or stop.
- Use specialized sub-agents only for a child card that is isolated enough to hand off cleanly.

## Survey Draft Smoke Test

The skill is test-ready when these checks pass:

1. The project venv exists and can import the base Python dependencies.
2. The paper-renaming script works on a sample PDF path.
3. The rescan script can enumerate PDFs without crashing.
4. The query script can call LightRAG or fails with a clear error.
5. The IEEE-style template compiles with BibTeX using the local bibliography file.
6. The checklist stays survey-only and contains no venue-specific sections.

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
- [scripts/smoke_test.py](scripts/smoke_test.py) - verify the local survey workflow
