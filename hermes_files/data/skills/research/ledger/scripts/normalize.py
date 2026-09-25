#!/usr/bin/env python3

"""
Normalize UTRGV MAIE Digital Measures data.

INPUT:
    data/maie_faculty_enriched.json

OUTPUT:
    data/maie_faculty_normalized.json

This script is READ-ONLY with respect to the source data.
It does NOT modify PostgreSQL or LightRAG.

Goals:
    - Deduplicate publications
    - Recover DOIs from other fields
    - Clean suspicious URLs
    - Normalize author names
    - Preserve Digital Measures provenance
    - Remove empty profile records
    - Preserve missing values as null
    - Generate data-quality flags
"""

import json
import re
import hashlib
from pathlib import Path
from collections import defaultdict


# ------------------------------------------------------------
# PATHS
# ------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
LEDGER_DIR = SCRIPT_DIR.parent

DATA_DIR = LEDGER_DIR / "data"

INPUT_FILE = DATA_DIR / "maie_faculty_enriched.json"
OUTPUT_FILE = DATA_DIR / "maie_faculty_normalized.json"


# ------------------------------------------------------------
# GENERAL HELPERS
# ------------------------------------------------------------

def clean_string(value):
    """Return a stripped string or None."""
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    value = value.strip()

    return value if value else None


def normalize_whitespace(value):
    """Collapse repeated whitespace."""
    value = clean_string(value)

    if value is None:
        return None

    return re.sub(r"\s+", " ", value)


def normalize_title(title):
    """
    Normalize a publication title for duplicate detection.

    This does NOT replace the original title.
    It is only used as a comparison key.
    """
    title = normalize_whitespace(title)

    if not title:
        return None

    title = title.lower()

    # Normalize common punctuation.
    title = re.sub(r"[“”\"'`]", "", title)
    title = re.sub(r"[^a-z0-9\s]", " ", title)
    title = re.sub(r"\s+", " ", title)

    return title.strip()


def normalize_name(name):
    """
    Normalize an author name for comparison.

    Original name is always preserved separately.
    """
    name = normalize_whitespace(name)

    if not name:
        return None

    name = name.lower()

    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def normalize_doi(value):
    """
    Extract and normalize a DOI.

    Accepts values such as:
        10.1234/example
        https://doi.org/10.1234/example
        DOI: https://doi.org/10.1234/example
    """
    value = clean_string(value)

    if not value:
        return None

    # Remove common prefixes.
    value = re.sub(
        r"^\s*(doi\s*:?\s*)",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # Search for DOI pattern.
    match = re.search(
        r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
        value,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    doi = match.group(1).strip()

    # Remove trailing punctuation commonly attached to DOI text.
    doi = doi.rstrip(".,;")

    return doi.lower()


def is_valid_url(value):
    """Return True only for actual HTTP/HTTPS URLs."""
    value = clean_string(value)

    if not value:
        return False

    return bool(
        re.match(
            r"^https?://",
            value,
            flags=re.IGNORECASE,
        )
    )


def clean_url(value):
    """
    Keep legitimate HTTP/HTTPS URLs.

    Suspicious non-URL values are returned as None.
    """
    value = clean_string(value)

    if not value:
        return None

    if is_valid_url(value):
        return value

    return None


def make_publication_key(publication):
    """
    Create the strongest available deduplication key.

    Priority:
        1. DOI
        2. normalized title + year
        3. normalized title alone

    The last fallback is intentionally weaker and marked as such.
    """
    doi = normalize_doi(publication.get("doi"))

    if doi:
        return ("doi", doi)

    title = normalize_title(publication.get("title"))
    year = publication.get("year")

    if title and year:
        return ("title_year", title, str(year))

    if title:
        return ("title", title)

    # Extremely unlikely because validation showed all titles present.
    raw = json.dumps(
        publication,
        sort_keys=True,
        default=str,
    )

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return ("raw", digest)


# ------------------------------------------------------------
# DOI RECOVERY
# ------------------------------------------------------------

def recover_doi(publication):
    """
    Attempt DOI recovery from fields other than 'doi'.

    Returns:
        doi,
        source_field
    """
    direct = normalize_doi(publication.get("doi"))

    if direct:
        return direct, "doi"

    # Check URL.
    url = publication.get("url")

    recovered = normalize_doi(url)

    if recovered:
        return recovered, "url"

    # Check ISBN/ISSN field.
    isbn_issn = publication.get("isbn_issn")

    recovered = normalize_doi(isbn_issn)

    if recovered:
        return recovered, "isbn_issn"

    # Check full text path or other string fields as a last resort.
    full_text = publication.get("full_text")

    recovered = normalize_doi(full_text)

    if recovered:
        return recovered, "full_text"

    return None, None


# ------------------------------------------------------------
# AUTHOR NORMALIZATION
# ------------------------------------------------------------

def normalize_author(author):
    """Normalize one author record while preserving original values."""

    original_name = clean_string(author.get("name"))

    first_name = normalize_whitespace(author.get("first_name"))
    middle_name = normalize_whitespace(author.get("middle_name"))
    last_name = normalize_whitespace(author.get("last_name"))

    normalized_name = normalize_name(original_name)

    return {
        "position": author.get("position"),
        "name": original_name,
        "normalized_name": normalized_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "faculty_id": clean_string(author.get("faculty_id")),
        "institution": normalize_whitespace(
            author.get("institution")
        ),
        "student_level": normalize_whitespace(
            author.get("student_level")
        ),
        "is_maie_faculty": bool(
            author.get("is_maie_faculty", False)
        ),
    }


# ------------------------------------------------------------
# EMPTY RECORD FILTERING
# ------------------------------------------------------------

def has_any_value(record):
    """
    Return True if a record contains meaningful information.

    Handles dictionaries containing only null/empty values.
    """
    if not isinstance(record, dict):
        return bool(record)

    for value in record.values():

        if isinstance(value, dict):
            if has_any_value(value):
                return True

        elif isinstance(value, list):
            if value:
                return True

        elif value not in (None, "", [], {}):
            return True

    return False


def clean_record_list(records):
    """Remove completely empty records."""
    if not isinstance(records, list):
        return []

    return [
        record
        for record in records
        if has_any_value(record)
    ]


# ------------------------------------------------------------
# PUBLICATION MERGING
# ------------------------------------------------------------

def merge_nonempty(existing, incoming):
    """
    Merge missing values from incoming into existing.

    Existing non-null values are preferred.
    """
    for key, value in incoming.items():

        if key not in existing:
            existing[key] = value
            continue

        current = existing[key]

        if current in (None, "", [], {}):
            if value not in (None, "", [], {}):
                existing[key] = value

    return existing


def merge_lists(existing, incoming):
    """Merge lists while avoiding exact duplicate JSON objects."""

    if not isinstance(existing, list):
        existing = []

    if not isinstance(incoming, list):
        incoming = []

    combined = list(existing)

    for item in incoming:

        if item not in combined:
            combined.append(item)

    return combined


def merge_publications(existing, incoming):
    """
    Merge duplicate publication records.

    We preserve:
        - original publication data
        - all source records
        - all Digital Measures IDs
        - all authors
        - all dates

    We prefer non-empty metadata when duplicates disagree.
    """

    # Preserve the strongest existing scalar values.
    scalar_fields = [
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
        "dm_record_id",
    ]

    for field in scalar_fields:

        old = existing.get(field)
        new = incoming.get(field)

        if old in (None, "") and new not in (None, ""):
            existing[field] = new

    # Dates.
    if isinstance(existing.get("dates"), dict) and isinstance(
        incoming.get("dates"), dict
    ):
        for field, value in incoming["dates"].items():

            if (
                existing["dates"].get(field) in (None, "")
                and value not in (None, "")
            ):
                existing["dates"][field] = value

    # Authors.
    existing["authors"] = merge_lists(
        existing.get("authors", []),
        incoming.get("authors", []),
    )

    # Source records.
    existing["sources"] = merge_lists(
        existing.get("sources", []),
        incoming.get("sources", []),
    )

    # Digital Measures record IDs.
    existing["dm_record_ids"] = merge_lists(
        existing.get("dm_record_ids", []),
        incoming.get("dm_record_ids", []),
    )

    return existing


# ------------------------------------------------------------
# PUBLICATION NORMALIZATION
# ------------------------------------------------------------

def normalize_publication(publication):
    """Normalize one publication."""

    title = normalize_whitespace(
        publication.get("title")
    )

    normalized_title = normalize_title(title)

    year = publication.get("year")

    # Normalize year if it arrived as a string.
    if isinstance(year, str):
        year = year.strip()

        try:
            year = int(year)
        except ValueError:
            pass

    doi, doi_source = recover_doi(publication)

    original_doi = clean_string(
        publication.get("doi")
    )

    url = clean_url(
        publication.get("url")
    )

    original_url = clean_string(
        publication.get("url")
    )

    suspicious_url = (
        original_url is not None
        and url is None
    )

    authors = [
        normalize_author(author)
        for author in publication.get("authors", [])
        if isinstance(author, dict)
    ]

    dates = publication.get("dates")

    if not isinstance(dates, dict):
        dates = {}

    normalized = {
        "title": title,
        "normalized_title": normalized_title,
        "year": year,

        "type": normalize_whitespace(
            publication.get("type")
        ),

        "status": normalize_whitespace(
            publication.get("status")
        ),

        "refereed": normalize_whitespace(
            publication.get("refereed")
        ),

        "publisher": normalize_whitespace(
            publication.get("publisher")
        ),

        "volume": normalize_whitespace(
            publication.get("volume")
        ),

        "issue": normalize_whitespace(
            publication.get("issue")
        ),

        "pages": normalize_whitespace(
            publication.get("pages")
        ),

        "url": url,

        "isbn_issn": normalize_whitespace(
            publication.get("isbn_issn")
        ),

        "pmcid": normalize_whitespace(
            publication.get("pmcid")
        ),

        "doi": doi,

        "abstract": normalize_whitespace(
            publication.get("abstract")
        ),

        "full_text": normalize_whitespace(
            publication.get("full_text")
        ),

        "impact": normalize_whitespace(
            publication.get("impact")
        ),

        "authors": authors,

        "dates": {
            "submitted": normalize_whitespace(
                dates.get("submitted")
            ),
            "accepted": normalize_whitespace(
                dates.get("accepted")
            ),
            "published": normalize_whitespace(
                dates.get("published")
            ),
        },

        "dm_record_id": clean_string(
            publication.get("dm_record_id")
        ),

        "sources": publication.get(
            "sources",
            []
        ),

        "dm_record_ids": [
            clean_string(value)
            for value in publication.get(
                "dm_record_ids",
                []
            )
            if clean_string(value)
        ],

        "quality": {
            "doi_status": (
                "original"
                if original_doi and doi
                else (
                    "recovered"
                    if doi
                    else "missing"
                )
            ),

            "doi_source": doi_source,

            "url_status": (
                "valid"
                if url
                else (
                    "suspicious"
                    if suspicious_url
                    else "missing"
                )
            ),

            "has_abstract": bool(
                publication.get("abstract")
            ),

            "has_full_text": bool(
                publication.get("full_text")
            ),

            "has_authors": bool(
                authors
            ),
        },

        # Preserve unusual original values so normalization
        # never destroys source information.
        "source_original": {
            "doi": original_doi,
            "url": original_url,
        },
    }

    return normalized


# ------------------------------------------------------------
# FACULTY NORMALIZATION
# ------------------------------------------------------------

def normalize_faculty_record(record):
    """Normalize one faculty member."""

    faculty = record.get("faculty", {})

    profile = faculty.get("profile", {})

    if not isinstance(profile, dict):
        profile = {}

    normalized_faculty = {
        "name": normalize_whitespace(
            faculty.get("name")
        ),

        "rank": normalize_whitespace(
            faculty.get("rank")
        ),

        "department": normalize_whitespace(
            faculty.get("department")
        ),

        "username": clean_string(
            faculty.get("username")
        ),

        "user_id": clean_string(
            faculty.get("user_id")
        ),

        "dm_user_id": clean_string(
            faculty.get("dm_user_id")
        ),

        "profile": {
            "prefix": normalize_whitespace(
                profile.get("prefix")
            ),

            "first_name": normalize_whitespace(
                profile.get("first_name")
            ),

            "middle_name": normalize_whitespace(
                profile.get("middle_name")
            ),

            "last_name": normalize_whitespace(
                profile.get("last_name")
            ),

            "full_name": normalize_whitespace(
                profile.get("full_name")
            ),

            "email": normalize_whitespace(
                profile.get("email")
            ),

            "campus": normalize_whitespace(
                profile.get("campus")
            ),

            "building": normalize_whitespace(
                profile.get("building")
            ),

            "room": normalize_whitespace(
                profile.get("room")
            ),

            "phone": profile.get(
                "phone",
                {}
            ),

            "bio": normalize_whitespace(
                profile.get("bio")
            ),

            "research_interests": normalize_whitespace(
                profile.get("research_interests")
            ),

            "structured_research_interests": (
                profile.get(
                    "structured_research_interests",
                    []
                )
                if isinstance(
                    profile.get(
                        "structured_research_interests",
                        []
                    ),
                    list
                )
                else []
            ),

            "photo": normalize_whitespace(
                profile.get("photo")
            ),

            "vita_available": normalize_whitespace(
                profile.get("vita_available")
            ),
        },

        "education": clean_record_list(
            record.get("education", [])
        ),

        "previous_positions": clean_record_list(
            record.get("previous_positions", [])
        ),

        "awards": clean_record_list(
            record.get("awards", [])
        ),
    }

    return normalized_faculty


# ------------------------------------------------------------
# MAIN NORMALIZATION
# ------------------------------------------------------------

def main():

    print("=" * 70)
    print("UTRGV MAIE DATA NORMALIZATION")
    print("=" * 70)

    print()
    print("Input:")
    print(INPUT_FILE)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file does not exist: {INPUT_FILE}"
        )

    with INPUT_FILE.open(
        "r",
        encoding="utf-8",
    ) as f:
        source = json.load(f)

    metadata = source.get(
        "metadata",
        {}
    )

    faculty_records = source.get(
        "faculty",
        []
    )

    print()
    print("SOURCE DATA")
    print("-" * 70)

    print(
        f"Faculty records:        {len(faculty_records)}"
    )

    source_publication_count = sum(
        len(record.get("publications", []))
        for record in faculty_records
    )

    print(
        f"Publication objects:    {source_publication_count}"
    )

    # --------------------------------------------------------
    # Faculty IDs
    # --------------------------------------------------------

    faculty_id_map = {}

    for record in faculty_records:

        faculty = record.get(
            "faculty",
            {}
        )

        faculty_id = clean_string(
            faculty.get("user_id")
        )

        name = normalize_whitespace(
            faculty.get("name")
        )

        if faculty_id:
            faculty_id_map[faculty_id] = name

    # --------------------------------------------------------
    # Normalize and deduplicate publications
    # --------------------------------------------------------

    publications_by_key = {}

    # Track which faculty members are associated with
    # each publication.
    publication_faculty = defaultdict(set)

    duplicate_doi_count = 0
    duplicate_title_year_count = 0

    normalized_faculty = []

    for record in faculty_records:

        faculty = normalize_faculty_record(
            record
        )

        faculty_id = faculty.get(
            "user_id"
        )

        faculty_name = faculty.get(
            "name"
        )

        faculty_publication_keys = []

        for raw_publication in record.get(
            "publications",
            []
        ):

            normalized = normalize_publication(
                raw_publication
            )

            key = make_publication_key(
                normalized
            )

            if key in publications_by_key:

                existing = publications_by_key[key]

                # Count duplicate groups by key type.
                if key[0] == "doi":
                    duplicate_doi_count += 1

                elif key[0] == "title_year":
                    duplicate_title_year_count += 1

                merge_publications(
                    existing,
                    normalized,
                )

            else:

                publications_by_key[key] = normalized

            faculty_publication_keys.append(
                key
            )

            if faculty_id:
                publication_faculty[key].add(
                    faculty_id
                )

        # Store publication references rather than
        # duplicating entire publication objects.
        faculty["publication_keys"] = [
            list(key)
            for key in faculty_publication_keys
        ]

        normalized_faculty.append(
            faculty
        )

    # --------------------------------------------------------
    # Convert publication dictionary into stable IDs
    # --------------------------------------------------------

    normalized_publications = []

    key_to_publication_id = {}

    for index, (key, publication) in enumerate(
        publications_by_key.items(),
        start=1,
    ):

        publication_id = (
            f"MAIE-PUB-{index:05d}"
        )

        key_to_publication_id[key] = publication_id

        publication["publication_id"] = (
            publication_id
        )

        publication["deduplication"] = {
            "key_type": key[0],
            "key": list(key),
        }

        # Faculty associated with this publication.
        faculty_ids = sorted(
            publication_faculty.get(
                key,
                set()
            )
        )

        publication["faculty_ids"] = faculty_ids

        publication["faculty_names"] = [
            faculty_id_map.get(
                faculty_id
            )
            for faculty_id in faculty_ids
            if faculty_id in faculty_id_map
        ]

        normalized_publications.append(
            publication
        )

    # --------------------------------------------------------
    # Replace faculty publication keys with IDs
    # --------------------------------------------------------

    for faculty in normalized_faculty:

        faculty["publication_ids"] = [
            key_to_publication_id[
                tuple(key)
            ]
            for key in faculty.pop(
                "publication_keys",
                []
            )
            if tuple(key) in key_to_publication_id
        ]

    # --------------------------------------------------------
    # Authorship quality checks
    # --------------------------------------------------------

    suspicious_authorship = []

    maie_faculty_ids = set(
        faculty_id_map.keys()
    )

    for publication in normalized_publications:

        for author in publication.get(
            "authors",
            []
        ):

            faculty_id = author.get(
                "faculty_id"
            )

            author_name = author.get(
                "name"
            )

            if (
                faculty_id
                and faculty_id in maie_faculty_ids
            ):

                expected_name = faculty_id_map[
                    faculty_id
                ]

                if (
                    normalize_name(
                        author_name
                    )
                    != normalize_name(
                        expected_name
                    )
                ):

                    suspicious_authorship.append({
                        "publication_id": publication[
                            "publication_id"
                        ],
                        "publication_title": publication[
                            "title"
                        ],
                        "faculty_id": faculty_id,
                        "faculty_name": expected_name,
                        "author_name": author_name,
                    })

    # --------------------------------------------------------
    # Publication quality statistics
    # --------------------------------------------------------

    doi_count = sum(
        bool(
            publication.get("doi")
        )
        for publication in normalized_publications
    )

    recovered_doi_count = sum(
        publication.get(
            "quality",
            {}
        ).get("doi_status")
        == "recovered"
        for publication in normalized_publications
    )

    abstract_count = sum(
        bool(
            publication.get("abstract")
        )
        for publication in normalized_publications
    )

    full_text_count = sum(
        bool(
            publication.get("full_text")
        )
        for publication in normalized_publications
    )

    suspicious_url_count = sum(
        publication.get(
            "quality",
            {}
        ).get("url_status")
        == "suspicious"
        for publication in normalized_publications
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output = {
        "metadata": {
            "institution": metadata.get(
                "institution"
            ),

            "college": metadata.get(
                "college"
            ),

            "department": metadata.get(
                "department"
            ),

            "faculty_count": len(
                normalized_faculty
            ),

            "source_publication_objects": (
                source_publication_count
            ),

            "source_metadata_publication_count": (
                metadata.get(
                    "publication_count"
                )
            ),

            "normalized_unique_publications": len(
                normalized_publications
            ),

            "source": metadata.get(
                "source"
            ),

            "api_endpoint": metadata.get(
                "api_endpoint"
            ),

            "generated_at": metadata.get(
                "generated_at"
            ),
        },

        "quality_summary": {
            "duplicate_doi_records": (
                duplicate_doi_count
            ),

            "duplicate_title_year_records": (
                duplicate_title_year_count
            ),

            "doi_count": doi_count,

            "recovered_doi_count": (
                recovered_doi_count
            ),

            "abstract_count": abstract_count,

            "full_text_count": full_text_count,

            "suspicious_url_count": (
                suspicious_url_count
            ),

            "suspicious_authorship_count": (
                len(suspicious_authorship)
            ),

            "faculty_with_publications": sum(
                bool(
                    faculty.get(
                        "publication_ids"
                    )
                )
                for faculty in normalized_faculty
            ),

            "faculty_without_publications": sum(
                not bool(
                    faculty.get(
                        "publication_ids"
                    )
                )
                for faculty in normalized_faculty
            ),
        },

        "faculty": normalized_faculty,

        "publications": normalized_publications,

        "suspicious_authorship": (
            suspicious_authorship
        ),
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

    # --------------------------------------------------------
    # Console report
    # --------------------------------------------------------

    print()
    print("NORMALIZATION RESULTS")
    print("-" * 70)

    print(
        f"Faculty:                         "
        f"{len(normalized_faculty)}"
    )

    print(
        f"Source publication objects:      "
        f"{source_publication_count}"
    )

    print(
        f"Unique normalized publications:  "
        f"{len(normalized_publications)}"
    )

    print(
        f"Duplicate DOI records:           "
        f"{duplicate_doi_count}"
    )

    print(
        f"Duplicate title/year records:    "
        f"{duplicate_title_year_count}"
    )

    print(
        f"DOIs:                             "
        f"{doi_count}"
    )

    print(
        f"Recovered DOIs:                   "
        f"{recovered_doi_count}"
    )

    print(
        f"Abstracts:                        "
        f"{abstract_count}"
    )

    print(
        f"Full text:                        "
        f"{full_text_count}"
    )

    print(
        f"Suspicious URLs:                  "
        f"{suspicious_url_count}"
    )

    print(
        f"Suspicious authorship entries:    "
        f"{len(suspicious_authorship)}"
    )

    print()
    print("FACULTY PUBLICATION COUNTS")
    print("-" * 70)

    for faculty in normalized_faculty:

        name = (
            faculty.get("name")
            or "UNKNOWN FACULTY"
        )

        count = len(
            faculty.get(
                "publication_ids",
                []
            )
        )

        print(
            f"{name:35} {count:4}"
        )

    print()
    print("=" * 70)
    print("NORMALIZATION COMPLETE")
    print("=" * 70)

    print()
    print("Output:")
    print(OUTPUT_FILE)

    print()
    print(
        "IMPORTANT: PostgreSQL and LightRAG "
        "were NOT modified."
    )


if __name__ == "__main__":
    main()