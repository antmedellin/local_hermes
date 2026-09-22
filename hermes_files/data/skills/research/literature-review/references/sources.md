# Source Bibliography

This document lists authoritative sources and tools used to build and run the literature-review skill.

---

## Origin & Attribution

The writing philosophy, citation verification workflow, and reference materials in this skill were originally compiled by **[Orchestra Research](https://github.com/orchestra-research)** as the `ml-paper-writing` skill, then integrated into hermes-agent and expanded into the current survey workflow.

---

## Writing Philosophy & Guides

### Primary Sources

| Source | Author | URL | Key Contribution |
|--------|--------|-----|------------------|
| **Highly Opinionated Advice on How to Write ML Papers** | Neel Nanda | [Alignment Forum](https://www.alignmentforum.org/posts/eJGptPbbFPZGLpjsp/highly-opinionated-advice-on-how-to-write-ml-papers) | Narrative framing, scope discipline, synthesis-first writing |
| **How to Write ML Papers** | Sebastian Farquhar (DeepMind) | [Blog](https://sebastianfarquhar.com/on-research/2024/11/04/how_to_write_ml_papers/) | Concise abstract formulas and section planning |
| **A Survival Guide to a PhD** | Andrej Karpathy | [Blog](http://karpathy.github.io/2016/09/07/phd/) | Practical writing and iteration mindset |
| **Heuristics for Scientific Writing** | Zachary Lipton (CMU) | [Blog](https://www.approximatelycorrect.com/2018/01/29/heuristics-technical-scientific-writing-machine-learning-perspective/) | Word choice, clarity, section balance |
| **Advice for Authors** | Jacob Steinhardt (UC Berkeley) | [Blog](https://jsteinhardt.stat.berkeley.edu/blog/advice-for-authors) | Precision and terminology discipline |
| **Easy Paper Writing Tips** | Ethan Perez (Anthropic) | [Blog](https://ethanperez.net/easy-paper-writing-tips/) | Micro-level clarity and editing tactics |

### Foundational Scientific Writing

| Source | Author | URL | Key Contribution |
|--------|--------|-----|------------------|
| **The Science of Scientific Writing** | Gopen & Swan | [PDF](https://cseweb.ucsd.edu/~swanson/papers/science-of-writing.pdf) | Topic/stress positions, old-before-new |
| **Summary of Science of Scientific Writing** | Lawrence Crowl | [Summary](https://www.crowl.org/Lawrence/writing/GopenSwan90.html) | Condensed overview of reader expectations |

### Survey-Specific Resources

| Source | URL | Key Contribution |
|--------|-----|------------------|
| Survey structure patterns | [paper-types.md](paper-types.md) | Survey, benchmark, theory, and position paper outlines |
| Survey drafting workflow | [phase5-paper-drafting.md](phase5-paper-drafting.md) | Context management and drafting loop |
| Experiment patterns for survey-backed claims | [experiment-patterns.md](experiment-patterns.md) | Corpus organization and analysis patterns |

---

## Citation APIs & Tools

### APIs

| API | Documentation | Best For |
|-----|---------------|----------|
| **Semantic Scholar** | [Docs](https://api.semanticscholar.org/api-docs/) | Paper metadata, citation graphs |
| **CrossRef** | [Docs](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | DOI lookup, BibTeX retrieval |
| **arXiv** | [Docs](https://info.arxiv.org/help/api/basics.html) | Preprints and PDF access |
| **OpenAlex** | [Docs](https://docs.openalex.org/) | Open metadata and bulk access |

### Python Libraries

| Library | Install | Purpose |
|---------|---------|---------|
| `semanticscholar` | `pip install semanticscholar` | Semantic Scholar wrapper |
| `arxiv` | `pip install arxiv` | arXiv search and download |
| `habanero` | `pip install habanero` | CrossRef client |

### Citation Verification

| Tool | URL | Purpose |
|------|-----|---------|
| Citely | [citely.ai](https://citely.ai/citation-checker) | Batch verification |
| ReciteWorks | [reciteworks.com](https://reciteworks.com/) | In-text citation checking |

---

## Visualization & Formatting

### Figure Creation

| Tool | URL | Purpose |
|------|-----|---------|
| PlotNeuralNet | [GitHub](https://github.com/HarisIqbal88/PlotNeuralNet) | TikZ neural-network diagrams |
| SciencePlots | [GitHub](https://github.com/garrettj403/SciencePlots) | Publication-ready matplotlib |
| Okabe-Ito Palette | [Reference](https://jfly.uni-koeln.de/color/) | Colorblind-safe colors |

### LaTeX Resources

| Resource | URL | Purpose |
|----------|-----|---------|
| Overleaf Templates | [Overleaf](https://www.overleaf.com/latex/templates) | Online LaTeX editor |
| BibLaTeX Guide | [CTAN](https://ctan.org/pkg/biblatex) | Modern citation management |

---

## Research on AI Writing & Hallucination

| Source | URL | Key Finding |
|--------|-----|-------------|
| AI Hallucinations in Citations | [Enago](https://www.enago.com/academy/ai-hallucinations-research-citations/) | Citation hallucination is a real risk |
| Hallucination in AI Writing | [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10726751/) | Types of citation errors |

---

## Quick Reference by Topic

### For Narrative & Structure
→ Start with: Neel Nanda, Sebastian Farquhar, Andrej Karpathy

### For Sentence-Level Clarity
→ Start with: Gopen & Swan, Ethan Perez, Zachary Lipton

### For Word Choice & Style
→ Start with: Zachary Lipton, Jacob Steinhardt

### For Survey Organization
→ Start with: paper-types.md, phase5-paper-drafting.md, reviewer-guidelines.md

### For Citation Management
→ Start with: Semantic Scholar API, CrossRef, citation-workflow.md

### For Human Evaluation
→ Start with: human-evaluation.md, Prolific/MTurk documentation

### For Non-Empirical Papers (Theory, Survey, Benchmark, Position)
→ Start with: paper-types.md
