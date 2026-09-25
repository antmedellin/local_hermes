#!/usr/bin/env python3

"""
Import the reconciled UTRGV MAIE research ledger into PostgreSQL.

IMPORTANT:
- This script performs real database writes.
- It uses the already reconciled dataset.
- Only explicitly safe authorship classifications are imported.
- Historical ID mismatches and moderate-review records are NOT imported.
- The entire import runs inside one PostgreSQL transaction.
- If anything fails, the transaction is rolled back.

Expected import state from the successful dry run:

    Departments       : 1
    Professors        : 14
    Canonical papers  : 454
    Authorships       : 433

No topics, documents, or ingestion runs are created here.
Those are later pipeline stages.
"""

import json
import os
import re
import sys
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

import psycopg2


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

RECONCILED_PATH = DATA_DIR / "maie_faculty_reconciled.json"
RECONCILIATION_PATH = DATA_DIR / "maie_authorship_reconciliation.json"


# ---------------------------------------------------------------------------
# PostgreSQL configuration
# ---------------------------------------------------------------------------

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "rag")
DB_USER = os.getenv("POSTGRES_USER", "rag")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "rag")


# ---------------------------------------------------------------------------
# Import policy
# ---------------------------------------------------------------------------

ALLOWED_CLASSIFICATIONS = {
    "EXACT",
    "NAME_VARIANT",
    "INITIAL_VARIANT",
    "NAME_WITHOUT_DM_ID",
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def normalize_key(value):
    """Normalize a name/title for safe lookup comparisons."""

    if value is None:
        return ""

    value = str(value)

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    value = value.lower().strip()

    value = re.sub(r"[“”\"'`]", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)

    return " ".join(value.split())


def load_json(path):
    """Load a UTF-8 JSON file."""

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def first_nonempty(*values):
    """Return the first non-empty value."""

    for value in values:
        if value not in (None, "", [], {}):
            return value

    return None


def parse_bool(value):
    """Convert common Digital Measures boolean representations."""

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    value = str(value).strip().lower()

    if value in {"true", "yes", "y", "1"}:
        return True

    if value in {"false", "no", "n", "0"}:
        return False

    return None


def parse_year(value):
    """Convert a publication year to an integer when possible."""

    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_int(value):
    """Convert an integer-like value to int or None."""

    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Faculty handling
# ---------------------------------------------------------------------------

def build_faculty_indexes(faculty_records):
    """
    Build lookup indexes for current MAIE faculty.

    The reconciled faculty records are already flattened, for example:

        {
            "name": "Alley Cowan Butler",
            "rank": "Full Professor",
            "user_id": "1450741",
            ...
        }

    There is no nested "faculty" object.
    """

    by_id = {}
    by_name = {}

    for faculty in faculty_records:

        user_id = first_nonempty(
            faculty.get("user_id"),
            faculty.get("dm_user_id"),
        )

        name = faculty.get("name")

        if user_id:
            by_id[str(user_id)] = faculty

        if name:
            by_name[normalize_key(name)] = faculty

    return by_id, by_name


def classify_current_maie(
    author,
    faculty_by_id,
    faculty_by_name,
):
    """
    Determine whether an already-reconciled author is safe to import.

    The reconciled publication records contain the authoritative
    reconciliation fields directly.

    Only these classifications are eligible:

        EXACT
        NAME_VARIANT
        INITIAL_VARIANT
        NAME_WITHOUT_DM_ID

    HISTORICAL_ID_MISMATCH, MODERATE_REVIEW, and EXTERNAL are
    deliberately excluded.
    """

    classification = author.get("reconciliation_status")

    if classification not in ALLOWED_CLASSIFICATIONS:
        return None

    mapped_id = author.get("mapped_faculty_id")

    if mapped_id:
        faculty = faculty_by_id.get(str(mapped_id))

        if faculty:
            return faculty

    mapped_name = author.get("mapped_faculty_name")

    if mapped_name:
        faculty = faculty_by_name.get(
            normalize_key(mapped_name)
        )

        if faculty:
            return faculty

    # NAME_WITHOUT_DM_ID may still be safely resolved by the
    # explicitly reconciled author name.
    if classification == "NAME_WITHOUT_DM_ID":

        original_name = author.get("author_name_original")

        if original_name:
            faculty = faculty_by_name.get(
                normalize_key(original_name)
            )

            if faculty:
                return faculty

    return None


# ---------------------------------------------------------------------------
# Publication canonicalization
# ---------------------------------------------------------------------------

def publication_key(publication):
    """
    PostgreSQL research.papers uses:

        UNIQUE(title, publication_year)

    Therefore canonicalization is based on normalized title + year.
    """

    title = (
        publication.get("title")
        or publication.get("normalized_title")
        or ""
    ).strip()

    year = parse_year(publication.get("year"))

    return (
        normalize_key(title),
        year,
    )


def build_canonical_publications(publications):
    """
    Collapse source publications that map to the same PostgreSQL
    title/year uniqueness key.

    Returns:

        canonical_publications
        source_to_canonical
        duplicate_groups
    """

    groups = defaultdict(list)

    for publication in publications:
        groups[publication_key(publication)].append(publication)

    canonical_publications = []
    source_to_canonical = {}
    duplicate_groups = []

    for key, group in groups.items():

        # Preserve the first normalized publication as the canonical
        # record and merge useful metadata from later records.
        canonical = dict(group[0])

        canonical_dm_ids = []

        for publication in group:

            source_id = publication.get("publication_id")

            if source_id:
                source_to_canonical[source_id] = canonical

            for dm_id in publication.get("dm_record_ids", []):
                if dm_id not in canonical_dm_ids:
                    canonical_dm_ids.append(dm_id)

        canonical["dm_record_ids"] = canonical_dm_ids

        # Fill missing canonical fields from duplicate source records.
        fields = [
            "title",
            "abstract",
            "year",
            "type",
            "status",
            "refereed",
            "publisher",
            "volume",
            "issue",
            "pages",
            "url",
            "isbn_issn",
            "pmcid",
            "doi",
            "full_text",
            "impact",
        ]

        for field in fields:

            if canonical.get(field) in (None, ""):

                for publication in group:

                    value = publication.get(field)

                    if value not in (None, ""):
                        canonical[field] = value
                        break

        canonical_publications.append(canonical)

        if len(group) > 1:

            duplicate_groups.append({
                "key": key,
                "publications": [
                    publication.get("publication_id")
                    for publication in group
                ],
            })

    return (
        canonical_publications,
        source_to_canonical,
        duplicate_groups,
    )


# ---------------------------------------------------------------------------
# Reconciliation handling
# ---------------------------------------------------------------------------

def build_decision_index(decisions):
    """
    Reconciliation decisions are keyed by publication + author position.

    Multiple source records can legitimately contain the same position,
    so each key maps to a queue rather than a single decision.
    """

    index = defaultdict(deque)

    for decision in decisions:

        key = (
            decision.get("publication_id"),
            decision.get("position"),
        )

        index[key].append(decision)

    return index


def consume_decision(
    decision_index,
    publication_id,
    position,
):
    """Consume exactly one reconciliation decision."""

    key = (
        publication_id,
        position,
    )

    queue = decision_index.get(key)

    if not queue:
        raise RuntimeError(
            "No reconciliation decision available for "
            f"publication={publication_id}, position={position}"
        )

    return queue.popleft()


# ---------------------------------------------------------------------------
# PostgreSQL helpers
# ---------------------------------------------------------------------------

def connect_database():
    """Open the PostgreSQL connection."""

    print("Connecting to PostgreSQL...")

    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def get_or_create_department(cursor):
    """Create or retrieve the MAIE department."""

    cursor.execute(
        """
        INSERT INTO research.departments (
            institution,
            department_name,
            department_url
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (institution, department_name)
        DO UPDATE SET
            department_url = COALESCE(
                research.departments.department_url,
                EXCLUDED.department_url
            ),
            updated_at = NOW()
        RETURNING department_id
        """,
        (
            "University of Texas Rio Grande Valley",
            "Department of Manufacturing and Industrial Engineering",
            "https://www.utrgv.edu/cecs/departments/maie/faculty/index.htm",
        ),
    )

    return cursor.fetchone()[0]


def upsert_professor(cursor, faculty, department_id):
    """Insert or update one current MAIE professor."""

    name = faculty.get("name") or faculty.get("full_name")

    profile = faculty.get("profile") or {}

    first_name = first_nonempty(
        faculty.get("first_name"),
        profile.get("first_name"),
    )

    middle_name = first_nonempty(
        faculty.get("middle_name"),
        profile.get("middle_name"),
    )

    last_name = first_nonempty(
        faculty.get("last_name"),
        profile.get("last_name"),
    )

    academic_title = first_nonempty(
        faculty.get("rank"),
        faculty.get("academic_title"),
    )

    profile_url = first_nonempty(
        faculty.get("profile_url"),
        profile.get("profile_url"),
    )

    cv_url = first_nonempty(
        faculty.get("cv_url"),
        profile.get("cv_url"),
    )

    email = first_nonempty(
        faculty.get("email"),
        profile.get("email"),
    )

    office_location = first_nonempty(
        faculty.get("office_location"),
        profile.get("office_location"),
    )

    research_interests = first_nonempty(
        faculty.get("research_interests"),
        profile.get("research_interests"),
    )

    lab_name = first_nonempty(
        faculty.get("lab_name"),
        profile.get("lab_name"),
    )

    lab_url = first_nonempty(
        faculty.get("lab_url"),
        profile.get("lab_url"),
    )

    orcid = first_nonempty(
        faculty.get("orcid"),
        profile.get("orcid"),
    )

    google_scholar_url = first_nonempty(
        faculty.get("google_scholar_url"),
        profile.get("google_scholar_url"),
    )

    semantic_scholar_id = first_nonempty(
        faculty.get("semantic_scholar_id"),
        profile.get("semantic_scholar_id"),
    )

    source_url = first_nonempty(
        faculty.get("source_url"),
        profile.get("source_url"),
    )

    cursor.execute(
        """
        INSERT INTO research.professors (
            full_name,
            first_name,
            middle_name,
            last_name,
            institution,
            department_id,
            academic_title,
            profile_url,
            cv_url,
            email,
            office_location,
            research_interests,
            lab_name,
            lab_url,
            orcid,
            google_scholar_url,
            semantic_scholar_id,
            source_url,
            discovery_status
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            'DISCOVERED'
        )
        ON CONFLICT (institution, full_name)
        DO UPDATE SET
            first_name = COALESCE(
                research.professors.first_name,
                EXCLUDED.first_name
            ),
            middle_name = COALESCE(
                research.professors.middle_name,
                EXCLUDED.middle_name
            ),
            last_name = COALESCE(
                research.professors.last_name,
                EXCLUDED.last_name
            ),
            department_id = EXCLUDED.department_id,
            academic_title = COALESCE(
                research.professors.academic_title,
                EXCLUDED.academic_title
            ),
            profile_url = COALESCE(
                research.professors.profile_url,
                EXCLUDED.profile_url
            ),
            cv_url = COALESCE(
                research.professors.cv_url,
                EXCLUDED.cv_url
            ),
            email = COALESCE(
                research.professors.email,
                EXCLUDED.email
            ),
            office_location = COALESCE(
                research.professors.office_location,
                EXCLUDED.office_location
            ),
            research_interests = COALESCE(
                research.professors.research_interests,
                EXCLUDED.research_interests
            ),
            lab_name = COALESCE(
                research.professors.lab_name,
                EXCLUDED.lab_name
            ),
            lab_url = COALESCE(
                research.professors.lab_url,
                EXCLUDED.lab_url
            ),
            orcid = COALESCE(
                research.professors.orcid,
                EXCLUDED.orcid
            ),
            google_scholar_url = COALESCE(
                research.professors.google_scholar_url,
                EXCLUDED.google_scholar_url
            ),
            semantic_scholar_id = COALESCE(
                research.professors.semantic_scholar_id,
                EXCLUDED.semantic_scholar_id
            ),
            source_url = COALESCE(
                research.professors.source_url,
                EXCLUDED.source_url
            ),
            updated_at = NOW()
        RETURNING professor_id
        """,
        (
            name,
            first_name,
            middle_name,
            last_name,
            "University of Texas Rio Grande Valley",
            department_id,
            academic_title,
            profile_url,
            cv_url,
            email,
            office_location,
            research_interests,
            lab_name,
            lab_url,
            orcid,
            google_scholar_url,
            semantic_scholar_id,
            source_url,
        ),
    )

    return cursor.fetchone()[0]


def upsert_paper(cursor, publication):
    """Insert or update one canonical paper."""

    title = (
        publication.get("title")
        or publication.get("normalized_title")
    )

    year = parse_year(publication.get("year"))

    dates = publication.get("dates") or {}

    publication_date = first_nonempty(
        dates.get("published"),
        dates.get("accepted"),
    )

    cursor.execute(
        """
        INSERT INTO research.papers (
            title,
            abstract,
            publication_year,
            publication_date,
            venue,
            publisher,
            doi,
            isbn,
            pmid,
            publication_url,
            legitimate_pdf_url,
            keywords,
            research_topics,
            citation_count,
            source_name,
            source_url,
            metadata_status,
            full_text_status
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            'DISCOVERED', 'UNKNOWN'
        )
        ON CONFLICT (title, publication_year)
        DO UPDATE SET
            abstract = COALESCE(
                research.papers.abstract,
                EXCLUDED.abstract
            ),
            publication_date = COALESCE(
                research.papers.publication_date,
                EXCLUDED.publication_date
            ),
            venue = COALESCE(
                research.papers.venue,
                EXCLUDED.venue
            ),
            publisher = COALESCE(
                research.papers.publisher,
                EXCLUDED.publisher
            ),
            doi = COALESCE(
                research.papers.doi,
                EXCLUDED.doi
            ),
            isbn = COALESCE(
                research.papers.isbn,
                EXCLUDED.isbn
            ),
            publication_url = COALESCE(
                research.papers.publication_url,
                EXCLUDED.publication_url
            ),
            source_url = COALESCE(
                research.papers.source_url,
                EXCLUDED.source_url
            ),
            updated_at = NOW()
        RETURNING paper_id
        """,
        (
            title,
            publication.get("abstract"),
            year,
            publication_date,
            None,# publication.get("type"),
            publication.get("publisher"),
            publication.get("doi"),
            None,# publication.get("isbn_issn"),
            publication.get("pmcid"),
            publication.get("url"),
            None, #legitimate_pdf_url
            None, #keywords
            None, #research_topics
            None, #citation count
            "UTRGV Digital Measures",
            None, #source_url
        ),
    )

    return cursor.fetchone()[0]


def insert_authorship(
    cursor,
    professor_id,
    paper_id,
    author,
):
    """Insert one canonical professor-paper authorship relationship."""

    cursor.execute(
        """
        INSERT INTO research.authorships (
            professor_id,
            paper_id,
            author_position,
            author_name_as_published,
            is_corresponding_author
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (professor_id, paper_id)
        DO UPDATE SET
            author_position = COALESCE(
                research.authorships.author_position,
                EXCLUDED.author_position
            ),
            author_name_as_published = COALESCE(
                research.authorships.author_name_as_published,
                EXCLUDED.author_name_as_published
            ),
            is_corresponding_author = COALESCE(
                research.authorships.is_corresponding_author,
                EXCLUDED.is_corresponding_author
            )
        """,
        (
            professor_id,
            paper_id,
            safe_int(author.get("position")),
            author.get("author_namr_original"),
            None,
        ),
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_database(cursor):
    """Verify the final database counts."""

    queries = {
        "departments": """
            SELECT COUNT(*) FROM research.departments
        """,
        "professors": """
            SELECT COUNT(*) FROM research.professors
        """,
        "papers": """
            SELECT COUNT(*) FROM research.papers
        """,
        "authorships": """
            SELECT COUNT(*) FROM research.authorships
        """,
        "topics": """
            SELECT COUNT(*) FROM research.topics
        """,
        "documents": """
            SELECT COUNT(*) FROM research.documents
        """,
        "ingestion_runs": """
            SELECT COUNT(*) FROM research.ingestion_runs
        """,
    }

    results = {}

    for name, query in queries.items():
        cursor.execute(query)
        results[name] = cursor.fetchone()[0]

    return results


def print_verification(results):
    """Print post-import verification."""

    print()
    print("=" * 80)
    print("POST-IMPORT DATABASE VERIFICATION")
    print("=" * 80)

    for key, value in results.items():
        print(f"{key:25}: {value}")

    print()
    print("Expected:")
    print("departments             : 1")
    print("professors              : 14")
    print("papers                  : 454")
    print("authorships             : 433")
    print("topics                  : 0")
    print("documents               : 0")
    print("ingestion_runs          : 0")


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

def main():

    print("=" * 80)
    print("MAIE DATABASE IMPORT")
    print("=" * 80)

    print()
    print("Loading reconciled source...")

    if not RECONCILED_PATH.exists():
        raise FileNotFoundError(RECONCILED_PATH)

    if not RECONCILIATION_PATH.exists():
        raise FileNotFoundError(RECONCILIATION_PATH)

    reconciled = load_json(RECONCILED_PATH)
    reconciliation = load_json(RECONCILIATION_PATH)

    faculty_records = reconciled["faculty"]
    publications = reconciled["publications"]

    decisions = reconciliation["decisions"]

    print(f"Faculty records       : {len(faculty_records)}")
    print(f"Publications          : {len(publications)}")
    print(f"Reconciliation        : {len(decisions)} decisions")

    # ---------------------------------------------------------------
    # Validate reconciliation coverage before touching PostgreSQL.
    # ---------------------------------------------------------------

    if len(decisions) != 1624:
        raise RuntimeError(
            "Unexpected reconciliation decision count: "
            f"{len(decisions)}"
        )

    # ---------------------------------------------------------------
    # Build current faculty indexes.
    # ---------------------------------------------------------------

    faculty_by_id, faculty_by_name = build_faculty_indexes(
        faculty_records
    )

    if len(faculty_by_id) != 14:
        raise RuntimeError(
            "Expected 14 current MAIE faculty IDs, got "
            f"{len(faculty_by_id)}"
        )

    # ---------------------------------------------------------------
    # Canonicalize publications.
    # ---------------------------------------------------------------

    (
        canonical_publications,
        source_to_canonical,
        duplicate_groups,
    ) = build_canonical_publications(publications)

    if len(canonical_publications) != 454:
        raise RuntimeError(
            "Expected 454 canonical papers, got "
            f"{len(canonical_publications)}"
        )

    if len(duplicate_groups) != 1:
        raise RuntimeError(
            "Expected exactly one publication merge group, got "
            f"{len(duplicate_groups)}"
        )

    current_maie_occurrences = []

    for publication in publications:

        publication_id = publication.get("publication_id")

        canonical_publication = source_to_canonical.get(
            publication_id
        )

        if canonical_publication is None:
            raise RuntimeError(
                "Publication was not mapped to a canonical paper: "
                f"{publication_id}"
            )

        for author in publication.get("authors", []):

            faculty = classify_current_maie(
                author,
                faculty_by_id,
                faculty_by_name,
            )

            if faculty is None:
                continue

            current_maie_occurrences.append({
                "publication": canonical_publication,
                "faculty": faculty,
                "author": author,
            })

    if len(current_maie_occurrences) != 436:
        raise RuntimeError(
            "Expected 436 safe MAIE author occurrences, got "
            f"{len(current_maie_occurrences)}"
        )

    # ---------------------------------------------------------------
    # Canonicalize authorships by professor + paper.
    # ---------------------------------------------------------------

    canonical_authorships = {}

    for occurrence in current_maie_occurrences:

        faculty = occurrence["faculty"]
        publication = occurrence["publication"]

        faculty_key = first_nonempty(
            faculty.get("user_id"),
            faculty.get("dm_user_id"),
        )

        if not faculty_key:
            raise RuntimeError(
                "Current MAIE faculty has no Digital Measures ID: "
                f"{faculty.get('name')}"
            )

        paper_key = (
            publication.get("title"),
            parse_year(publication.get("year")),
        )

        relationship_key = (
            str(faculty_key),
            paper_key,
        )

        canonical_authorships.setdefault(
            relationship_key,
            occurrence,
        )

    if len(canonical_authorships) != 433:
        raise RuntimeError(
            "Expected 433 canonical authorships, got "
            f"{len(canonical_authorships)}"
        )

    print()
    print("-" * 80)
    print("PRE-IMPORT VALIDATION")
    print("-" * 80)

    print(f"Canonical papers       : {len(canonical_publications)}")
    print(f"Safe MAIE occurrences  : {len(current_maie_occurrences)}")
    print(f"Canonical authorships  : {len(canonical_authorships)}")

    # ---------------------------------------------------------------
    # Connect and start transaction.
    # ---------------------------------------------------------------

    connection = connect_database()

    try:

        # psycopg2 starts a transaction automatically after the first
        # database operation.
        cursor = connection.cursor()

        print()
        print("-" * 80)
        print("IMPORTING")
        print("-" * 80)

        # -----------------------------------------------------------
        # Department
        # -----------------------------------------------------------

        department_id = get_or_create_department(cursor)

        print(
            f"Department ready       : department_id={department_id}"
        )

        # -----------------------------------------------------------
        # Professors
        # -----------------------------------------------------------

        professor_ids = {}

        for faculty in faculty_records:

            faculty_id = first_nonempty(
                faculty.get("user_id"),
                faculty.get("dm_user_id"),
            )

            professor_id = upsert_professor(
                cursor,
                faculty,
                department_id,
            )

            professor_ids[str(faculty_id)] = professor_id

        print("Professors imported     : 14")

        # -----------------------------------------------------------
        # Papers
        # -----------------------------------------------------------

        paper_ids = {}

        for publication in canonical_publications:

            paper_id = upsert_paper(
                cursor,
                publication,
            )

            paper_key = (
                publication.get("title"),
                parse_year(publication.get("year")),
            )

            paper_ids[paper_key] = paper_id

        print(
            f"Papers imported        : {len(paper_ids)}"
        )

        # -----------------------------------------------------------
        # Authorships
        # -----------------------------------------------------------

        for occurrence in canonical_authorships.values():

            faculty = occurrence["faculty"]
            publication = occurrence["publication"]
            author = occurrence["author"]

            faculty_id = str(
                first_nonempty(
                    faculty.get("user_id"),
                    faculty.get("dm_user_id"),
                )
            )

            paper_key = (
                publication.get("title"),
                parse_year(publication.get("year")),
            )

            professor_id = professor_ids[faculty_id]
            paper_id = paper_ids[paper_key]

            insert_authorship(
                cursor,
                professor_id,
                paper_id,
                author,
            )

        print(
            f"Authorships imported   : "
            f"{len(canonical_authorships)}"
        )

        # -----------------------------------------------------------
        # Verify BEFORE COMMIT.
        # -----------------------------------------------------------

        results = verify_database(cursor)

        print_verification(results)

        expected = {
            "departments": 1,
            "professors": 14,
            "papers": 454,
            "authorships": 433,
            "topics": 0,
            "documents": 0,
            "ingestion_runs": 0,
        }

        if results != expected:
            raise RuntimeError(
                "Post-import verification failed.\n"
                f"Expected: {expected}\n"
                f"Actual:   {results}"
            )

        # -----------------------------------------------------------
        # COMMIT.
        # -----------------------------------------------------------

        connection.commit()

        print()
        print("=" * 80)
        print("IMPORT RESULT: PASS")
        print("=" * 80)
        print()
        print("The MAIE research ledger was committed successfully.")
        print()
        print("Database now contains:")
        print("  1 department")
        print("  14 professors")
        print("  454 canonical papers")
        print("  433 canonical MAIE authorship relationships")
        print()
        print("No topics, documents, or ingestion runs were created.")

    except Exception:

        print()
        print("=" * 80)
        print("IMPORT FAILED")
        print("=" * 80)
        print()
        print("Rolling back the transaction...")

        connection.rollback()

        print("ROLLBACK COMPLETE")

        raise

    finally:

        connection.close()


if __name__ == "__main__":
    main()