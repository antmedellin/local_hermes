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
   - Run a LightRAG `/query` that requests a generated answer, not context only.
   - Make the query document-specific by including the paper's exact title,
     arXiv ID, or exact ingested filename.
   - Confirm that the generated answer is about the requested paper and,
     when references are returned, that they point to the requested document.
   - If the response is context only, fails, times out, mixes in another
     document, or does not clearly identify the requested paper, verification
     has failed. Do NOT mark the task complete.
   - Successful upload or `processed` status alone does NOT mean the task
     is complete.
9. RESEARCH / COMPARE / SYNTHESIZE

---

## MANDATORY LIGHTRAG INGESTION PROCEDURE

When importing a paper into LightRAG, follow this procedure exactly:

1. Download the paper and validate that it is a real PDF.
2. Invoke the Hermes terminal tool with `timeout=600` when running `lightrag_ingest.py` on the validated PDF. Do NOT add `--timeout 600` to the Python command; `lightrag_ingest.py` does not accept a `--timeout` argument.
3. If ingestion succeeds or the script reports that a duplicate resolves to
   an already processed document, proceed to retrieval verification.
4. If LightRAG reports a duplicate:
   - Do NOT rename the PDF.
   - Do NOT upload the same paper again under another filename.
   - Do NOT repeatedly retry ingestion.
   - Use the duplicate information to identify the original document.
   - Continue only when the original document is confirmed as processed.
5. Run `lightrag_search.py` with a document-specific query containing the
   paper's exact arXiv ID, exact title, or exact ingested filename.
6. The query must request a generated answer, not context only.
7. Confirm that the returned answer actually describes the requested paper.
8. If the answer is missing, times out, is unrelated, or refers to another
   document, retrieval verification has failed.
9. Do NOT mark the Kanban task complete unless retrieval verification succeeds.
10. Do NOT claim that a summary was generated unless the LightRAG query
    actually returned a generated summary.

The task completion decision must be based on the actual LightRAG query
result, not on an assumption that ingestion succeeded.

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

---

# DOWNLOAD AND VALIDATE PDFS

When downloading a PDF from a direct URL:

1. Follow HTTP redirects. For example, use `curl -L --fail` rather than
   plain `curl` when retrieving a direct PDF URL.
2. Save the downloaded file under `/opt/ai_files`.
3. Before calling the LightRAG ingestion script, verify that the file is
   actually a PDF and not an HTML redirect, error page, or other content.
4. If PDF validation fails, do NOT rename the file and retry ingestion.
   Search for another legitimate full-text source or redownload using
   a method that follows redirects.
5. Only pass a validated PDF to `lightrag_ingest.py`.

Example:

    curl -L --fail --retry 3 -o /opt/ai_files/paper.pdf <PDF_URL>

Do not assume that a file ending in `.pdf` is actually a PDF.

When LightRAG reports that a document is a duplicate:

- Do NOT rename the PDF and upload it again.
- Do NOT repeatedly retry the same document under different filenames.
- Treat the ingestion as successful only if the duplicate record resolves to an already processed original document.
- Proceed to retrieval verification using the processed document.
- If the duplicate chain does not resolve to a processed document, report the ingestion failure and do not mark the task complete.

---

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
