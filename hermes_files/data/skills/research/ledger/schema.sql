-- ============================================================
-- Local Hermes Research Ledger
-- PostgreSQL schema
-- ============================================================

CREATE SCHEMA IF NOT EXISTS research;

-- ============================================================
-- Departments
-- ============================================================

CREATE TABLE IF NOT EXISTS research.departments (
    department_id SERIAL PRIMARY KEY,

    institution VARCHAR(255) NOT NULL,
    department_name VARCHAR(500) NOT NULL,

    department_url TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(institution, department_name)
);


-- ============================================================
-- Professors / Researchers
-- ============================================================

CREATE TABLE IF NOT EXISTS research.professors (
    professor_id BIGSERIAL PRIMARY KEY,

    full_name VARCHAR(500) NOT NULL,

    first_name VARCHAR(255),
    middle_name VARCHAR(255),
    last_name VARCHAR(255),

    institution VARCHAR(255),

    department_id INTEGER
        REFERENCES research.departments(department_id)
        ON DELETE SET NULL,

    academic_title VARCHAR(255),

    profile_url TEXT,
    cv_url TEXT,

    email TEXT,

    office_location TEXT,

    research_interests TEXT,

    lab_name VARCHAR(500),
    lab_url TEXT,

    orcid VARCHAR(255),
    google_scholar_url TEXT,
    semantic_scholar_id VARCHAR(255),

    source_url TEXT,

    discovery_status VARCHAR(50)
        NOT NULL DEFAULT 'DISCOVERED',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(institution, full_name)
);


-- ============================================================
-- Papers
-- ============================================================

CREATE TABLE IF NOT EXISTS research.papers (
    paper_id BIGSERIAL PRIMARY KEY,

    title TEXT NOT NULL,

    abstract TEXT,

    publication_year INTEGER,

    publication_date DATE,

    venue VARCHAR(1000),

    publisher VARCHAR(500),

    doi VARCHAR(500),

    isbn VARCHAR(255),

    arxiv_id VARCHAR(255),

    pmid VARCHAR(255),

    publication_url TEXT,

    legitimate_pdf_url TEXT,

    keywords TEXT,

    research_topics TEXT,

    citation_count INTEGER,

    source_name VARCHAR(255),
    source_url TEXT,

    metadata_status VARCHAR(50)
        NOT NULL DEFAULT 'DISCOVERED',

    full_text_status VARCHAR(50)
        NOT NULL DEFAULT 'UNKNOWN',

    local_pdf_path TEXT,

    lightrag_track_id TEXT,

    lightrag_status VARCHAR(50),

    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(title, publication_year)
);


-- ============================================================
-- Professor ↔ Paper
-- Many-to-many relationship
-- ============================================================

CREATE TABLE IF NOT EXISTS research.authorships (
    professor_id BIGINT NOT NULL
        REFERENCES research.professors(professor_id)
        ON DELETE CASCADE,

    paper_id BIGINT NOT NULL
        REFERENCES research.papers(paper_id)
        ON DELETE CASCADE,

    author_position INTEGER,

    author_name_as_published VARCHAR(500),

    is_corresponding_author BOOLEAN,

    PRIMARY KEY(professor_id, paper_id)
);


-- ============================================================
-- Topics
-- ============================================================

CREATE TABLE IF NOT EXISTS research.topics (
    topic_id BIGSERIAL PRIMARY KEY,

    topic_name VARCHAR(500) NOT NULL,

    description TEXT,

    parent_topic_id BIGINT
        REFERENCES research.topics(topic_id)
        ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(topic_name)
);


-- ============================================================
-- Professor ↔ Topic
-- ============================================================

CREATE TABLE IF NOT EXISTS research.professor_topics (
    professor_id BIGINT NOT NULL
        REFERENCES research.professors(professor_id)
        ON DELETE CASCADE,

    topic_id BIGINT NOT NULL
        REFERENCES research.topics(topic_id)
        ON DELETE CASCADE,

    confidence REAL,

    source VARCHAR(255),

    PRIMARY KEY(professor_id, topic_id)
);


-- ============================================================
-- Paper ↔ Topic
-- ============================================================

CREATE TABLE IF NOT EXISTS research.paper_topics (
    paper_id BIGINT NOT NULL
        REFERENCES research.papers(paper_id)
        ON DELETE CASCADE,

    topic_id BIGINT NOT NULL
        REFERENCES research.topics(topic_id)
        ON DELETE CASCADE,

    confidence REAL,

    source VARCHAR(255),

    PRIMARY KEY(paper_id, topic_id)
);


-- ============================================================
-- Documents
--
-- Represents an actual file associated with a paper.
-- A paper can eventually have multiple documents:
-- PDF, HTML, supplementary material, etc.
-- ============================================================

CREATE TABLE IF NOT EXISTS research.documents (
    document_id BIGSERIAL PRIMARY KEY,

    paper_id BIGINT
        REFERENCES research.papers(paper_id)
        ON DELETE CASCADE,

    document_type VARCHAR(100)
        NOT NULL DEFAULT 'PDF',

    source_url TEXT,

    local_path TEXT,

    filename VARCHAR(1000),

    file_size_bytes BIGINT,

    sha256 VARCHAR(128),

    download_status VARCHAR(50)
        NOT NULL DEFAULT 'NOT_DOWNLOADED',

    parser VARCHAR(100),

    lightrag_track_id TEXT,

    lightrag_status VARCHAR(50),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(sha256)
);


-- ============================================================
-- Ingestion Runs
--
-- Records what Hermes did with a document.
-- ============================================================

CREATE TABLE IF NOT EXISTS research.ingestion_runs (
    ingestion_id BIGSERIAL PRIMARY KEY,

    document_id BIGINT
        REFERENCES research.documents(document_id)
        ON DELETE CASCADE,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    status VARCHAR(50)
        NOT NULL DEFAULT 'STARTED',

    parser VARCHAR(100),

    lightrag_track_id TEXT,

    chunks_count INTEGER,

    error_message TEXT,

    metadata JSONB
);


-- ============================================================
-- Useful indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_professors_name
ON research.professors(full_name);

CREATE INDEX IF NOT EXISTS idx_professors_department
ON research.professors(department_id);

CREATE INDEX IF NOT EXISTS idx_papers_title
ON research.papers(title);

CREATE INDEX IF NOT EXISTS idx_papers_doi
ON research.papers(doi);

CREATE INDEX IF NOT EXISTS idx_papers_year
ON research.papers(publication_year);

CREATE INDEX IF NOT EXISTS idx_authorships_professor
ON research.authorships(professor_id);

CREATE INDEX IF NOT EXISTS idx_authorships_paper
ON research.authorships(paper_id);

CREATE INDEX IF NOT EXISTS idx_documents_paper
ON research.documents(paper_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_document
ON research.ingestion_runs(document_id);


-- ============================================================
-- Research pipeline states
-- ============================================================
--
-- Professor:
--
-- DISCOVERED
-- PROFILE_FOUND
-- PUBLICATIONS_FOUND
-- COMPLETE
--
-- Paper:
--
-- DISCOVERED
-- METADATA_FOUND
-- ABSTRACT_FOUND
-- FULL_TEXT_FOUND
-- DOWNLOADED
-- INGESTING
-- PROCESSED
-- VERIFIED
--
-- Document:
--
-- NOT_DOWNLOADED
-- DOWNLOADED
-- PARSING
-- PARSED
-- INGESTED
-- FAILED
--
-- ============================================================
