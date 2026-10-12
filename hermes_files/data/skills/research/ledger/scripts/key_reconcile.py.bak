import argparse
import json
from pathlib import Path
from collections import defaultdict
import yaml

# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
LEDGER_DIR = SCRIPT_DIR.parent


def parse_args():
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Compare publication identity keys before and "
            "after normalization."
        )
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to the department configuration YAML file.",
    )

    return parser.parse_args()


def load_config(config_file):
    """Load and validate the department configuration."""

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    required_fields = [
        "institution",
        "department_name",
        "output_directory",
    ]

    for field in required_fields:

        if field not in config:

            raise ValueError(
                f"Missing required configuration field: {field}"
            )

    return config


def resolve_output_directory(
    config_file,
    configured_path,
):
    """
    Resolve the configured department output directory.

    Relative paths are resolved from the repository root.
    Absolute paths are used unchanged.
    """

    output_directory = Path(configured_path)

    if output_directory.is_absolute():
        return output_directory

    repository_root = LEDGER_DIR.parents[4]

    return repository_root / output_directory


# ============================================================
# LOAD CONFIGURATION
# ============================================================

args = parse_args()

config_file = Path(args.config).resolve()

config = load_config(config_file)

output_directory = resolve_output_directory(
    config_file,
    config["output_directory"],
)


# ============================================================
# INPUT FILES
# ============================================================

RAW_FILE = (
    output_directory / "faculty_enriched.json"
)

NORMALIZED_FILE = (
    output_directory / "faculty_normalized.json"
)


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
# Build normalized lookup indexes
#
# We use several identifiers because normalization can
# legitimately change a publication's identity key.
#
# Matching priority:
#
#   1. Exact identity key
#   2. Digital Measures record ID
#   3. Title + year
#   4. Truly missing
#
# A Digital Measures ID is especially useful because it
# survives DOI recovery and title normalization.
# -------------------------------------------------------

normalized_keys = {
    key(pub)
    for pub in normalized
}


normalized_dm_ids = defaultdict(list)

for pub in normalized:

    # A normalized publication can contain the DM ID in
    # several places. Check both representations.

    dm_id = clean(
        pub.get("dm_record_id")
    )

    if dm_id:

        normalized_dm_ids[dm_id].append(pub)

    for dm_id in pub.get("dm_record_ids", []):

        dm_id = clean(dm_id)

        if dm_id:

            normalized_dm_ids[dm_id].append(pub)


# -------------------------------------------------------
# Find raw groups whose exact identity key disappeared
# -------------------------------------------------------

missing = []

for raw_key, records in raw_groups.items():

    if raw_key not in normalized_keys:

        missing.append(
            (raw_key, records)
        )


# -------------------------------------------------------
# Reconcile missing identity keys
#
# These records are NOT automatically considered missing.
#
# A raw key can disappear because normalization:
#
#   - recovered a DOI
#   - cleaned the title
#   - merged duplicate records
#   - otherwise changed the strongest available key
# -------------------------------------------------------

changed = []
dm_id_matches = []
title_year_matches = []
truly_missing = []


for raw_key, records in missing:

    # All records in this raw group should represent the
    # same publication identity for our purposes.
    first = records[0]


    # ---------------------------------------------------
    # 1. Check Digital Measures record IDs
    # ---------------------------------------------------

    dm_candidates = []

    raw_dm_ids = set()

    for record in records:

        dm_id = clean(
            record.get("dm_record_id")
        )

        if dm_id:

            raw_dm_ids.add(dm_id)


    for dm_id in raw_dm_ids:

        for candidate in normalized_dm_ids.get(
            dm_id,
            []
        ):

            if candidate not in dm_candidates:

                dm_candidates.append(candidate)


    if dm_candidates:

        dm_id_matches.append(
            (
                raw_key,
                records,
                dm_candidates,
            )
        )

        continue


    # ---------------------------------------------------
    # 2. Check normalized title + year
    # ---------------------------------------------------

    title = normalize_text(
        first.get("normalized_title")
        or first.get("title")
    )

    year = clean(
        first.get("year")
    )

    candidates = normalized_title_year.get(
        (title, year),
        []
    )


    if candidates:

        changed.append(
            (
                raw_key,
                records,
                candidates,
            )
        )

        title_year_matches.append(
            (
                raw_key,
                records,
                candidates,
            )
        )

        continue


    # ---------------------------------------------------
    # 3. No reliable match was found
    # ---------------------------------------------------

    truly_missing.append(
        (
            raw_key,
            records,
        )
    )


# -------------------------------------------------------
# Reconciliation summary
# -------------------------------------------------------

# Exact key matches are the raw groups that did not appear
# in the "missing" list.
#
# In other words:
#
#   total raw groups
#   - groups whose exact key disappeared
#   = exact key matches
#
# These records did not require any additional reconciliation.
exact_key_matches = (
    len(raw_groups)
    - len(missing)
)


# Groups whose original identity key disappeared but were
# successfully recovered using a Digital Measures ID.
dm_id_reconciled = len(dm_id_matches)


# Groups whose original identity key disappeared but were
# recovered using normalized title + year.
title_year_reconciled = len(title_year_matches)


# All groups that required some form of reconciliation.
changed_key_groups = (
    dm_id_reconciled
    + title_year_reconciled
)


# -------------------------------------------------------
# Print reconciliation summary
# -------------------------------------------------------

print()
print("=" * 70)
print("KEY RECONCILIATION")
print("=" * 70)

print(
    f"Raw publication objects:       {len(raw)}"
)

print(
    f"Raw unique identity groups:    {len(raw_groups)}"
)

print(
    f"Normalized publications:       {len(normalized)}"
)

print(
    f"Exact key matches:             "
    f"{exact_key_matches}"
)

print(
    f"Changed keys reconciled:       "
    f"{changed_key_groups}"
)

print(
    f"    DM ID matches:             "
    f"{dm_id_reconciled}"
)

print(
    f"    Title/year matches:        "
    f"{title_year_reconciled}"
)

print(
    f"Truly missing groups:          "
    f"{len(truly_missing)}"
)


# -------------------------------------------------------
# Integrity check
# -------------------------------------------------------

reconciled_total = (
    exact_key_matches
    + changed_key_groups
    + len(truly_missing)
)


print()
print("=" * 70)
print("RECONCILIATION INTEGRITY")
print("=" * 70)

print(
    f"Raw identity groups accounted for: "
    f"{reconciled_total} / {len(raw_groups)}"
)


if reconciled_total == len(raw_groups):

    print(
        "RECONCILIATION: PASS"
    )

    print(
        "Every raw identity group is represented "
        "in the normalized data."
    )

else:

    print(
        "RECONCILIATION: FAIL"
    )

    print(
        "One or more raw identity groups could not "
        "be reconciled with the normalized data."
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
        "No raw identity groups were lost during "
        "normalization."
    )

    print(
        "Any difference between the raw identity-group "
        "count and normalized publication count is "
        "explained by identity-key changes and/or "
        "publication grouping."
    )

else:

    print(
        f"WARNING: {len(truly_missing)} raw identity "
        f"group(s) could not be reconciled."
    )