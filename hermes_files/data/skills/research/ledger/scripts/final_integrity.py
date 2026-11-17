#!/usr/bin/env python3

"""
Department-independent final integrity audit.

Validates the normalized, reconciliation, and reconciled
research ledger datasets before database import.

READ-ONLY:
- Does not modify JSON source files.
- Does not modify PostgreSQL.
- Does not change authorship mappings.
"""

import argparse
import hashlib
import json

from collections import Counter
from pathlib import Path

import yaml

# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
LEDGER_DIR = SCRIPT_DIR.parent

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the final research ledger integrity audit."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Department configuration YAML file.",
    )
    return parser.parse_args()


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    required_fields = [
        "institution",
        "department_name",
        "output_directory",
    ]
    for field in required_fields:
        if field not in config:
            raise ValueError(
                f"Missing configuration field: {field}"
            )
    return config

def resolve_output_directory(configured_path):
    path = Path(configured_path)
    if path.is_absolute():
        return path
    repository_root = LEDGER_DIR.parents[4]
    return repository_root / path

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Required file not found: {path}"
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()

def collect_dm_ids(publications):
    result = set()
    for publication in publications:
        for dm_id in publication.get("dm_record_ids", []):
            if dm_id:
                result.add(str(dm_id))
    return result

def count_authors(publications):
    return sum(
        len(publication.get("authors", []))
        for publication in publications
    )

# ============================================================
# LOAD DEPARTMENT
# ============================================================

args = parse_args()

config_path = Path(args.config).resolve()

config = load_config(config_path)

output_directory = resolve_output_directory(
    config["output_directory"]
)

department_name = config["department_name"]
department_slug = config.get(
    "department_slug",
    output_directory.name,
)


# ============================================================
# INPUT FILES
# ============================================================

NORMALIZED_PATH = (
    output_directory / "faculty_normalized.json"
)

RECONCILIATION_PATH = (
    output_directory / "authorship_reconciliation.json"
)

RECONCILED_PATH = (
    output_directory / "faculty_reconciled.json"
)

MANIFEST_PATH = (
    output_directory / "validation_manifest.json"
)


# ============================================================
# LOAD DATA
# ============================================================

normalized = load_json(NORMALIZED_PATH)
reconciliation = load_json(RECONCILIATION_PATH)
reconciled = load_json(RECONCILED_PATH)


normalized_faculty = normalized.get("faculty", [])
normalized_publications = normalized.get("publications", [])

faculty = reconciled.get("faculty", [])
publications = reconciled.get("publications", [])

decisions = reconciliation.get("decisions", [])

errors = []
warnings = []

status_counts = Counter()

mapped_faculty_ids = set()


# ============================================================
# ALLOWED RECONCILIATION STATUSES
# ============================================================

ALLOWED_STATUSES = {
    "EXACT",
    "NAME_VARIANT",
    "INITIAL_VARIANT",
    "HIGH_SIMILARITY",
    "MODERATE_REVIEW",
    "HISTORICAL_ID_MISMATCH",
    "HISTORICAL_ID_SWAP_RECOVERED",
    "NAME_WITHOUT_DM_ID",
    "NAME_VARIANT_WITHOUT_DM_ID",
    "EXTERNAL",
}


# ============================================================
# FACULTY VALIDATION
# ============================================================

faculty_ids = set()

for person in faculty:

    faculty_id = person.get("user_id")

    if faculty_id is None:
        errors.append(
            "Faculty record without user_id"
        )
        continue

    faculty_id = str(faculty_id)

    if faculty_id in faculty_ids:
        errors.append(
            f"Duplicate faculty ID: {faculty_id}"
        )

    faculty_ids.add(faculty_id)


if len(faculty) != len(normalized_faculty):

    errors.append(
        "Faculty count differs between normalized and "
        "reconciled datasets: "
        f"{len(normalized_faculty)} vs {len(faculty)}"
    )


# ============================================================
# PUBLICATION VALIDATION
# ============================================================

publication_ids = set()

for pub in publications:

    publication_id = pub.get("publication_id")

    if not publication_id:
        errors.append(
            "Publication without publication_id"
        )
        continue

    if publication_id in publication_ids:
        errors.append(
            f"Duplicate publication_id: {publication_id}"
        )

    publication_ids.add(publication_id)

    if not pub.get("title"):
        errors.append(
            f"{publication_id}: missing title"
        )

    # A missing publication year is a metadata-quality
    # issue, not automatically a structural integrity failure.
    # Preserve the source value; do not infer a year.
    if pub.get("year") is None:
        warnings.append(
            f"{publication_id}: publication year is missing "
            "from the source data"
        )


normalized_publication_ids = {
    pub.get("publication_id")
    for pub in normalized_publications
    if pub.get("publication_id")
}

if publication_ids != normalized_publication_ids:

    errors.append(
        "Publication IDs differ between normalized "
        "and reconciled datasets."
    )


# ============================================================
# AUTHOR VALIDATION
# ============================================================

total_authors = 0

for pub in publications:

    publication_id = pub.get("publication_id")

    for author in pub.get("authors", []):

        total_authors += 1

        position = author.get("position")

        # Position must exist, but does NOT need to be unique.
        if position is None:

            errors.append(
                f"{publication_id}: author missing position"
            )

        # -----------------------------------------------
        # Source author identity completeness
        # -----------------------------------------------

        status = author.get(
            "reconciliation_status"
        )

        identity_fields = (
            "author_name_original",
            "first_name",
            "middle_name",
            "last_name",
            "normalized_name",
            "source_faculty_id",
        )

        has_identity_information = any(
            author.get(field) not in (None, "")
            for field in identity_fields
        )

        mapped_id = author.get("mapped_faculty_id")

        if not has_identity_information:

            # A completely empty author occurrence is acceptable
            # only when the source supplied no identity information
            # and reconciliation correctly left it external.
            if status == "EXTERNAL" and mapped_id is None:

                warnings.append(
                    f"{publication_id}, position {position}: "
                    "source author identity is unavailable; "
                    "preserved as an unmapped EXTERNAL occurrence"
                )

            else:

                errors.append(
                    f"{publication_id}, position {position}: "
                    "author identity is missing for a record "
                    "that is not an unmapped EXTERNAL occurrence"
                )

        else:

            # If some identity information exists, the two
            # principal name fields must remain available.
            if not author.get("author_name_original"):

                errors.append(
                    f"{publication_id}, position {position}: "
                    "missing author_name_original"
                )

            if not author.get("normalized_name"):

                errors.append(
                    f"{publication_id}, position {position}: "
                    "missing normalized_name"
                )

        # -----------------------------------------------
        # Reconciliation status
        # -----------------------------------------------

        if status not in ALLOWED_STATUSES:

            errors.append(
                f"{publication_id}, position {position}: "
                f"unknown reconciliation status: {status!r}"
            )

        else:
            status_counts[status] += 1

        # -----------------------------------------------
        # Faculty mapping
        # -----------------------------------------------

        mapped_id = author.get("mapped_faculty_id")

        if mapped_id is not None:

            mapped_id = str(mapped_id)

            mapped_faculty_ids.add(mapped_id)

            if mapped_id not in faculty_ids:

                errors.append(
                    f"{publication_id}, position {position}: "
                    f"mapped faculty ID {mapped_id} "
                    f"does not belong to {department_name}"
                )

        # -----------------------------------------------
        # Historical mismatch safety
        # -----------------------------------------------

        if (
            status == "HISTORICAL_ID_MISMATCH"
            and mapped_id is not None
        ):

            warnings.append(
                f"{publication_id}, position {position}: "
                "historical ID mismatch has a mapped faculty ID; "
                "inspect reconciliation evidence"
            )


# ============================================================
# AUTHOR OCCURRENCE CONSISTENCY
# ============================================================

normalized_author_count = count_authors(
    normalized_publications
)

reconciled_author_count = count_authors(
    publications
)

if normalized_author_count != reconciled_author_count:

    errors.append(
        "Author occurrence count differs between normalized "
        "and reconciled datasets: "
        f"{normalized_author_count} vs {reconciled_author_count}"
    )

if len(decisions) != reconciled_author_count:

    errors.append(
        "Reconciliation decision count differs from "
        "reconciled author occurrences: "
        f"{len(decisions)} vs {reconciled_author_count}"
    )


# ============================================================
# DM RECORD ID TRACEABILITY
# ============================================================

normalized_dm_ids = collect_dm_ids(
    normalized_publications
)

reconciled_dm_ids = collect_dm_ids(
    publications
)

missing_dm_ids = (
    normalized_dm_ids - reconciled_dm_ids
)

extra_dm_ids = (
    reconciled_dm_ids - normalized_dm_ids
)

if missing_dm_ids:

    errors.append(
        "DM record IDs missing from reconciled dataset: "
        + ", ".join(sorted(missing_dm_ids))
    )

if extra_dm_ids:

    errors.append(
        "Unexpected DM record IDs in reconciled dataset: "
        + ", ".join(sorted(extra_dm_ids))
    )


# ============================================================
# DATABASE FLAG
# ============================================================

database_imported = reconciled.get(
    "metadata",
    {}
).get("database_imported")

if database_imported is not False:

    errors.append(
        "metadata.database_imported is not false"
    )


# ============================================================
# VALIDATION MANIFEST
# ============================================================

manifest_verified = False
manifest_counts = {}

if MANIFEST_PATH.exists():

    manifest = load_json(MANIFEST_PATH)

    manifest_status = manifest.get("status")

    artifacts = manifest.get("artifacts", {})

    artifact_checks = [
        "faculty_reconciled.json",
        "authorship_reconciliation.json",
    ]

    manifest_verified = True

    for filename in artifact_checks:

        expected_hash = artifacts.get(filename)

        artifact_path = output_directory / filename

        if not expected_hash:

            warnings.append(
                f"Manifest does not contain a hash for {filename}"
            )

            manifest_verified = False
            continue

        actual_hash = sha256_file(artifact_path)

        if actual_hash != expected_hash:

            warnings.append(
                f"Manifest hash mismatch: {filename}"
            )

            manifest_verified = False

    if manifest_status != "approved":

        warnings.append(
            f"Manifest status is {manifest_status!r}, not approved."
        )

        manifest_verified = False

    if manifest_verified:

        manifest_counts = manifest.get("counts", {})

        expected_checks = {
            "expected_faculty_count": len(faculty),
            "expected_publication_count": len(publications),
            "expected_unique_dm_record_count": len(normalized_dm_ids),
            "expected_reconciliation_decision_count": len(decisions),
            "source_author_occurrence_count": normalized_author_count,
        }

        for key, actual_value in expected_checks.items():

            expected_value = manifest_counts.get(key)

            if expected_value is None:
                continue

            if expected_value != actual_value:

                errors.append(
                    f"Approved manifest count mismatch for {key}: "
                    f"expected {expected_value}, found {actual_value}"
                )

else:

    warnings.append(
        "No validation manifest exists for this department."
    )


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 80)
print(f"{department_name.upper()} FINAL PRE-IMPORT INTEGRITY AUDIT")
print("=" * 80)
print()

print(f"Department                      : {department_name}")
print(f"Department slug                 : {department_slug}")
print(f"Faculty records                 : {len(faculty)}")
print(f"Publications                    : {len(publications)}")
print(f"Author occurrences              : {total_authors}")
print(f"Reconciliation decisions        : {len(decisions)}")
print(f"Unique normalized DM record IDs : {len(normalized_dm_ids)}")
print(f"Unique reconciled DM record IDs : {len(reconciled_dm_ids)}")
print(f"Current faculty IDs             : {len(faculty_ids)}")
print(f"Mapped faculty IDs used         : {len(mapped_faculty_ids)}")
print(f"Missing DM IDs                  : {len(missing_dm_ids)}")
print(f"Extra DM IDs                    : {len(extra_dm_ids)}")
print(f"Manifest verified               : {manifest_verified}")
print()

print("Reconciliation status counts:")

for status in sorted(status_counts):

    print(
        f"  {status:<32}: {status_counts[status]}"
    )

print()
print(f"Warnings                        : {len(warnings)}")
print(f"Errors                          : {len(errors)}")
print()


# ============================================================
# WARNINGS
# ============================================================

if warnings:

    print("=" * 80)
    print("WARNINGS")
    print("=" * 80)

    for warning in warnings:
        print(f"WARNING: {warning}")

    print()


# ============================================================
# ERRORS
# ============================================================

if errors:

    print("=" * 80)
    print("ERRORS")
    print("=" * 80)

    for error in errors:
        print(f"ERROR: {error}")

    print()


# ============================================================
# FINAL RESULT
# ============================================================

print("=" * 80)
print("FINAL RESULT")
print("=" * 80)
print()

if errors:

    print("RESULT: REVIEW REQUIRED")
    print(
        f"{len(errors)} integrity error(s) must be resolved "
        "before database import."
    )

else:
    print("RESULT: PASS")
    print()
    print(
        "The reconciled dataset passed all structural "
        "pre-import integrity checks."
    )
    if manifest_verified:
        print(
            "The approved validation manifest also matches "
            "the current artifacts."
        )
    print()
    print("No database changes were made.")

print()
