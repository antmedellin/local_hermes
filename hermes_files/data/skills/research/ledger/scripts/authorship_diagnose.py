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

INPUT_FILE = (
    BASE_DIR
    / "data"
    / "maie_faculty_normalized.json"
)

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "maie_authorship_diagnosis.json"
)


# -------------------------------------------------------
# Name normalization
# -------------------------------------------------------

def clean_name(name):
    """
    Create a simplified version of a name for comparison.

    This DOES NOT modify the original name stored in our
    research data. It is only used for comparison.
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

    # Remove parenthetical names.
    #
    # Example:
    # Jianzhi (James) Li
    #
    # becomes:
    # Jianzhi Li
    name = re.sub(
        r"\([^)]*\)",
        " ",
        name,
    )

    # Remove punctuation that does not matter for
    # identity comparison.
    name = name.replace(",", " ")
    name = name.replace(".", " ")

    # Normalize different dash characters.
    name = name.replace("–", "-")
    name = name.replace("—", "-")

    # Collapse multiple spaces.
    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    return name.lower()


def name_parts(name):
    """
    Split a name into parts.

    Returns:
        parts
        first name
        last name
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


def first_initial(name):
    """
    Get the first initial of a name.
    """

    _, first, _ = name_parts(name)

    if first:
        return first[0]

    return ""


def initials(name):
    """
    Get all initials from a name.

    Example:

        Anil Kumar Srivastava

    becomes:

        aks
    """

    parts, _, _ = name_parts(name)

    return "".join(
        part[0]
        for part in parts
        if part
    )


# -------------------------------------------------------
# Name comparison
# -------------------------------------------------------

def classify_name_match(
    historical_name,
    current_name,
):
    """
    Determine how closely a historical author name
    matches the current faculty name.

    IMPORTANT:
    This function only classifies the names.

    It does NOT modify either name.
    """

    historical_clean = clean_name(
        historical_name
    )

    current_clean = clean_name(
        current_name
    )

    if not historical_clean or not current_clean:
        return "UNKNOWN"

    # ---------------------------------------------------
    # Exact normalized match
    # ---------------------------------------------------

    if historical_clean == current_clean:
        return "EXACT"

    # ---------------------------------------------------
    # Compare first and last names
    # ---------------------------------------------------

    (
        historical_parts,
        historical_first,
        historical_last,
    ) = name_parts(historical_name)

    (
        current_parts,
        current_first,
        current_last,
    ) = name_parts(current_name)

    # Same first + last name.
    #
    # This allows middle-name differences.
    #
    # Example:
    # Douglas Timmer
    # Douglas H Timmer
    if (
        historical_first == current_first
        and historical_last == current_last
    ):
        return "SAME_FIRST_LAST"

    # ---------------------------------------------------
    # Same last name + first initial
    # ---------------------------------------------------

    if (
        historical_last == current_last
        and first_initial(historical_name)
        == first_initial(current_name)
    ):
        return "SAME_LAST_FIRST_INITIAL"

    # ---------------------------------------------------
    # Initials comparison
    # ---------------------------------------------------

    historical_initials = initials(
        historical_name
    )

    current_initials = initials(
        current_name
    )

    if (
        historical_initials
        and current_initials
        and historical_last == current_last
        and (
            historical_initials
            == current_initials
            or historical_initials.startswith(
                current_initials[:1]
            )
            or current_initials.startswith(
                historical_initials[:1]
            )
        )
    ):
        return "INITIALS_VARIANT"

    # ---------------------------------------------------
    # General string similarity
    # ---------------------------------------------------

    similarity = SequenceMatcher(
        None,
        historical_clean,
        current_clean,
    ).ratio()

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

with INPUT_FILE.open(
    "r",
    encoding="utf-8",
) as f:

    data = json.load(f)


faculty_records = data.get(
    "faculty",
    []
)

publications = data.get(
    "publications",
    [] 
)

print(
    f"Faculty records: {len(faculty_records)}"
)

print(
    f"Publication records: {len(publications)}"
)


# -------------------------------------------------------
# Build current faculty ID map
# -------------------------------------------------------

faculty_id_map = {}

for faculty in faculty_records:

    # IMPORTANT:
    #
    # In the normalized file, the faculty record
    # itself contains user_id.
    #
    # It is NOT nested inside faculty["faculty"].

    faculty_id = (
        faculty.get("user_id")
        or faculty.get("dm_user_id")
    )

    faculty_name = faculty.get(
        "name"
    )

    if faculty_id and faculty_name:

        faculty_id_map[
            str(faculty_id)
        ] = faculty_name


print(
    f"Faculty IDs available: "
    f"{len(faculty_id_map)}"
)


# -------------------------------------------------------
# Examine authorship records
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


# -------------------------------------------------------
# IMPORTANT:
#
# The normalized file has publications at the TOP LEVEL.
#
# Therefore we inspect:
#
# data["publications"]
#
# rather than looking inside each faculty record.
# -------------------------------------------------------

for publication in publications:

    title = publication.get(
        "title"
    )

    year = publication.get(
        "year"
    )

    doi = publication.get(
        "doi"
    )

    authors = publication.get(
        "authors",
        []
    )

    for author in authors:

        faculty_id = author.get(
            "faculty_id"
        )

        author_name = author.get(
            "name"
        )

        if not faculty_id:
            continue

        faculty_id = str(
            faculty_id
        )

        # Only analyze authors whose faculty ID
        # corresponds to one of our current MAIE
        # faculty members.
        if faculty_id not in faculty_id_map:
            continue

        total_maie_authors += 1

        current_name = faculty_id_map[
            faculty_id
        ]

        category = classify_name_match(
            author_name,
            current_name,
        )

        category_counts[
            category
        ] += 1

        # Save only non-exact matches.
        if category != "EXACT":

            diagnosis.append(
                {
                    "faculty_id": faculty_id,
                    "current_faculty_name": current_name,
                    "historical_author_name": author_name,
                    "category": category,
                    "publication_title": title,
                    "publication_year": year,
                    "doi": doi,
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

print(
    f"MAIE faculty-ID author entries: "
    f"{total_maie_authors}"
)

print()
print("Category counts:")

for category, count in category_counts.items():

    print(
        f"  {category:<30} {count}"
    )


print()
print(
    "Non-exact entries requiring review: "
    f"{len(diagnosis)}"
)


# -------------------------------------------------------
# Possible mismatches
# -------------------------------------------------------

major = [
    item
    for item in diagnosis
    if item["category"]
    == "POSSIBLE_MISMATCH"
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
            f"Faculty ID: "
            f"{item['faculty_id']}"
        )

        print(
            f"Current name:    "
            f"{item['current_faculty_name']}"
        )

        print(
            f"Historical name: "
            f"{item['historical_author_name']}"
        )

        print(
            f"Publication:     "
            f"{item['publication_title']}"
        )

        print(
            f"Year:            "
            f"{item['publication_year']}"
        )

        if item["doi"]:

            print(
                f"DOI:             "
                f"{item['doi']}"
            )


# -------------------------------------------------------
# Moderate similarity
# -------------------------------------------------------

moderate = [
    item
    for item in diagnosis
    if item["category"]
    == "MODERATE_SIMILARITY"
]

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
            f"Faculty ID: "
            f"{item['faculty_id']}"
        )

        print(
            f"Current name:    "
            f"{item['current_faculty_name']}"
        )

        print(
            f"Historical name: "
            f"{item['historical_author_name']}"
        )

        print(
            f"Publication:     "
            f"{item['publication_title']}"
        )


# -------------------------------------------------------
# Save diagnosis
# -------------------------------------------------------

output = {
    "metadata": {
        "description": (
            "Diagnosis of MAIE authorship names "
            "associated with current Digital "
            "Measures faculty IDs."
        ),
        "faculty_count": len(
            faculty_records
        ),
        "publication_count": len(
            publications
        ),
        "maie_faculty_id_author_entries":
            total_maie_authors,
        "non_exact_entries":
            len(diagnosis),
    },
    "category_counts":
        category_counts,
    "diagnosis":
        diagnosis,
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

print(
    "Diagnosis written to:"
)

print(
    OUTPUT_FILE
)

print()
print("Done.")