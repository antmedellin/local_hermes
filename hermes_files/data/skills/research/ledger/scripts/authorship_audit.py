import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from difflib import SequenceMatcher


# ============================================================
# FILE PATHS
# ============================================================

BASE_DIR = Path(
    "hermes_files/data/skills/research/ledger"
)

NORMALIZED_FILE = (
    BASE_DIR / "data" / "maie_faculty_normalized.json"
)

REPORT_FILE = (
    BASE_DIR / "data" / "maie_authorship_audit.json"
)


# ============================================================
# NAME NORMALIZATION
# ============================================================

def normalize_name(name):
    """
    Normalize a person's name so that small formatting
    differences do not look like different people.

    Examples:

        "Douglas H Timmer"
        "Douglas Timmer"

    or:

        "Anil K. Srivastava"
        "Anil Kumar Srivastava"

    may still need special handling, but this gives us
    a consistent baseline.
    """

    if not name:
        return ""

    name = name.lower()

    # Remove punctuation.
    name = re.sub(r"[^a-z0-9\s]", " ", name)

    # Collapse whitespace.
    name = re.sub(r"\s+", " ", name).strip()

    return name


def name_parts(name):
    """
    Return first and last name components.
    """

    normalized = normalize_name(name)

    if not normalized:
        return "", ""

    parts = normalized.split()

    if len(parts) == 1:
        return parts[0], parts[0]

    return parts[0], parts[-1]


# ============================================================
# NAME COMPARISON
# ============================================================

def classify_name_match(historical_name, current_name):
    """
    Classify how closely the historical Digital Measures
    author name matches the current MAIE faculty name.
    """

    historical = normalize_name(historical_name)
    current = normalize_name(current_name)

    if not historical or not current:
        return "UNKNOWN"

    # Exact normalized match.
    if historical == current:
        return "EXACT"

    hist_first, hist_last = name_parts(historical)
    curr_first, curr_last = name_parts(current)

    # Same first + same last.
    if hist_first == curr_first and hist_last == curr_last:
        return "SAME_FIRST_LAST"

    # Same last + first initial.
    if (
        hist_last == curr_last
        and hist_first
        and curr_first
        and hist_first[0] == curr_first[0]
    ):
        return "SAME_LAST_FIRST_INITIAL"

    # Compare initials.
    hist_initials = "".join(
        part[0] for part in historical.split() if part
    )

    curr_initials = "".join(
        part[0] for part in current.split() if part
    )

    if hist_initials == curr_initials:
        return "INITIALS_VARIANT"

    # Overall string similarity.
    similarity = SequenceMatcher(
        None,
        historical,
        current
    ).ratio()

    if similarity >= 0.80:
        return "HIGH_SIMILARITY"

    if similarity >= 0.60:
        return "MODERATE_SIMILARITY"

    return "POSSIBLE_MISMATCH"


# ============================================================
# LOAD DATA
# ============================================================

print("=" * 70)
print("MAIE AUTHORSHIP PROVENANCE AUDIT")
print("=" * 70)

print()
print("Loading normalized data...")

with open(NORMALIZED_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)


faculty = data["faculty"]
publications = data["publications"]


print(f"Faculty records:       {len(faculty)}")
print(f"Publication records:   {len(publications)}")


# ============================================================
# CURRENT FACULTY MAP
# ============================================================

faculty_id_map = {}

for person in faculty:

    faculty_id = (
        person.get("user_id")
        or person.get("dm_user_id")
    )

    if faculty_id:
        faculty_id_map[str(faculty_id)] = person["name"]


print(f"Faculty IDs available: {len(faculty_id_map)}")


# ============================================================
# AUDIT AUTHORSHIP
# ============================================================

category_counts = Counter()

entries_by_category = defaultdict(list)

faculty_history = defaultdict(Counter)

possible_mismatches = []

total_faculty_id_entries = 0


for publication in publications:

    publication_id = publication.get("publication_id")

    title = publication.get("title")
    year = publication.get("year")

    authors = publication.get("authors", [])

    for author in authors:

        faculty_id = author.get("faculty_id")
        author_name = author.get("name")

        # We only want authorship records where
        # Digital Measures supplied a faculty ID.
        if faculty_id is None:
            continue

        faculty_id = str(faculty_id)

        # Only audit IDs belonging to current MAIE faculty.
        if faculty_id not in faculty_id_map:
            continue

        total_faculty_id_entries += 1

        current_name = faculty_id_map[faculty_id]

        category = classify_name_match(
            author_name,
            current_name
        )

        category_counts[category] += 1

        # Track historical names associated with
        # each current faculty ID.
        faculty_history[faculty_id][author_name] += 1

        entry = {
            "publication_id": publication_id,
            "title": title,
            "year": year,
            "faculty_id": faculty_id,
            "current_faculty_name": current_name,
            "historical_author_name": author_name,
            "category": category,
        }

        entries_by_category[category].append(entry)

        if category == "POSSIBLE_MISMATCH":
            possible_mismatches.append(entry)


# ============================================================
# PRINT SUMMARY
# ============================================================

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)

print()
print(
    f"MAIE faculty-ID author entries: "
    f"{total_faculty_id_entries}"
)

print()
print("Category counts:")

category_order = [
    "EXACT",
    "SAME_FIRST_LAST",
    "SAME_LAST_FIRST_INITIAL",
    "INITIALS_VARIANT",
    "HIGH_SIMILARITY",
    "MODERATE_SIMILARITY",
    "POSSIBLE_MISMATCH",
    "UNKNOWN",
]

for category in category_order:

    print(
        f"  {category:<30} "
        f"{category_counts[category]}"
    )


# ============================================================
# HISTORICAL NAME SUMMARY
# ============================================================

print()
print("=" * 70)
print("HISTORICAL NAME VARIANTS")
print("=" * 70)


historical_name_report = []


for faculty_id, names in sorted(
    faculty_history.items(),
    key=lambda item: faculty_id_map[item[0]]
):

    current_name = faculty_id_map[faculty_id]

    print()
    print(
        f"{current_name} "
        f"(faculty ID {faculty_id})"
    )

    for historical_name, count in names.most_common():

        category = classify_name_match(
            historical_name,
            current_name
        )

        print(
            f"  {count:>3}  "
            f"{category:<28} "
            f"{historical_name}"
        )

        historical_name_report.append({
            "faculty_id": faculty_id,
            "current_faculty_name": current_name,
            "historical_author_name": historical_name,
            "count": count,
            "category": category,
        })


# ============================================================
# POSSIBLE MISMATCHES
# ============================================================

print()
print("=" * 70)
print("POSSIBLE MISMATCHES")
print("=" * 70)

print()
print(
    f"Possible mismatch entries: "
    f"{len(possible_mismatches)}"
)

for entry in possible_mismatches:

    print()
    print(
        f"Faculty ID: {entry['faculty_id']}"
    )

    print(
        f"Current faculty: "
        f"{entry['current_faculty_name']}"
    )

    print(
        f"Historical author: "
        f"{entry['historical_author_name']}"
    )

    print(
        f"Year: {entry['year']}"
    )

    print(
        f"Publication: {entry['title']}"
    )


# ============================================================
# WRITE REPORT
# ============================================================

report = {
    "summary": {
        "faculty_records": len(faculty),
        "publication_records": len(publications),
        "maie_faculty_id_author_entries": total_faculty_id_entries,
        "category_counts": dict(category_counts),
        "possible_mismatch_count": len(possible_mismatches),
    },

    "historical_name_variants": historical_name_report,

    "possible_mismatches": possible_mismatches,

    "all_categories": {
        category: entries
        for category, entries in entries_by_category.items()
    },
}


with open(REPORT_FILE, "w", encoding="utf-8") as f:

    json.dump(
        report,
        f,
        indent=2,
        ensure_ascii=False
    )


print()
print("=" * 70)
print("REPORT WRITTEN")
print("=" * 70)

print()
print(REPORT_FILE)