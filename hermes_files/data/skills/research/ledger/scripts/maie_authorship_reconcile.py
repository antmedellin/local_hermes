#!/usr/bin/env python3

"""
Reconcile MAIE Digital Measures authorship records.

IMPORTANT:
- This script is READ-ONLY with respect to the source JSON.
- It does NOT modify PostgreSQL.
- It preserves the original author name and original Digital Measures faculty ID.
- It attempts to detect historical Digital Measures ID/name swaps by examining
  the COMPLETE author list of each publication.

Classification:

EXACT
    Faculty ID points to a current MAIE faculty member and the author name
    exactly matches the current faculty name.

NAME_VARIANT
    Faculty ID points to a current MAIE faculty member and the author's
    first/last name matches despite middle-name/title formatting differences.

INITIAL_VARIANT
    Faculty ID points to a current MAIE faculty member and the name is
    represented primarily through initials.

MODERATE_REVIEW
    The name is somewhat similar to the faculty name but is not strong
    enough for automatic mapping.

HISTORICAL_ID_MISMATCH
    A Digital Measures faculty ID points to a current MAIE faculty member,
    but the author name is clearly someone else.

HISTORICAL_ID_SWAP_RECOVERED
    A suspicious historical ID/name pairing exists, BUT the current MAIE
    faculty member's name also appears elsewhere in the same publication's
    author list. This is strong evidence of an ID/name swap.

EXTERNAL
    Author has no MAIE faculty ID and does not match a current MAIE faculty
    member.

"""

import json
import re
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher


BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data"

INPUT_FILE = DATA_DIR / "maie_faculty_normalized.json"
OUTPUT_FILE = DATA_DIR / "maie_authorship_reconciliation.json"


# ------------------------------------------------------------
# Name normalization
# ------------------------------------------------------------

def normalize_name(name):
    """Normalize a name for comparison."""
    if not name:
        return ""

    name = unicodedata.normalize("NFKD", str(name))
    name = name.replace("-", " ")
    name = name.replace("–", " ")
    name = name.replace("—", " ")
    name = name.replace(".", " ")

    # Remove punctuation except letters/numbers/spaces.
    name = re.sub(r"[^A-Za-z0-9\s]", " ", name)

    # Collapse whitespace.
    name = re.sub(r"\s+", " ", name)

    return name.strip().lower()


def name_parts(name):
    """Return normalized first/middle/last name components."""
    normalized = normalize_name(name)

    if not normalized:
        return "", "", ""

    parts = normalized.split()

    if len(parts) == 1:
        return parts[0], "", parts[0]

    first = parts[0]
    last = parts[-1]
    middle = " ".join(parts[1:-1])

    return first, middle, last


def first_last_key(name):
    first, middle, last = name_parts(name)
    return first, last


def initials(name):
    """
    Extract initials from all name components.

    Example:
        Anil K Srivastava -> aks
        A K Srivastava    -> aks
    """
    normalized = normalize_name(name)

    if not normalized:
        return ""

    return "".join(part[0] for part in normalized.split() if part)


# ------------------------------------------------------------
# Name classification
# ------------------------------------------------------------

def classify_name(author_name, faculty_name):
    """
    Compare an author name with a current MAIE faculty name.

    Returns:
        category, similarity
    """

    a = normalize_name(author_name)
    f = normalize_name(faculty_name)

    if not a or not f:
        return "UNKNOWN", 0.0

    if a == f:
        return "EXACT", 1.0

    a_first, a_middle, a_last = name_parts(author_name)
    f_first, f_middle, f_last = name_parts(faculty_name)

    # Strong first + last match.
    if a_first == f_first and a_last == f_last:
        return "NAME_VARIANT", 0.95

    # First initial + exact last name.
    if a_last == f_last and a_first and f_first:
        if a_first[0] == f_first[0]:
            return "INITIAL_VARIANT", 0.90

    # Compare initials.
    ai = initials(author_name)
    fi = initials(faculty_name)

    if ai and fi and ai == fi and a_last == f_last:
        return "INITIAL_VARIANT", 0.90

    similarity = SequenceMatcher(None, a, f).ratio()

    if similarity >= 0.85:
        return "HIGH_SIMILARITY", similarity

    if similarity >= 0.65:
        return "MODERATE_REVIEW", similarity

    return "HISTORICAL_ID_MISMATCH", similarity


# ------------------------------------------------------------
# Load data
# ------------------------------------------------------------

print("=" * 70)
print("MAIE AUTHORSHIP RECONCILIATION")
print("=" * 70)

print(f"Input : {INPUT_FILE}")
print(f"Output: {OUTPUT_FILE}")
print()

with INPUT_FILE.open("r", encoding="utf-8") as f:
    data = json.load(f)


faculty_records = data.get("faculty", [])
publications = data.get("publications", [])


print(f"Faculty records      : {len(faculty_records)}")
print(f"Publications         : {len(publications)}")


# ------------------------------------------------------------
# Current MAIE faculty lookup
# ------------------------------------------------------------

faculty_by_id = {}
faculty_by_normalized_name = {}

for faculty in faculty_records:

    faculty_id = str(
        faculty.get("user_id")
        or faculty.get("dm_user_id")
        or ""
    ).strip()

    faculty_name = faculty.get("name", "").strip()

    if not faculty_id or not faculty_name:
        continue

    faculty_by_id[faculty_id] = faculty
    faculty_by_normalized_name[normalize_name(faculty_name)] = faculty


current_faculty_ids = set(faculty_by_id)


print(f"Current MAIE IDs    : {len(current_faculty_ids)}")
print()


# ------------------------------------------------------------
# Reconciliation
# ------------------------------------------------------------

decisions = []

summary = {
    "publications": len(publications),
    "author_entries": 0,
    "faculty_id_entries": 0,
    "EXACT": 0,
    "NAME_VARIANT": 0,
    "INITIAL_VARIANT": 0,
    "MODERATE_REVIEW": 0,
    "HIGH_SIMILARITY": 0,
    "HISTORICAL_ID_MISMATCH": 0,
    "HISTORICAL_ID_SWAP_RECOVERED": 0,
    "EXTERNAL": 0,
    "UNKNOWN": 0,
}


for publication in publications:

    publication_id = publication.get("publication_id")
    title = publication.get("title")
    year = publication.get("year")

    authors = publication.get("authors") or []

    summary["author_entries"] += len(authors)

    # --------------------------------------------------------
    # Build normalized-name lookup for THIS publication.
    #
    # This is the key part of the reconciliation.
    # --------------------------------------------------------

    publication_name_matches = {}

    for author in authors:

        author_name = author.get("name")

        if not author_name:
            continue

        normalized = normalize_name(author_name)

        if normalized:
            publication_name_matches.setdefault(
                normalized,
                []
            ).append(author)

    # --------------------------------------------------------
    # Examine every author.
    # --------------------------------------------------------

    for author in authors:

        author_name = author.get("name")
        faculty_id_original = author.get("faculty_id")

        position = author.get("position")

        if faculty_id_original is not None:
            faculty_id_original = str(faculty_id_original).strip()

        # Default decision.
        decision = {
            "publication_id": publication_id,
            "title": title,
            "year": year,
            "position": position,

            # Preserve raw DM values.
            "author_name_original": author_name,
            "faculty_id_original": faculty_id_original,

            # Resolved values.
            "mapped_faculty_id": None,
            "mapped_faculty_name": None,

            # Classification/evidence.
            "classification": None,
            "confidence": None,
            "evidence": None,
        }

        # ----------------------------------------------------
        # Case 1: no faculty ID.
        # ----------------------------------------------------

        if not faculty_id_original:

            normalized_author = normalize_name(author_name)

            direct_faculty = faculty_by_normalized_name.get(
                normalized_author
            )

            if direct_faculty:

                decision["mapped_faculty_id"] = str(
                    direct_faculty.get("user_id")
                    or direct_faculty.get("dm_user_id")
                )

                decision["mapped_faculty_name"] = direct_faculty.get(
                    "name"
                )

                decision["classification"] = "NAME_WITHOUT_DM_ID"
                decision["confidence"] = "HIGH"
                decision["evidence"] = (
                    "Author name directly matches a current MAIE "
                    "faculty member, but Digital Measures supplied "
                    "no faculty ID."
                )

            else:

                decision["classification"] = "EXTERNAL"
                decision["confidence"] = "NONE"
                decision["evidence"] = (
                    "No current MAIE faculty ID or direct current "
                    "faculty-name match."
                )

            summary[decision["classification"]] = (
                summary.get(decision["classification"], 0) + 1
            )

            decisions.append(decision)

            continue

        # ----------------------------------------------------
        # Case 2: faculty ID belongs to current MAIE faculty.
        # ----------------------------------------------------

        if faculty_id_original in current_faculty_ids:

            summary["faculty_id_entries"] += 1

            faculty = faculty_by_id[faculty_id_original]

            current_faculty_name = faculty.get("name")

            category, similarity = classify_name(
                author_name,
                current_faculty_name
            )

            # -----------------------------------------------
            # Strong direct match.
            # -----------------------------------------------

            if category in {
                "EXACT",
                "NAME_VARIANT",
                "INITIAL_VARIANT",
                "HIGH_SIMILARITY",
            }:

                decision["mapped_faculty_id"] = faculty_id_original
                decision["mapped_faculty_name"] = current_faculty_name
                decision["classification"] = category

                if category == "EXACT":
                    decision["confidence"] = "HIGH"
                    decision["evidence"] = (
                        "Digital Measures faculty ID and author name "
                        "both match the current MAIE faculty record."
                    )

                elif category in {
                    "NAME_VARIANT",
                    "INITIAL_VARIANT",
                }:
                    decision["confidence"] = "HIGH"
                    decision["evidence"] = (
                        "Digital Measures faculty ID matches the "
                        "current faculty record and the author name "
                        "is a documented naming/initial variant."
                    )

                else:
                    decision["confidence"] = "MEDIUM"
                    decision["evidence"] = (
                        "Faculty ID matches and name similarity is high."
                    )

                summary[category] += 1

                decisions.append(decision)

                continue

            # -----------------------------------------------
            # Suspicious ID/name mismatch.
            # -----------------------------------------------

            # Look for the actual current faculty member elsewhere
            # in THIS SAME publication.
            current_name_normalized = normalize_name(
                current_faculty_name
            )

            same_faculty_name_authors = publication_name_matches.get(
                current_name_normalized,
                []
            )

            # Exclude the current suspicious author itself.
            other_matching_authors = [
                other
                for other in same_faculty_name_authors
                if other is not author
            ]

            if other_matching_authors:

                # We have strong evidence that the DM ID was attached
                # to the wrong author while the real faculty member
                # appears separately in the author list.
                decision["classification"] = (
                    "HISTORICAL_ID_SWAP_RECOVERED"
                )

                decision["confidence"] = "HIGH"

                decision["mapped_faculty_id"] = None
                decision["mapped_faculty_name"] = None

                decision["evidence"] = (
                    f"Digital Measures ID {faculty_id_original} "
                    f"currently belongs to {current_faculty_name}, "
                    f"but the ID is attached to "
                    f"'{author_name}'. The current faculty name "
                    f"'{current_faculty_name}' also appears separately "
                    f"in this publication's author list. Preserve "
                    f"the original pairing and map the separate "
                    f"name-matching author instead."
                )

                summary["HISTORICAL_ID_SWAP_RECOVERED"] += 1

            else:

                decision["classification"] = category

                if category == "MODERATE_REVIEW":
                    decision["confidence"] = "REVIEW"

                else:
                    decision["confidence"] = "LOW"

                decision["evidence"] = (
                    f"Digital Measures ID {faculty_id_original} "
                    f"currently belongs to {current_faculty_name}, "
                    f"but the recorded author name is "
                    f"'{author_name}'. No matching current faculty "
                    f"name was found elsewhere in this publication."
                )

                summary[category] += 1

            decisions.append(decision)

            continue

        # ----------------------------------------------------
        # Case 3: faculty ID exists but is NOT a current MAIE ID.
        # ----------------------------------------------------

        decision["classification"] = "EXTERNAL"
        decision["confidence"] = "NONE"
        decision["evidence"] = (
            "Digital Measures faculty ID does not belong to the "
            "current MAIE faculty roster."
        )

        summary["EXTERNAL"] += 1

        decisions.append(decision)


# ------------------------------------------------------------
# Second pass:
#
# For authors without an ID whose name directly matches current
# faculty, make sure we distinguish them from ordinary external
# authors.
# ------------------------------------------------------------

# Already handled above.


# ------------------------------------------------------------
# Build recovered swap summary
# ------------------------------------------------------------

recovered_swaps = [
    d for d in decisions
    if d["classification"] == "HISTORICAL_ID_SWAP_RECOVERED"
]


unresolved_mismatches = [
    d for d in decisions
    if d["classification"] in {
        "HISTORICAL_ID_MISMATCH",
        "MODERATE_REVIEW",
    }
]


# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

output = {
    "metadata": {
        "source_file": str(INPUT_FILE),
        "purpose": (
            "Authorship reconciliation before PostgreSQL ledger import"
        ),
        "read_only": True,
    },

    "summary": summary,

    "recovered_id_swaps": recovered_swaps,

    "unresolved_reviews": unresolved_mismatches,

    "decisions": decisions,
}


with OUTPUT_FILE.open("w", encoding="utf-8") as f:
    json.dump(
        output,
        f,
        indent=2,
        ensure_ascii=False
    )


# ------------------------------------------------------------
# Human-readable terminal summary
# ------------------------------------------------------------

print()
print("=" * 70)
print("RECONCILIATION SUMMARY")
print("=" * 70)

for key in [
    "publications",
    "author_entries",
    "faculty_id_entries",
    "EXACT",
    "NAME_VARIANT",
    "INITIAL_VARIANT",
    "HIGH_SIMILARITY",
    "MODERATE_REVIEW",
    "HISTORICAL_ID_MISMATCH",
    "HISTORICAL_ID_SWAP_RECOVERED",
    "EXTERNAL",
    "UNKNOWN",
]:
    print(f"{key:35} {summary.get(key, 0)}")


print()
print(f"Recovered ID/name swaps : {len(recovered_swaps)}")
print(f"Needs manual review     : {len(unresolved_mismatches)}")

print()
print(f"Written: {OUTPUT_FILE}")
print()
print("NO DATABASE CHANGES WERE MADE.")