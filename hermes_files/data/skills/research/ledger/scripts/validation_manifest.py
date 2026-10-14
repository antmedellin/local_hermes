#!/usr/bin/env python3
"""Generate a pending-review validation manifest without database access."""
import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LEDGER_DIR = SCRIPT_DIR.parent
REPO_ROOT = LEDGER_DIR.parents[4]

ALLOWED_CLASSIFICATIONS = {
    "EXACT",
    "NAME_VARIANT",
    "INITIAL_VARIANT",
    "NAME_WITHOUT_DM_ID",
}

def normalize_key(value):
    """Match the importer's case/whitespace/punctuation normalization."""
    if value is None:
        value = ""

    value = unicodedata.normalize("NFKC", str(value))
    value = value.casefold()
    value = re.sub(r"[^\w\s]", " ", value)
    return " ".join(value.split())

def parse_year(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\b(19|20)\d{2}\b", str(value))
        return int(match.group()) if match else None

def first_nonempty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def get_faculty(source):
    records = source.get("faculty", [])
    if not isinstance(records, list):
        raise ValueError("'faculty' must be a list")
    return records

def get_publications(source):
    records = source.get("publications", [])
    if not isinstance(records, list):
        raise ValueError("'publications' must be a list")
    return records

def get_decisions(source):
    records = source.get("decisions", [])
    if not isinstance(records, list):
        raise ValueError("'decisions' must be a list")
    return records

def build_faculty_indexes(records):
    by_id = {}
    by_name = {}

    for faculty in records:
        user_id = first_nonempty(
            faculty.get("user_id"),
            faculty.get("dm_user_id"),
        )
        name = faculty.get("name")

        if user_id:
            by_id[str(user_id)] = faculty
        if name:
            by_name[normalize_key(name)] = faculty

    return by_id, by_name

def classify_current_department(author, by_id, by_name):
    classification = author.get("reconciliation_status")
    if classification is None:
        classification = author.get("classification")

    if classification not in ALLOWED_CLASSIFICATIONS:
        return None

    mapped_id = author.get("mapped_faculty_id")
    if mapped_id:
        faculty = by_id.get(str(mapped_id))
        if faculty:
            return faculty

    mapped_name = author.get("mapped_faculty_name")
    if mapped_name:
        faculty = by_name.get(normalize_key(mapped_name))
        if faculty:
            return faculty

    if classification == "NAME_WITHOUT_DM_ID":
        original_name = author.get("author_name_original")
        if original_name:
            return by_name.get(normalize_key(original_name))

    return None

def publication_key(publication):
    title = (
        publication.get("title")
        or publication.get("normalized_title")
        or ""
    ).strip()
    return normalize_key(title), parse_year(publication.get("year"))


def build_canonical_publications(publications):
    groups = defaultdict(list)
    for publication in publications:
        groups[publication_key(publication)].append(publication)

    canonical = []
    source_to_canonical = {}
    duplicate_groups = []

    for key, group in groups.items():
        # Match import.py: the first publication is the representative.
        representative = dict(group[0])
        canonical.append(representative)

        for publication in group:
            source_id = publication.get("publication_id")
            if source_id:
                source_to_canonical[source_id] = representative

        if len(group) > 1:
            duplicate_groups.append({
                "key": list(key),
                "publication_ids": [
                    p.get("publication_id") for p in group
                ],
            })

    return canonical, source_to_canonical, duplicate_groups


def calculate_counts(reconciled, reconciliation):
    faculty = get_faculty(reconciled)
    publications = get_publications(reconciled)
    decisions = get_decisions(reconciliation)

    by_id, by_name = build_faculty_indexes(faculty)

    canonical_publications, source_to_canonical, duplicate_groups = (
        build_canonical_publications(publications)
    )

    occurrences = []

    for publication in publications:
        source_id = publication.get("publication_id")
        canonical_publication = source_to_canonical.get(source_id)

        if canonical_publication is None:
            raise ValueError(
                f"Publication has no canonical mapping: {source_id!r}"
            )

        # Match import.py's canonical authorship key exactly:
        # representative's original title plus parsed year.
        paper_key = (
            canonical_publication.get("title"),
            parse_year(canonical_publication.get("year")),
        )

        for author in publication.get("authors", []):
            # Importer consumes reconciliation fields directly on authors.
            resolved = classify_current_department(author, by_id, by_name)
            if resolved is None:
                continue

            faculty_id = first_nonempty(
                resolved.get("user_id"),
                resolved.get("dm_user_id"),
            )
            if not faculty_id:
                continue

            occurrences.append((str(faculty_id), paper_key))

    # Decision-based fallback mirrors the read-only dry-run's relationship
    # calculation and is recorded separately for comparison.
    source_publication_map = {
        p.get("publication_id"): (
            normalize_key(p.get("title")),
            p.get("year"),
        )
        for p in publications
        if p.get("publication_id")
    }

    decision_occurrences = []
    for decision in decisions:
        resolved = classify_current_department(decision, by_id, by_name)
        if resolved is None:
            continue

        faculty_id = first_nonempty(
            resolved.get("user_id"),
            resolved.get("dm_user_id"),
        )
        if not faculty_id:
            continue

        paper_key = source_publication_map.get(
            decision.get("publication_id")
        )
        if paper_key is None:
            paper_key = (
                normalize_key(decision.get("title")),
                decision.get("year"),
            )

        decision_occurrences.append((str(faculty_id), paper_key))

    unique_dm_ids = {
        str(dm_id)
        for publication in publications
        for dm_id in publication.get("dm_record_ids", [])
        if dm_id is not None
    }

    classification_counts = Counter(
        decision.get("classification", "<missing>")
        for decision in decisions
    )

    return {
        "expected_faculty_count": len(by_id),
        "expected_publication_count": len(publications),
        "expected_unique_dm_record_count": len(unique_dm_ids),
        "expected_reconciliation_decision_count": len(decisions),
        "expected_canonical_publication_count": len(canonical_publications),
        "expected_publication_merge_group_count": len(duplicate_groups),
        "expected_department_author_occurrence_count": len(occurrences),
        "expected_canonical_authorship_count": len(set(occurrences)),
        "dry_run_decision_occurrence_count": len(decision_occurrences),
        "dry_run_canonical_authorship_count": len(set(decision_occurrences)),
        "classification_counts": dict(sorted(classification_counts.items())),
        "source_author_occurrence_count": sum(
            len(p.get("authors", [])) for p in publications
        ),
        "source_publication_duplicate_groups": duplicate_groups,
    }

def main():
    parser = argparse.ArgumentParser(
        description="Generate a pending-review validation manifest."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the manifest; without this flag, print the report only.",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_json(config_path) if config_path.suffix == ".json" else None

    if config is None:
        try:
            import yaml
        except ImportError as exc:
            raise SystemExit("PyYAML is required to read config.yaml") from exc
        with config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)

    output_directory = Path(config["output_directory"])
    if not output_directory.is_absolute():
        output_directory = REPO_ROOT / output_directory

    reconciled_path = output_directory / "faculty_reconciled.json"
    reconciliation_path = output_directory / "authorship_reconciliation.json"
    manifest_path = output_directory / "validation_manifest.json"

    for path in (reconciled_path, reconciliation_path):
        if not path.is_file():
            raise SystemExit(f"Required artifact not found: {path}")

    reconciled = load_json(reconciled_path)
    reconciliation = load_json(reconciliation_path)
    counts = calculate_counts(reconciled, reconciliation)

    manifest = {
        "manifest_version": 1,
        "status": "pending_review",
        "department_name": config["department_name"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            reconciled_path.name: sha256_file(reconciled_path),
            reconciliation_path.name: sha256_file(reconciliation_path),
        },
        "counts": counts,
        "approval": None,
        "notes": [
            "Generated counts are not approved import expectations.",
            "Review the occurrence-count comparison before approving.",
            "Publication identity remains normalized title plus parsed year.",
        ],
    }

    print(json.dumps(manifest, indent=2, ensure_ascii=False))

    if args.write:
        if manifest_path.exists():
            raise SystemExit(
                f"Refusing to overwrite existing manifest: {manifest_path}"
            )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote pending-review manifest: {manifest_path}")


if __name__ == "__main__":
    main()