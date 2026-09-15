import json
from pathlib import Path
from collections import defaultdict


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

RAW_FILE = DATA_DIR / "maie_faculty_enriched.json"
NORMALIZED_FILE = DATA_DIR / "maie_faculty_normalized.json"


def clean(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_text(value):
    value = clean(value).lower()
    return " ".join(value.split())


def identity_key(pub):
    """
    Identity used by the raw reconciliation.
    """

    doi = normalize_text(pub.get("doi"))

    if doi:
        return ("doi", doi)

    title = normalize_text(
        pub.get("normalized_title") or pub.get("title")
    )

    year = clean(pub.get("year"))

    return ("title_year", title, year)


# -------------------------------------------------------
# Load data
# -------------------------------------------------------

with open(RAW_FILE, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

with open(NORMALIZED_FILE, "r", encoding="utf-8") as f:
    normalized_data = json.load(f)


# -------------------------------------------------------
# Collect raw records
# -------------------------------------------------------

raw_publications = []

for faculty_record in raw_data.get("faculty", []):

    faculty_info = faculty_record.get("faculty", {})
    faculty_name = faculty_info.get("name", "UNKNOWN")

    for pub in faculty_record.get("publications", []):

        copy = dict(pub)
        copy["_faculty_name"] = faculty_name

        raw_publications.append(copy)


# -------------------------------------------------------
# Build raw identity groups
# -------------------------------------------------------

raw_groups = defaultdict(list)

for pub in raw_publications:
    raw_groups[identity_key(pub)].append(pub)


# -------------------------------------------------------
# Build normalized groups
# -------------------------------------------------------

normalized_groups = defaultdict(list)

for pub in normalized_data.get("publications", []):

    normalized_groups[identity_key(pub)].append(pub)


# -------------------------------------------------------
# Find raw groups that disappeared
# -------------------------------------------------------

missing_groups = []

for key in raw_groups:

    if key not in normalized_groups:

        missing_groups.append(
            (key, raw_groups[key])
        )


# -------------------------------------------------------
# Print results
# -------------------------------------------------------

print()
print("=" * 70)
print("IDENTITY GROUPS PRESENT IN RAW DATA BUT ABSENT FROM NORMALIZED DATA")
print("=" * 70)

print()
print(f"Groups missing from normalized data: {len(missing_groups)}")


for number, (key, records) in enumerate(
    missing_groups,
    start=1
):

    print()
    print("=" * 70)
    print(f"MISSING GROUP {number}")
    print("=" * 70)

    print(f"Identity key: {key}")

    for record_number, pub in enumerate(
        records,
        start=1
    ):

        print()
        print(f"Record {record_number}")

        print(
            f"  Title: "
            f"{pub.get('title')}"
        )

        print(
            f"  Year: "
            f"{pub.get('year')}"
        )

        print(
            f"  DOI: "
            f"{pub.get('doi')}"
        )

        print(
            f"  Type: "
            f"{pub.get('type')}"
        )

        print(
            f"  Status: "
            f"{pub.get('status')}"
        )

        print(
            f"  Faculty: "
            f"{pub.get('_faculty_name')}"
        )

        print(
            f"  DM record ID: "
            f"{pub.get('dm_record_id')}"
        )

        print(
            f"  Sources: "
            f"{pub.get('sources')}"
        )


# -------------------------------------------------------
# Also inspect normalized records with matching titles
# -------------------------------------------------------

print()
print("=" * 70)
print("DONE")
print("=" * 70)