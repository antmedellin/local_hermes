#!/usr/bin/env python3

"""
Import a reconciled department research ledger into PostgreSQL.

IMPORTANT:
- This script performs real database writes.
- It uses the already reconciled dataset.
- Only explicitly safe authorship classifications are imported.
- Historical ID mismatches and moderate-review records are NOT imported.
- The entire import runs inside one PostgreSQL transaction.
- If anything fails, the transaction is rolled back.

The department-specific paths, metadata, source information, and
validation expectations come from the department config.yaml file.

No topics, documents, or ingestion runs are created here.
Those are later pipeline stages.
"""

import argparse
import json
import os
import re
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

import psycopg2
import yaml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
LEDGER_DIR = SCRIPT_DIR.parent


# ---------------------------------------------------------------------------
# Command-line arguments
# ---------------------------------------------------------------------------

def parse_args():
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Import a reconciled department research ledger into PostgreSQL."
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to the department configuration YAML file.",
    )

    return parser.parse_args()


def load_config(config_file):
    """
    Load and validate the department configuration.

    The config contains department-specific information such as:
        - institution
        - department name
        - department URL
        - output directory
        - source information
        - expected validation counts
    """

    with config_file.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    required_fields = [
        "institution",
        "department_name",
        "department_url",
        "output_directory",
        "sources",
        "validation",
    ]

    for field in required_fields:
        if field not in config:
            raise ValueError(
                f"Missing required configuration field: {field}"
            )

    if "faculty" not in config["sources"]:
        raise ValueError(
            "Missing required configuration section: sources.faculty"
        )

    return config


def resolve_output_directory(config_file, configured_path):
    """
    Resolve the configured output directory.

    Relative paths are interpreted relative to the repository root.
    Absolute paths are used unchanged.
    """

    output_directory = Path(configured_path)

    if output_directory.is_absolute():
        return output_directory

    repository_root = LEDGER_DIR.parents[4]

    return repository_root / output_directory


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

args = parse_args()

CONFIG_FILE = Path(args.config).resolve()
CONFIG = load_config(CONFIG_FILE)

INSTITUTION = CONFIG["institution"]
DEPARTMENT_NAME = CONFIG["department_name"]
DEPARTMENT_URL = CONFIG["department_url"]

OUTPUT_DIRECTORY = resolve_output_directory(
    CONFIG_FILE,
    CONFIG["output_directory"],
)

RECONCILED_PATH = OUTPUT_DIRECTORY / "faculty_reconciled.json"
RECONCILIATION_PATH = OUTPUT_DIRECTORY / "authorship_reconciliation.json"

FACULTY_SOURCE = CONFIG["sources"]["faculty"]
SOURCE_NAME = FACULTY_SOURCE.get(
    "source_name",
    FACULTY_SOURCE.get("type", "Unknown source"),
)

VALIDATION = CONFIG["validation"]


# ---------------------------------------------------------------------------
# PostgreSQL configuration
# ---------------------------------------------------------------------------

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "rag")
DB_USER = os.getenv("POSTGRES_USER", "rag")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "rag")


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
    # "NAME_VARIANT_WITHOUT_DM_ID",
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
    Build lookup indexes for current department faculty.

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


def classify_current_department(
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
    """Create or retrieve the configured department."""

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
            INSTITUTION,
            DEPARTMENT_NAME,
            DEPARTMENT_URL,
        ),
    )

    return cursor.fetchone()[0]


def upsert_professor(cursor, faculty, department_id):
    """Insert or update one current department professor."""

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
            INSTITUTION,
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
            SOURCE_NAME,
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
            author.get("author_name_original"),
            None,
        ),
    )

def verify_expected_authorships(
    cursor,
    department_id,
    expected_authorship_pairs,
):
    """Verify that every expected department authorship exists."""

    cursor.execute(
        """
        SELECT a.professor_id, a.paper_id
        FROM research.authorships a
        JOIN research.professors p
          ON p.professor_id = a.professor_id
        WHERE p.department_id = %s
        """,
        (department_id,),
    )

    actual_authorship_pairs = {
        (row[0], row[1])
        for row in cursor.fetchall()
    }

    missing = expected_authorship_pairs - actual_authorship_pairs
    # unexpected = actual_authorship_pairs - expected_authorship_pairs

    if missing:
        raise RuntimeError(
            "Authorship relationship verification failed.\n"
            f"Missing relationships: {len(missing)}\n"
            # f"Unexpected relationships: {len(unexpected)}"
        )

    print("Expected authorship relationships: PASS")
    print(f"Verified relationships           : {len(actual_authorship_pairs)}")

def get_global_counts(cursor):
    """Return row counts for the research ledger tables."""

    global_counts = {}

    for table in (
        "departments",
        "professors",
        "papers",
        "authorships",
        "topics",
        "documents",
        "ingestion_runs",
    ):
        cursor.execute(f"SELECT COUNT(*) FROM research.{table}")
        global_counts[table] = cursor.fetchone()[0]

    return global_counts

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_database(cursor):
    """Verify the configured department and global ledger counts."""

    cursor.execute(
        """
        SELECT department_id
        FROM research.departments
        WHERE institution = %s
          AND department_name = %s
        """,
        (INSTITUTION, DEPARTMENT_NAME),
    )
    department_row = cursor.fetchone()

    if department_row is None:
        raise RuntimeError(
            f"Configured department was not found: {DEPARTMENT_NAME}"
        )

    department_id = department_row[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM research.professors
        WHERE department_id = %s
        """,
        (department_id,),
    )
    department_professors = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM research.authorships a
        JOIN research.professors p
          ON p.professor_id = a.professor_id
        WHERE p.department_id = %s
        """,
        (department_id,),
    )
    department_authorships = cursor.fetchone()[0]

    # Global counts are diagnostic; they are not department-specific.
    global_counts = get_global_counts(cursor)

    return {
        "department_id": department_id,
        "department_professors": department_professors,
        "department_authorships": department_authorships,
        "global_counts": global_counts,
    }


def print_verification(results, expected):
    """Print department-specific and global verification counts."""

    print()
    print("=" * 80)
    print("POST-IMPORT DATABASE VERIFICATION")
    print("=" * 80)

    print(f"Department ID             : {results['department_id']}")
    print(
        f"Department professors     : "
        f"{results['department_professors']}"
    )
    print(
        f"Department authorships    : "
        f"{results['department_authorships']}"
    )

    print()
    print("Expected department counts:")

    for key, value in expected.items():
        print(f"{key:28}: {value}")

    print()
    print("Global database counts:")

    for key, value in results["global_counts"].items():
        print(f"{key:28}: {value}")


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

def main():

    print("=" * 80)
    print("DATABASE IMPORT")
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
    expected_decisions = VALIDATION["expected_reconciliation_decision_count"]
    if len(decisions) != expected_decisions:
        raise RuntimeError(
            "Unexpected reconciliation decision count: "
            f"{len(decisions)} "
            f"(expected {expected_decisions})"
        )

    # ---------------------------------------------------------------
    # Build current faculty indexes.
    # ---------------------------------------------------------------

    faculty_by_id, faculty_by_name = build_faculty_indexes(
        faculty_records
    )
    expected_faculty_count = VALIDATION["expected_faculty_count"]

    if len(faculty_by_id) != expected_faculty_count:
        raise RuntimeError(
            f"Expected {expected_faculty_count} current department faculty IDs, "
            f"got {len(faculty_by_id)}"
        )

    # ---------------------------------------------------------------
    # Canonicalize publications.
    # ---------------------------------------------------------------

    (
        canonical_publications,
        source_to_canonical,
        duplicate_groups,
    ) = build_canonical_publications(publications)

    expected_canonical_papers = VALIDATION["expected_canonical_publication_count"]
    if len(canonical_publications) != expected_canonical_papers:
        raise RuntimeError(
            f"Expected {expected_canonical_papers} canonical papers, "
            f"got {len(canonical_publications)}"
        )

    expected_merge_groups = VALIDATION["expected_publication_merge_group_count"]

    if len(duplicate_groups) != expected_merge_groups:
        raise RuntimeError(
            f"Expected {expected_merge_groups} publication merge group, "
            f"got {len(duplicate_groups)}"
        )

    current_department_occurrences = []

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

            faculty = classify_current_department(
                author,
                faculty_by_id,
                faculty_by_name,
            )

            if faculty is None:
                continue

            current_department_occurrences.append({
                "publication": canonical_publication,
                "faculty": faculty,
                "author": author,
            })
    expected_department_occurrences = VALIDATION["expected_department_author_occurrence_count"]

    if len(current_department_occurrences) != expected_department_occurrences:
        raise RuntimeError(
            f"Expected {expected_department_occurrences} safe department "
            f"author occurrences, got {len(current_department_occurrences)}"
        )

    # ---------------------------------------------------------------
    # Canonicalize authorships by professor + paper.
    # ---------------------------------------------------------------

    canonical_authorships = {}

    for occurrence in current_department_occurrences:

        faculty = occurrence["faculty"]
        publication = occurrence["publication"]

        faculty_key = first_nonempty(
            faculty.get("user_id"),
            faculty.get("dm_user_id"),
        )

        if not faculty_key:
            raise RuntimeError(
                "Current department faculty has no Digital Measures ID: "
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

    expected_canonical_authorships = VALIDATION["expected_canonical_authorship_count"]

    if len(canonical_authorships) != expected_canonical_authorships:
        raise RuntimeError(
            f"Expected {expected_canonical_authorships} canonical "
            f"authorships, got {len(canonical_authorships)}"
        )

    print()
    print("-" * 80)
    print("PRE-IMPORT VALIDATION")
    print("-" * 80)

    print(f"Canonical papers       : {len(canonical_publications)}")
    print(f"Safe department occurrences  : {len(current_department_occurrences)}")
    print(f"Canonical authorships  : {len(canonical_authorships)}")

    # ---------------------------------------------------------------
    # Connect and start transaction.
    # ---------------------------------------------------------------

    connection = connect_database()

    try:

        # psycopg2 starts a transaction automatically after the first
        # database operation.
        cursor = connection.cursor()
        #capture the starting state for post-import comparison
        baseline_counts = get_global_counts(cursor)
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

        print(f"Professors imported     : {len(professor_ids)}")

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
        
        expected_authorship_pairs = set()

        for occurrence in canonical_authorships.values():
            faculty = occurrence["faculty"]
            publication = occurrence["publication"]

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

            expected_authorship_pairs.add(
                (
                    professor_ids[faculty_id],
                    paper_ids[paper_key],
                )
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

        verify_expected_authorships(
            cursor,
            department_id,
            expected_authorship_pairs,
        )

        expected = {
            "department_professors": (
                VALIDATION["expected_faculty_count"]
            ),
            "department_authorships": (
                VALIDATION["expected_canonical_authorship_count"]
            ),
        }

        print_verification(results, expected)

        actual_department_counts = {
            "department_professors": results["department_professors"],
            "department_authorships": results["department_authorships"],
        }

        if actual_department_counts != expected:
            raise RuntimeError(
                "Post-import department verification failed.\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual_department_counts}"
            )

        # This import should not create unrelated ledger records.
        unchanged_tables = ("topics", "documents", "ingestion_runs")

        changed_tables = {
            table: {
                "before": baseline_counts[table],
                "after": results["global_counts"][table],
            }
            for table in unchanged_tables
            if baseline_counts[table] != results["global_counts"][table]
        }

        if changed_tables:
            raise RuntimeError(
                "Unexpected changes to unrelated ledger tables:\n"
                f"{changed_tables}"
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
        print(
            f"The {DEPARTMENT_NAME} research ledger "
            "was committed successfully."
        )
        print()
        print("Database now contains:")
        print(f"  {results['department_professors']} department professors")
        print(f"  {results['department_authorships']} department authorships")
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