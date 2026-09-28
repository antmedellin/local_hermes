#!/usr/bin/env python3

import json
from pathlib import Path
from collections import Counter, defaultdict


BASE = Path.home() / "local_hermes" / "hermes_files" / "data" / "skills" / "research" / "ledger" / "data"

ENRICHED = BASE / "maie_faculty_enriched.json"
NORMALIZED = BASE / "maie_faculty_normalized.json"
RECONCILIATION = BASE / "maie_authorship_reconciliation.json"
OUTPUT = BASE / "maie_authorship_reconciliation_diagnostic.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def norm_name(name):
    """
    Normalize a name only for comparison.

    This does NOT modify the stored name.
    """
    if not name:
        return ""

    name = name.lower()

    # Remove common punctuation.
    for ch in [".", ",", "(", ")", "-", "_"]:
        name = name.replace(ch, " ")

    # Collapse whitespace.
    return " ".join(name.split())


def first_last(name):
    """
    Return a simplified (first, last) pair.
    """
    parts = norm_name(name).split()

    if len(parts) < 2:
        return ("", "")

    return (parts[0], parts[-1])


# ----------------------------------------------------------------------
# Load data
# ----------------------------------------------------------------------

enriched = load_json(ENRICHED)
normalized = load_json(NORMALIZED)
reconciliation = load_json(RECONCILIATION)


# ----------------------------------------------------------------------
# 1. Count author entries in ENRICHED
# ----------------------------------------------------------------------

enriched_publications = []

for faculty_record in enriched.get("faculty", []):
    for pub in faculty_record.get("publications", []):
        enriched_publications.append(pub)

enriched_author_count = sum(
    len(pub.get("authors", []))
    for pub in enriched_publications
)

enriched_pub_count = len(enriched_publications)


# ----------------------------------------------------------------------
# 2. Count author entries in NORMALIZED
# ----------------------------------------------------------------------

normalized_publications = normalized.get("publications", [])

normalized_author_count = sum(
    len(pub.get("authors", []))
    for pub in normalized_publications
)

normalized_pub_count = len(normalized_publications)


# ----------------------------------------------------------------------
# 3. Count authors on source records that disappeared during
#    normalization.
#
#    This is the important part for explaining 1774 vs 1624.
# ----------------------------------------------------------------------

source_dm_ids = set()
normalized_dm_ids = set()

for pub in enriched_publications:
    for dm_id in pub.get("dm_record_ids", []):
        source_dm_ids.add(str(dm_id))

for pub in normalized_publications:
    for dm_id in pub.get("dm_record_ids", []):
        normalized_dm_ids.add(str(dm_id))


# ----------------------------------------------------------------------
# 4. Build current MAIE faculty lookup tables.
# ----------------------------------------------------------------------

current_faculty_by_id = {}
current_faculty_by_name = {}

for faculty in normalized.get("faculty", []):

    name = faculty.get("name", "")
    user_id = faculty.get("user_id") or faculty.get("dm_user_id")

    if user_id:
        current_faculty_by_id[str(user_id)] = name

    if name:
        current_faculty_by_name[norm_name(name)] = {
            "name": name,
            "user_id": str(user_id) if user_id else None
        }


# Also support first/last comparisons.
current_by_first_last = defaultdict(list)

for faculty in normalized.get("faculty", []):
    name = faculty.get("name", "")
    fl = first_last(name)

    if fl != ("", ""):
        current_by_first_last[fl].append({
            "name": name,
            "user_id": str(faculty.get("user_id"))
            if faculty.get("user_id") else None
        })


# ----------------------------------------------------------------------
# 5. Analyze every reconciliation review item.
# ----------------------------------------------------------------------

review_items = reconciliation.get("reviews", [])

diagnostic_reviews = []

for review in review_items:

    pub_id = review.get("publication_id")
    year = review.get("year")
    suspicious_name = review.get("author_name")
    suspicious_id = review.get("faculty_id")
    reason = review.get("classification")

    # Find the publication.
    publication = None

    for pub in normalized_publications:
        if pub.get("publication_id") == pub_id:
            publication = pub
            break

    # Some versions of the reconciliation script may use "id".
    if publication is None:
        for pub in normalized_publications:
            if pub.get("id") == pub_id:
                publication = pub
                break

    authors = publication.get("authors", []) if publication else []

    # Look for current MAIE faculty names in this publication.
    current_name_matches = []

    for author in authors:

        author_name = author.get("name", "")
        author_id = author.get("faculty_id")

        # Direct current-ID match.
        id_match = (
            author_id is not None
            and str(author_id) in current_faculty_by_id
        )

        # Exact normalized-name match.
        name_match = norm_name(author_name) in current_faculty_by_name

        # First/last match.
        fl_match = first_last(author_name) in current_by_first_last

        if id_match or name_match or fl_match:

            current_name_matches.append({
                "name": author_name,
                "faculty_id": str(author_id)
                if author_id is not None else None,
                "is_current_id": id_match,
                "is_current_name": name_match,
                "is_current_first_last": fl_match,
                "current_faculty_by_id": (
                    current_faculty_by_id.get(str(author_id))
                    if author_id is not None else None
                ),
            })

    diagnostic_reviews.append({
        "publication_id": pub_id,
        "year": year,
        "suspicious_author": suspicious_name,
        "suspicious_faculty_id": (
            str(suspicious_id)
            if suspicious_id is not None else None
        ),
        "classification": reason,

        "publication_title": (
            publication.get("title")
            if publication else None
        ),

        "dm_record_ids": (
            publication.get("dm_record_ids", [])
            if publication else []
        ),

        "all_authors": authors,

        "current_maie_faculty_matches": current_name_matches,
    })


# ----------------------------------------------------------------------
# 6. Group review cases by suspicious faculty ID.
# ----------------------------------------------------------------------

reviews_by_id = defaultdict(list)

for item in diagnostic_reviews:
    reviews_by_id[item["suspicious_faculty_id"]].append(item)


# ----------------------------------------------------------------------
# 7. Find source publication objects that disappeared during
#    normalization and count their authors.
# ----------------------------------------------------------------------

normalized_dm_id_set = set()

for pub in normalized_publications:
    for dm_id in pub.get("dm_record_ids", []):
        normalized_dm_id_set.add(str(dm_id))

removed_source_records = []

for pub in enriched_publications:

    dm_ids = [
        str(x)
        for x in pub.get("dm_record_ids", [])
    ]

    # If none of this source record's IDs occur in normalized,
    # it is a source object removed by normalization.
    if dm_ids and not any(x in normalized_dm_id_set for x in dm_ids):

        removed_source_records.append({
            "title": pub.get("title"),
            "year": pub.get("year"),
            "dm_record_ids": dm_ids,
            "author_count": len(pub.get("authors", [])),
            "authors": pub.get("authors", []),
        })


removed_author_count = sum(
    x["author_count"]
    for x in removed_source_records
)


# ----------------------------------------------------------------------
# 8. Count author entries by publication object.
# ----------------------------------------------------------------------

enriched_author_histogram = Counter(
    len(pub.get("authors", []))
    for pub in enriched_publications
)

normalized_author_histogram = Counter(
    len(pub.get("authors", []))
    for pub in normalized_publications
)


# ----------------------------------------------------------------------
# 9. Build final diagnostic report.
# ----------------------------------------------------------------------

report = {
    "summary": {
        "enriched_publication_objects": enriched_pub_count,
        "normalized_unique_publications": normalized_pub_count,

        "enriched_author_entries": enriched_author_count,
        "normalized_author_entries": normalized_author_count,

        "author_entry_difference": (
            enriched_author_count - normalized_author_count
        ),

        "source_unique_dm_record_ids": len(source_dm_ids),
        "normalized_unique_dm_record_ids": len(normalized_dm_ids),

        "removed_source_publication_objects": len(
            removed_source_records
        ),

        "authors_in_removed_source_objects": removed_author_count,

        "reconciliation_review_items": len(review_items),
    },

    "current_maie_faculty": [
        {
            "name": f.get("name"),
            "user_id": f.get("user_id"),
        }
        for f in normalized.get("faculty", [])
    ],

    "review_cases": diagnostic_reviews,

    "review_cases_by_faculty_id": {
        str(k): v
        for k, v in reviews_by_id.items()
    },

    "removed_source_records": removed_source_records,

    "author_count_histograms": {
        "enriched": dict(sorted(enriched_author_histogram.items())),
        "normalized": dict(sorted(normalized_author_histogram.items())),
    },
}


# ----------------------------------------------------------------------
# Write report
# ----------------------------------------------------------------------

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------------
# Human-readable terminal summary
# ----------------------------------------------------------------------

print("=" * 70)
print("MAIE AUTHORSHIP RECONCILIATION DIAGNOSTIC")
print("=" * 70)

print()
print("PUBLICATION / AUTHOR ACCOUNTING")
print("-" * 70)
print(f"Enriched publication objects : {enriched_pub_count}")
print(f"Normalized publications      : {normalized_pub_count}")
print(f"Enriched author entries      : {enriched_author_count}")
print(f"Normalized author entries    : {normalized_author_count}")
print(
    f"Author-entry difference      : "
    f"{enriched_author_count - normalized_author_count}"
)

print()
print("DM RECORD ACCOUNTING")
print("-" * 70)
print(f"Raw unique DM record IDs     : {len(source_dm_ids)}")
print(f"Normalized unique DM IDs     : {len(normalized_dm_ids)}")
print(
    f"Removed source pub objects   : "
    f"{len(removed_source_records)}"
)
print(
    f"Authors in removed objects   : "
    f"{removed_author_count}"
)

print()
print("RECONCILIATION REVIEWS")
print("-" * 70)
print(f"Review items                 : {len(review_items)}")

print()
print("REVIEW CASES BY FACULTY ID")
print("-" * 70)

for faculty_id, cases in sorted(
    reviews_by_id.items(),
    key=lambda x: str(x[0])
):
    current_name = current_faculty_by_id.get(str(faculty_id))

    print(
        f"ID {faculty_id} -> "
        f"{current_name if current_name else 'NOT CURRENT MAIE'} : "
        f"{len(cases)} review cases"
    )

print()
print("DETAILED REVIEW CASES")
print("-" * 70)

for item in diagnostic_reviews:

    print()
    print(
        f"{item['publication_id']} | "
        f"{item['year']} | "
        f"{item['classification']}"
    )

    print(f"Title: {item['publication_title']}")
    print(
        f"Suspicious author: "
        f"{item['suspicious_author']} "
        f"(ID {item['suspicious_faculty_id']})"
    )

    print("Authors:")

    for author in item["all_authors"]:

        marker = ""

        if author.get("faculty_id") is not None:
            marker = f" [ID={author.get('faculty_id')}]"

        print(
            f"  - {author.get('name')}"
            f"{marker}"
        )

    if item["current_maie_faculty_matches"]:

        print("Current MAIE faculty matches:")

        for match in item["current_maie_faculty_matches"]:
            print(
                f"  * {match['name']} "
                f"(ID={match['faculty_id']})"
            )

print()
print("=" * 70)
print(f"Diagnostic written to:")
print(OUTPUT)
print("=" * 70)
