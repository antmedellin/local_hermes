#!/usr/bin/env python3

"""
Enrich the faculty discovered from UTRGV's official Digital Measures API.

Input:
    data/faculty.json

Outputs:
    data/<dept>/raw/<username>.json
        Raw Digital Measures response for each faculty member.

    data/<dept>/faculty_enriched.json
        Normalized faculty + research + publication data.

This script DOES NOT modify PostgreSQL.
"""

import json
import re
import time
import urllib.parse
import urllib.request
import unicodedata
from pathlib import Path

import argparse
import yaml


# -------------------------------------------------------
# Paths
# -------------------------------------------------------

# SCRIPT_DIR = Path(__file__).resolve().parent
# LEDGER_DIR = SCRIPT_DIR.parent

# DATA_DIR = LEDGER_DIR / "data"
# FACULTY_FILE = DATA_DIR / "faculty.json"

# RAW_DIR = DATA_DIR / "raw" / "maie"
# OUTPUT_FILE = DATA_DIR / "faculty_enriched.json"


# -------------------------------------------------------
# Base paths
# -------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
LEDGER_DIR = SCRIPT_DIR.parent

# -------------------------------------------------------
# UTRGV API
# -------------------------------------------------------

API_DM_USER = (
    "https://webapps.utrgv.edu/aa/dm/api/DMUser/"
    "GetDMuser?username="
)

# -------------------------------------------------------
# Command-line configuration
# -------------------------------------------------------

def parse_args():
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Enrich faculty records using the "
            "UTRGV Digital Measures API."
        )
    )

    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to the department config.yaml file.",
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Ignore cached raw API responses and "
            "download faculty profiles again."
        ),
    )

    return parser.parse_args()


def load_config(config_file):
    """Load and validate a department YAML configuration."""

    config_file = config_file.expanduser().resolve()

    if not config_file.exists():
        raise FileNotFoundError(
            f"Configuration file not found:\n{config_file}"
        )

    if not config_file.is_file():
        raise ValueError(
            f"Configuration path is not a file:\n{config_file}"
        )

    with config_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError(
            "The YAML configuration must contain a mapping."
        )

    required_fields = [
        "institution",
        "department_name",
        "output_directory",
    ]

    missing_fields = [
        field
        for field in required_fields
        if not config.get(field)
    ]

    if missing_fields:
        raise ValueError(
            "Missing required configuration fields: "
            + ", ".join(missing_fields)
        )

    return config_file, config


def resolve_output_directory(config_file, configured_path):
    """
    Resolve the configured output directory.

    Paths are first interpreted relative to the current working
    directory. If that location does not exist, the config file's
    parent directory is used when the configured path points to the
    same department directory.
    """

    output_directory = Path(configured_path).expanduser()

    if output_directory.is_absolute():
        return output_directory.resolve()

    working_directory_path = (
        Path.cwd() / output_directory
    ).resolve()

    if working_directory_path.exists():
        return working_directory_path

    # A config stored at ledger/data/ies/config.yaml normally means
    # that ledger/data/ies is itself the department output directory.
    config_parent = config_file.parent.resolve()

    if config_parent.name == output_directory.name:
        return config_parent

    return working_directory_path

# -------------------------------------------------------
# Helper functions
# -------------------------------------------------------

def clean_string(value):
    """Convert a value to a clean string or None."""
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return value

    value = str(value).strip()

    if not value:
        return None

    return value


def normalize_text(value):
    """
    Normalize text for comparisons/deduplication.

    Example:
        '  A Review of   Ceramic-Reinforced Alloys '
        ->
        'a review of ceramic-reinforced alloys'
    """
    if not value:
        return ""

    value = unicodedata.normalize("NFKC", str(value))

    value = value.lower()

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_doi(value):
    """Normalize a DOI into a consistent form."""
    if not value:
        return None

    value = str(value).strip()

    value = value.replace("https://doi.org/", "")
    value = value.replace("http://doi.org/", "")
    value = value.replace("https://dx.doi.org/", "")
    value = value.replace("http://dx.doi.org/", "")

    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)

    value = value.strip()

    if not value:
        return None

    return value.lower()


def parse_year(record):
    """
    Try to determine the publication year from the available
    Digital Measures date fields.
    """

    possible_fields = [
        "PUBLICATION_DATE",
        "DATE_PUBLISHED",
        "PUBLISHED_DATE",
        "PUB_DATE",
        "YEAR",
        "DATE",
        "ACCEPT_DATE",
        "ACCEPTED_DATE",
    ]

    for field in possible_fields:
        value = record.get(field)

        if value:
            match = re.search(r"\b(19|20)\d{2}\b", str(value))

            if match:
                return int(match.group(0))

    # Fall back to scanning the whole record for a 4-digit year.
    text = json.dumps(record, ensure_ascii=False)

    years = re.findall(r"\b(19|20)\d{2}\b", text)

    if years:
        # The regex above captures only the prefix.
        full_years = re.findall(r"\b(?:19|20)\d{2}\b", text)

        if full_years:
            return int(full_years[0])

    return None


def get_index_entry(record, key):
    """Extract a Digital Measures index entry."""
    entries = record.get("dmd:IndexEntry", [])

    if not isinstance(entries, list):
        entries = [entries]

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        if entry.get("@indexKey") == key:
            return (
                entry.get("@text")
                or entry.get("@entryKey")
            )

    return None


def safe_list(value):
    """Always return a list."""
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


# -------------------------------------------------------
# API request
# -------------------------------------------------------

def fetch_faculty(username):
    """Download one Digital Measures faculty profile."""

    encoded_username = urllib.parse.quote(username)

    url = API_DM_USER + encoded_username

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read().decode(
            "utf-8",
            errors="replace",
        )

    # Digital Measures sometimes returns JSON encoded
    # inside another JSON string.
    data = json.loads(raw)

    if isinstance(data, str):
        data = json.loads(data)

    return data


# -------------------------------------------------------
# Extract faculty profile
# -------------------------------------------------------

def extract_profile(record):
    """Extract useful information from PCI."""

    pci = record.get("PCI", {})

    if not isinstance(pci, dict):
        pci = {}

    first_name = clean_string(pci.get("FNAME"))
    middle_name = clean_string(pci.get("MNAME"))
    last_name = clean_string(pci.get("LNAME"))

    name_parts = [
        first_name,
        middle_name,
        last_name,
    ]

    full_name = " ".join(
        part for part in name_parts if part
    )

    research_interests = clean_string(
        pci.get("RESEARCH_INTERESTS")
    )

    structured_interests = pci.get(
        "PCI_RESEARCH_INTERESTS"
    )

    if structured_interests is None:
        structured_interests = []

    if not isinstance(structured_interests, list):
        structured_interests = [structured_interests]

    # Keep the structured research interests as their
    # original Digital Measures objects.
    structured_interests_clean = []

    for item in structured_interests:
        if isinstance(item, dict):
            structured_interests_clean.append(item)
        elif item:
            structured_interests_clean.append(str(item))

    return {
        "prefix": clean_string(pci.get("PREFIX")),
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "full_name": full_name,

        "email": clean_string(pci.get("EMAIL")),

        "campus": clean_string(pci.get("CAMPUS")),
        "building": clean_string(pci.get("BUILDING")),
        "room": clean_string(pci.get("ROOMNUM")),

        "phone": {
            "office": "-".join(
                clean_string(pci.get(field))
                for field in ("OPHONE1", "OPHONE2", "OPHONE3")
                if clean_string(pci.get(field))
            ),

            "department": "-".join(
                clean_string(pci.get(field))
                for field in ("DPHONE1", "DPHONE2", "DPHONE3")
                if clean_string(pci.get(field))
            ),
        },

        "bio": clean_string(pci.get("BIO")),

        "research_interests": research_interests,

        "structured_research_interests":
            structured_interests_clean,

        "photo": clean_string(
            pci.get("UPLOAD_PHOTO")
        ),

        "vita_available": (
            clean_string(pci.get("PROFILE_VITA"))
        ),
    }


# -------------------------------------------------------
# Extract education
# -------------------------------------------------------

def extract_education(record):
    """Preserve useful education records."""

    education = []

    for item in safe_list(record.get("EDUCATION")):

        if not isinstance(item, dict):
            continue

        education.append({
            "institution": clean_string(
                item.get("INSTITUTION")
            ),
            "degree": clean_string(
                item.get("DEGREE")
            ),
            "discipline": clean_string(
                item.get("DISCIPLINE")
            ),
            "specialization": clean_string(
                item.get("SPECIALIZATION")
            ),
            "graduation_date": clean_string(
                item.get("GRADUATION_DATE")
            ),
            "dissertation": clean_string(
                item.get("DISSERTATION")
            ),
        })

    return education


# -------------------------------------------------------
# Extract previous positions
# -------------------------------------------------------

def extract_previous_positions(record):
    """Extract previous academic/professional positions."""

    positions = []

    for item in safe_list(record.get("PASTHIST")):

        if not isinstance(item, dict):
            continue

        positions.append({
            "institution": clean_string(
                item.get("INSTITUTION")
            ),
            "title": clean_string(
                item.get("TITLE")
            ),
            "department": clean_string(
                item.get("DEPARTMENT")
            ),
            "start_date": clean_string(
                item.get("START_DATE")
            ),
            "end_date": clean_string(
                item.get("END_DATE")
            ),
        })

    return positions


# -------------------------------------------------------
# Extract awards
# -------------------------------------------------------

def extract_awards(record):
    """Extract awards/honors."""

    awards = []

    for item in safe_list(record.get("AWARDHONOR")):

        if not isinstance(item, dict):
            continue

        awards.append({
            "title": clean_string(
                item.get("TITLE")
            ),
            "organization": clean_string(
                item.get("ORGANIZATION")
            ),
            "date": clean_string(
                item.get("DATE")
            ),
            "description": clean_string(
                item.get("DESCRIPTION")
            ),
        })

    return awards


# -------------------------------------------------------
# Extract publication authors
# -------------------------------------------------------

def extract_authors(publication):
    """
    Extract every author listed by Digital Measures.

    FACULTY_NAME is especially useful because it contains
    the Digital Measures faculty user ID when the author
    is a UTRGV faculty member.
    """

    authors = []

    for position, author in enumerate(
        safe_list(publication.get("INTELLCONT_AUTH")),
        start=1,
    ):

        if not isinstance(author, dict):
            continue

        first_name = clean_string(
            author.get("FNAME")
        )

        middle_name = clean_string(
            author.get("MNAME")
        )

        last_name = clean_string(
            author.get("LNAME")
        )

        faculty_id = clean_string(
            author.get("FACULTY_NAME")
        )

        author_name = " ".join(
            part
            for part in [
                first_name,
                middle_name,
                last_name,
            ]
            if part
        )

        # Some records may not have first/last names,
        # so retain FACULTY_NAME as a fallback.
        if not author_name:
            author_name = faculty_id

        authors.append({
            "position": position,
            "name": author_name,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "faculty_id": faculty_id,
            "institution": clean_string(
                author.get("INSTITUTION")
            ),
            "student_level": clean_string(
                author.get("STUDENT_LEVEL")
            ),
        })

    return authors


# -------------------------------------------------------
# Extract one publication record
# -------------------------------------------------------

def extract_publication(record):
    """Convert one INTELLCONT record into normalized data."""

    title = clean_string(record.get("TITLE"))

    if not title:
        return None

    doi = normalize_doi(
        record.get("DOI")
    )

    year = parse_year(record)

    authors = extract_authors(record)

    publication = {
        "title": title,

        "normalized_title":
            normalize_text(title),

        "year": year,

        "type": clean_string(
            record.get("CONTYPE")
        ),

        "status": clean_string(
            record.get("STATUS")
        ),

        "refereed": clean_string(
            record.get("REFEREED")
        ),

        "publisher": clean_string(
            record.get("PUBLISHER")
        ),

        "volume": clean_string(
            record.get("VOLUME")
        ),

        "issue": clean_string(
            record.get("ISSUE")
        ),

        "pages": clean_string(
            record.get("PAGENUM")
        ),

        "url": clean_string(
            record.get("WEB_ADDRESS")
        ),

        "isbn_issn": clean_string(
            record.get("ISBNISSN")
        ),

        "pmcid": clean_string(
            record.get("PMCID")
        ),

        "doi": doi,

        "abstract": clean_string(
            record.get("ABSTRACT")
        ),

        "full_text": clean_string(
            record.get("FULL_TEXT")
        ),

        "impact": clean_string(
            record.get("IMPACT")
        ),

        "authors": authors,

        "dates": {
            "submitted": clean_string(
                record.get("SUBMISSION_DATE")
            ),
            "accepted": clean_string(
                record.get("ACCEPTANCE_DATE")
            ),
            "published": clean_string(
                record.get("PUBLICATION_DATE")
            ),
        },

        # Preserve the original DM record ID so that
        # we can trace this normalized record back to
        # the source.
        "dm_record_id": clean_string(
            record.get("@id")
        ),
    }

    return publication


# -------------------------------------------------------
# Publication deduplication
# -------------------------------------------------------

STATUS_PRIORITY = {
    "published": 5,
    "accepted": 4,
    "submitted": 3,
    "in preparation": 2,
    "not yet submitted": 1,
}


def publication_key(publication):
    """
    Create a stable deduplication key.

    DOI is preferred.

    If DOI is missing:
        normalized title + year
    """

    doi = publication.get("doi")

    if doi:
        return "doi:" + doi

    title = publication.get(
        "normalized_title",
        "",
    )

    year = publication.get("year")

    return f"title:{title}|year:{year}"


def status_score(status):
    """Return a ranking for publication status."""

    if not status:
        return 0

    return STATUS_PRIORITY.get(
        normalize_text(status),
        0,
    )


def merge_publication(existing, new):
    """
    Merge duplicate publication records.

    Prefer the record with the stronger status,
    but preserve information from both.
    """

    existing_score = status_score(
        existing.get("status")
    )

    new_score = status_score(
        new.get("status")
    )

    if new_score > existing_score:
        canonical = dict(new)
        secondary = existing
    else:
        canonical = dict(existing)
        secondary = new

    # Fill missing fields from the other record.
    for key, value in secondary.items():

        if key in {
            "authors",
            "sources",
            "dm_record_ids",
        }:
            continue

        if not canonical.get(key) and value:
            canonical[key] = value

    # Merge source information.
    sources = canonical.get(
        "sources",
        [],
    )

    if not sources:
        sources = []

    sources.append({
        "status": secondary.get("status"),
        "type": secondary.get("type"),
        "publisher": secondary.get("publisher"),
        "url": secondary.get("url"),
        "dm_record_id": secondary.get(
            "dm_record_id"
        ),
    })

    canonical["sources"] = sources

    # Preserve all DM record IDs.
    ids = canonical.get(
        "dm_record_ids",
        [],
    )

    if canonical.get("dm_record_id"):
        ids.append(
            canonical["dm_record_id"]
        )

    if secondary.get("dm_record_id"):
        ids.append(
            secondary["dm_record_id"]
        )

    canonical["dm_record_ids"] = sorted(
        set(ids)
    )

    # Merge authors by faculty ID/name.
    merged_authors = {}

    for author in (
        existing.get("authors", [])
        + new.get("authors", [])
    ):

        author_id = (
            author.get("faculty_id")
            or normalize_text(
                author.get("name")
            )
        )

        if author_id not in merged_authors:
            merged_authors[author_id] = author

    canonical["authors"] = list(
        merged_authors.values()
    )

    return canonical


def deduplicate_publications(publications):
    """Deduplicate all publication records."""

    unique = {}

    for publication in publications:

        key = publication_key(
            publication
        )

        if key not in unique:
            publication["sources"] = [{
                "status": publication.get(
                    "status"
                ),
                "type": publication.get(
                    "type"
                ),
                "publisher": publication.get(
                    "publisher"
                ),
                "url": publication.get(
                    "url"
                ),
                "dm_record_id":
                    publication.get(
                        "dm_record_id"
                    ),
            }]

            publication["dm_record_ids"] = []

            if publication.get(
                "dm_record_id"
            ):
                publication[
                    "dm_record_ids"
                ].append(
                    publication[
                        "dm_record_id"
                    ]
                )

            unique[key] = publication

        else:
            unique[key] = merge_publication(
                unique[key],
                publication,
            )

    return list(unique.values())


# -------------------------------------------------------
# Main enrichment
# -------------------------------------------------------
# -------------------------------------------------------
# Main enrichment
# -------------------------------------------------------

def main():

    args = parse_args()

    config_file, config = load_config(
        args.config
    )

    institution = config["institution"]
    department_name = config["department_name"]

    college_name = config.get(
        "college",
        "College of Engineering and Computer Science",
    )

    output_directory = resolve_output_directory(
        config_file,
        config["output_directory"],
    )

    faculty_file = (
        output_directory / "faculty.json"
    )

    raw_directory = (
        output_directory / "raw"
    )

    output_file = (
        output_directory / "faculty_enriched.json"
    )

    print("=" * 60)
    print("UTRGV FACULTY ENRICHMENT")
    print("=" * 60)
    print()
    print(f"Institution: {institution}")
    print(f"Department:  {department_name}")
    print(f"Config:      {config_file}")
    print(f"Input:       {faculty_file}")
    print(f"Raw data:    {raw_directory}")
    print(f"Output:      {output_file}")
    print()

    # ---------------------------------------------------
    # Load discovered faculty
    # ---------------------------------------------------

    if not faculty_file.exists():
        raise FileNotFoundError(
            "Faculty file not found:\n"
            f"{faculty_file}\n\n"
            "Run discover_faculty.py first using the same "
            "--config file."
        )

    with faculty_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        faculty_list = json.load(file)

    if not isinstance(faculty_list, list):
        raise ValueError(
            "The faculty input file must contain a JSON list:\n"
            f"{faculty_file}"
        )

    print(
        f"Faculty discovered: {len(faculty_list)}"
    )

    raw_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    enriched_faculty = []
    all_publications = []

    faculty_ids = {
        str(faculty.get("user_id"))
        for faculty in faculty_list
        if faculty.get("user_id") is not None
    }

    # ---------------------------------------------------
    # Fetch each faculty profile
    # ---------------------------------------------------

    for index, faculty in enumerate(
        faculty_list,
        start=1,
    ):

        if not isinstance(faculty, dict):
            print()
            print(
                f"[{index}/{len(faculty_list)}] "
                "Invalid faculty record"
            )

            enriched_faculty.append({
                "faculty": faculty,
                "error": "Faculty record is not an object.",
                "publications": [],
                "statistics": {},
            })

            continue

        username = clean_string(
            faculty.get("username")
        )

        name = (
            clean_string(faculty.get("name"))
            or username
            or "Unknown faculty member"
        )

        print()
        print(
            f"[{index}/{len(faculty_list)}] "
            f"{name} ({username or 'no username'})"
        )

        if not username:
            error_message = (
                "Faculty record does not contain a username."
            )

            print(f"  ERROR: {error_message}")

            enriched_faculty.append({
                "faculty": faculty,
                "error": error_message,
                "publications": [],
                "statistics": {},
            })

            continue

        safe_username = re.sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            username,
        )

        raw_file = raw_directory / (
            safe_username + ".json"
        )

        try:

            # -------------------------------------------
            # Use cached raw data if available.
            # -------------------------------------------

            if raw_file.exists() and not args.refresh:

                print(
                    "  Using cached API response..."
                )

                with raw_file.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    api_data = json.load(file)

            else:

                if args.refresh and raw_file.exists():
                    print(
                        "  Refresh requested. "
                        "Downloading Digital Measures..."
                    )
                else:
                    print(
                        "  Downloading Digital Measures..."
                    )

                api_data = fetch_faculty(
                    username
                )

                with raw_file.open(
                    "w",
                    encoding="utf-8",
                ) as file:
                    json.dump(
                        api_data,
                        file,
                        indent=2,
                        ensure_ascii=False,
                    )

                    file.write("\n")

                # Be polite to the API.
                time.sleep(0.5)

            # -------------------------------------------
            # Locate Record
            # -------------------------------------------

            record = (
                api_data
                .get("Data", {})
                .get("Record", {})
            )

            if isinstance(record, list):
                if len(record) == 1:
                    record = record[0]
                else:
                    raise ValueError(
                        "Expected one Data.Record but received "
                        f"{len(record)} records."
                    )

            if not isinstance(
                record,
                dict,
            ):
                raise ValueError(
                    "Could not find Data.Record"
                )

            user_id = clean_string(
                record.get("@userId")
            )

            # -------------------------------------------
            # Extract profile
            # -------------------------------------------

            profile = extract_profile(
                record
            )

            # -------------------------------------------
            # Extract publications
            # -------------------------------------------

            raw_publications = []

            for publication_record in safe_list(
                record.get("INTELLCONT")
            ):

                if not isinstance(
                    publication_record,
                    dict,
                ):
                    continue

                publication = extract_publication(
                    publication_record
                )

                if publication:
                    raw_publications.append(
                        publication
                    )

            publications = deduplicate_publications(
                raw_publications
            )


            # -------------------------------------------
            # Mark authors belonging to this department
            # -------------------------------------------

            for publication in publications:

                for author in publication["authors"]:

                    faculty_id = author.get(
                        "faculty_id"
                    )

                    author[
                        "is_department_faculty"
                    ] = (
                        str(faculty_id)
                        in faculty_ids
                        if faculty_id
                        else False
                    )

            # -------------------------------------------
            # Build enriched faculty record
            # -------------------------------------------

            try:
                relative_raw_file = raw_file.relative_to(
                    LEDGER_DIR
                )

                raw_source = str(
                    relative_raw_file
                )

            except ValueError:
                raw_source = str(
                    raw_file
                )

            enriched_record = {
                "faculty": {
                    **faculty,

                    "dm_user_id": user_id,

                    "profile": profile,

                    "education": extract_education(
                        record
                    ),

                    "previous_positions":
                        extract_previous_positions(
                            record
                        ),

                    "awards":
                        extract_awards(
                            record
                        ),
                },

                "publications": publications,

                "statistics": {
                    "raw_publication_records":
                        len(raw_publications),

                    "unique_publications":
                        len(publications),

                    "publications_with_abstract":
                        sum(
                            1
                            for publication
                            in publications
                            if publication.get(
                                "abstract"
                            )
                        ),

                    "publications_with_doi":
                        sum(
                            1
                            for publication
                            in publications
                            if publication.get(
                                "doi"
                            )
                        ),

                    "publications_with_full_text":
                        sum(
                            1
                            for publication
                            in publications
                            if publication.get(
                                "full_text"
                            )
                        ),
                },

                "raw_source": raw_source,
            }
            
            
            enriched_faculty.append(
                enriched_record
            )

            all_publications.extend(
                publications
            )

            print(
                f"  DM user ID: {user_id}"
            )

            print(
                f"  Raw publication records: "
                f"{len(raw_publications)}"
            )

            print(
                f"  Unique publications: "
                f"{len(publications)}"
            )

            print(
                "  Research interests: "
                f"{'yes' if profile.get('research_interests') else 'no'}"
            )

        except Exception as error:
            print(f"  ERROR: {error}")

            import traceback
            traceback.print_exc()

            enriched_faculty.append({
                "faculty": faculty,
                "error": str(error),
                "publications": [],
                "statistics": {},
                "raw_source": str(raw_file),
            })


    # ---------------------------------------------------
    # Build global publication list
    # ---------------------------------------------------

    global_publications = (
        deduplicate_publications(
            all_publications
        )
    )

    # ---------------------------------------------------
    # Build final output
    # ---------------------------------------------------

    output = {
        "metadata": {
            "institution": institution,
            "college": college_name,
            "department": department_name,

            "department_url":
                config.get("department_url"),

            "faculty_url":
                config.get("faculty_url"),

            "faculty_count":
                len(enriched_faculty),

            "publication_count":
                len(global_publications),

            "source":
                "UTRGV Digital Measures API",

            "api_endpoint":
                API_DM_USER,

            "generated_at":
                time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                ),
        },

        "faculty": enriched_faculty,
        "publications": global_publications,
    }

    # ---------------------------------------------------
    # Write output
    # ---------------------------------------------------

    print()
    print(f"Writing output to: {output_file}")

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

        file.write("\n")

    print(
        f"Successfully wrote {output_file}"
    )

    print()
    print("=" * 60)
    print("ENRICHMENT COMPLETE")
    print("=" * 60)

    print(
        f"Faculty records: {len(enriched_faculty)}"
    )

    print(
        f"Publications: {len(global_publications)}"
    )



if __name__ == "__main__":
    main()