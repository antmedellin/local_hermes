#!/usr/bin/env python3

import json
from pathlib import Path
from collections import defaultdict, deque


# ============================================================
# PATHS
# ============================================================

BASE = Path(
    "hermes_files/data/skills/research/ledger/data"
)

NORMALIZED_PATH = BASE / "maie_faculty_normalized.json"
RECONCILIATION_PATH = BASE / "maie_authorship_reconciliation.json"
OUTPUT_PATH = BASE / "maie_faculty_reconciled.json"


# ============================================================
# LOAD INPUT FILES
# ============================================================

with NORMALIZED_PATH.open("r", encoding="utf-8") as f:
    normalized = json.load(f)

with RECONCILIATION_PATH.open("r", encoding="utf-8") as f:
    reconciliation = json.load(f)


# ============================================================
# IMPORTANT:
#
# publication_id + position is NOT guaranteed to be unique.
#
# This happens because some normalized publications represent
# multiple merged Digital Measures records.
#
# Therefore, instead of storing one decision per key, we store
# a QUEUE of decisions for each (publication_id, position).
#
# The reconciliation script generated decisions in the same
# publication/author traversal order used by the normalized
# dataset, so we consume those decisions in order.
# ============================================================

decisions_by_key = defaultdict(deque)

for decision in reconciliation.get("decisions", []):

    key = (
        decision.get("publication_id"),
        decision.get("position"),
    )

    decisions_by_key[key].append(decision)


total_reconciliation_decisions = len(
    reconciliation.get("decisions", [])
)


# ============================================================
# BUILD RECONCILED PUBLICATIONS
# ============================================================

reconciled_publications = []

total_authors = 0
matched_decisions = 0


for publication in normalized.get("publications", []):

    publication_id = publication.get("publication_id")

    reconciled = dict(publication)

    reconciled_authors = []

    for author in publication.get("authors", []):

        position = author.get("position")

        key = (
            publication_id,
            position,
        )

        queue = decisions_by_key.get(key)

        if not queue:
            raise RuntimeError(
                "No unused reconciliation decision found for "
                f"publication={publication_id}, "
                f"position={position}, "
                f"author={author.get('name')!r}"
            )

        # ----------------------------------------------------
        # Consume exactly ONE decision for this author
        # occurrence.
        # ----------------------------------------------------

        decision = queue.popleft()

        # ----------------------------------------------------
        # Safety check:
        #
        # The reconciliation decision should refer to the same
        # publication and position we are currently processing.
        # ----------------------------------------------------

        if decision.get("publication_id") != publication_id:
            raise RuntimeError(
                "Publication mismatch while consuming "
                "reconciliation decision: "
                f"expected {publication_id}, "
                f"got {decision.get('publication_id')}"
            )

        if decision.get("position") != position:
            raise RuntimeError(
                "Position mismatch while consuming "
                "reconciliation decision: "
                f"expected {position}, "
                f"got {decision.get('position')}"
            )

        # ----------------------------------------------------
        # Build the import-ready author record.
        # ----------------------------------------------------

        reconciled_author = {
            "position": position,

            # Original Digital Measures author identity.
            "author_name_original": (
                decision.get("author_name_original")
            ),

            # Normalized name components.
            "first_name": author.get("first_name"),
            "middle_name": author.get("middle_name"),
            "last_name": author.get("last_name"),

            # Original Digital Measures faculty ID.
            "source_faculty_id": (
                decision.get("faculty_id_original")
            ),

            # Current faculty mapping, only when supported by
            # the reconciliation process.
            "mapped_faculty_id": (
                decision.get("mapped_faculty_id")
            ),

            "mapped_faculty_name": (
                decision.get("mapped_faculty_name")
            ),

            # Reconciliation result.
            "reconciliation_status": (
                decision.get("classification")
            ),

            "confidence": (
                decision.get("confidence")
            ),

            "evidence": (
                decision.get("evidence")
            ),

            # Metadata preserved from normalized data.
            "institution": author.get("institution"),
            "student_level": author.get("student_level"),

            # Normalized identity used by the preservation audit.
            "normalized_name": author.get("name"),
        }

        reconciled_authors.append(reconciled_author)

        total_authors += 1
        matched_decisions += 1

    reconciled["authors"] = reconciled_authors

    reconciled_publications.append(reconciled)


# ============================================================
# VERIFY THAT EVERY RECONCILIATION DECISION WAS CONSUMED
# ============================================================

unused_decisions = []

for key, queue in decisions_by_key.items():

    for decision in queue:

        unused_decisions.append(decision)


if unused_decisions:

    print()
    print("=" * 80)
    print("UNUSED RECONCILIATION DECISIONS")
    print("=" * 80)
    print()

    for decision in unused_decisions[:20]:

        print(
            f"{decision.get('publication_id')} | "
            f"position={decision.get('position')} | "
            f"author={decision.get('author_name_original')!r}"
        )

    if len(unused_decisions) > 20:
        print(
            f"... and {len(unused_decisions) - 20} more"
        )

    raise RuntimeError(
        f"{len(unused_decisions)} reconciliation decisions "
        "were not consumed."
    )


# ============================================================
# FACULTY
# ============================================================

reconciled_faculty = normalized.get("faculty", [])


# ============================================================
# OUTPUT
# ============================================================

output = {
    "metadata": {
        "source": "maie_faculty_normalized.json",
        "authorship_reconciliation_source":
            "maie_authorship_reconciliation.json",
        "description":
            "Import-ready MAIE research ledger layer combining "
            "normalized publication data with explicit authorship "
            "reconciliation decisions.",
        "database_imported": False,
    },

    "quality_summary": normalized.get(
        "quality_summary",
        {}
    ),

    "reconciliation_summary":
        reconciliation.get("summary", {}),

    "faculty": reconciled_faculty,

    "publications": reconciled_publications,
}


# ============================================================
# WRITE OUTPUT
# ============================================================

with OUTPUT_PATH.open("w", encoding="utf-8") as f:

    json.dump(
        output,
        f,
        indent=2,
        ensure_ascii=False,
    )

    f.write("\n")


# ============================================================
# FINAL REPORT
# ============================================================

print()
print("=" * 80)
print("MAIE FINAL RECONCILED DATASET")
print("=" * 80)
print()

print(
    f"Faculty records              : "
    f"{len(reconciled_faculty)}"
)

print(
    f"Publications                 : "
    f"{len(reconciled_publications)}"
)

print(
    f"Author occurrences           : "
    f"{total_authors}"
)

print(
    f"Reconciliation decisions     : "
    f"{total_reconciliation_decisions}"
)

print(
    f"Matched decisions            : "
    f"{matched_decisions}"
)

print(
    f"Unused decisions             : "
    f"{len(unused_decisions)}"
)

print()

if matched_decisions != total_reconciliation_decisions:

    raise RuntimeError(
        "Author occurrence count does not match "
        "reconciliation decision count."
    )

print("DECISION COVERAGE: PASS")
print("Every reconciliation decision was consumed exactly once.")

print()
print(f"Written: {OUTPUT_PATH}")
print()
print("NO DATABASE CHANGES WERE MADE.")
print()