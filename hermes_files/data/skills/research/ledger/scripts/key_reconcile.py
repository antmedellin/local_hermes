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


def key(pub):
    """
    Identity key used for comparison.
    """

    doi = normalize_text(pub.get("doi"))

    if doi:
        return ("doi", doi)

    title = normalize_text(
        pub.get("normalized_title") or pub.get("title")
    )

    year = clean(pub.get("year"))

    return ("title_year", title, year)


def short(pub):
    title = clean(pub.get("title"))
    year = clean(pub.get("year"))
    doi = clean(pub.get("doi"))

    return f"{title} [{year}] DOI={doi or 'NONE'}"


# -------------------------------------------------------
# Load
# -------------------------------------------------------

with open(RAW_FILE, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

with open(NORMALIZED_FILE, "r", encoding="utf-8") as f:
    normalized_data = json.load(f)


# -------------------------------------------------------
# Raw records
# -------------------------------------------------------

raw = []

for faculty_record in raw_data.get("faculty", []):

    faculty_name = (
        faculty_record
        .get("faculty", {})
        .get("name", "UNKNOWN")
    )

    for pub in faculty_record.get("publications", []):

        p = dict(pub)
        p["_faculty_name"] = faculty_name

        raw.append(p)


normalized = normalized_data.get("publications", [])


# -------------------------------------------------------
# Group normalized records by title/year
#
# This lets us find records whose DOI changed during
# normalization.
# -------------------------------------------------------

normalized_title_year = defaultdict(list)

for pub in normalized:

    title = normalize_text(
        pub.get("normalized_title") or pub.get("title")
    )

    year = clean(pub.get("year"))

    normalized_title_year[(title, year)].append(pub)


# -------------------------------------------------------
# Raw unique groups
# -------------------------------------------------------

raw_groups = defaultdict(list)

for pub in raw:
    raw_groups[key(pub)].append(pub)


# -------------------------------------------------------
# Find raw groups whose exact key disappeared
# -------------------------------------------------------

missing = []

for raw_key, records in raw_groups.items():

    if raw_key not in {
        key(pub)
        for pub in normalized
    }:

        missing.append((raw_key, records))


# -------------------------------------------------------
# Determine whether each missing group still exists
# by title/year.
# -------------------------------------------------------

print()
print("=" * 70)
print("KEY RECONCILIATION")
print("=" * 70)

print(f"Raw publication objects:       {len(raw)}")
print(f"Raw unique identity groups:    {len(raw_groups)}")
print(f"Normalized publications:       {len(normalized)}")
print(f"Raw groups with changed keys:  {len(missing)}")


changed = []
truly_missing = []


for raw_key, records in missing:

    # All records in this raw group should have the same
    # title/year for our purposes.
    first = records[0]

    title = normalize_text(
        first.get("normalized_title") or first.get("title")
    )

    year = clean(first.get("year"))

    candidates = normalized_title_year.get(
        (title, year),
        []
    )

    if candidates:

        changed.append(
            (raw_key, records, candidates)
        )

    else:

        truly_missing.append(
            (raw_key, records)
        )


# -------------------------------------------------------
# Print changed keys
# -------------------------------------------------------

print()
print("=" * 70)
print("RAW GROUPS THAT STILL EXIST BUT CHANGED IDENTITY KEY")
print("=" * 70)

print(f"Count: {len(changed)}")


for number, (old_key, raw_records, candidates) in enumerate(
    changed,
    start=1
):

    print()
    print(f"{number}. OLD KEY:")
    print(f"   {old_key}")

    print("   RAW RECORD:")

    for record in raw_records:

        print(
            f"      {short(record)}"
        )

        print(
            f"      Faculty: "
            f"{record.get('_faculty_name')}"
        )

        print(
            f"      DM ID: "
            f"{record.get('dm_record_id')}"
        )

    print("   NORMALIZED MATCH:")

    for candidate in candidates:

        print(
            f"      {short(candidate)}"
        )

        print(
            f"      Publication ID: "
            f"{candidate.get('publication_id')}"
        )

        print(
            f"      DM IDs: "
            f"{candidate.get('dm_record_ids')}"
        )


# -------------------------------------------------------
# Print genuinely missing groups
# -------------------------------------------------------

print()
print("=" * 70)
print("TRULY MISSING GROUPS")
print("=" * 70)

print(f"Count: {len(truly_missing)}")


for number, (old_key, records) in enumerate(
    truly_missing,
    start=1
):

    print()
    print(f"{number}. {old_key}")

    for record in records:

        print(
            f"   {short(record)}"
        )

        print(
            f"   Faculty: "
            f"{record.get('_faculty_name')}"
        )

        print(
            f"   DM ID: "
            f"{record.get('dm_record_id')}"
        )


# -------------------------------------------------------
# Final conclusion
# -------------------------------------------------------

print()
print("=" * 70)
print("CONCLUSION")
print("=" * 70)

if len(truly_missing) == 0:

    print(
        "GOOD: Every raw identity group still exists "
        "in the normalized data."
    )

    print(
        "The 459 -> 455 difference is caused by "
        "identity-key changes/grouping, not lost papers."
    )

else:

    print(
        "WARNING: Some raw identity groups are genuinely "
        "absent from the normalized data."
    )

    print(
        f"Genuinely missing groups: "
        f"{len(truly_missing)}"
    )