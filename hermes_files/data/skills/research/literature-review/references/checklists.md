# Survey Paper Checklist

This checklist is the default operating checklist for literature reviews and survey papers in the literature-review skill. Use it for every draft unless the user supplies a more specific venue checklist.

---

## Universal Survey Checklist

### Scope and Structure

- [ ] The paper is clearly framed as a literature review or survey
- [ ] The one-sentence contribution states the taxonomy, synthesis, or insight the survey provides
- [ ] The organization is thematic or methodological, not paper-by-paper
- [ ] Open problems or future directions are included
- [ ] Limitations of the survey scope are stated honestly

### Source Corpus

- [ ] Relevant papers are discovered from multiple legitimate sources
- [ ] Every paper used as a reference is downloaded locally
- [ ] Each downloaded paper is renamed to `FirstAuthorLastName_Year_DocumentTitle.pdf`
- [ ] The downloaded corpus is deduplicated
- [ ] All reference PDFs are imported into LightRAG
- [ ] LightRAG rescans complete without missing or partially processed documents
- [ ] Any failed ingestion is retried before drafting continues

### Citation and Writing Rules

- [ ] Drafting uses only LightRAG query output and returned citations
- [ ] No citation appears unless it was verified from a query result or downloaded reference metadata
- [ ] A `.bib` file is used for bibliography management
- [ ] The bibliography file contains every cited work in the draft
- [ ] No citations are invented from memory
- [ ] The final draft includes at least 15 verified citations unless the user requests otherwise

### Formatting and Layout

- [ ] The selected template matches the user's requested output format
- [ ] The paper length matches the target scope, defaulting to a 5-page survey if no other length was specified
- [ ] Figures and tables are self-contained and captioned
- [ ] References compile cleanly with no unresolved citations
- [ ] The final PDF compiles without layout or citation errors

### Reproducibility and Environment

- [ ] A project-local virtual environment exists in the project folder
- [ ] The virtual environment is activated before running project Python code
- [ ] All base Python dependencies are installed into the project venv
- [ ] Required LaTeX dependencies are installed on the system
- [ ] Reproduction commands are documented
- [ ] Any data, code, and environment assumptions are documented

### Quality Review

- [ ] The related work section covers the core literature without obvious gaps
- [ ] The survey highlights comparisons and contrasts between works
- [ ] Claims are supported by the cited evidence
- [ ] The draft has been checked for hallucinated references or unsupported statements

### Final Review

- [ ] The draft was reviewed after the last LightRAG rescan
- [ ] The bibliography and template are in sync
- [ ] The final manuscript is ready for the next phase of editing or release
