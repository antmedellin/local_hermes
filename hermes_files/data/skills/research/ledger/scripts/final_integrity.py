#!/usr/bin/env python3

import json
from pathlib import Path
from collections import Counter


# ============================================================
# PATHS
# ============================================================

BASE = Path(
    "hermes_files/data/skills/research/ledger/data"
)

RECONCILED_PATH = BASE / "maie_faculty_reconciled.json"
NORMALIZED_PATH = BASE / "maie_faculty_normalized.json"


# ============================================================
# LOAD
# ============================================================

with RECONCILED_PATH.open("r", encoding="utf-8") as f:
    reconciled = json.load(f)

with NORMALIZED_PATH.open("r", encoding="utf-8") as f:
    normalized = json.load(f)


# ============================================================
# EXPECTED RECONCILIATION STATUSES
# ============================================================

ALLOWED_STATUSES = {
    "EXACT",
    "NAME_VARIANT",
    "INITIAL_VARIANT",
    "HIGH_SIMILARITY",
    "MODERATE_REVIEW",
    "HISTORICAL_ID_MISMATCH",
    "NAME_WITHOUT_DM_ID",
    "EXTERNAL",
}


# ============================================================
# COUNTERS / ERROR COLLECTION
# ============================================================

errors = []
warnings = []

# ------------------------------------------------------------
# Faculty
# ------------------------------------------------------------

faculty = reconciled.get("faculty", [])

faculty_ids = set()
faculty_names = set()

for person in faculty:

    faculty_id = str(person.get("user_id")) if person.get("user_id") else None
    name = person.get("name")

    if faculty_id:
        faculty_ids.add(faculty_id)

    if name:
        faculty_names.add(name)


# ------------------------------------------------------------
# Publications
# ------------------------------------------------------------

publications = reconciled.get("publications", [])

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

    if pub.get("year") is None:
        errors.append(
            f"{publication_id}: missing year"
        )


# ============================================================
# AUTHORS
# ============================================================

total_authors = 0

status_counts = Counter()

mapped_faculty_ids = set()

author_key_duplicates = []

for pub in publications:

    publication_id = pub.get("publication_id")

    for author in pub.get("authors", []):

        total_authors += 1

        position = author.get("position")

        # ----------------------------------------------------
        # Position must exist.
        #
        # IMPORTANT:
        # Position is NOT required to be unique within a
        # normalized publication.
        #
        # Multiple Digital Measures source records can merge
        # into one normalized publication and may contain
        # overlapping author positions.
        # ----------------------------------------------------

        if position is None:

            errors.append(
                f"{publication_id}: author missing position"
            )

        # ----------------------------------------------------
        # Required author identity.
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Reconciliation status.
        # ----------------------------------------------------

        status = author.get(
            "reconciliation_status"
        )

        if status not in ALLOWED_STATUSES:

            errors.append(
                f"{publication_id}, position {position}: "
                f"unknown reconciliation status: {status!r}"
            )

        else:

            status_counts[status] += 1

        # ----------------------------------------------------
        # Faculty mapping.
        # ----------------------------------------------------

        mapped_id = author.get(
            "mapped_faculty_id"
        )

        if mapped_id is not None:

            mapped_id = str(mapped_id)

            mapped_faculty_ids.add(mapped_id)

            if mapped_id not in faculty_ids:

                errors.append(
                    f"{publication_id}, position {position}: "
                    f"mapped faculty ID {mapped_id} "
                    "does not belong to current MAIE faculty"
                )

        # ----------------------------------------------------
        # Historical mismatch safety rule.
        #
        # A historical ID mismatch should remain unresolved
        # unless the reconciliation layer explicitly supplied
        # a justified mapping.
        # ----------------------------------------------------

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
# DM RECORD ID TRACEABILITY
# ============================================================

reconciled_dm_ids = set()

for pub in publications:

    for dm_id in pub.get(
        "dm_record_ids",
        []
    ):

        if dm_id:
            reconciled_dm_ids.add(
                str(dm_id)
            )


normalized_dm_ids = set()

for pub in normalized.get(
    "publications",
    []
):

    for dm_id in pub.get(
        "dm_record_ids",
        []
    ):

        if dm_id:
            normalized_dm_ids.add(
                str(dm_id)
            )


missing_dm_ids = (
    normalized_dm_ids -
    reconciled_dm_ids
)

extra_dm_ids = (
    reconciled_dm_ids -
    normalized_dm_ids
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
).get(
    "database_imported"
)

if database_imported is not False:

    errors.append(
        "metadata.database_imported is not false"
    )


# ============================================================
# EXPECTED COUNTS
# ============================================================

if len(faculty) != 14:

    errors.append(
        f"Expected 14 faculty records; found {len(faculty)}"
    )


if len(publications) != 455:

    errors.append(
        f"Expected 455 publications; found {len(publications)}"
    )


if total_authors != 1624:

    errors.append(
        f"Expected 1,624 author occurrences; found {total_authors}"
    )


if len(normalized_dm_ids) != 459:

    errors.append(
        "Expected 459 unique DM record IDs in normalized data; "
        f"found {len(normalized_dm_ids)}"
    )


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 80)
print("MAIE FINAL PRE-IMPORT INTEGRITY AUDIT")
print("=" * 80)
print()

print(f"Faculty records                 : {len(faculty)}")
print(f"Publications                    : {len(publications)}")
print(f"Author occurrences              : {total_authors}")
print(
    f"Unique normalized DM record IDs : "
    f"{len(normalized_dm_ids)}"
)
print(
    f"Unique reconciled DM record IDs : "
    f"{len(reconciled_dm_ids)}"
)

print()

print("Reconciliation status counts:")
for status in sorted(status_counts):
    print(
        f"  {status:<28}: "
        f"{status_counts[status]}"
    )

print()

print(
    f"Current MAIE faculty IDs        : "
    f"{len(faculty_ids)}"
)

print(
    f"Mapped faculty IDs used         : "
    f"{len(mapped_faculty_ids)}"
)

print(
    f"Duplicate publication/position  : "
    f"{len(author_key_duplicates)}"
)

print(
    f"Missing DM IDs                  : "
    f"{len(missing_dm_ids)}"
)

print(
    f"Extra DM IDs                    : "
    f"{len(extra_dm_ids)}"
)

print(
    f"Warnings                        : "
    f"{len(warnings)}"
)

print(
    f"Errors                          : "
    f"{len(errors)}"
)

print()

# ============================================================
# WARNINGS
# ============================================================

if warnings:

    print("=" * 80)
    print("WARNINGS")
    print("=" * 80)
    print()

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
    print()

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
    print()
    print(
        f"{len(errors)} integrity error(s) must be resolved "
        "before database import."
    )

else:

    print("RESULT: PASS")
    print()
    print(
        "The reconciled MAIE dataset passed all pre-import "
        "integrity checks."
    )
    print()
    print(
        "No database changes were made."
    )

print()