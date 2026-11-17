#!/usr/bin/env python3
"""
CLEF SHADOW EVALUATION RUNNER
=============================

Submits read-only authorship identity cases to Clef-Flash.

Responsibilities:
    1. Load the existing Clef case preview.
    2. Verify that its source files have not changed.
    3. Submit each case's existing evidence to System One.
    4. Preserve the complete model response.
    5. Append an audit event for every attempted evaluation.
    6. Generate separate decision and evaluation reports.
    7. Verify audit-chain integrity.
    8. Verify that protected source files remain unchanged.

SAFETY:
    - No PostgreSQL access.
    - No authorship reconciliation writes.
    - No faculty reconciliation writes.
    - No validation manifest writes.
    - No automatic authorship approval.
    - Every result remains shadow_only.

Each execution creates a unique run directory.
Existing evaluation runs are never overwritten.
"""

import argparse
import hashlib
import json
import sys
import uuid

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from clef_decision_engine import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    evaluate_identity,
)

from clef_audit import (
    append_audit_event,
    verify_audit_log,
)


# ============================================================
# CONFIGURATION
# ============================================================

PREVIEW_FILENAME = "clef_cases_preview.json"

PROTECTED_FILES = {
    "authorship_reconciliation": "authorship_reconciliation.json",
    "faculty_normalized": "faculty_normalized.json",
    "validation_manifest": "validation_manifest.json",
    "case_preview": PREVIEW_FILENAME,
}


# ============================================================
# GENERAL UTILITIES
# ============================================================

def load_json(path):
    """Load JSON without modifying the source file."""

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, data):
    """Write formatted JSON to a new or designated output file."""

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

        file.write("\n")


def sha256_file(path):
    """Calculate SHA-256 for a file."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


def utc_timestamp():
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


# ============================================================
# DEPARTMENT CONFIGURATION
# ============================================================

def resolve_department_directory(config_path):
    """
    Resolve the department output directory using config.yaml.

    Relative output paths are interpreted from repository root,
    matching the existing clef_policy.py behavior.
    """

    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("Department configuration must be a YAML mapping.")

    output_directory = config.get("output_directory")

    if not output_directory:
        raise ValueError("Missing output_directory in config.")

    repository_root = Path(__file__).resolve().parents[6]

    output_path = Path(output_directory)

    if not output_path.is_absolute():
        output_path = repository_root / output_path

    return output_path.resolve()


# ============================================================
# SOURCE PROTECTION
# ============================================================

def get_protected_paths(department_dir):
    """Resolve all protected input artifacts."""

    return {
        name: department_dir / filename
        for name, filename in PROTECTED_FILES.items()
    }


def calculate_source_hashes(protected_paths):
    """Calculate hashes for all protected inputs."""

    hashes = {}

    for name, path in protected_paths.items():

        if not path.is_file():
            raise FileNotFoundError(
                f"Required protected file missing: {path}"
            )

        hashes[name] = sha256_file(path)

    return hashes


def verify_preview_provenance(preview, source_hashes):
    """
    Verify that the case preview was generated from the
    currently available reconciliation and normalized files.
    """

    metadata = preview.get("metadata", {})

    recorded_hashes = metadata.get("source_hashes", {})

    expected = {
        "authorship_reconciliation.json":
            source_hashes["authorship_reconciliation"],

        "faculty_normalized.json":
            source_hashes["faculty_normalized"],
    }

    for filename, actual_hash in expected.items():

        recorded_hash = recorded_hashes.get(filename)

        if recorded_hash != actual_hash:
            raise ValueError(
                f"Source provenance mismatch for {filename}.\n"
                f"Preview hash: {recorded_hash}\n"
                f"Current hash: {actual_hash}\n"
                "Regenerate the case preview before evaluation."
            )

    if metadata.get("approved_reconciliation_modified") is True:
        raise ValueError(
            "Preview metadata indicates approved reconciliation "
            "was modified. Evaluation stopped."
        )

    if metadata.get("database_imported") is True:
        raise ValueError(
            "Preview metadata indicates database import occurred. "
            "Evaluation stopped."
        )


# ============================================================
# RUN MANAGEMENT
# ============================================================

def create_run_directory(department_dir):
    """
    Create a unique directory for this evaluation.

    Existing runs are never reused or overwritten.
    """

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "_"
        + uuid.uuid4().hex[:8]
    )

    run_directory = (
        department_dir / "clef_runs" / run_id
    )

    run_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    return run_id, run_directory


# ============================================================
# CASE VALIDATION
# ============================================================

def validate_cases(preview):
    """Validate the structure and eligibility of the preview."""

    cases = preview.get("cases")

    if not isinstance(cases, list):
        raise ValueError("Preview does not contain a cases list.")

    seen_case_ids = set()

    for index, case in enumerate(cases):

        if not isinstance(case, dict):
            raise ValueError(
                f"Case {index} is not a JSON object."
            )

        case_id = case.get("case_id")

        if not case_id:
            raise ValueError(
                f"Case {index} is missing case_id."
            )

        if case_id in seen_case_ids:
            raise ValueError(
                f"Duplicate case ID detected: {case_id}"
            )

        seen_case_ids.add(case_id)

        if case.get("policy_status") != (
            "ELIGIBLE_FOR_SHADOW_EVALUATION"
        ):
            raise ValueError(
                f"Case {case_id} is not eligible for shadow evaluation."
            )

        if not isinstance(case.get("evidence"), dict):
            raise ValueError(
                f"Case {case_id} has invalid evidence."
            )

        if not case["evidence"].get("source_author"):
            raise ValueError(
                f"Case {case_id} has no source author evidence."
            )
        # if not case["evidence"].get("proposed_candidate"):
        #     raise ValueError(
        #         f"Case {case_id} has no proposed candidate."
        #     )
    return cases

###precheck handling
def get_precheck_abstention_reason(evidence):
    """
    Determine whether a case has enough basic identity evidence
    to be sent to Clef-Flash.

    This does not determine whether two people are the same.
    It only checks whether the required inputs exist.
    """

    source_author = evidence.get("source_author")

    if (
        not isinstance(source_author, dict)
        or not source_author.get("name")
        or not str(source_author.get("name")).strip()
    ):
        return "SOURCE_AUTHOR_REQUIRED"

    candidate = evidence.get("proposed_candidate")

    if (
        not isinstance(candidate, dict)
        or not candidate.get("name")
        or not str(candidate.get("name")).strip()
        or not candidate.get("faculty_id")
    ):
        return "VALID_CANDIDATE_REQUIRED"

    return None

# ============================================================
# INDIVIDUAL CASE EVALUATION
# ============================================================

def evaluate_case(
    case,
    endpoint,
    model,
    timeout,
    source_hashes,
):
    """
    Evaluate one identity case.

    Returns a result record.

    Exceptions from the model/API are converted into error
    records so that subsequent cases can still be evaluated.
    """

    case_id = case["case_id"]

    started_at = utc_timestamp()

    # --------------------------------------------------------
    # Deterministic precheck: do not call the model when
    # required identity evidence is missing.
    # --------------------------------------------------------

    precheck_reason = get_precheck_abstention_reason(
        case.get("evidence", {})
    )

    if precheck_reason:

        return {
            "case_id": case["case_id"],
            "source_decision_index": case.get(
                "source_decision_index"
            ),
            "source_occurrence": case.get(
                "source_occurrence"
            ),
            "classification": case.get("classification"),
            "warnings": case.get("warnings", []),

            "evaluation_status": "PRECHECK_ABSTENTION",

            "started_at_utc": started_at,
            "completed_at_utc": utc_timestamp(),

            "model": model,
            "model_decision": None,
            "model_confidence": None,
            "model_probabilities": None,
            "usage": None,

            "policy_decision": (
                "CANDIDATE_REQUIRED"
                if precheck_reason == "VALID_CANDIDATE_REQUIRED"
                else "SOURCE_AUTHOR_REQUIRED"
            ),

            "precheck_reason": precheck_reason,

            "operational_authorization": "shadow_only",
            "approval_status": "not_approved",
            "human_review_required": True,

            "database_updated": False,
            "approved_reconciliation_modified": False,

            "source_hashes": source_hashes,

            "model_response": None,
            "error": None,
        }
    try:

        # Pass the exact evidence generated by clef_policy.py.
        result = evaluate_identity(
            evidence=case["evidence"],
            endpoint=endpoint,
            model=model,
            timeout=timeout,
        )

        completed_at = utc_timestamp()

        decision_record = {
            "case_id": case_id,

            "source_decision_index":
                case["source_decision_index"],

            "source_occurrence":
                case["source_occurrence"],

            "classification":
                case["classification"],

            "warnings":
                case.get("warnings", []),

            "evaluation_status": "EVALUATED",

            "started_at_utc": started_at,

            "completed_at_utc": completed_at,

            "model": result.get("model") or model,

            "model_decision": result["choice"],

            "model_confidence": result.get("confidence"),

            "model_probabilities":
                result.get("probabilities"),

            "usage": result.get("usage"),

            "policy_decision":
                "ELIGIBLE_FOR_SHADOW_EVALUATION",

            "operational_authorization": "shadow_only",

            "approval_status": "not_approved",

            "human_review_required": True,

            "database_updated": False,

            "approved_reconciliation_modified": False,

            "source_hashes": source_hashes,

            "model_response": result.get("raw_response"),
        }

    except Exception as exc:

        completed_at = utc_timestamp()

        decision_record = {
            "case_id": case_id,

            "source_decision_index":
                case["source_decision_index"],

            "source_occurrence":
                case["source_occurrence"],

            "classification":
                case["classification"],

            "warnings":
                case.get("warnings", []),

            "evaluation_status": "ERROR",

            "started_at_utc": started_at,

            "completed_at_utc": completed_at,

            "model": model,

            "model_decision": None,

            "model_confidence": None,

            "model_probabilities": None,

            "usage": None,

            "policy_decision":
                "ELIGIBLE_FOR_SHADOW_EVALUATION",

            "operational_authorization": "shadow_only",

            "approval_status": "not_approved",

            "human_review_required": True,

            "database_updated": False,

            "approved_reconciliation_modified": False,

            "source_hashes": source_hashes,

            "model_response": None,

            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

    return decision_record


# ============================================================
# AUDIT EVENT CONSTRUCTION
# ============================================================

def build_audit_data(case, decision, run_id):
    """Convert an evaluation result into an audit event."""

    if decision["evaluation_status"] == "EVALUATED":
        event_type = "identity_evaluation"

    elif decision["evaluation_status"] == "PRECHECK_ABSTENTION":
        event_type = "identity_evaluation_precheck_abstention"

    else:
        event_type = "identity_evaluation_error"

    return {
        "event_type": event_type,

        "case_id": case["case_id"],

        "run_id": run_id,

        "model": decision.get("model"),

        "model_decision": decision.get("model_decision"),

        "model_confidence": decision.get("model_confidence"),

        "model_probabilities":
            decision.get("model_probabilities"),

        "policy_decision": decision.get("policy_decision"),

        "operational_authorization": "shadow_only",

        "approval_status": "not_approved",

        "human_review_required": True,

        "source_hashes": decision.get("source_hashes"),

        "evidence": case["evidence"],

        "model_response": {
            "response": decision.get("model_response"),
            "usage": decision.get("usage"),
            "evaluation_status": decision.get("evaluation_status"),
            "precheck_reason": decision.get("precheck_reason"),
        },

        "error": decision.get("error"),

        "database_updated": False,

        "approved_reconciliation_modified": False,
    }

# ============================================================
# REPORT GENERATION
# ===========================================================
def build_report(
    run_id,
    run_directory,
    decisions,
    audit_report,
    initial_hashes,
    final_hashes,
    preview,
):
    """Build aggregate evaluation results."""

    # --------------------------------------------------------
    # Initialize aggregate counters and result collections
    # --------------------------------------------------------

    decision_counts = Counter()

    classification_counts = Counter()

    classification_decisions = defaultdict(Counter)

    error_cases = []

    precheck_abstention_cases = []

    evaluation_status_counts = Counter()

    # --------------------------------------------------------
    # Process every case result
    # --------------------------------------------------------

    for record in decisions:

        status = record["evaluation_status"]

        classification = record.get("classification")

        # Count every case by its original classification.
        classification_counts[classification] += 1

        # Count every case by its evaluation status.
        evaluation_status_counts[status] += 1

        # ----------------------------------------------------
        # Case 1: Precheck abstention
        # ----------------------------------------------------

        if status == "PRECHECK_ABSTENTION":

            precheck_abstention_cases.append({
                "case_id": record["case_id"],
                "classification": classification,
                "reason": record.get("precheck_reason"),
                "policy_decision": record.get("policy_decision"),
            })

            # Do not count this as a model decision.
            continue

        # ----------------------------------------------------
        # Case 2: Model/API error
        # ----------------------------------------------------

        if status == "ERROR":
            # decision_counts["ERROR"] += 1
            error_cases.append({
                "case_id": record["case_id"],
                "classification": classification,
                "error": record.get("error"),
            })

            continue

        # ----------------------------------------------------
        # Case 3: Successfully evaluated by Clef-Flash
        # ----------------------------------------------------

        if status == "EVALUATED":

            choice = record.get("model_decision")

            if choice is not None:

                decision_counts[choice] += 1

                classification_decisions[classification][choice] += 1

    # --------------------------------------------------------
    # Verify protected source files
    # --------------------------------------------------------

    source_files_unchanged = (
        initial_hashes == final_hashes
    )

    # --------------------------------------------------------
    # Build evaluation report
    # --------------------------------------------------------

    report = {
        "run_id": run_id,

        "generated_at_utc": utc_timestamp(),

        "department": preview.get(
            "metadata", {}
        ).get("department"),

        "mode": "SHADOW_EVALUATION",

        "model": (
            decisions[0].get("model")
            if decisions else None
        ),

        "run_directory": str(run_directory),

        # Total number of cases represented in this run.
        "input_case_count": len(decisions),

        # Cases actually sent to and evaluated by Clef-Flash.
        "evaluated_case_count": evaluation_status_counts[
            "EVALUATED"
        ],

        # Cases deliberately not sent to the model.
        "precheck_abstention_count": evaluation_status_counts[
            "PRECHECK_ABSTENTION"
        ],

        "precheck_abstention_cases": precheck_abstention_cases,

        # Cases that encountered an actual execution/API error.
        "error_case_count": len(error_cases),

        "error_cases": error_cases,

        # Breakdown of all evaluation outcomes.
        "evaluation_status_counts": {
            "EVALUATED": evaluation_status_counts["EVALUATED"],
            "PRECHECK_ABSTENTION": evaluation_status_counts[
                "PRECHECK_ABSTENTION"
            ],
            "ERROR": evaluation_status_counts["ERROR"],
        },

        # Model decisions only; abstentions are excluded.
        "model_decision_counts": dict(decision_counts),

        # Original classification distribution across all cases.
        "classification_counts": dict(classification_counts),

        # Model decisions grouped by original classification.
        "decisions_by_classification": {
            classification: dict(counts)
            for classification, counts
            in classification_decisions.items()
        },

        "source_hashes_before": initial_hashes,

        "source_hashes_after": final_hashes,

        "protected_sources_unchanged": source_files_unchanged,

        "audit_integrity": audit_report,

        # ----------------------------------------------------
        # Operational safeguards
        # ----------------------------------------------------

        "database_updated": False,

        "approved_reconciliation_modified": False,

        "validation_manifest_modified": False,

        "automatic_approvals": 0,

        "operational_authorization": "shadow_only",

        "approval_status": "not_approved",

        # ----------------------------------------------------
        # Interpretation safeguards
        # ----------------------------------------------------

        "interpretation_warning": (
            "Model decision counts are descriptive, not accuracy "
            "measurements. Existing reconciliation classifications "
            "are not independently verified ground truth. "
            "Model confidence and probabilities are not assumed "
            "to be calibrated correctness probabilities. "
            "Precheck abstentions represent cases that were not "
            "sent to the model because required evidence was missing."
        ),
    }

    # --------------------------------------------------------
    # Determine whether the evaluation run passed integrity
    # checks.
    #
    # A deliberate precheck abstention is not an execution error.
    # --------------------------------------------------------

    report["run_integrity_passed"] = (
        source_files_unchanged
        and audit_report["valid"]
        and len(error_cases) == 0
    )

    return report

# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Run Clef-Flash shadow authorship evaluation."
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Department config.yaml",
    )

    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="Ollama System One endpoint",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Clef model name",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Request timeout in seconds",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of cases to evaluate",
    )

    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero.")

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be greater than zero.")

    config_path = Path(args.config).resolve()

    if not config_path.is_file():
        raise FileNotFoundError(config_path)

    department_dir = resolve_department_directory(config_path)

    protected_paths = get_protected_paths(department_dir)

    preview_path = protected_paths["case_preview"]

    print("=" * 70)
    print("CLEF SHADOW EVALUATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Load and validate inputs
    # --------------------------------------------------------

    print("\n[1/7] Loading case preview...")

    preview = load_json(preview_path)

    cases = validate_cases(preview)

    print(f"Cases available: {len(cases)}")

    # --------------------------------------------------------
    # Capture source hashes
    # --------------------------------------------------------

    print("\n[2/7] Verifying source provenance...")

    initial_hashes = calculate_source_hashes(
        protected_paths
    )

    verify_preview_provenance(
        preview,
        initial_hashes,
    )

    print("Source hashes match the preview metadata.")

    # --------------------------------------------------------
    # Apply optional case limit
    # --------------------------------------------------------

    if args.limit is not None:
        cases = cases[:args.limit]

    print(f"Cases selected for evaluation: {len(cases)}")

    # --------------------------------------------------------
    # Create a unique run directory
    # --------------------------------------------------------

    print("\n[3/7] Creating evaluation run...")

    run_id, run_directory = create_run_directory(
        department_dir
    )

    print(f"Run ID: {run_id}")
    print(f"Run directory: {run_directory}")

    audit_path = run_directory / "clef_audit.jsonl"

    decisions_path = run_directory / "clef_decisions.jsonl"

    # --------------------------------------------------------
    # Save run metadata
    # --------------------------------------------------------

    run_metadata = {
        "run_id": run_id,

        "started_at_utc": utc_timestamp(),

        "department": preview.get(
            "metadata", {}
        ).get("department"),

        "mode": "SHADOW_EVALUATION",

        "endpoint": args.endpoint,

        "model_requested": args.model,

        "timeout_seconds": args.timeout,

        "selected_case_count": len(cases),

        "source_hashes": initial_hashes,

        "database_access": False,

        "approval_enabled": False,
    }

    write_json(
        run_directory / "run_metadata.json",
        run_metadata,
    )

    # --------------------------------------------------------
    # Evaluate cases
    # --------------------------------------------------------

    print("\n[4/7] Evaluating cases with Clef-Flash...")

    decisions = []

    with decisions_path.open(
        "x",
        encoding="utf-8"
    ) as decisions_file:

        for index, case in enumerate(cases, start=1):

            print(
                f"\n[{index}/{len(cases)}] "
                f"{case['case_id']} "
                f"({case['classification']})"
            )

            decision = evaluate_case(
                case=case,
                endpoint=args.endpoint,
                model=args.model,
                timeout=args.timeout,
                source_hashes=initial_hashes,
            )

            # The audit record is written before the result record.
            # If audit writing fails, execution stops.
            audit_event = append_audit_event(
                audit_path,
                build_audit_data(
                    case,
                    decision,
                    run_id,
                ),
            )

            decision["audit_event_id"] = audit_event["event_id"]

            decision["audit_event_hash"] = audit_event["event_hash"]

            # Preserve each result immediately.
            decisions_file.write(
                json.dumps(
                    decision,
                    ensure_ascii=False,
                    sort_keys=True,
                ) + "\n"
            )

            decisions_file.flush()

            decisions.append(decision)

            if decision["evaluation_status"] == "EVALUATED":

                print(
                    "  CLEF DECISION:",
                    decision["model_decision"],
                )

                print(
                    "  CONFIDENCE:",
                    decision["model_confidence"],
                )

            else:

                print(
                    "  ERROR:",
                    decision.get("error"),
                )

            print("  AUTHORIZATION: shadow_only")

    # --------------------------------------------------------
    # Verify source files
    # --------------------------------------------------------

    print("\n[5/7] Verifying protected source files...")

    final_hashes = calculate_source_hashes(
        protected_paths
    )

    source_files_unchanged = (
        initial_hashes == final_hashes
    )

    print(
        "Protected source files unchanged:",
        "YES" if source_files_unchanged else "NO",
    )

    # --------------------------------------------------------
    # Verify audit chain
    # --------------------------------------------------------

    print("\n[6/7] Verifying audit integrity...")

    audit_report = verify_audit_log(audit_path)

    print(
        "Audit valid:",
        audit_report["valid"],
    )

    print(
        "Events checked:",
        audit_report["events_checked"],
    )

    # --------------------------------------------------------
    # Generate final report
    # --------------------------------------------------------

    print("\n[7/7] Generating evaluation report...")

    report = build_report(
        run_id=run_id,
        run_directory=run_directory,
        decisions=decisions,
        audit_report=audit_report,
        initial_hashes=initial_hashes,
        final_hashes=final_hashes,
        preview=preview,
    )

    write_json(
        run_directory / "clef_evaluation_report.json",
        report,
    )

    print("\n" + "=" * 70)
    print("CLEF EVALUATION SUMMARY")
    print("=" * 70)

    print(
        json.dumps(
            report["model_decision_counts"],
            indent=2,
        )
    )

    print("\nEvaluated:", report["evaluated_case_count"])

    print("Errors:", report["error_case_count"])

    print(
        "Source files unchanged:",
        report["protected_sources_unchanged"],
    )

    print(
        "Audit integrity:",
        report["audit_integrity"]["valid"],
    )

    print(
        "Automatic approvals:",
        report["automatic_approvals"],
    )

    print(
        "Database updated:",
        report["database_updated"],
    )

    print(
        "Approved reconciliation modified:",
        report["approved_reconciliation_modified"],
    )

    print("\nRun directory:", run_directory)

    if report["run_integrity_passed"]:
        print("\nRESULT: SHADOW EVALUATION COMPLETED SUCCESSFULLY")
        return 0

    print("\nRESULT: EVALUATION COMPLETED WITH ERRORS OR INTEGRITY WARNINGS")
    return 1


if __name__ == "__main__":
    sys.exit(main())
