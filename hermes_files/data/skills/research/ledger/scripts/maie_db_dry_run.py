#!/usr/bin/env python3

"""
MAIE DATABASE IMPORT DRY RUN

Read-only validation of the reconciled MAIE dataset against PostgreSQL.

No INSERT/UPDATE/DELETE/ALTER statements are executed.

The script:
1. Canonicalizes publications by (title, year).
2. Reads the reconciliation decisions already produced by the
   authorship-reconciliation pipeline.
3. Counts only reconciliation decisions that map to current MAIE faculty.
4. Collapses duplicate professor/paper relationships to satisfy the
   research.authorships primary key.
5. Verifies the PostgreSQL schema and current DB state.
"""

import json
import os
import sys
from collections import defaultdict

import psycopg2


REPO_ROOT = os.path.expanduser("~/local_hermes")

DATA_DIR = os.path.join(
    REPO_ROOT,
    "hermes_files/data/skills/research/ledger/data",
)

SOURCE_PATH = os.path.join(
    DATA_DIR,
    "maie_faculty_reconciled.json",
)

RECONCILIATION_PATH = os.path.join(
    DATA_DIR,
    "maie_authorship_reconciliation.json",
)

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "rag",
    "user": "rag",
    "password": "rag",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_key(value):
    if value is None:
        return ""

    return " ".join(str(value).strip().split()).casefold()


def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_faculty(data):
    faculty = data.get("faculty", [])

    if not isinstance(faculty, list):
        raise ValueError("Expected 'faculty' to be a list.")

    return faculty


def get_publications(data):
    publications = data.get("publications", [])

    if not isinstance(publications, list):
        raise ValueError("Expected 'publications' to be a list.")

    return publications


def canonicalize_publications(publications):
    """
    Canonical database identity:

        (title, publication_year)

    Multiple normalized source publications with the same key become
    one database paper while all source publication IDs remain visible.
    """

    groups = defaultdict(list)

    for pub in publications:

        key = (
            normalize_key(pub.get("title")),
            pub.get("year"),
        )

        groups[key].append(pub)

    canonical = []

    for key, group in groups.items():

        representative = dict(group[0])

        source_publication_ids = []

        for pub in group:

            publication_id = pub.get("publication_id")

            if publication_id not in source_publication_ids:
                source_publication_ids.append(publication_id)

        representative["_source_publication_ids"] = (
            source_publication_ids
        )

        representative["_source_publication_count"] = len(group)

        canonical.append(representative)

    return canonical, groups


def build_faculty_indexes(faculty_records):

    by_id = {}
    by_name = {}

    for faculty in faculty_records:

        faculty_id = (
            faculty.get("user_id")
            or faculty.get("dm_user_id")
        )

        name = faculty.get("name")

        if faculty_id:
            by_id[str(faculty_id)] = faculty

        if name:
            by_name[normalize_key(name)] = faculty

    return by_id, by_name


def get_reconciliation_decisions(reconciliation):
    """
    The reconciliation file contains one decision per normalized
    author occurrence.

    The exact field name is detected defensively so that this script
    remains compatible with the generated reconciliation artifact.
    """

    if isinstance(reconciliation, list):
        return reconciliation

    for key in (
        "decisions",
        "author_decisions",
        "reconciliations",
        "records",
    ):
        value = reconciliation.get(key)

        if isinstance(value, list):
            return value

    raise ValueError(
        "Could not locate reconciliation decisions in "
        "maie_authorship_reconciliation.json"
    )


def classify_current_maie(decision, faculty_by_id, faculty_by_name):

    mapped_id = decision.get("mapped_faculty_id")
    mapped_name = decision.get("mapped_faculty_name")

    # First use the explicit reconciliation mapping.
    if mapped_id:
        faculty = faculty_by_id.get(str(mapped_id))

        if faculty:
            return faculty

    if mapped_name:
        faculty = faculty_by_name.get(
            normalize_key(mapped_name)
        )

        if faculty:
            return faculty

    # Some exact/variant decisions may carry the original faculty ID.
    original_id = decision.get("faculty_id_original")

    if original_id:
        faculty = faculty_by_id.get(str(original_id))

        if faculty:
            return faculty

    return None


def build_source_publication_map(publications):

    mapping = {}

    for pub in publications:

        publication_id = pub.get("publication_id")

        if publication_id:
            mapping[publication_id] = (
                normalize_key(pub.get("title")),
                pub.get("year"),
            )

    return mapping


def build_canonical_authorships(
    decisions,
    faculty_by_id,
    faculty_by_name,
    source_publication_map,
):
    """
    Build the actual relationships that can be inserted into:

        research.authorships

    Multiple source author occurrences can point to the same
    professor/paper relationship. Those occurrences are retained in
    provenance but only one relationship is prospective for PostgreSQL.
    """

    relationships = {}

    current_maie_occurrences = []

    for decision in decisions:

        faculty = classify_current_maie(
            decision,
            faculty_by_id,
            faculty_by_name,
        )

        if faculty is None:
            continue

        publication_id = decision.get("publication_id")

        paper_key = source_publication_map.get(publication_id)

        if paper_key is None:

            title = decision.get("title")
            year = decision.get("year")

            paper_key = (
                normalize_key(title),
                year,
            )

        professor_id = (
            faculty.get("user_id")
            or faculty.get("dm_user_id")
        )

        if not professor_id:
            continue

        occurrence = {
            "publication_id": publication_id,
            "paper_key": paper_key,
            "professor_id": str(professor_id),
            "professor_name": faculty.get("name"),
            "position": decision.get("position"),
            "author_name": decision.get("author_name_original"),
            "classification": decision.get("classification"),
        }

        current_maie_occurrences.append(occurrence)

        relationship_key = (
            str(professor_id),
            paper_key,
        )

        if relationship_key not in relationships:

            relationships[relationship_key] = {
                "professor_id": str(professor_id),
                "professor_name": faculty.get("name"),
                "paper_key": paper_key,
                "source_occurrences": [],
            }

        relationships[relationship_key][
            "source_occurrences"
        ].append(occurrence)

    return relationships, current_maie_occurrences


def verify_schema(conn):

    required_tables = {
        "departments",
        "professors",
        "papers",
        "authorships",
        "topics",
        "professor_topics",
        "paper_topics",
        "documents",
        "ingestion_runs",
    }

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'research'
            """
        )

        actual = {
            row[0]
            for row in cur.fetchall()
        }

    return required_tables - actual


def get_database_state(conn):

    tables = [
        "authorships",
        "departments",
        "documents",
        "ingestion_runs",
        "paper_topics",
        "papers",
        "professor_topics",
        "professors",
        "topics",
    ]

    state = {}

    with conn.cursor() as cur:

        for table in tables:

            cur.execute(
                f"SELECT COUNT(*) FROM research.{table}"
            )

            state[table] = cur.fetchone()[0]

    return state


def find_existing_records(
    conn,
    faculty_records,
    canonical_papers,
):

    existing_department = False
    existing_professors = 0
    existing_papers = 0

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT COUNT(*)
            FROM research.departments
            WHERE institution = %s
              AND department_name = %s
            """,
            (
                "UTRGV",
                "Department of Manufacturing and Industrial Engineering",
            ),
        )

        existing_department = cur.fetchone()[0] > 0

        for faculty in faculty_records:

            cur.execute(
                """
                SELECT COUNT(*)
                FROM research.professors
                WHERE institution = %s
                  AND full_name = %s
                """,
                (
                    "UTRGV",
                    faculty.get("name"),
                ),
            )

            existing_professors += cur.fetchone()[0]

        for paper in canonical_papers:

            cur.execute(
                """
                SELECT COUNT(*)
                FROM research.papers
                WHERE title = %s
                  AND publication_year IS NOT DISTINCT FROM %s
                """,
                (
                    paper.get("title"),
                    paper.get("year"),
                ),
            )

            existing_papers += cur.fetchone()[0]

    return (
        existing_department,
        existing_professors,
        existing_papers,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    print()
    print("=" * 80)
    print("MAIE DATABASE IMPORT DRY RUN")
    print("=" * 80)

    # -----------------------------------------------------------------------
    # Load artifacts
    # -----------------------------------------------------------------------

    print()
    print("Loading reconciled source...")
    source = load_json(SOURCE_PATH)

    print("Loading authorship reconciliation...")
    reconciliation = load_json(RECONCILIATION_PATH)

    faculty_records = get_faculty(source)
    publications = get_publications(source)
    decisions = get_reconciliation_decisions(reconciliation)

    # -----------------------------------------------------------------------
    # Basic source counts
    # -----------------------------------------------------------------------

    author_occurrences = sum(
        len(pub.get("authors", []))
        for pub in publications
    )

    unique_dm_ids = set()

    for pub in publications:

        for dm_id in pub.get("dm_record_ids", []):

            if dm_id is not None:
                unique_dm_ids.add(str(dm_id))

    # -----------------------------------------------------------------------
    # Publication canonicalization
    # -----------------------------------------------------------------------

    canonical_papers, publication_groups = (
        canonicalize_publications(publications)
    )

    duplicate_publication_groups = [
        group
        for group in publication_groups.values()
        if len(group) > 1
    ]

    # -----------------------------------------------------------------------
    # Faculty indexes
    # -----------------------------------------------------------------------

    faculty_by_id, faculty_by_name = (
        build_faculty_indexes(faculty_records)
    )

    # -----------------------------------------------------------------------
    # Authorship canonicalization
    # -----------------------------------------------------------------------

    source_publication_map = (
        build_source_publication_map(publications)
    )

    canonical_authorships, current_maie_occurrences = (
        build_canonical_authorships(
            decisions,
            faculty_by_id,
            faculty_by_name,
            source_publication_map,
        )
    )

    duplicate_authorship_groups = [
        relationship
        for relationship in canonical_authorships.values()
        if len(relationship["source_occurrences"]) > 1
    ]

    # -----------------------------------------------------------------------
    # Connect
    # -----------------------------------------------------------------------

    print()
    print("Connecting to PostgreSQL...")

    try:

        conn = psycopg2.connect(**DB_CONFIG)

    except Exception as exc:

        print()
        print("ERROR: Could not connect to PostgreSQL.")
        print(exc)
        sys.exit(1)

    try:

        # Explicit read-only session.
        conn.set_session(readonly=True)

        schema_errors = verify_schema(conn)

        # -------------------------------------------------------------------
        # SOURCE
        # -------------------------------------------------------------------

        print()
        print("-" * 80)
        print("SOURCE")
        print("-" * 80)

        print(
            f"Faculty records              : "
            f"{len(faculty_records)}"
        )

        print(
            f"Publications                : "
            f"{len(publications)}"
        )

        print(
            f"Author occurrences          : "
            f"{author_occurrences}"
        )

        print(
            f"Unique DM records           : "
            f"{len(unique_dm_ids)}"
        )

        print(
            f"Reconciliation decisions    : "
            f"{len(decisions)}"
        )

        # -------------------------------------------------------------------
        # CANONICALIZATION
        # -------------------------------------------------------------------

        print()
        print("-" * 80)
        print("CANONICALIZATION")
        print("-" * 80)

        print(
            f"Source publications         : "
            f"{len(publications)}"
        )

        print(
            f"Canonical database papers   : "
            f"{len(canonical_papers)}"
        )

        print(
            f"Merged publication groups   : "
            f"{len(duplicate_publication_groups)}"
        )

        print(
            f"Source MAIE author entries  : "
            f"{len(current_maie_occurrences)}"
        )

        print(
            f"Canonical MAIE authorships  : "
            f"{len(canonical_authorships)}"
        )

        print(
            f"Collapsed duplicate links  : "
            f"{len(current_maie_occurrences) - len(canonical_authorships)}"
        )

        # -------------------------------------------------------------------
        # Prospective ledger
        # -------------------------------------------------------------------

        print()
        print("-" * 80)
        print("PROSPECTIVE CORE LEDGER ROWS")
        print("-" * 80)

        print("Departments                 : 1")
        print(
            f"Professors                  : "
            f"{len(faculty_records)}"
        )
        print(
            f"Papers                      : "
            f"{len(canonical_papers)}"
        )
        print(
            f"MAIE authorship relationships: "
            f"{len(canonical_authorships)}"
        )

        # -------------------------------------------------------------------
        # Existing DB records
        # -------------------------------------------------------------------

        (
            existing_department,
            existing_professors,
            existing_papers,
        ) = find_existing_records(
            conn,
            faculty_records,
            canonical_papers,
        )

        print()
        print("-" * 80)
        print("ALREADY PRESENT IN DATABASE")
        print("-" * 80)

        print(
            f"Existing department         : "
            f"{'YES' if existing_department else 'NO'}"
        )

        print(
            f"Existing professors         : "
            f"{existing_professors}"
        )

        print(
            f"Existing papers             : "
            f"{existing_papers}"
        )

        # -------------------------------------------------------------------
        # Topics/documents intentionally deferred
        # -------------------------------------------------------------------

        print()
        print("-" * 80)
        print("TOPICS / DOCUMENTS")
        print("-" * 80)

        print("Topics                      : 0")
        print("Professor-topic links       : 0")
        print("Paper-topic links           : 0")
        print("Documents                   : 0")
        print("Ingestion runs              : 0")

        # -------------------------------------------------------------------
        # DB state
        # -------------------------------------------------------------------

        state = get_database_state(conn)

        print()
        print("-" * 80)
        print("DATABASE STATE")
        print("-" * 80)

        for table in sorted(state):

            print(
                f"{table:28}: "
                f"{state[table]}"
            )

        # -------------------------------------------------------------------
        # Publication canonicalization details
        # -------------------------------------------------------------------

        print()
        print("=" * 80)
        print("PUBLICATION CANONICALIZATION")
        print("=" * 80)

        if duplicate_publication_groups:

            for group in duplicate_publication_groups:

                representative = group[0]

                print()
                print(
                    f"{representative.get('year')} | "
                    f"{representative.get('title')}"
                )

                for pub in group:

                    dm_ids = pub.get(
                        "dm_record_ids",
                        [],
                    )

                    print(
                        f"    {pub.get('publication_id')} "
                        f"| DM IDs: "
                        f"{', '.join(str(x) for x in dm_ids)}"
                    )

            print()
            print(
                "These source records become ONE canonical "
                "research.papers row."
            )

        else:

            print()
            print(
                "No publication canonicalization required."
            )

        # -------------------------------------------------------------------
        # Authorship canonicalization details
        # -------------------------------------------------------------------

        print()
        print("=" * 80)
        print("AUTHORSHIP CANONICALIZATION")
        print("=" * 80)

        if duplicate_authorship_groups:

            for relationship in duplicate_authorship_groups:

                print()
                print(
                    f"Professor : "
                    f"{relationship['professor_name']}"
                )

                print(
                    f"Paper     : "
                    f"{relationship['paper_key'][0]} "
                    f"| {relationship['paper_key'][1]}"
                )

                print(
                    f"Source occurrences: "
                    f"{len(relationship['source_occurrences'])}"
                )

                for occurrence in (
                    relationship["source_occurrences"]
                ):

                    print(
                        f"    {occurrence['publication_id']} "
                        f"| position="
                        f"{occurrence['position']} "
                        f"| name="
                        f"'{occurrence['author_name']}' "
                        f"| status="
                        f"{occurrence['classification']}"
                    )

            print()
            print(
                "These source occurrences become ONE canonical "
                "research.authorships row."
            )

        else:

            print()
            print(
                "No authorship canonicalization required."
            )

        # -------------------------------------------------------------------
        # Validation
        # -------------------------------------------------------------------

        errors = []
        warnings = []

        if schema_errors:

            errors.append(
                "Missing required research schema tables: "
                + ", ".join(sorted(schema_errors))
            )

        if len(faculty_records) != 14:

            errors.append(
                f"Expected 14 faculty records; found "
                f"{len(faculty_records)}."
            )

        if len(publications) != 455:

            errors.append(
                f"Expected 455 publications; found "
                f"{len(publications)}."
            )

        if len(unique_dm_ids) != 459:

            errors.append(
                f"Expected 459 unique DM record IDs; found "
                f"{len(unique_dm_ids)}."
            )

        # We expect the already validated reconciliation to have one
        # decision per author occurrence.
        if len(decisions) != author_occurrences:

            errors.append(
                "Reconciliation decision count does not equal "
                "source author occurrence count: "
                f"{len(decisions)} vs {author_occurrences}."
            )

        if not current_maie_occurrences:

            errors.append(
                "No current-MAIE authorship relationships were recovered "
                "from the reconciliation decisions."
            )

        # The prior validated pipeline established 436 prospective MAIE
        # source author occurrences.
        if len(current_maie_occurrences) != 436:

            errors.append(
                "Expected 436 prospective MAIE author occurrences; "
                f"found {len(current_maie_occurrences)}."
            )

        # The prior database dry run established exactly one PK collision,
        # producing 435 canonical relationships.
        if len(canonical_authorships) != 435:

            errors.append(
                "Expected 435 canonical MAIE authorship relationships; "
                f"found {len(canonical_authorships)}."
            )

        if len(duplicate_authorship_groups) != 1:

            errors.append(
                "Expected exactly one duplicate professor/paper "
                "relationship group; found "
                f"{len(duplicate_authorship_groups)}."
            )

        # -------------------------------------------------------------------
        # Final
        # -------------------------------------------------------------------

        print()
        print("-" * 80)
        print("VALIDATION")
        print("-" * 80)

        print(
            f"Source title/year duplicate groups : "
            f"{len(duplicate_publication_groups)}"
        )

        print(
            f"Canonical database papers          : "
            f"{len(canonical_papers)}"
        )

        print(
            f"Source MAIE author occurrences     : "
            f"{len(current_maie_occurrences)}"
        )

        print(
            f"Canonical authorship relationships : "
            f"{len(canonical_authorships)}"
        )

        print(
            f"Schema errors                       : "
            f"{len(schema_errors)}"
        )

        print(
            f"Warnings                            : "
            f"{len(warnings)}"
        )

        print(
            f"Errors                              : "
            f"{len(errors)}"
        )

        if warnings:

            print()
            print("-" * 80)
            print("WARNINGS")
            print("-" * 80)

            for warning in warnings:
                print(
                    f"WARNING: {warning}"
                )

        if errors:

            print()
            print("-" * 80)
            print("ERRORS")
            print("-" * 80)

            for error in errors:
                print(
                    f"ERROR: {error}"
                )

            print()
            print("=" * 80)
            print("DRY RUN RESULT: FAILED")
            print("=" * 80)

            print()
            print(
                "NO DATABASE CHANGES WERE MADE."
            )

            conn.rollback()
            sys.exit(2)

        print()
        print("=" * 80)
        print("DRY RUN RESULT: PASS")
        print("=" * 80)

        print()
        print(
            "Publication and authorship canonicalization "
            "successfully resolves the PostgreSQL uniqueness constraints."
        )

        print()
        print(
            "NO DATABASE CHANGES WERE MADE."
        )

        conn.rollback()

    finally:

        conn.close()


if __name__ == "__main__":
    main()