---
name: lightrag
description: Ingest and query research papers in the local LightRAG knowledge base. Use LightRAG for literature retrieval, paper comparison, research synthesis, and persistent research context.
version: 2.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, papers, literature, rag, lightrag, knowledge-graph]
    category: research
---

# LightRAG Research Skill

---
name: lightrag
description: Research and literature-review workflow using LightRAG. Discover papers, recover legitimate accessible full text when publishers or academic search sites are inaccessible, ingest papers with MinerU, and query the resulting knowledge base.
---

# LightRAG Research Skill

Use LightRAG as the persistent research knowledge base for papers, technical documents, experiments, infrastructure decisions, and literature reviews.

The goal is to build a reliable research corpus rather than relying on a single website or search engine.

Use the local LightRAG installation as the persistent research knowledge base.

LightRAG is available at:

```text
http://local-hermes-lightrag-1:9621
```

---

## Core Research Workflow

For literature research, follow this pipeline:

1. DISCOVER
2. IDENTIFY
3. LOCATE LEGITIMATE FULL TEXT
4. DOWNLOAD
5. DEDUPLICATE
6. INGEST INTO LIGHTRAG
7. POLL PROCESSING
8. VERIFY RETRIEVAL
9. RESEARCH / COMPARE / SYNTHESIZE

Do not stop simply because the first website is inaccessible.

---

# 1. DISCOVER

Use academic search engines and web search to identify relevant papers.

Possible discovery sources include:

- Google Scholar
- Semantic Scholar
- Crossref
- OpenAlex
- PubMed / PubMed Central
- arXiv
- IEEE
- ACM
- Springer
- Elsevier
- MDPI
- conference websites
- university publication pages

Academic search engines are primarily used for:

- paper title
- authors
- publication year
- DOI
- venue
- abstract
- citation information
- links to possible full-text copies

---

# 2. HANDLE CAPTCHAS AND ACCESS BLOCKS

CAPTCHAs and automated-access blocks are not to be defeated.

Do NOT:

- solve CAPTCHAs automatically
- bypass CAPTCHA challenges
- rotate proxies to evade a block
- use stealth fingerprints to evade detection
- defeat access controls
- circumvent authentication
- bypass a publisher's technical restrictions

Instead, treat the inaccessible website as a discovery source.

If Google Scholar or another site becomes inaccessible:

1. Preserve any title, author, DOI, abstract, or citation information already obtained.
2. Search for the same paper using its title.
3. Search using title + first author.
4. Search using the DOI.
5. Search for an openly accessible copy.
6. Continue with another legitimate source.

Example:

```text
Scholar blocked
     ↓
Paper title + authors + DOI
     ↓
Search web
     ↓
University repository?
Author publication page?
arXiv?
PubMed Central?
Conference repository?
Publisher open-access version?
Institutional repository?
     ↓
Accessible PDF

SOURCE ACCESS FALLBACK

A failure of one access method does NOT mean that the information is
unavailable.

Distinguish between:

1. SOURCE FAILURE
   The website itself is inaccessible.

2. TOOL FAILURE
   The browser, extractor, or other access mechanism failed.

When a TOOL FAILURE occurs, continue using other available methods.

For example:

Browser backend failed
    ↓
Do NOT immediately tell the user the page cannot be accessed.
    ↓
Try:
- normal web retrieval
- direct URL retrieval
- search-engine indexing
- exact-name/domain searches
- alternative official institutional pages
- institutional repositories
- publicly indexed documents

FACULTY / RESEARCHER DOCUMENT WORKFLOW

When asked to find a faculty member's CV:

1. Find the faculty member on the official institution website.
2. Open their official profile if possible.
3. Look for:
   - CV
   - Curriculum Vitae
   - Vita
   - Resume
   - downloadable PDF
4. If the profile is a JavaScript application:
   - attempt browser navigation
   - attempt direct retrieval
   - search the institution's domain for the person's name
   - search for:
       "Full Name" CV
       "Full Name" "Curriculum Vitae"
       "Full Name" filetype:pdf
5. Search legitimate institutional repositories.
6. Search the person's official research/lab page.
7. If a legitimate PDF is found:
   - download it
   - store it in /opt/ai_files
   - ingest it into LightRAG
   - verify retrieval
8. If no CV is found, report exactly what was searched and
   distinguish "not found" from "could not access."

DO NOT ASK THE USER TO PROVIDE THE PDF UNTIL ALTERNATIVE
LEGITIMATE SOURCES HAVE BEEN EXHAUSTED.