#!/usr/bin/env python3
"""
CLEF AUDIT MODULE
=================

Provides append-only JSONL audit logging for Clef authorship
identity evaluations.

Design principles:
    1. Never modify existing audit events.
    2. Preserve the distinction between model decisions,
       policy decisions, and operational authorization.
    3. Record source-file hashes for reproducibility.
    4. Link events through a SHA-256 hash chain.
    5. Verify the integrity of the audit log.

This module does NOT:
    - Call the Clef API.
    - Modify authorship_reconciliation.json.
    - Modify faculty_reconciled.json.
    - Write to PostgreSQL.
    - Approve authorship mappings.

During shadow evaluation, all cases must remain shadow_only.
"""

import argparse
import fcntl
import hashlib
import json
import os
import sys

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SCHEMA_VERSION = "1.0"

GENESIS_HASH = "0" * 64


# ============================================================
# SERIALIZATION AND HASHING
# ============================================================

def canonical_json(data):
    """
    Convert an object into deterministic JSON.

    Sorting keys and using consistent separators ensures
    that the same event always produces the same hash.
    """

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )


def calculate_hash(data):
    """
    Calculate the SHA-256 hash of a JSON-compatible object.
    """

    serialized = canonical_json(data).encode("utf-8")

    return hashlib.sha256(serialized).hexdigest()


def calculate_file_hash(file_path):
    """
    Calculate the SHA-256 hash of a source file.

    Returns None if the file does not exist.
    """

    path = Path(file_path)

    if not path.is_file():
        return None

    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def calculate_source_hashes(source_files):
    """
    Calculate hashes for multiple source files.

    source_files should be a dictionary:

        {
            "faculty_normalized": "/path/to/file.json",
            "authorship_reconciliation": "/path/to/file.json"
        }
    """

    hashes = {}

    for name, file_path in source_files.items():
        hashes[name] = calculate_file_hash(file_path)

    return hashes


# ============================================================
# AUDIT CHAIN
# ============================================================

def get_last_event_hash(audit_path):
    """
    Return the hash of the last valid JSONL event.

    An empty audit log starts with the genesis hash.

    This function does not silently ignore malformed records.
    """

    path = Path(audit_path)

    if not path.exists() or path.stat().st_size == 0:
        return GENESIS_HASH

    last_event = None

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):

            if not line.strip():
                continue

            try:
                last_event = json.loads(line)

            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed audit record at line {line_number}"
                ) from exc

    if last_event is None:
        return GENESIS_HASH

    event_hash = last_event.get("event_hash")

    if not event_hash:
        raise ValueError(
            "Last audit event does not contain event_hash."
        )

    return event_hash


# ============================================================
# EVENT CREATION
# ============================================================

def build_audit_event(event_data, previous_hash):
    """
    Build a complete audit event.

    The caller supplies the event-specific information.
    This function adds audit metadata and the hash chain.
    """

    event = {
        "schema_version": SCHEMA_VERSION,

        "event_id": str(uuid4()),

        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "event_type": event_data.get(
            "event_type",
            "identity_evaluation"
        ),

        "case_id": event_data.get("case_id"),
        "run_id": event_data.get("run_id"),

        # Model output and operational authorization
        # are deliberately separate fields.

        "model": event_data.get("model"),

        "model_decision": event_data.get(
            "model_decision"
        ),

        "model_confidence": event_data.get(
            "model_confidence"
        ),

        "model_probabilities": event_data.get(
            "model_probabilities"
        ),

        "policy_decision": event_data.get(
            "policy_decision"
        ),

        "operational_authorization": event_data.get(
            "operational_authorization",
            "shadow_only"
        ),

        "approval_status": event_data.get(
            "approval_status",
            "not_approved"
        ),

        "human_review_required": event_data.get(
            "human_review_required",
            True
        ),

        # Source provenance

        "source_hashes": event_data.get(
            "source_hashes",
            {}
        ),

        "evidence": event_data.get(
            "evidence",
            {}
        ),

        # Preserve the original model response where supplied.

        "model_response": event_data.get(
            "model_response"
        ),

        "error": event_data.get("error"),

        # Safety and operational state

        "database_updated": event_data.get(
            "database_updated",
            False
        ),

        "approved_reconciliation_modified": event_data.get(
            "approved_reconciliation_modified",
            False
        ),

        "previous_event_hash": previous_hash
    }

    # Hash everything except event_hash itself.
    event["event_hash"] = calculate_hash(event)

    return event


# ============================================================
# APPEND-ONLY AUDIT WRITING
# ============================================================

def append_audit_event(audit_path, event_data):
    """
    Append one event to the JSONL audit log.

    Uses an exclusive file lock and fsync to reduce the
    possibility of concurrent-write corruption or loss.

    Existing events are never rewritten.
    """

    path = Path(audit_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Open in append mode. Never truncate existing records.
    with path.open("a+", encoding="utf-8") as file:

        # Prevent concurrent writers from interleaving events.
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)

        try:

            # Determine the previous event hash while locked.
            previous_hash = get_last_event_hash(path)

            event = build_audit_event(
                event_data,
                previous_hash
            )

            serialized = canonical_json(event)

            file.seek(0, os.SEEK_END)

            file.write(serialized + "\n")
            file.flush()

            # Request that the operating system flush data.
            os.fsync(file.fileno())

            return event

        finally:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)


# ============================================================
# AUDIT VERIFICATION
# ============================================================

def verify_audit_log(audit_path):
    """
    Verify the integrity and continuity of the hash chain.

    Checks:
        - JSONL syntax.
        - Required event hashes.
        - Previous-event hash continuity.
        - Event hash correctness.

    Returns a verification report.
    """

    path = Path(audit_path)

    report = {
        "audit_file": str(path),
        "exists": path.exists(),
        "valid": False,
        "events_checked": 0,
        "errors": [],
        "final_event_hash": GENESIS_HASH
    }

    if not path.exists():
        report["errors"].append("Audit file does not exist.")
        return report

    expected_previous_hash = GENESIS_HASH

    with path.open("r", encoding="utf-8") as file:

        for line_number, line in enumerate(file, start=1):

            if not line.strip():
                report["errors"].append(
                    f"Empty line at line {line_number}."
                )
                continue

            try:
                event = json.loads(line)

            except json.JSONDecodeError:
                report["errors"].append(
                    f"Invalid JSON at line {line_number}."
                )
                continue

            report["events_checked"] += 1

            recorded_hash = event.get("event_hash")

            if not recorded_hash:
                report["errors"].append(
                    f"Missing event hash at line {line_number}."
                )
                continue

            recorded_previous_hash = event.get(
                "previous_event_hash"
            )

            if recorded_previous_hash != expected_previous_hash:
                report["errors"].append(
                    f"Hash-chain mismatch at line {line_number}."
                )

            # Recalculate the event hash without event_hash.
            event_without_hash = dict(event)
            event_without_hash.pop("event_hash", None)

            calculated_hash = calculate_hash(
                event_without_hash
            )

            if calculated_hash != recorded_hash:
                report["errors"].append(
                    f"Event hash mismatch at line {line_number}."
                )

            expected_previous_hash = recorded_hash

    report["final_event_hash"] = expected_previous_hash

    report["valid"] = (
        report["events_checked"] > 0
        and len(report["errors"]) == 0
    )

    return report


# ============================================================
# COMMAND-LINE INTERFACE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Clef authorship audit utility."
    )

    parser.add_argument(
        "--verify",
        type=str,
        help="Verify an existing JSONL audit log."
    )

    args = parser.parse_args()

    if args.verify:

        report = verify_audit_log(args.verify)

        print(json.dumps(
            report,
            indent=2
        ))

        if report["valid"]:
            print("\nRESULT: AUDIT LOG INTEGRITY VERIFIED")
            return 0

        print("\nRESULT: AUDIT LOG VERIFICATION FAILED")
        return 1

    parser.print_help()
    return 0

if __name__ == "__main__":
    sys.exit(main())
