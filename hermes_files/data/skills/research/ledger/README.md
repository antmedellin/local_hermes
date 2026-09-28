# Research Ledger Skill

## 1. Purpose

The Research Ledger is the authoritative structured research inventory for departments, faculty, publications, authorship, topics, documents, and LightRAG ingestion state.

The architecture separates responsibilities:

```text
Official Sources
      │
      ▼
Faculty Discovery
      │
      ▼
Faculty Enrichment
      │
      ▼
Publication Discovery
      │
      ▼
Publication Normalization
      │
      ▼
Authorship Reconciliation
      │
      ▼
Validation
      │
      ▼
PostgreSQL Research Ledger
      │
      ├───────────────┐
      ▼               ▼
PDF Documents     Abstract-only Documents
      │               │
      ▼               ▼
LightRAG Ingestion
      │
      ▼
Retrieval Verification
      │
      ▼
Research-Ready Department
```

PostgreSQL is the **structured source of truth**.

LightRAG is the **retrieval and knowledge layer**.

The goal is that adding another department requires a new dataset/configuration and source-specific discovery work, rather than creating an entirely new architecture.

---

# 2. Repository Layout

The research skill should eventually follow a structure similar to:

```text
hermes_files/
└── data/
    └── skills/
        └── research/
            ├── ledger/
            │   ├── README.md
            │   ├── schema.sql
            │   │
            │   ├── scripts/
            │   │   ├── discover_faculty.py
            │   │   ├── enrich_faculty.py
            │   │   ├── normalize.py
            │   │   ├── normalize.py
            │   │   ├── reconcile_authorship.py
            │   │   ├── validate.py
            │   │   └── import.py
            │   │
            │   └── data/
            │       ├── maie/
            │       │   ├── config.yaml
            │       │   ├── faculty.json
            │       │   ├── faculty_enriched.json
            │       │   ├── publications.json
            │       │   ├── normalized.json
            │       │   ├── authorship_reconciliation.json
            │       │   └── reconciled.json
            │       │
            │       └── <department_name>/
            │           ├── config.yaml
            │           ├── faculty.json
            │           ├── faculty_enriched.json
            │           ├── publications.json
            │           ├── normalized.json
            │           ├── authorship_reconciliation.json
            │           └── reconciled.json
            │
            └── lightrag/
                └── scripts/
                    ├── lightrag_ingest.py
                    └── <department>_abstract_ingest.py
```

The existing MAIE implementation can serve as the reference implementation.

---

# 3. Environment Preparation

Before beginning a new department, verify that the local infrastructure is running.

From the repository:

```bash
cd ~/local_hermes
```

Activate the Python virtual environment:

```bash
source .venv/bin/activate
```

Verify Python:

```bash
which python
python --version
```

Verify `psycopg2`:

```bash
python -c "import psycopg2; print(psycopg2.__version__)"
```

The project environment should contain:

```text
psycopg2-binary
```

Do not accidentally run the ledger scripts with the system Python if the dependencies are installed only inside `.venv`.

For example, this may fail:

```bash
python3 script.py
```

while this works:

```bash
~/local_hermes/.venv/bin/python script.py
```

---

# 4. Verify Infrastructure

Check Docker:

```bash
docker ps
```

The research infrastructure should include the PostgreSQL and LightRAG services.

The current environment uses:

```text
PostgreSQL
    service: local-hermes-postgres-1
    database: rag
    user: rag
    password: rag

LightRAG
    container: local-hermes-lightrag-1
    API: http://localhost:9621
```

From inside the Docker network, LightRAG can be addressed as:

```text
http://local-hermes-lightrag-1:9621
```

The ledger scripts should use the appropriate environment-specific connection settings rather than hard-coding assumptions wherever possible.

---

# 5. Initialize the Research Schema

The database schema is defined in:

```text
hermes_files/data/skills/research/ledger/schema.sql
```

Apply it to PostgreSQL:

```bash
docker exec -i local-hermes-postgres-1 \
    psql -U rag -d rag \
    < hermes_files/data/skills/research/ledger/schema.sql
```

Verify:

```bash
docker exec -it local-hermes-postgres-1 \
    psql -U rag -d rag
```

Then:

```sql
\dt research.*
```

The core tables are:

```text
research.departments
research.professors
research.papers
research.authorships
research.topics
research.professor_topics
research.paper_topics
research.documents
research.ingestion_runs
```

---

# 6. Create the New Department Workspace

All department-specific JSON outputs should live under:

```text
hermes_files/data/skills/research/ledger/data/<department_name>/
```

Use a stable department slug for `<department_name>` (for example,
`computer-science`, `mathematics`, or `maie`).

Create the directory:

```bash
mkdir -p \
  hermes_files/data/skills/research/ledger/data/<department_name>
```

The important output rule is:

> **Do not write department JSON files directly under `ledger/`, `ledger/scripts/`, or a separate `ledger/departments/` tree. Every department's generated JSON belongs in `ledger/data/<department_name>/`.**

A typical department workspace is:

```text
ledger/data/<department_name>/
├── config.yaml
├── faculty.json
├── faculty_enriched.json
├── publications.json
├── normalized.json
├── authorship_reconciliation.json
└── reconciled.json
```

`config.yaml` is configuration; the remaining files are generated/intermediate
research datasets unless a script explicitly documents otherwise.

For example:

```bash
mkdir -p \
  hermes_files/data/skills/research/ledger/data/computer-science
```

Create the configuration:

```text
config.yaml
```

A department configuration should contain at least:

```yaml
institution: "University Name"

department_name: "Department of Example"

department_url: "https://example.edu/department"

faculty_url: "https://example.edu/department/faculty"

output_directory: "./departments/example"
```

For departments using Digital Measures or another structured institutional source, also record the source configuration:

```yaml
sources:
  faculty:
    - official_department_page
    - digital_measures

  publications:
    - digital_measures
    - orcid
    - crossref
```

The exact source list should reflect the department's actual data sources.

---

# 7. Step 1 — Discover Faculty

The first script should establish the faculty roster.

Recommended script:

```text
ledger/scripts/discover_faculty.py
```

Usage:

```bash
python ledger/scripts/discover_faculty.py \
    --config ledger/data/<department_name>/config.yaml
```

Output:

```text
faculty.json
```

Example:

```json
[
  {
    "full_name": "Jane Smith",
    "academic_title": "Associate Professor",
    "profile_url": "https://example.edu/faculty/jane-smith",
    "source_url": "https://example.edu/department/faculty"
  }
]
```

## Important rule

Faculty discovery should establish **who belongs to the department**.

It should not yet attempt to create the final professor records.

Do not silently add people merely because a publication database associates them with the institution.

The authoritative department roster should come from the department/institutional source whenever possible.

---

# 8. Validate Faculty Discovery

Before enrichment:

```bash
python ledger/scripts/validate.py \
    --stage faculty \
    --input ledger/data/<department_name>/faculty.json
```

At minimum verify:

* faculty count is plausible
* names are non-empty
* no duplicate faculty names
* department affiliation is correct
* source URLs exist
* faculty records are not accidentally pulled from another department

For MAIE, this validation established the 14-person faculty roster.

---

# 9. Step 2 — Enrich Faculty

Use:

```text
ledger/scripts/enrich_faculty.py
```

Usage:

```bash
python ledger/scripts/enrich_faculty.py \
    --config ledger/data/<department_name>/config.yaml \
    --input ledger/data/<department_name>/faculty.json \
    --output ledger/data/<department_name>/faculty_enriched.json
```

The enriched record can contain:

```text
full_name
first_name
middle_name
last_name
institution
department
academic_title
profile_url
cv_url
email
office_location
research_interests
lab_name
lab_url
orcid
google_scholar_url
semantic_scholar_id
source_url
```

Not every field will be available for every faculty member.

Missing information should remain missing rather than being fabricated.

---

# 10. Preserve Research Interests

The professor table contains:

```sql
research_interests TEXT
```

This field is useful for department-level research discovery.

For example:

```text
Professor:
    Jane Smith

Research interests:
    machine learning; computer vision; robotics
```

Later, these can also be normalized into:

```text
research.topics
research.professor_topics
```

Do not populate topic relationships merely because a keyword happens to appear once.

Topic assignment should have an identifiable source or confidence value.

---

# 11. Step 3 — Discover Publications

Recommended script:

```text
ledger/scripts/normalize.py
```

Usage:

```bash
python ledger/scripts/normalize.py \
    --config ledger/data/<department_name>/config.yaml \
    --faculty ledger/data/<department_name>/faculty_enriched.json \
    --output ledger/data/<department_name>/publications.json
```

Publication sources may include:

```text
Digital Measures
ORCID
Crossref
PubMed
Semantic Scholar
Google Scholar
publisher pages
institutional repositories
faculty CVs
```

The exact sources depend on the department.

The goal at this stage is **recall**, not aggressive deduplication.

It is acceptable for multiple sources to describe the same paper.

---

# 12. Do Not Deduplicate Too Early

Suppose three sources contain:

```text
Source A:
Deep Learning for Manufacturing

Source B:
Deep Learning for Manufacturing

Source C:
Deep Learning for Manufacturing
DOI: 10.xxxx/example
```

Do not immediately discard A and B.

Instead preserve:

```text
source
source_url
original metadata
source identifier
author information
```

Then perform normalization.

This makes later auditing possible.

---

# 13. Step 4 — Normalize Publications

Use:

```text
ledger/scripts/normalize.py
```

Usage:

```bash
python ledger/scripts/normalize.py \
    --input ledger/data/<department_name>/publications.json \
    --output ledger/data/<department_name>/normalized.json
```

Normalization should attempt to establish:

```text
canonical title
publication year
publication date
DOI
venue
publisher
publication URL
legitimate PDF URL
abstract
keywords
research topics
```

Primary identity signals should generally be:

1. DOI
2. exact/normalized title + year
3. carefully reviewed metadata similarity

The normalized publication record should preserve provenance.

---

# 14. Publication Validation

Run:

```bash
python ledger/scripts/validate.py \
    --stage publications \
    --input ledger/data/<department_name>/normalized.json
```

Check for:

```text
duplicate DOI
duplicate title/year
missing titles
invalid publication years
suspicious URLs
missing authors
malformed DOI values
```

A useful PostgreSQL post-import check is:

```sql
SELECT
    LOWER(TRIM(title)) AS normalized_title,
    publication_year,
    COUNT(*) AS count
FROM research.papers
GROUP BY LOWER(TRIM(title)), publication_year
HAVING COUNT(*) > 1;
```

Expected result:

```text
0 rows
```

---

# 15. Step 5 — Reconcile Authorship

This is one of the most important stages.

A publication may contain:

```text
Jane Smith
J. Smith
Smith, Jane
J Smith
Jane A. Smith
```

while the institutional faculty record may contain:

```text
Jane Alice Smith
```

The system must distinguish between:

```text
safe identity match
possible identity match
historical identity
external author
unknown author
```

Use:

```text
ledger/scripts/reconcile_authorship.py
```

Example:

```bash
python ledger/scripts/reconcile_authorship.py \
    --faculty ledger/data/<department_name>/faculty_enriched.json \
    --publications ledger/data/<department_name>/normalized.json \
    --output ledger/data/<department_name>/authorship_reconciliation.json
```

---

# 16. Never Silently Correct Historical Identity Data

Institutional systems may contain historical identifiers that no longer match current faculty identifiers.

For example:

```text
historical DM ID
        ↓
same person
        ↓
current faculty ID
```

The reconciliation layer should preserve the original identity and document the mapping.

The MAIE dataset demonstrated why this matters.

The final reconciliation contained classifications including:

```text
EXACT
NAME_VARIANT
INITIAL_VARIANT
MODERATE_REVIEW
HISTORICAL_ID_MISMATCH
EXTERNAL
NAME_WITHOUT_DM_ID
```

The important principle is:

> Reconcile identity without destroying the original source identity.

---

# 17. Step 6 — Final Reconciliation

The final normalized dataset should contain:

```text
faculty
publications
author occurrences
reconciliation decisions
```

Example:

```text
reconciled.json
```

Before importing it, validate:

```bash
python ledger/scripts/validate.py \
    --stage final \
    --input ledger/data/<department_name>/reconciled.json
```

The validation should check:

```text
faculty count
publication count
author occurrence count
faculty IDs
publication IDs
duplicate publication/author positions
missing identities
extra identities
reconciliation classifications
```

The MAIE final pre-import audit used this type of invariant:

```text
duplicate publication/position = 0
missing DM IDs = 0
extra DM IDs = 0
errors = 0
warnings = 0
```

The exact expected counts naturally change for every department.

---

# 18. Step 7 — Import Into PostgreSQL

Use the existing department-aware import script:

```text
ledger/scripts/import.py
```

Example:

```bash
python ledger/scripts/import.py \
    --config ledger/data/<department_name>/config.yaml \
    --input ledger/data/<department_name>/reconciled.json
```

The import should:

1. create/find the department
2. import professors
3. import canonical papers
4. create authorship relationships
5. preserve metadata
6. commit only after validation succeeds

The relationships are:

```text
department
    │
    └── professors
            │
            └── authorships
                    │
                    └── papers
```

Papers should not be duplicated simply because multiple faculty members authored them.

---

# 19. Verify the Database Import

Connect to PostgreSQL:

```bash
docker exec -it local-hermes-postgres-1 \
    psql -U rag -d rag
```

Check department:

```sql
SELECT *
FROM research.departments;
```

Check professors:

```sql
SELECT
    professor_id,
    full_name,
    academic_title
FROM research.professors
ORDER BY full_name;
```

Check paper count:

```sql
SELECT COUNT(*)
FROM research.papers;
```

Check authorships:

```sql
SELECT COUNT(*)
FROM research.authorships;
```

Check the new department specifically:

```sql
SELECT
    d.department_name,
    COUNT(DISTINCT p.professor_id) AS professors
FROM research.departments d
LEFT JOIN research.professors p
    ON p.department_id = d.department_id
GROUP BY d.department_id, d.department_name;
```

---

# 20. Determine Document Availability

After the structured ledger is imported, classify every paper.

Conceptually:

```text
                         Paper
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         Full PDF       Abstract       No document
         available      available       available
              │            │
              ▼            ▼
          PDF ingest   Abstract ingest
              │            │
              └──────┬─────┘
                     ▼
                  LightRAG
```

The three useful states are:

```text
FULL_TEXT_AVAILABLE
ABSTRACT_ONLY
NO_DOCUMENT
```

A paper without a legitimate PDF should not be treated as full-text available.

---

# 21. Step 8 — Download Legitimate PDFs

For papers with legitimate PDF sources:

```text
research.papers.legitimate_pdf_url
```

download the file into the department's document directory.

For example:

```text
data/research/<department>/pdf/
```

Calculate a SHA-256 hash:

```bash
sha256sum paper.pdf
```

Store the hash in:

```text
research.documents.sha256
```

This provides document-level identity.

---

# 22. Register Documents in PostgreSQL

For every downloaded document create:

```text
research.documents
```

A document should contain:

```text
paper_id
document_type
source_url
local_path
filename
file_size_bytes
sha256
download_status
parser
lightrag_track_id
lightrag_status
```

This creates a distinction between:

```text
paper metadata
```

and

```text
physical document
```

That distinction is important because one paper can have multiple representations.

---

# 23. Step 9 — Full-PDF LightRAG Ingestion

The existing PDF workflow is:

```text
hermes_files/data/skills/research/lightrag/scripts/lightrag_ingest.py
```

The basic flow is:

```text
PDF
 │
 ▼
LightRAG /documents/upload
 │
 ▼
document parsing
 │
 ▼
MinerU / parser
 │
 ▼
chunks
 │
 ▼
embeddings
 │
 ▼
entities / relationships
 │
 ▼
PostgreSQL + vector/graph stores
 │
 ▼
retrieval
```

The PDF ingestion script should not be replaced by the abstract-ingestion workflow.

They are two different document pipelines.

---

# 24. Verify PDF Processing

A successful HTTP upload is not enough.

The ingestion pipeline is asynchronous.

The system should:

```text
upload
   ↓
receive track_id
   ↓
poll track status
   ↓
wait for processed
   ↓
verify document
   ↓
update PostgreSQL
```

Do not mark a document as processed merely because:

```json
{
  "status": "success"
}
```

was returned by the upload endpoint.

That only indicates that LightRAG accepted the request.

---

# 25. Step 10 — Abstract-Only Ingestion

Papers with abstracts but no legitimate full text can still provide useful retrieval information.

The abstract ingestion script should live under:

```text
hermes_files/data/skills/research/lightrag/scripts/
```

For example:

```text
<department>_abstract_ingest.py
```

The MAIE implementation is:

```text
maie_abstract_ingest.py
```

A generalized implementation should eventually become:

```text
abstract_ingest.py
```

with the department passed as configuration.

---

# 26. Abstract Document Construction

Each abstract becomes a deterministic LightRAG text document.

Example:

```text
Paper ID: 123

Title: Example Research Paper

Publication Year: 2025

DOI: 10.xxxx/example

Authors:
Jane Smith
John Doe
Mary Jones

Abstract:
<abstract text>

Source:
research ledger / paper_id=123
```

This gives LightRAG enough context to answer questions about the paper without pretending that the entire PDF was ingested.

---

# 27. Deterministic LightRAG Source IDs

Each abstract should have a stable source identifier.

For example:

```text
maie-paper-000123
```

For another department:

```text
cs-paper-000123
```

or preferably:

```text
<department-slug>-paper-<paper_id>
```

This allows PostgreSQL and LightRAG to be correlated.

For example:

```text
PostgreSQL:
paper_id = 123

LightRAG:
file_source = cs-paper-000123
```

---

# 28. Abstract Ingestion API

LightRAG supports text insertion through:

```text
/documents/text
```

and batch insertion through:

```text
/documents/texts
```

The batch request contains:

```json
{
  "texts": [
    "...",
    "..."
  ],
  "file_sources": [
    "cs-paper-000001",
    "cs-paper-000002"
  ]
}
```

The API returns a track ID.

Example:

```text
insert_20260922_165838_c0a1425b
```

That track ID must be retained.

---

# 29. Batch Size

Use a conservative batch size.

The MAIE implementation uses:

```text
BATCH_SIZE = 10
```

This is appropriate because LightRAG's batch endpoint has a maximum number of texts per request.

The workflow becomes:

```text
77 abstracts

Batch 1: 10
Batch 2: 10
Batch 3: 10
Batch 4: 10
Batch 5: 10
Batch 6: 10
Batch 7: 7
```

---

# 30. Poll LightRAG Asynchronously

LightRAG processing is asynchronous.

The polling function should recognize intermediate states:

```text
analyzing
processing
pending
queued
```

as normal.

These are not failures.

Terminal success:

```text
processed
```

Terminal failure states include:

```text
failed
failure
error
```

The polling logic should therefore behave like:

```text
submitted
    │
    ▼
analyzing / processing
    │
    ├── failed → stop
    │
    └── processed → success
```

Do not treat a temporarily empty document list as a permanent failure.

---

# 31. Important Recovery Rule

A batch can be accepted by LightRAG while the documents are still being processed.

For example:

```text
HTTP response:
success
track_id = insert_...
```

followed immediately by:

```text
processed = 0
missing = 10
```

does **not** necessarily mean the documents failed.

A later status request may show:

```text
analyzing = 7
processing = 3
```

and eventually:

```text
processed = 10
```

Therefore:

> Initial absence from the status response is an intermediate state, not automatically a failure.

---

# 32. PostgreSQL Update Gate

PostgreSQL should only be updated after the entire batch has been verified.

Correct:

```text
submit
   ↓
poll
   ↓
all documents processed
   ↓
update PostgreSQL
```

Incorrect:

```text
submit
   ↓
HTTP success
   ↓
mark PostgreSQL PROCESSED
```

This prevents the ledger from claiming successful ingestion when LightRAG has actually failed.

---

# 33. LightRAG Status Fields

For papers, maintain:

```text
lightrag_track_id
lightrag_status
```

Example:

```text
paper_id: 123
lightrag_track_id: insert_2026...
lightrag_status: PROCESSED
```

For physical documents, maintain the same relationship in:

```text
research.documents
```

This creates an auditable chain:

```text
paper
  ↓
document
  ↓
LightRAG track
  ↓
LightRAG document
```

---

# 34. Resume and Idempotency

A production ingestion script must be safe to resume.

Do not blindly ingest all abstracts every time the script runs.

Before submission, query:

```sql
SELECT
    paper_id,
    lightrag_status
FROM research.papers
WHERE abstract IS NOT NULL
  AND TRIM(abstract) <> '';
```

Then separate:

```text
already processed
```

from:

```text
not processed
```

For example:

```python
pending_papers = [
    paper
    for paper in papers
    if paper["lightrag_status"] != "PROCESSED"
]
```

This prevents rerunning successful documents.

The same principle should eventually be applied to PDF ingestion.

---

# 35. Recovery of Interrupted Batches

If the script is interrupted after LightRAG accepted a batch but before PostgreSQL was updated:

1. preserve the original LightRAG track ID
2. query the track
3. verify every expected source
4. update PostgreSQL
5. remove those papers from the pending queue

Do not submit the same documents again merely because PostgreSQL still says they are unprocessed.

The MAIE implementation demonstrated this recovery requirement with:

```text
insert_20260922_165838_c0a1425b
```

The ten documents were later confirmed as:

```text
processed
```

and could be recovered from the existing track.

---

# 36. Step 11 — Retrieval Verification

After ingestion, perform a document-specific query.

For example:

```bash
docker exec hermes-dashboard \
    python3 \
    /opt/data/skills/research/lightrag/scripts/lightrag_search.py \
    "Summarize paper 123 using the ingested document."
```

The answer should demonstrate that LightRAG actually knows the document.

Verification should test:

```text
paper title
authors
research subject
specific abstract facts
source/document identity
```

Do not consider ingestion complete merely because:

```text
status = processed
```

The actual research requirement is:

```text
processed + retrievable
```

---

# 37. Abstract Retrieval Has a Deliberate Limitation

If only the abstract was ingested, the system should answer only from the abstract-level evidence.

It should not imply that it has access to:

```text
full methodology
complete experimental results
full tables
supplementary material
complete references
```

unless those documents were actually ingested.

This distinction is important for research integrity.

---

# 38. Step 12 — Topics

After the core ledger is stable, populate:

```text
research.topics
research.professor_topics
research.paper_topics
```

A topic can have:

```text
topic_name
description
parent_topic_id
```

Professor relationships include:

```text
confidence
source
```

Paper relationships include:

```text
confidence
source
```

This permits queries such as:

```text
Which professors research machine learning?
```

or:

```text
Which papers relate to cybersecurity?
```

without forcing topics into the raw publication records.

---

# 39. Department Completion Checklist

A department is not complete merely because faculty were found.

Use this lifecycle:

```text
DISCOVERED
    ↓
ENRICHED
    ↓
NORMALIZED
    ↓
RECONCILED
    ↓
VALIDATED
    ↓
IMPORTED
    ↓
DOCUMENTS_INGESTED
    ↓
RETRIEVAL_VERIFIED
    ↓
RESEARCH_READY
```

A department is `RESEARCH_READY` only when:

```text
[ ] faculty discovered
[ ] faculty validated
[ ] faculty enriched
[ ] publications discovered
[ ] publications normalized
[ ] duplicate publications resolved
[ ] authorship reconciled
[ ] final dataset validated
[ ] PostgreSQL import completed
[ ] database counts verified
[ ] full PDFs identified
[ ] abstract-only papers identified
[ ] legitimate documents ingested
[ ] LightRAG tracks verified
[ ] retrieval tested
[ ] topics populated where appropriate
```

---

# 40. Useful PostgreSQL Verification Queries

## Department counts

```sql
SELECT
    d.department_name,
    COUNT(DISTINCT p.professor_id) AS professors
FROM research.departments d
LEFT JOIN research.professors p
    ON p.department_id = d.department_id
GROUP BY
    d.department_id,
    d.department_name;
```

## Papers with abstracts

```sql
SELECT COUNT(*)
FROM research.papers
WHERE abstract IS NOT NULL
  AND TRIM(abstract) <> '';
```

## Papers without abstracts

```sql
SELECT COUNT(*)
FROM research.papers
WHERE abstract IS NULL
   OR TRIM(abstract) = '';
```

## LightRAG status

```sql
SELECT
    lightrag_status,
    COUNT(*)
FROM research.papers
GROUP BY lightrag_status
ORDER BY lightrag_status;
```

## Authors per paper

```sql
SELECT
    p.paper_id,
    p.title,
    COUNT(a.professor_id) AS author_count
FROM research.papers p
LEFT JOIN research.authorships a
    ON a.paper_id = p.paper_id
GROUP BY
    p.paper_id,
    p.title
ORDER BY author_count DESC;
```

## Papers for one professor

```sql
SELECT
    pr.full_name,
    p.title,
    p.publication_year,
    p.doi
FROM research.professors pr
JOIN research.authorships a
    ON a.professor_id = pr.professor_id
JOIN research.papers p
    ON p.paper_id = a.paper_id
WHERE pr.full_name = 'Jane Smith'
ORDER BY
    p.publication_year DESC;
```

---

# 41. Recommended Script Responsibilities

The ledger directory currently contains the following scripts:

```text
ledger/scripts/
├── authorship_audit.py
├── authorship_diagnostic.py
├── authorship_diagnose.py
├── build_reconciled.py
├── db_dry_run.py
├── enrich_faculty.py
├── final_integrity.py
├── import.py
├── key_reconcile.py
├── normalize.py
├── reconcile.py
├── reconcile_authorship.py
├── validate.py
└── discover_faculty.py
```

Use these existing filenames in the workflow rather than creating parallel
`discover_publications.py` or `normalize_publications.py` scripts.

### `discover_faculty.py`

```text
Input:
    department configuration

Output:
    ledger/data/<department_name>/faculty.json

Responsibility:
    establish the authoritative faculty roster
```

### `enrich_faculty.py`

```text
Input:
    faculty.json

Output:
    ledger/data/<department_name>/faculty_enriched.json

Responsibility:
    collect additional faculty metadata
```

### `normalize.py`

```text
Input:
    discovered publication/source data

Output:
    ledger/data/<department_name>/normalized.json

Responsibility:
    normalize publication metadata and canonical publication identity
```

If the current implementation also writes an intermediate `publications.json`,
keep that file in the same department directory:

```text
ledger/data/<department_name>/publications.json
```

### `reconcile.py`

```text
Input:
    normalized publication data and reconciliation inputs

Output:
    ledger/data/<department_name>/reconciled.json

Responsibility:
    perform the general reconciliation step
```

### `reconcile_authorship.py`

```text
Input:
    faculty + normalized publications

Output:
    ledger/data/<department_name>/authorship_reconciliation.json

Responsibility:
    map publication authors to faculty identities
```

### `authorship_audit.py`

```text
Input:
    authorship/reconciliation data

Output:
    diagnostic or audit results

Responsibility:
    audit authorship mappings and identify suspicious cases
```

### `authorship_diagnostic.py`

```text
Input:
    authorship/reconciliation data

Output:
    diagnostic results

Responsibility:
    investigate authorship identity and matching behavior
```

### `authorship_diagnose.py`

```text
Input:
    authorship/reconciliation data

Output:
    diagnostic results

Responsibility:
    perform authorship-focused diagnosis
```

### `key_reconcile.py`

```text
Input:
    reconciliation/key data

Output:
    reconciliation results

Responsibility:
    reconcile stable identifiers or key-based identity mappings
```

### `build_reconciled.py`

```text
Input:
    normalized and reconciliation data

Output:
    ledger/data/<department_name>/reconciled.json

Responsibility:
    build the final reconciled dataset from the intermediate results
```

### `final_integrity.py`

```text
Input:
    ledger/data/<department_name>/reconciled.json

Output:
    PASS / FAIL integrity results

Responsibility:
    perform the final pre-import integrity checks
```

### `validate.py`

```text
Input:
    stage-specific dataset

Output:
    PASS / FAIL

Responsibility:
    prevent invalid data from advancing through the pipeline
```

### `import.py`

```text
Input:
    ledger/data/<department_name>/reconciled.json

Output:
    PostgreSQL

Responsibility:
    authoritative structured import
```

### `db_dry_run.py`

```text
Input:
    reconciled/import data

Output:
    dry-run database validation/results

Responsibility:
    test database import behavior without committing the final import
```

### LightRAG scripts

The full-text ingestion script remains:

```text
hermes_files/data/skills/research/lightrag/scripts/lightrag_ingest.py
```

Abstract ingestion should use the existing department-specific or generalized
LightRAG script already present in that directory. Do not introduce a new
ledger script name solely to mirror an older README recommendation.

---

# 42. Technical Data Flow

The complete system can be summarized as:

```text
                    ┌──────────────────────┐
                    │ Official University  │
                    │ Sources              │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Faculty Discovery    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Faculty Enrichment   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Publication Discovery│
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Normalization        │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Authorship           │
                    │ Reconciliation       │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Validation Gate      │
                    └──────────┬───────────┘
                               │
                               ▼
                 ┌─────────────────────────────┐
                 │ PostgreSQL Research Ledger  │
                 └─────────────┬───────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        Full PDF          Abstract only     No document
              │                │
              ▼                ▼
        PDF ingestion   Text ingestion
              │                │
              └────────┬───────┘
                       ▼
                  ┌──────────┐
                  │ LightRAG │
                  └────┬─────┘
                       │
                       ▼
                Retrieval Testing
                       │
                       ▼
                Research Ready
```

---

# 43. What Changes for a New Department?

The pipeline should remain the same.

These things change:

```text
department name
department URL
faculty source
faculty roster
publication sources
department-specific source IDs
department slug
data files
```

These things should remain common:

```text
PostgreSQL schema
validation philosophy
normalization rules
authorship model
document model
LightRAG ingestion model
track-status verification
retrieval verification
```

That is the central architectural goal.

---

# 44. Example: Onboarding a Completely New Department

Suppose the next department is:

```text
Computer Science
```

The workflow becomes:

```bash
cd ~/local_hermes
source .venv/bin/activate
```

Create:

```bash
mkdir -p \
  hermes_files/data/skills/research/ledger/data/computer-science
```

Create:

```text
config.yaml
```

Run:

```bash
python hermes_files/data/skills/research/ledger/scripts/discover_faculty.py \
    --config hermes_files/data/skills/research/ledger/data/computer-science/config.yaml
```

Then:

```bash
python hermes_files/data/skills/research/ledger/scripts/enrich_faculty.py \
    --config hermes_files/data/skills/research/ledger/data/computer-science/config.yaml
```

Then publication discovery:

```bash
python hermes_files/data/skills/research/ledger/scripts/normalize.py \
    --config hermes_files/data/skills/research/ledger/data/computer-science/config.yaml
```

Normalize:

```bash
python hermes_files/data/skills/research/ledger/scripts/normalize.py \
    --input hermes_files/data/skills/research/ledger/data/computer-science/publications.json \
    --output hermes_files/data/skills/research/ledger/data/computer-science/normalized.json
```

Reconcile:

```bash
python hermes_files/data/skills/research/ledger/scripts/reconcile_authorship.py \
    --faculty hermes_files/data/skills/research/ledger/data/computer-science/faculty_enriched.json \
    --publications hermes_files/data/skills/research/ledger/data/computer-science/normalized.json \
    --output hermes_files/data/skills/research/ledger/data/computer-science/authorship_reconciliation.json
```

Validate:

```bash
python hermes_files/data/skills/research/ledger/scripts/validate.py \
    --stage final \
    --input hermes_files/data/skills/research/ledger/data/computer-science/reconciled.json
```

Import:

```bash
python hermes_files/data/skills/research/ledger/scripts/import.py \
    --config hermes_files/data/skills/research/ledger/data/computer-science/config.yaml \
    --input hermes_files/data/skills/research/ledger/data/computer-science/reconciled.json
```

Then classify documents and run the appropriate:

```text
PDF ingestion
```

or:

```text
abstract ingestion
```

Finally perform document-specific retrieval verification.

---

# 45. The Most Important Operational Rule

Every stage should have a validation gate.

Do not use:

```text
discover → immediately import
```

Use:

```text
discover
   ↓
validate
   ↓
enrich
   ↓
validate
   ↓
discover publications
   ↓
normalize
   ↓
validate
   ↓
reconcile
   ↓
validate
   ↓
import
   ↓
verify database
   ↓
ingest documents
   ↓
verify LightRAG
   ↓
verify retrieval
```

This prevents an error in an upstream source from propagating through the entire research infrastructure.

---

# 46. Rebuilding a Department from Scratch

If a department needs to be rebuilt:

### 1. Preserve source data

Keep:

```text
faculty.json
faculty_enriched.json
publications.json
normalized.json
authorship_reconciliation.json
reconciled.json
```

These are useful for auditing.

### 2. Validate the final dataset

```bash
python validate.py --stage final ...
```

### 3. Remove only the department's database records

Do not blindly delete all research data.

The database is designed for multiple departments.

### 4. Re-import

Run the import script again.

### 5. Reconcile LightRAG

Do not blindly re-ingest documents that already exist.

Check:

```text
lightrag_track_id
lightrag_status
```

and LightRAG's own document records.

---

# Department JSON Output Convention

All generated department JSON must be colocated under the department's data
directory:

```text
hermes_files/data/skills/research/ledger/data/<department_name>/
```

Recommended filenames:

```text
faculty.json
faculty_enriched.json
publications.json
normalized.json
authorship_reconciliation.json
reconciled.json
```

This keeps each department self-contained and makes it straightforward to
archive, validate, rebuild, or audit one department without mixing its
intermediate data with another department.

# 47. Final Architecture

The resulting research infrastructure has three major layers.

## Layer 1 — Source Collection

```text
University websites
Digital Measures
ORCID
Crossref
PubMed
faculty CVs
publisher pages
repositories
```

## Layer 2 — Research Ledger

```text
PostgreSQL
```

Stores:

```text
departments
professors
papers
authorships
topics
documents
ingestion runs
```

## Layer 3 — Research Retrieval

```text
LightRAG
    │
    ├── document parsing
    ├── chunks
    ├── embeddings
    ├── entities
    ├── relationships
    └── retrieval
```

The ledger answers:

> What do we know structurally?

LightRAG answers:

> What can we retrieve from the ingested research material?

The two systems should remain connected through stable identifiers and ingestion metadata rather than being treated as one database.

---

# 48. Definition of Done

A new department is considered successfully onboarded when:

```text
✓ Department exists in PostgreSQL
✓ Faculty roster is validated
✓ Faculty metadata is enriched
✓ Publications are discovered
✓ Publication identities are normalized
✓ Duplicate publications are resolved
✓ Authorship is reconciled
✓ Historical identities are preserved
✓ Final dataset passes validation
✓ PostgreSQL import passes
✓ Database counts are verified
✓ Full-text documents are classified
✓ Abstract-only documents are classified
✓ PDFs are ingested where available
✓ Abstracts are ingested where appropriate
✓ LightRAG processing tracks reach terminal success
✓ PostgreSQL reflects verified ingestion state
✓ Retrieval has been tested against actual documents
✓ Topics are populated where appropriate
✓ Department can be queried as a research corpus
```

The fundamental principle is:

> **A new department should be a new dataset flowing through the same validated pipeline—not a new one-off implementation.**
