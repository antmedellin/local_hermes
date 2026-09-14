#!/usr/bin/env python3

"""
Validate the UTRGV MAIE enriched faculty dataset.

This script is READ-ONLY.
It does NOT modify PostgreSQL or LightRAG.

It checks:
- faculty counts
- publication counts
- duplicate publications
- missing metadata
- recoverable DOIs
- suspicious URLs
- missing abstracts/full text
- faculty with no publications
- author/faculty ID consistency
- placeholder profile records
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
LEDGER_DIR = SCRIPT_DIR.parent
DATA_DIR = LEDGER_DIR / "data"

INPUT_FILE = DATA_DIR / "maie_faculty_enriched.json"
REPORT_FILE = DATA_DIR / "maie_validation_report.json"


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def clean(value):
    """Convert a value to a normalized string."""
    if value is None:
        return ""

    return str(value).strip()


def normalize_title(title):
    """
    Normalize a publication title so that small differences
    in capitalization/punctuation do not prevent duplicate
    detection.
    """
    title = clean(title).lower()

    # Remove punctuation.
    title = re.sub(r"[^a-z0-9]+", " ", title)

    # Collapse whitespace.
    title = re.sub(r"\s+", " ", title)

    return title.strip()


def extract_year(publication):
    """Return publication year as an integer when possible."""
    value = publication.get("year")

    if value is None:
        return None

    match = re.search(r"\b(19|20)\d{2}\b", str(value))

    if match:
        return int(match.group(0))

    return None


def normalize_doi(value):
    """
    Extract and normalize a DOI from a field.

    Examples:
        DOI: 10.1234/example
        https://doi.org/10.1234/example
    """

    if not value:
        return None

    text = str(value).strip()

    # Look for DOI pattern.
    match = re.search(
        r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    doi = match.group(0).rstrip(".,;")

    return doi.lower()


def looks_like_url(value):
    """Check whether a value appears to be a real HTTP(S) URL."""

    if not value:
        return False

    value = str(value).strip()

    try:
        parsed = urlparse(value)

        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
        )

    except Exception:
        return False


def is_probably_bad_url(value):
    """
    Detect values that are stored in the URL field but clearly
    aren't URLs.
    """

    if not value:
        return False

    value = str(value).strip()

    if looks_like_url(value):
        return False

    return True


def has_real_content(value):
    """Return True if a field contains meaningful content."""
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, list):
        return len(value) > 0

    if isinstance(value, dict):
        return len(value) > 0

    return True


# ---------------------------------------------------------
# Load dataset
# ---------------------------------------------------------

print("=" * 70)
print("UTRGV MAIE DATA VALIDATION")
print("=" * 70)

print()
print(f"Input: {INPUT_FILE}")

if not INPUT_FILE.exists():
    print()
    print("ERROR: Input file does not exist.")
    print(f"Expected: {INPUT_FILE}")
    print()
    sys.exit(1)


with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)


# ---------------------------------------------------------
# Basic structure
# ---------------------------------------------------------

faculty_list = data.get("faculty", [])

metadata = data.get("metadata", {})

print()
print("BASIC DATASET")
print("-" * 70)

print(f"Faculty records:              {len(faculty_list)}")
print(f"Metadata publication count:   {metadata.get('publication_count')}")


# ---------------------------------------------------------
# Faculty validation
# ---------------------------------------------------------

faculty_ids = {}
faculty_names = {}

faculty_with_no_publications = []
faculty_missing_research = []

for faculty_record in faculty_list:

    faculty = faculty_record.get("faculty", {})
    publications = faculty_record.get("publications", [])

    faculty_id = clean(faculty.get("user_id"))
    name = clean(faculty.get("full_name"))

    if faculty_id:
        faculty_ids[faculty_id] = name

    if name:
        faculty_names[name.lower()] = faculty_id

    if len(publications) == 0:
        faculty_with_no_publications.append(name)

    if not has_real_content(faculty.get("research_interests")):
        structured = faculty.get("structured_research_interests")

        if not has_real_content(structured):
            faculty_missing_research.append(name)


# ---------------------------------------------------------
# Flatten publications
# ---------------------------------------------------------

all_publications = []

for faculty_record in faculty_list:

    faculty = faculty_record.get("faculty", {})

    faculty_name = clean(faculty.get("full_name"))
    faculty_id = clean(faculty.get("user_id"))

    for publication in faculty_record.get("publications", []):

        # Make a copy so we don't modify the source data.
        pub = dict(publication)

        # Keep track of which faculty record contained it.
        pub["_ledger_faculty_name"] = faculty_name
        pub["_ledger_faculty_id"] = faculty_id

        all_publications.append(pub)


print()
print("PUBLICATION COUNTS")
print("-" * 70)

print(f"Publication objects found:    {len(all_publications)}")
print(f"Metadata says:                {metadata.get('publication_count')}")

if metadata.get("publication_count") != len(all_publications):
    print()
    print("WARNING:")
    print("The metadata publication count does not match the")
    print("number of publication objects found in faculty arrays.")


# ---------------------------------------------------------
# Publication duplicate analysis
# ---------------------------------------------------------

doi_groups = defaultdict(list)
title_year_groups = defaultdict(list)

for index, publication in enumerate(all_publications):

    doi = normalize_doi(publication.get("doi"))

    # Also search common fields for DOI values.
    if not doi:
        for field in ("isbn_issn", "url", "full_text"):
            doi = normalize_doi(publication.get(field))

            if doi:
                break

    if doi:
        doi_groups[doi].append(index)

    title = normalize_title(publication.get("title"))
    year = extract_year(publication)

    if title and year:
        title_year_groups[(title, year)].append(index)


duplicate_doi_groups = {
    doi: indexes
    for doi, indexes in doi_groups.items()
    if len(indexes) > 1
}

duplicate_title_year_groups = {
    key: indexes
    for key, indexes in title_year_groups.items()
    if len(indexes) > 1
}


print()
print("DUPLICATES")
print("-" * 70)

print(f"Unique DOI values:             {len(doi_groups)}")
print(f"DOI duplicate groups:          {len(duplicate_doi_groups)}")
print(f"Title/year duplicate groups:  {len(duplicate_title_year_groups)}")


# ---------------------------------------------------------
# Metadata completeness
# ---------------------------------------------------------

publication_fields = [
    "title",
    "year",
    "type",
    "status",
    "refereed",
    "publisher",
    "volume",
    "issue",
    "pages",
    "url",
    "isbn_issn",
    "pmcid",
    "doi",
    "abstract",
    "full_text",
    "impact",
    "authors",
]

field_counts = {}

for field in publication_fields:

    present = sum(
        1
        for publication in all_publications
        if has_real_content(publication.get(field))
    )

    missing = len(all_publications) - present

    field_counts[field] = {
        "present": present,
        "missing": missing,
        "percent_present": round(
            (present / len(all_publications) * 100)
            if all_publications
            else 0,
            1,
        ),
    }


print()
print("PUBLICATION METADATA COMPLETENESS")
print("-" * 70)

for field in publication_fields:

    stats = field_counts[field]

    print(
        f"{field:15} "
        f"{stats['present']:4}/{len(all_publications):4} "
        f"present "
        f"({stats['percent_present']:5.1f}%)"
    )


# ---------------------------------------------------------
# Recoverable DOI analysis
# ---------------------------------------------------------

recoverable_dois = []

for index, publication in enumerate(all_publications):

    # Only count these if the normal DOI field is missing.
    if normalize_doi(publication.get("doi")):
        continue

    recovered_from = None
    recovered_doi = None

    for field in ("isbn_issn", "url", "full_text"):

        candidate = normalize_doi(publication.get(field))

        if candidate:
            recovered_doi = candidate
            recovered_from = field
            break

    if recovered_doi:

        recoverable_dois.append({
            "index": index,
            "title": publication.get("title"),
            "year": extract_year(publication),
            "doi": recovered_doi,
            "source_field": recovered_from,
        })


print()
print("RECOVERABLE DOIS")
print("-" * 70)

print(
    f"DOIs recoverable from other fields: "
    f"{len(recoverable_dois)}"
)


# ---------------------------------------------------------
# URL validation
# ---------------------------------------------------------

bad_urls = []

for index, publication in enumerate(all_publications):

    value = publication.get("url")

    if value and is_probably_bad_url(value):

        bad_urls.append({
            "index": index,
            "title": publication.get("title"),
            "url": value,
        })


print()
print("URL VALIDATION")
print("-" * 70)

print(f"Non-empty URL fields:          {sum(1 for p in all_publications if p.get('url'))}")
print(f"Suspicious/non-URL values:     {len(bad_urls)}")


# ---------------------------------------------------------
# Abstract analysis
# ---------------------------------------------------------

missing_abstracts = []

for index, publication in enumerate(all_publications):

    if not has_real_content(publication.get("abstract")):

        missing_abstracts.append({
            "index": index,
            "title": publication.get("title"),
            "year": extract_year(publication),
            "faculty": publication.get("_ledger_faculty_name"),
        })


print()
print("ABSTRACTS")
print("-" * 70)

print(f"Missing abstracts:             {len(missing_abstracts)}")
print(
    f"Abstract coverage:             "
    f"{round((1 - len(missing_abstracts) / len(all_publications)) * 100, 1) if all_publications else 0}%"
)


# ---------------------------------------------------------
# Full-text analysis
# ---------------------------------------------------------

missing_full_text = []

for index, publication in enumerate(all_publications):

    if not has_real_content(publication.get("full_text")):

        missing_full_text.append({
            "index": index,
            "title": publication.get("title"),
            "year": extract_year(publication),
        })


print()
print("FULL TEXT")
print("-" * 70)

print(f"Missing full-text values:      {len(missing_full_text)}")


# ---------------------------------------------------------
# Status distribution
# ---------------------------------------------------------

status_counter = Counter()

for publication in all_publications:

    status = clean(publication.get("status"))

    if not status:
        status = "UNKNOWN"

    status_counter[status] += 1


print()
print("PUBLICATION STATUS")
print("-" * 70)

for status, count in status_counter.most_common():

    print(f"{status:40} {count}")


# ---------------------------------------------------------
# Publication type distribution
# ---------------------------------------------------------

type_counter = Counter()

for publication in all_publications:

    pub_type = clean(publication.get("type"))

    if not pub_type:
        pub_type = "UNKNOWN"

    type_counter[pub_type] += 1


print()
print("PUBLICATION TYPES")
print("-" * 70)

for pub_type, count in type_counter.most_common():

    print(f"{pub_type:40} {count}")


# ---------------------------------------------------------
# Author validation
# ---------------------------------------------------------

total_authors = 0
faculty_author_entries = 0

unknown_faculty_ids = Counter()
faculty_author_names = Counter()

suspicious_faculty_author_entries = []

for publication_index, publication in enumerate(all_publications):

    authors = publication.get("authors", [])

    if not isinstance(authors, list):
        continue

    for author in authors:

        if not isinstance(author, dict):
            continue

        total_authors += 1

        author_name = clean(author.get("name"))
        faculty_id = clean(author.get("faculty_id"))

        if faculty_id:

            if faculty_id in faculty_ids:

                faculty_author_entries += 1
                faculty_author_names[author_name] += 1

            else:

                unknown_faculty_ids[faculty_id] += 1

        # Detect suspicious cases where the source claims an MAIE
        # faculty relationship but the author's name differs greatly
        # from the current faculty name.
        if faculty_id in faculty_ids:

            expected_name = faculty_ids[faculty_id]

            normalized_author = normalize_title(author_name)
            normalized_expected = normalize_title(expected_name)

            if (
                normalized_author
                and normalized_expected
                and normalized_author != normalized_expected
                and normalized_author not in normalized_expected
                and normalized_expected not in normalized_author
            ):

                suspicious_faculty_author_entries.append({
                    "publication_index": publication_index,
                    "publication_title": publication.get("title"),
                    "author_name": author_name,
                    "faculty_id": faculty_id,
                    "current_faculty_name": expected_name,
                })


print()
print("AUTHORSHIP")
print("-" * 70)

print(f"Total author entries:          {total_authors}")
print(f"MAIE faculty ID matches:       {faculty_author_entries}")
print(f"Unknown faculty IDs:           {len(unknown_faculty_ids)}")
print(
    f"Suspicious faculty/name pairs: "
    f"{len(suspicious_faculty_author_entries)}"
)


# ---------------------------------------------------------
# Profile field completeness
# ---------------------------------------------------------

profile_fields = [
    "bio",
    "building",
    "campus",
    "email",
    "first_name",
    "full_name",
    "last_name",
    "middle_name",
    "phone",
    "photo",
    "prefix",
    "research_interests",
    "room",
    "structured_research_interests",
    "vita_available",
]

profile_counts = {}

for field in profile_fields:

    present = 0

    for faculty_record in faculty_list:

        faculty = faculty_record.get("faculty", {})

        if has_real_content(faculty.get(field)):
            present += 1

    profile_counts[field] = {
        "present": present,
        "missing": len(faculty_list) - present,
    }


print()
print("FACULTY PROFILE COMPLETENESS")
print("-" * 70)

for field in profile_fields:

    stats = profile_counts[field]

    print(
        f"{field:30} "
        f"{stats['present']:2}/{len(faculty_list):2} "
        f"present"
    )


# ---------------------------------------------------------
# Suspicious placeholder profile records
# ---------------------------------------------------------

placeholder_education = 0
placeholder_positions = 0
placeholder_awards = 0

for faculty_record in faculty_list:

    for education in faculty_record.get("education", []):

        if isinstance(education, dict):

            if not any(has_real_content(v) for v in education.values()):
                placeholder_education += 1

    for position in faculty_record.get("previous_positions", []):

        if isinstance(position, dict):

            if not any(has_real_content(v) for v in position.values()):
                placeholder_positions += 1

    for award in faculty_record.get("awards", []):

        if isinstance(award, dict):

            if not any(has_real_content(v) for v in award.values()):
                placeholder_awards += 1


print()
print("PLACEHOLDER PROFILE RECORDS")
print("-" * 70)

print(f"Empty education records:       {placeholder_education}")
print(f"Empty position records:        {placeholder_positions}")
print(f"Empty award records:            {placeholder_awards}")


# ---------------------------------------------------------
# Faculty publication summary
# ---------------------------------------------------------

faculty_publication_counts = []

for faculty_record in faculty_list:

    faculty = faculty_record.get("faculty", {})

    faculty_publication_counts.append({
        "name": faculty.get("full_name"),
        "user_id": faculty.get("user_id"),
        "publication_count": len(
            faculty_record.get("publications", [])
        ),
    })


faculty_publication_counts.sort(
    key=lambda x: x["publication_count"],
    reverse=True,
)


print()
print("PUBLICATIONS BY FACULTY")
print("-" * 70)

for item in faculty_publication_counts:

    name = item.get("name") or "UNKNOWN FACULTY"

    print(
        f"{'name':35} "
        f"{'publication_count':4}"
    )


# ---------------------------------------------------------
# Build report
# ---------------------------------------------------------

report = {
    "input_file": str(INPUT_FILE),
    "metadata": metadata,

    "summary": {
        "faculty_count": len(faculty_list),
        "publication_objects": len(all_publications),
        "metadata_publication_count": metadata.get(
            "publication_count"
        ),
        "publication_count_mismatch": (
            metadata.get("publication_count")
            != len(all_publications)
        ),
        "unique_doi_values": len(doi_groups),
        "doi_duplicate_groups": len(
            duplicate_doi_groups
        ),
        "title_year_duplicate_groups": len(
            duplicate_title_year_groups
        ),
        "recoverable_dois": len(
            recoverable_dois
        ),
        "bad_urls": len(bad_urls),
        "missing_abstracts": len(
            missing_abstracts
        ),
        "missing_full_text": len(
            missing_full_text
        ),
        "faculty_with_no_publications": len(
            faculty_with_no_publications
        ),
        "faculty_missing_research": len(
            faculty_missing_research
        ),
        "total_authors": total_authors,
        "maie_faculty_author_entries": faculty_author_entries,
        "suspicious_faculty_author_entries": len(
            suspicious_faculty_author_entries
        ),
    },

    "faculty_with_no_publications":
        faculty_with_no_publications,

    "faculty_missing_research":
        faculty_missing_research,

    "faculty_publication_counts":
        faculty_publication_counts,

    "publication_field_completeness":
        field_counts,

    "profile_field_completeness":
        profile_counts,

    "status_distribution":
        dict(status_counter),

    "publication_type_distribution":
        dict(type_counter),

    "recoverable_dois":
        recoverable_dois,

    "bad_urls":
        bad_urls,

    "missing_abstracts":
        missing_abstracts,

    "missing_full_text":
        missing_full_text,

    "duplicate_doi_groups": {
        doi: indexes
        for doi, indexes in duplicate_doi_groups.items()
    },

    "duplicate_title_year_groups": {
        f"{title}|{year}": indexes
        for (title, year), indexes
        in duplicate_title_year_groups.items()
    },

    "unknown_faculty_ids":
        dict(unknown_faculty_ids),

    "suspicious_faculty_author_entries":
        suspicious_faculty_author_entries,

    "placeholder_records": {
        "education": placeholder_education,
        "previous_positions": placeholder_positions,
        "awards": placeholder_awards,
    },
}


# ---------------------------------------------------------
# Save report
# ---------------------------------------------------------

with open(REPORT_FILE, "w", encoding="utf-8") as f:

    json.dump(
        report,
        f,
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------
# Final summary
# ---------------------------------------------------------

print()
print("=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)

print()
print(f"Faculty:                       {len(faculty_list)}")
print(f"Publication objects:           {len(all_publications)}")
print(f"Recoverable DOIs:              {len(recoverable_dois)}")
print(f"Suspicious URLs:               {len(bad_urls)}")
print(f"Missing abstracts:             {len(missing_abstracts)}")
print(f"Missing full text:              {len(missing_full_text)}")
print(f"Duplicate DOI groups:          {len(duplicate_doi_groups)}")
print(f"Duplicate title/year groups:   {len(duplicate_title_year_groups)}")
print(
    f"Suspicious authorship entries: "
    f"{len(suspicious_faculty_author_entries)}"
)

print()
print(f"Report written to:")
print(REPORT_FILE)

print()
print("IMPORTANT: No PostgreSQL or LightRAG data was modified.")
print("=" * 70)