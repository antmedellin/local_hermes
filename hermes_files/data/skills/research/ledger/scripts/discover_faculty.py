#!/usr/bin/env python3

"""
MAIE Faculty Discovery

Purpose:
    Retrieve the faculty/researcher records used by the official
    UTRGV MAIE Faculty Directory.

Source:
    UTRGV Digital Measures Faculty Directory API

This script is READ-ONLY with respect to PostgreSQL.
It does not create or modify database records.

Output:
    ledger/data/maie_faculty.json
"""

import json
import urllib.request
from pathlib import Path


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

API_URL = (
    "https://webapps.utrgv.edu/aa/dm/api/DMUser/GetDMList"
)

TARGET_DEPARTMENT = (
    "Department of Manufacturing and Industrial Engineering"
)

OUTPUT_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "maie_faculty.json"
)


# ------------------------------------------------------------
# Download the official faculty directory data
# ------------------------------------------------------------

def fetch_faculty_data():
    """
    Download the faculty directory data from UTRGV.

    The API returns JSON encoded inside a JSON string,
    so we may need to decode it twice.
    """

    request = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )

    print("Downloading UTRGV faculty directory...")

    with urllib.request.urlopen(request, timeout=30) as response:
        raw_data = response.read().decode(
            "utf-8",
            errors="replace"
        )

    # First JSON decoding.
    data = json.loads(raw_data)

    # The API currently returns a JSON string containing JSON.
    if isinstance(data, str):
        data = json.loads(data)

    return data


# ------------------------------------------------------------
# Extract a value from the IndexEntry records
# ------------------------------------------------------------

def get_index_value(entries, index_key):
    """
    Find an index entry such as DEPARTMENT or RANK.
    """

    if not isinstance(entries, list):
        return ""

    for entry in entries:

        if not isinstance(entry, dict):
            continue

        if entry.get("@indexKey") == index_key:
            return entry.get("@text", "") or ""

    return ""


# ------------------------------------------------------------
# Build a person's full name
# ------------------------------------------------------------

def build_name(pci):
    """
    Build the faculty member's name from the PCI fields.
    """

    if not isinstance(pci, dict):
        return ""

    parts = [
        pci.get("PREFIX"),
        pci.get("FNAME"),
        pci.get("MNAME"),
        pci.get("LNAME"),
        pci.get("SUFFIX"),
    ]

    # Remove empty values.
    parts = [
        str(part).strip()
        for part in parts
        if part
    ]

    return " ".join(parts)


# ------------------------------------------------------------
# Extract MAIE faculty
# ------------------------------------------------------------

def extract_maie_faculty(data):
    """
    Extract everyone belonging to the MAIE department.

    We intentionally keep all records returned for the
    department, including lecturers and professors of practice.

    The official MAIE Faculty Directory is our authority for
    who belongs in this initial roster.
    """

    records = data.get("Data", {}).get("Record", [])

    if not isinstance(records, list):
        raise ValueError(
            "Unexpected API format: Data.Record is not a list."
        )

    faculty = []

    for record in records:

        if not isinstance(record, dict):
            continue

        entries = record.get("dmd:IndexEntry", [])

        department = get_index_value(
            entries,
            "DEPARTMENT"
        )

        # Exact department match.
        if department != TARGET_DEPARTMENT:
            continue

        pci = record.get("PCI", {})

        name = build_name(pci)

        if not name:
            continue

        rank = get_index_value(
            entries,
            "RANK"
        )

        faculty_member = {
            "name": name,
            "rank": rank,
            "department": department,
            "username": record.get("@username"),
            "user_id": record.get("@userId"),
        }

        faculty.append(faculty_member)

    # Keep the output deterministic.
    faculty.sort(
        key=lambda person: person["name"].lower()
    )

    return faculty


# ------------------------------------------------------------
# Save the roster
# ------------------------------------------------------------

def save_faculty(faculty):
    """
    Save the MAIE faculty roster as formatted JSON.
    """

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            faculty,
            file,
            indent=2,
            ensure_ascii=False
        )

        file.write("\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    print("=" * 60)
    print("UTRGV MAIE FACULTY DISCOVERY")
    print("=" * 60)
    print()

    print("Source:")
    print(API_URL)
    print()

    # Download API data.
    data = fetch_faculty_data()

    # Extract MAIE faculty.
    faculty = extract_maie_faculty(data)

    print()
    print("=" * 60)
    print("MAIE FACULTY FOUND")
    print("=" * 60)
    print()

    for number, person in enumerate(faculty, start=1):

        print(
            f"{number:2}. "
            f"{person['name']}"
        )

        print(
            f"    Rank:     {person['rank']}"
        )

        print(
            f"    Username: {person['username']}"
        )

        print()

    # Save JSON.
    save_faculty(faculty)

    print("=" * 60)
    print(f"TOTAL FACULTY: {len(faculty)}")
    print("=" * 60)
    print()

    print("Saved to:")
    print(OUTPUT_FILE)
    print()

    print("READ-ONLY:")
    print("No PostgreSQL records were created or modified.")


if __name__ == "__main__":
    main()