import json
from pathlib import Path
from collections import defaultdict


# -------------------------------------------------------
# Paths
# -------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

RAW_FILE = DATA_DIR / "maie_faculty_enriched.json"
NORMALIZED_FILE = DATA_DIR / "maie_faculty_normalized.json"


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def clean(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_text(value):
    """
    Normalize text enough for comparison.

    This is ONLY for diagnosing duplicates.
    It does not modify the actual database data.
    """

    value = clean(value).lower()

    # Collapse whitespace
    value = " ".join(value.split())

    return value


def publication_key(pub):
    """
    Reproduce the basic identity logic used by normalization.

    DOI is preferred.

    If DOI is unavailable, use normalized title + year.
    """

    doi = normalize_text(pub.get("doi"))

    if doi:
        return ("doi", doi)

    title = normalize_text(
        pub.get("normalized_title") or pub.get("title")
    )

    year = clean(pub.get("year"))

    return ("title_year", title, year)


def display_pub(pub):
    """
    Create a short human-readable description.
    """

    title = clean(pub.get("title"))

    if not title:
        title = "(no title)"

    year = clean(pub.get("year"))

    doi = clean(pub.get("doi"))

    if doi:
        return f"{title} [{year}] DOI={doi}"

    return f"{title} [{year}]"


# -------------------------------------------------------
# Load files
# -------------------------------------------------------

print("Loading raw and normalized data...")

with open(RAW_FILE, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

with open(NORMALIZED_FILE, "r", encoding="utf-8") as f:
    normalized_data = json.load(f)


# -------------------------------------------------------
# Extract raw publications
# -------------------------------------------------------

raw_publications = []

for faculty_record in raw_data.get("faculty", []):

    faculty_info = faculty_record.get("faculty", {})

    faculty_name = faculty_info.get("name", "UNKNOWN")

    for pub in faculty_record.get("publications", []):

        # Keep track of which faculty record produced it.
        pub_copy = dict(pub)

        pub_copy["_faculty_name"] = faculty_name

        raw_publications.append(pub_copy)


normalized_publications = normalized_data.get(
    "publications",
    []
)


# -------------------------------------------------------
# Basic counts
# -------------------------------------------------------

print()
print("=" * 60)
print("COUNT SUMMARY")
print("=" * 60)

print(
    f"Raw publication objects:        "
    f"{len(raw_publications)}"
)

print(
    f"Normalized publications:        "
    f"{len(normalized_publications)}"
)

print(
    f"Objects removed by normalization:"
    f" {len(raw_publications) - len(normalized_publications)}"
)


# -------------------------------------------------------
# Group RAW records by the normalization key
# -------------------------------------------------------

raw_groups = defaultdict(list)

for pub in raw_publications:

    key = publication_key(pub)

    raw_groups[key].append(pub)


# -------------------------------------------------------
# Analyze duplicate groups
# -------------------------------------------------------

duplicate_groups = {
    key: pubs
    for key, pubs in raw_groups.items()
    if len(pubs) > 1
}


print()
print("=" * 60)
print("RAW DUPLICATE GROUPS")
print("=" * 60)

print(
    f"Unique identity groups from raw data: "
    f"{len(raw_groups)}"
)

print(
    f"Groups containing duplicates: "
    f"{len(duplicate_groups)}"
)

duplicate_objects_removed = sum(
    len(pubs) - 1
    for pubs in duplicate_groups.values()
)

print(
    f"Duplicate objects removed: "
    f"{duplicate_objects_removed}"
)


# -------------------------------------------------------
# Print every duplicate group
# -------------------------------------------------------

print()
print("=" * 60)
print("EVERY DUPLICATE GROUP")
print("=" * 60)

group_number = 1

for key, pubs in sorted(
    duplicate_groups.items(),
    key=lambda item: str(item[0])
):

    print()
    print(f"GROUP {group_number}")
    print("-" * 60)

    print(f"Identity key: {key}")

    for index, pub in enumerate(pubs, start=1):

        print(
            f"  Record {index}: "
            f"{display_pub(pub)}"
        )

        print(
            f"      Faculty: "
            f"{pub.get('_faculty_name')}"
        )

        print(
            f"      Type: "
            f"{pub.get('type')}"
        )

        print(
            f"      Status: "
            f"{pub.get('status')}"
        )

        print(
            f"      DM record ID: "
            f"{pub.get('dm_record_id')}"
        )

        print(
            f"      DOI: "
            f"{pub.get('doi')}"
        )

        print(
            f"      Publisher: "
            f"{pub.get('publisher')}"
        )

    group_number += 1


# -------------------------------------------------------
# Compare the number of raw identity groups
# -------------------------------------------------------

print()
print("=" * 60)
print("RECONCILIATION")
print("=" * 60)

print(
    f"Raw objects:              "
    f"{len(raw_publications)}"
)

print(
    f"Raw identity groups:      "
    f"{len(raw_groups)}"
)

print(
    f"Normalized publications:  "
    f"{len(normalized_publications)}"
)

print()

if len(raw_groups) == len(normalized_publications):

    print(
        "GOOD: The normalized publication count "
        "matches the number of raw identity groups."
    )

else:

    print(
        "WARNING: Raw identity groups and normalized "
        "publications do not match."
    )

    print(
        f"Difference: "
        f"{len(raw_groups) - len(normalized_publications)}"
    )


# -------------------------------------------------------
# Check the 459 question
# -------------------------------------------------------

print()
print("=" * 60)
print("ABOUT THE ORIGINAL 459 COUNT")
print("=" * 60)

original_metadata_count = (
    raw_data
    .get("metadata", {})
    .get("publication_count")
)

print(
    f"Original enriched metadata count: "
    f"{original_metadata_count}"
)

print(
    f"Raw publication objects recovered: "
    f"{len(raw_publications)}"
)

if original_metadata_count is not None:

    difference = (
        original_metadata_count
        - len(normalized_publications)
    )

    print(
        f"Original metadata count minus "
        f"normalized count: {difference}"
    )

    print()

    if difference == 0:

        print(
            "The original metadata count matches "
            "the normalized publication count."
        )

    else:

        print(
            "The original metadata count does NOT "
            "match the normalized count."
        )

        print(
            "We need to determine what the original "
            "459 count represented."
        )


print()
print("Reconciliation finished.")