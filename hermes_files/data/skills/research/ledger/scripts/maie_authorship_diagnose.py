import json
import re
from pathlib import Path
from difflib import SequenceMatcher


# -------------------------------------------------------
# Paths
# -------------------------------------------------------

BASE_DIR = Path(
    "hermes_files/data/skills/research/ledger"
)

INPUT_FILE = BASE_DIR / "data" / "maie_faculty_normalized.json"
OUTPUT_FILE = BASE_DIR / "data" / "maie_authorship_diagnosis.json"


# -------------------------------------------------------
# Name normalization helpers
# -------------------------------------------------------

def clean_name(name):
    """
    Make a name easier to compare.

    We intentionally DO NOT completely replace the
    original author name. This is only for comparison.
    """

    if not name:
        return ""

    name = str(name).strip()

    # Remove common titles.
    titles = [
        "Dr.",
        "Dr",
        "Prof.",
        "Prof",
        "Professor",
        "Mr.",
        "Mr",
        "Ms.",
        "Ms",
        "Mrs.",
        "Mrs",
        "CDR",
        "Commander",
    ]

    for title in titles:
        name = re.sub(
            rf"\b{re.escape(title)}\b",
            "",
            name,
            flags=re.IGNORECASE,
        )

    # Remove text in parentheses.
    # Example:
    # Jianzhi (James) Li -> Jianzhi Li
    name = re.sub(r"\([^)]*\)", " ", name)

    # Remove commas and periods.
    name = name.replace(",", " ")
    name = name.replace(".", " ")

    # Normalize hyphens.
    name = name.replace("–", "-")
    name = name.replace("—", "-")

    # Collapse whitespace.
    name = re.sub(r"\s+", " ", name).strip()

    return name.lower()


def name_parts(name):
    """
    Break a cleaned name into first/middle/last components.
    """

    cleaned = clean_name(name)

    if not cleaned:
        return [], "", ""

    parts = cleaned.split()

    if len(parts) == 1:
        return parts, parts[0], parts[0]

    first = parts[0]
    last = parts[-1]

    return parts, first, last


def initials(name):
    """
    Return initials from the cleaned name.

    Example:
        Anil Kumar Srivastava
        -> aks

    Example:
        A K Srivastava
        -> aks
    """

    parts, _, _ = name_parts(name)

    return "".join(part[0] for part in parts if part)


def first_initial(name):
    """
    Return the first-name initial.
    """

    _, first, _ = name_parts(name)

    if first:
        return first[0]

    return ""


# -------------------------------------------------------
# Comparison logic
# -------------------------------------------------------

def classify_name_match(author_name, canonical_name):
    """
    Classify how closely an historical author name matches
    the current MAIE faculty name.

    IMPORTANT:
    This function does not modify either name.
    """

    author_clean = clean_name(author_name)
    canonical_clean = clean_name(canonical_name)

    if not author_clean or not canonical_clean:
        return "UNKNOWN"

    # Exact normalized match.
    if author_clean == canonical_clean:
        return "EXACT"

    author_parts, author_first, author_last = name_parts(author_name)
    canon_parts, canon_first, canon_last = name_parts(canonical_name)

    # Same first and last name, possibly different middle names.
    if (
        author_first == canon_first
        and author_last == canon_last
    ):
        return "SAME_FIRST_LAST"

    # Same surname and same first initial.
    if (
        author_last == canon_last
        and first_initial(author_name) == first_initial(canonical_name)
    ):
        return "SAME_LAST_FIRST_INITIAL"

    # Compare complete initials.
    author_initials = initials(author_name)
    canon_initials = initials(canonical_name)

    if (
        author_initials
        and canon_initials
        and author_last == canon_last
        and (
            author_initials == canon_initials
            or author_initials.startswith(canon_initials[:1])
            or canon_initials.startswith(author_initials[:1])
        )
    ):
        return "INITIALS_VARIANT"

    # Similarity score as a secondary signal.
    similarity = SequenceMatcher(
        None,
        author_clean,
        canonical_clean,
    ).ratio()

    # Strongly similar strings.
    if similarity >= 0.85:
        return "HIGH_SIMILARITY"

    if similarity >= 0.70:
        return "MODERATE_SIMILARITY"

    return "POSSIBLE_MISMATCH"


# -------------------------------------------------------
# Load normalized data
# -------------------------------------------------------

print()
print("Loading normalized MAIE data...")
print(f"Input: {INPUT_FILE}")

with INPUT_FILE.open("r", encoding="utf-8") as f:
    data = json.load(f)


faculty_records = data.get("faculty", [])

print(f"Faculty records: {len(faculty_records)}")


# -------------------------------------------------------
# Build faculty ID -> canonical name map
# -------------------------------------------------------

faculty_id_map = {}

for record in faculty_records:

    faculty = record.get("faculty", {})

    faculty_id = faculty.get("faculty_id")

    name = faculty.get("name")

    if faculty_id and name:
        faculty_id_map[str(faculty_id)] = name


print(f"Faculty IDs available: {len(faculty_id_map)}")


# -------------------------------------------------------
# Examine every authorship record
# -------------------------------------------------------

diagnosis = []

category_counts = {
    "EXACT": 0,
    "SAME_FIRST_LAST": 0,
    "SAME_LAST_FIRST_INITIAL": 0,
    "INITIALS_VARIANT": 0,
    "HIGH_SIMILARITY": 0,
    "MODERATE_SIMILARITY": 0,
    "POSSIBLE_MISMATCH": 0,
    "UNKNOWN": 0,
}


total_maie_authors = 0


for faculty_record in faculty_records:

    faculty = faculty_record.get("faculty", {})

    publications = faculty_record.get(
        "publications",
        []
    )

    for publication in publications:

        title = publication.get("title")

        authors = publication.get(
            "authors",
            []
        )

        for author in authors:

            faculty_id = author.get("faculty_id")

            author_name = author.get("name")

            # We only diagnose authors that have a
            # faculty ID corresponding to a current MAIE
            # faculty member.
            if not faculty_id:
                continue

            faculty_id = str(faculty_id)

            if faculty_id not in faculty_id_map:
                continue

            total_maie_authors += 1

            canonical_name = faculty_id_map[faculty_id]

            category = classify_name_match(
                author_name,
                canonical_name,
            )

            category_counts[category] += 1

            # Only save non-exact matches.
            if category != "EXACT":

                diagnosis.append(
                    {
                        "faculty_id": faculty_id,
                        "current_faculty_name": canonical_name,
                        "historical_author_name": author_name,
                        "category": category,
                        "publication_title": title,
                        "publication_year": publication.get(
                            "year"
                        ),
                        "doi": publication.get(
                            "doi"
                        ),
                    }
                )


# -------------------------------------------------------
# Sort results
# -------------------------------------------------------

severity_order = {
    "POSSIBLE_MISMATCH": 0,
    "MODERATE_SIMILARITY": 1,
    "HIGH_SIMILARITY": 2,
    "INITIALS_VARIANT": 3,
    "SAME_LAST_FIRST_INITIAL": 4,
    "SAME_FIRST_LAST": 5,
}


diagnosis.sort(
    key=lambda item: (
        severity_order.get(
            item["category"],
            99,
        ),
        item["current_faculty_name"],
        item["historical_author_name"] or "",
    )
)


# -------------------------------------------------------
# Print summary
# -------------------------------------------------------

print()
print("=" * 60)
print("AUTHORSHIP DIAGNOSIS")
print("=" * 60)

print(f"MAIE faculty-ID author entries: {total_maie_authors}")

print()
print("Category counts:")

for category, count in category_counts.items():
    print(f"  {category:<30} {count}")


print()
print(
    f"Non-exact entries requiring review: {len(diagnosis)}"
)


# -------------------------------------------------------
# Print suspicious / major mismatches
# -------------------------------------------------------

major = [
    item
    for item in diagnosis
    if item["category"] == "POSSIBLE_MISMATCH"
]

moderate = [
    item
    for item in diagnosis
    if item["category"] == "MODERATE_SIMILARITY"
]


print()
print("=" * 60)
print("POSSIBLE MISMATCHES")
print("=" * 60)

if not major:
    print("None found.")
else:

    for item in major[:50]:

        print()
        print(
            f"Faculty ID: {item['faculty_id']}"
        )

        print(
            f"Current name:    {item['current_faculty_name']}"
        )

        print(
            f"Historical name: {item['historical_author_name']}"
        )

        print(
            f"Publication:     {item['publication_title']}"
        )

        print(
            f"Year:            {item['publication_year']}"
        )

        if item["doi"]:
            print(
                f"DOI:             {item['doi']}"
            )


print()
print("=" * 60)
print("MODERATE SIMILARITY")
print("=" * 60)

if not moderate:
    print("None found.")
else:

    for item in moderate[:30]:

        print()
        print(
            f"Faculty ID: {item['faculty_id']}"
        )

        print(
            f"Current name:    {item['current_faculty_name']}"
        )

        print(
            f"Historical name: {item['historical_author_name']}"
        )

        print(
            f"Publication:     {item['publication_title']}"
        )


# -------------------------------------------------------
# Save diagnosis
# -------------------------------------------------------

output = {
    "metadata": {
        "description": (
            "Diagnosis of MAIE authorship names associated "
            "with current Digital Measures faculty IDs."
        ),
        "faculty_count": len(faculty_records),
        "maie_faculty_id_author_entries": total_maie_authors,
        "non_exact_entries": len(diagnosis),
    },
    "category_counts": category_counts,
    "diagnosis": diagnosis,
}


with OUTPUT_FILE.open(
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        output,
        f,
        indent=2,
        ensure_ascii=False,
    )


print()
print("=" * 60)
print("OUTPUT")
print("=" * 60)

print(f"Diagnosis written to:")
print(OUTPUT_FILE)

print()
print("Done.")