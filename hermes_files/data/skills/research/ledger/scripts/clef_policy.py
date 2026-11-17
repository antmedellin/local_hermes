
#!/usr/bin/env python3
"""
CLEF POLICY LAYER
=================
Builds a read-only set of identity-evaluation cases for Clef-Flash.

This script:
    1. Reads normalized faculty and publication records.
    2. Reads deterministic authorship reconciliation decisions.
    3. Selects only explicitly permitted evaluation classifications.
    4. Preserves individual author occurrences, including duplicate
       publication positions.
    5. Attaches relevant faculty identity information.
    6. Labels evidence provenance and limitations.
    7. Writes a separate Clef evaluation input file.

IMPORTANT:
    This script does NOT:
        - Modify authorship_reconciliation.json
        - Modify faculty_reconciled.json
        - Modify validation_manifest.json
        - Write to PostgreSQL
        - Approve or change identity mappings
"""
import argparse
import hashlib
import json
import sys

from collections import defaultdict, deque
from pathlib import Path

import yaml

# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------
ELIGIBLE_CLASSIFICATIONS = {
    "HIGH_SIMILARITY",
    "MODERATE_REVIEW",
    "INITIAL_VARIANT",
    "NAME_VARIANT_WITHOUT_DM_ID",
}

# These classifications are deliberately excluded from the
# initial evaluation. They involve historical identity conflicts.
EXCLUDED_CLASSIFICATIONS = {
    "HISTORICAL_ID_MISMATCH",
    "HISTORICAL_ID_SWAP_RECOVERED",
}

OUTPUT_FILENAME = "clef_cases_preview.json"


# ------------------------------------------------------------
# GENERAL UTILITIES
# ------------------------------------------------------------

def load_json(path):
    """Load a JSON file without modifying it."""

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_name(value):
    """Normalize a name for occurrence matching."""

    if not value:
        return ""

    return " ".join(str(value).casefold().split())


def sha256_file(path):
    """Calculate a source file's SHA-256 hash."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


def faculty_id(value):
    """Normalize faculty IDs while preserving missing values."""

    if value is None:
        return None

    value = str(value).strip()

    return value or None


# ------------------------------------------------------------
# CONFIGURATION LOADING
# ------------------------------------------------------------

def resolve_department_directory(config_path):
    """
    Resolve the configured department output directory.

    Relative paths are interpreted from the repository root.
    """

    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("Department configuration must be a YAML mapping.")

    output_directory = config.get("output_directory")

    if not output_directory:
        raise ValueError("Missing output_directory in department config.")

    repository_root = Path(__file__).resolve().parents[6]

    output_path = Path(output_directory)

    if not output_path.is_absolute():
        output_path = repository_root / output_path

    return output_path.resolve()


# ------------------------------------------------------------
# INDEX NORMALIZED DATA
# ------------------------------------------------------------

def index_publications(publications):
    """Index publications by their canonical publication IDs."""

    result = {}

    for publication in publications:
        publication_id = publication.get("publication_id")

        if not publication_id:
            continue

        if publication_id in result:
            raise ValueError(
                f"Duplicate normalized publication ID: {publication_id}"
            )

        result[publication_id] = publication

    return result


def index_faculty(faculty_records):
    """Index current faculty records by Digital Measures ID."""

    result = {}

    for faculty in faculty_records:
        identifier = faculty_id(
            faculty.get("dm_user_id") or faculty.get("user_id")
        )

        if not identifier:
            continue

        if identifier in result:
            raise ValueError(
                f"Duplicate faculty ID in normalized roster: {identifier}"
            )

        result[identifier] = faculty

    return result


# ------------------------------------------------------------
# AUTHOR OCCURRENCE MATCHING
# ------------------------------------------------------------

def build_author_occurrence_index(publications):
    """
    Build queues of normalized author occurrences.

    Publication ID + position is not unique.

    We therefore use:
        publication ID
        position
        normalized author name
        source faculty ID

    Each queue preserves the original normalized author array order.
    """

    exact_index = defaultdict(deque)
    name_index = defaultdict(deque)
    position_index = defaultdict(deque)

    for publication_id, publication in publications.items():

        authors = publication.get("authors", [])

        for author_index, author in enumerate(authors):

            position = author.get("position")
            name = normalize_name(
                author.get("name")
                or author.get("normalized_name")
            )

            identifier = faculty_id(author.get("faculty_id"))

            exact_key = (
                publication_id,
                position,
                name,
                identifier,
            )

            name_key = (
                publication_id,
                position,
                name,
            )

            position_key = (
                publication_id,
                position,
            )

            occurrence = {
                "author_index": author_index,
                "author": author,
            }

            exact_index[exact_key].append(occurrence)
            name_index[name_key].append(occurrence)
            position_index[position_key].append(occurrence)

    return exact_index, name_index, position_index


def consume_occurrence(
    decision,
    exact_index,
    name_index,
    position_index,
):
    """
    Match one reconciliation decision to one normalized author.

    Exact matching is attempted first.

    If source ID differs or is absent, name + position is attempted.

    Position-only matching is allowed only when exactly one
    unmatched candidate remains.

    A matched occurrence is consumed once.
    """

    publication_id = decision.get("publication_id")
    position = decision.get("position")

    name = normalize_name(decision.get("author_name_original"))
    identifier = faculty_id(decision.get("faculty_id_original"))

    exact_key = (
        publication_id,
        position,
        name,
        identifier,
    )

    name_key = (
        publication_id,
        position,
        name,
    )

    position_key = (
        publication_id,
        position,
    )

    if exact_index[exact_key]:
        return exact_index[exact_key].popleft(), "EXACT"

    if name_index[name_key]:
        return name_index[name_key].popleft(), "NAME_AND_POSITION"

    remaining = position_index[position_key]

    if len(remaining) == 1:
        return remaining.popleft(), "UNIQUE_POSITION_FALLBACK"

    return None, "UNMATCHED_OR_AMBIGUOUS"


# ------------------------------------------------------------
# EVIDENCE CONSTRUCTION
# ------------------------------------------------------------

def build_evidence(decision, publication, faculty_record, occurrence):
    """
    Construct a bounded evidence package for Clef.

    Evidence is separated by provenance.

    Digital Measures fields are not treated as independent
    corroboration merely because they appear in multiple files.
    """

    candidate_id = faculty_id(decision.get("mapped_faculty_id"))

    source_id = faculty_id(decision.get("faculty_id_original"))

    normalized_author = None

    if occurrence:
        normalized_author = occurrence["author"]

    candidate = None

    if faculty_record:
        candidate = {
            "faculty_id": candidate_id,
            "name": faculty_record.get("name"),
            "rank": faculty_record.get("rank"),
            "department": faculty_record.get("department"),
        }

    # Publication metadata provides context, not independent
    # identity verification.
    publication_context = None

    if publication:
        publication_context = {
            "publication_id": publication.get("publication_id"),
            "title": publication.get("title"),
            "year": publication.get("year"),
        }

    return {
        "source_author": {
            "name": decision.get("author_name_original"),
            "source_faculty_id": source_id,
        },

        "proposed_candidate": candidate,

        "deterministic_reconciliation": {
            "classification": decision.get("classification"),
            "confidence": decision.get("confidence"),
            "mapped_faculty_id": candidate_id,
            "mapped_faculty_name": decision.get(
                "mapped_faculty_name"
            ),
            "evidence": decision.get("evidence"),
        },

        "publication_context": publication_context,

        "normalized_author_occurrence": {
            "name": normalized_author.get("name"),
            "faculty_id": faculty_id(
                normalized_author.get("faculty_id")
            ),
            "is_faculty": normalized_author.get("is_faculty"),
        } if normalized_author else None,

        "evidence_provenance": {
            "source_system": "UTRGV Digital Measures",

            "faculty_roster": (
                "Digital Measures-derived normalized faculty data"
            ),

            "publication_author": (
                "Digital Measures-derived normalized publication data"
            ),

            "publication_faculty_association": (
                "Derived from normalized source records; "
                "not independent corroboration"
            ),

            "independent_external_verification": False,

            "warning": (
                "Multiple fields originating from Digital Measures "
                "must not be counted as independent evidence."
            ),
        },
    }


# ------------------------------------------------------------
# POLICY EVALUATION
# ------------------------------------------------------------

def determine_policy(decision):
    """
    Determine whether a decision belongs in the initial shadow run.

    This is deterministic policy logic, not an AI decision.
    """

    classification = decision.get("classification")

    if classification in EXCLUDED_CLASSIFICATIONS:
        return "EXCLUDED_HISTORICAL_CONFLICT"

    if classification not in ELIGIBLE_CLASSIFICATIONS:
        return "NOT_IN_INITIAL_SCOPE"

    if not decision.get("author_name_original"):
        return "ABSTAIN_MISSING_AUTHOR_NAME"

    if (
        classification == "HIGH_SIMILARITY"
        and not decision.get("mapped_faculty_id")
    ):
        return "ABSTAIN_MISSING_CANDIDATE"

    if (
        classification == "INITIAL_VARIANT"
        and not decision.get("mapped_faculty_id")
    ):
        return "ABSTAIN_MISSING_CANDIDATE"

    if (
        classification == "NAME_VARIANT_WITHOUT_DM_ID"
        and not decision.get("mapped_faculty_id")
    ):
        return "ABSTAIN_MISSING_CANDIDATE"

    return "ELIGIBLE_FOR_SHADOW_EVALUATION"


# ------------------------------------------------------------
# CASE BUILDER
# ------------------------------------------------------------

def build_cases(reconciliation, normalized):
    """Build the read-only Clef evaluation case collection."""

    decisions = reconciliation.get("decisions", [])

    publications = index_publications(
        normalized.get("publications", [])
    )

    faculty = index_faculty(
        normalized.get("faculty", [])
    )

    exact_index, name_index, position_index = (
        build_author_occurrence_index(publications)
    )

    cases = []

    statistics = defaultdict(int)

    for decision_index, decision in enumerate(decisions):

        classification = decision.get("classification", "MISSING")

        statistics[f"classification:{classification}"] += 1

        policy = determine_policy(decision)

        if policy != "ELIGIBLE_FOR_SHADOW_EVALUATION":
            continue

        publication_id = decision.get("publication_id")

        publication = publications.get(publication_id)

        occurrence, occurrence_match = consume_occurrence(
            decision,
            exact_index,
            name_index,
            position_index,
        )

        candidate_id = faculty_id(
            decision.get("mapped_faculty_id")
        )

        faculty_record = faculty.get(candidate_id)

        warnings = []

        if publication is None:
            warnings.append("NORMALIZED_PUBLICATION_NOT_FOUND")

        if occurrence is None:
            warnings.append("NORMALIZED_AUTHOR_OCCURRENCE_NOT_MATCHED")

        if candidate_id and faculty_record is None:
            warnings.append("CANDIDATE_NOT_FOUND_IN_CURRENT_FACULTY_ROSTER")

        if occurrence_match == "UNIQUE_POSITION_FALLBACK":
            warnings.append("OCCURRENCE_MATCHED_BY_POSITION_ONLY")

        if classification == "NAME_VARIANT_WITHOUT_DM_ID":
            warnings.append(
                "NO_DIRECT_SOURCE_AUTHOR_FACULTY_ID"
            )

            warnings.append(
                "PUBLICATION_LEVEL_FACULTY_ASSOCIATION_IS_NOT_INDEPENDENT"
            )

        # The decision's array index is preserved as its stable
        # identity within this exact source-file version.
        case_id = (
            f"MECE-{decision_index:05d}-"
            f"{publication_id}-"
            f"P{decision.get('position')}"
        )

        evidence = build_evidence(
            decision,
            publication,
            faculty_record,
            occurrence,
        )

        case = {
            "case_id": case_id,

            "source_decision_index": decision_index,

            "source_occurrence": {
                "publication_id": publication_id,
                "position": decision.get("position"),
                "author_name_original": decision.get(
                    "author_name_original"
                ),
                "faculty_id_original": decision.get(
                    "faculty_id_original"
                ),
            },

            "classification": classification,

            "policy_status": policy,

            "normalized_author_index": (
                occurrence["author_index"]
                if occurrence else None
            ),

            "occurrence_match_method": occurrence_match,

            "evidence": evidence,

            "warnings": warnings,

            "clef_evaluation": {
                "status": "PENDING",
                "choice": None,
                "confidence": None,
                "probabilities": None,
            },
        }

        cases.append(case)

        statistics[f"eligible:{classification}"] += 1

        if warnings:
            statistics["cases_with_warnings"] += 1

    return cases, statistics


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Build read-only Clef identity evaluation cases."
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to department config.yaml",
    )

    args = parser.parse_args()

    config_path = Path(args.config).resolve()

    if not config_path.exists():
        raise FileNotFoundError(config_path)

    department_dir = resolve_department_directory(config_path)

    reconciliation_path = (
        department_dir / "authorship_reconciliation.json"
    )

    normalized_path = (
        department_dir / "faculty_normalized.json"
    )

    for path in [reconciliation_path, normalized_path]:
        if not path.exists():
            raise FileNotFoundError(path)

    print("=" * 70)
    print("CLEF POLICY LAYER")
    print("=" * 70)

    print(f"Department directory: {department_dir}")

    # Record source hashes before reading.
    source_hashes = {
        "authorship_reconciliation.json": sha256_file(
            reconciliation_path
        ),
        "faculty_normalized.json": sha256_file(
            normalized_path
        ),
    }

    reconciliation = load_json(reconciliation_path)
    normalized = load_json(normalized_path)

    cases, statistics = build_cases(
        reconciliation,
        normalized,
    )

    output = {
        "metadata": {
            "department": "MECE",
            "engine": "Clef-Flash",
            "mode": "SHADOW_EVALUATION",
            "generated_by": "clef_policy.py",
            "source_hashes": source_hashes,
            "eligible_classifications": sorted(
                ELIGIBLE_CLASSIFICATIONS
            ),
            "excluded_classifications": sorted(
                EXCLUDED_CLASSIFICATIONS
            ),
            "database_imported": False,
            "approved_reconciliation_modified": False,
        },

        "summary": {
            "total_cases": len(cases),
            "cases_by_classification": {
                classification: sum(
                    1 for case in cases
                    if case["classification"] == classification
                )
                for classification in sorted(
                    ELIGIBLE_CLASSIFICATIONS
                )
            },
            "cases_with_warnings": statistics[
                "cases_with_warnings"
            ],
        },

        "cases": cases,
    }

    output_path = department_dir / OUTPUT_FILENAME

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

        file.write("\n")

    # Verify source files did not change during execution.
    final_hashes = {
        "authorship_reconciliation.json": sha256_file(
            reconciliation_path
        ),
        "faculty_normalized.json": sha256_file(
            normalized_path
        ),
    }

    if source_hashes != final_hashes:
        raise RuntimeError(
            "Source files changed during policy execution."
        )

    print("\nCLASSIFICATION COUNTS")

    for key, value in sorted(statistics.items()):
        if key.startswith("classification:"):
            print(f"{key.split(':', 1)[1]:35} {value}")

    print("\nCLEF CASE COUNTS")

    for classification, count in output["summary"][
        "cases_by_classification"
    ].items():
        print(f"{classification:35} {count}")

    print(f"\nTotal evaluation cases: {len(cases)}")
    print(
        f"Cases with warnings: "
        f"{output['summary']['cases_with_warnings']}"
    )
    print(f"\nOutput: {output_path}")
    print("\nSource hashes unchanged: YES")
    print("Approved reconciliation modified: NO")
    print("Database changes: NONE")
    print("\nRESULT: POLICY CASE GENERATION COMPLETE")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
