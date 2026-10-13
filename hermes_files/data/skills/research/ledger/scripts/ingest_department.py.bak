#!/usr/bin/env python3
"""Safely orchestrate department research-ledger ingestion."""

import argparse
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[5]
LEDGER_DATA = SCRIPT_DIR.parent / "data"

# Each stage is run as a subprocess because some existing scripts execute
# their pipeline at module load time.
PREPARATION_STAGES = [
    ("Discover faculty", "discover_faculty.py", ["faculty.json"]),
    ("Enrich faculty", "enrich_faculty.py", ["faculty_enriched.json"]),
    ("Normalize faculty and publications", "normalize.py", ["faculty_normalized.json"]),
    ("Reconcile record keys", "key_reconcile.py", []),
    ("Reconcile faculty records", "reconcile.py", []),
    ("Reconcile authorship", "reconcile_authorship.py", ["authorship_reconciliation.json"]),
    ("Build reconciled ledger", "build_reconciled.py", ["faculty_reconciled.json"]),
    ("Validate artifacts", "validate.py", ["validation_report.json"]),
    ("Validate database import (read-only)", "db_dry_run.py", []),
]

def parse_args():
    parser = argparse.ArgumentParser(
        description="Orchestrate a department research-ledger ingestion."
    )
    parser.add_argument("--config", required=True, help="Department config.yaml")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Show the plan and validate configuration without running pipeline stages.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Pass --refresh to enrich_faculty.py.",
    )
    parser.add_argument(
        "--allow-db-write",
        action="store_true",
        help="Allow the PostgreSQL import stage after all checks pass.",
    )
    parser.add_argument(
        "--allow-lightrag-write",
        action="store_true",
        help="Explicitly allow LightRAG abstract ingestion after PostgreSQL import.",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Allow preparation stages to overwrite existing expected artifacts.",
    )
    return parser.parse_args()

def load_config(config_path):
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict):
        raise ValueError("Configuration must contain a YAML mapping.")

    for key in ("institution", "department_name", "output_directory", "sources"):
        if not config.get(key):
            raise ValueError(f"Missing or empty required config field: {key}")

    if not config.get("department_slug"):
        raise ValueError(
            "Missing department_slug. Add a stable slug such as 'maie' to config.yaml."
        )

    faculty_source = config["sources"].get("faculty")
    if not faculty_source:
        raise ValueError("Missing sources.faculty configuration.")

    if not isinstance(faculty_source, (dict, list)):
        raise ValueError("sources.faculty must be a mapping or list.")

    if not config.get("department_url") or not config.get("faculty_url"):
        raise ValueError("department_url and faculty_url must be configured.")

    if not config.get("validation"):
        raise ValueError(
            "Missing validation expectations. Configure validation before ingestion."
        )
    return config

def resolve_output_directory(config, config_path):
    configured = Path(config["output_directory"]).expanduser()

    if configured.is_absolute():
        return configured.resolve()

    # Department output paths are repository-relative.
    # Normalize the legacy IES path ./ledger/data/ies to the canonical location.
    if configured.parts[:2] == ("ledger", "data"):
        configured = Path("hermes_files/data/skills/research") / configured

    return (REPO_ROOT / configured).resolve()

def artifact_is_valid(path):
    """Require JSON artifacts to exist and parse successfully."""
    if not path.is_file():
        return False, "missing"
    try:
        with path.open("r", encoding="utf-8") as handle:
            json.load(handle)
        return True, "valid JSON"
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid JSON: {exc}"

def build_stages(args, config_path, output_dir, department_slug):
    python = sys.executable
    stages = []

    for name, script_name, artifacts in PREPARATION_STAGES:
        command = [python, str(SCRIPT_DIR / script_name), "--config", str(config_path)]

        if script_name == "enrich_faculty.py" and args.refresh:
            command.append("--refresh")

        stages.append({
            "name": name,
            "command": command,
            "artifacts": [output_dir / name for name in artifacts],
            "write_stage": script_name != "db_dry_run.py",
        })

    if args.allow_db_write:
        stages.append({
            "name": "Import reconciled ledger into PostgreSQL",
            "command": [
                python, str(SCRIPT_DIR / "import.py"),
                "--config", str(config_path),
            ],
            "artifacts": [],
            "write_stage": True,
        })

    if args.allow_lightrag_write and not args.allow_db_write:
        raise ValueError(
            "--allow-lightrag-write requires --allow-db-write so the "
            "PostgreSQL import completes before LightRAG ingestion."
        )

    if args.allow_lightrag_write:
        if department_slug != "maie":
            raise ValueError(
                "The current LightRAG worker is MAIE-specific. "
                "Use it only with department_slug: maie."
            )

        lightrag_script = (
            REPO_ROOT
            / "hermes_files/data/skills/research/lightrag/scripts/"
              "maie_abstract_ingest.py"
        )

        if not lightrag_script.is_file():
            raise FileNotFoundError(
                f"LightRAG ingestion script not found: {lightrag_script}"
            )

        stages.append({
            "name": "Ingest abstracts into LightRAG",
            "command": [python, str(lightrag_script)],
            "artifacts": [],
            "write_stage": True,
        })

    return stages

def main():
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()

    if not config_path.is_file():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 2

    try:
        config = load_config(config_path)
        output_dir = resolve_output_directory(config, config_path)
        stages = build_stages(args, config_path, output_dir, config['department_slug'])
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Department : {config['department_name']}")
    print(f"Slug       : {config['department_slug']}")
    print(f"Config     : {config_path}")
    print(f"Output     : {output_dir}")
    print(f"Mode       : {'PLAN ONLY' if args.plan else 'EXECUTION'}")
    print(f"DB writes  : {'ENABLED' if args.allow_db_write else 'DISABLED'}")
    print(f"LightRAG   : {'ENABLED' if args.allow_lightrag_write else 'DISABLED'}")
    print()

    if args.plan:
        print("Planned stages:")
        for index, stage in enumerate(stages, 1):
            print(f"{index:02}. {stage['name']}")
            print("    " + " ".join(stage["command"]))
            for artifact in stage["artifacts"]:
                print(f"    expected: {artifact}")
        print()
        print("Plan complete. No pipeline stages were executed.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = output_dir / f"ingest_run_{run_id}.json"
    run_record = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "department": config["department_name"],
        "department_slug": config["department_slug"],
        "config": str(config_path),
        "output_directory": str(output_dir),
        "stages": [],
        "status": "running",
    }

    def save_log():
        log_path.write_text(
            json.dumps(run_record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    try:
        for stage in stages:
            print(f"\n===== {stage['name']} =====")
            command = stage["command"]

            if stage["name"] != "Import reconciled ledger into PostgreSQL":
                for artifact in stage["artifacts"]:
                    if artifact.exists() and not args.allow_overwrite:
                        raise RuntimeError(
                            f"Refusing to overwrite existing artifact: {artifact}\n"
                            "Use --allow-overwrite only after reviewing existing data."
                        )

            started = time.time()
            stage_record = {
                "name": stage["name"],
                "command": command,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "running",
            }
            run_record["stages"].append(stage_record)
            save_log()

            result = subprocess.run(command, cwd=REPO_ROOT, check=False)
            stage_record["return_code"] = result.returncode
            stage_record["duration_seconds"] = round(time.time() - started, 2)
            stage_record["finished_at"] = datetime.now(timezone.utc).isoformat()

            if result.returncode != 0:
                stage_record["status"] = "failed"
                raise RuntimeError(
                    f"Stage '{stage['name']}' exited with code {result.returncode}."
                )

            # Check JSON outputs for corruption after the stage succeeds.
            for artifact in stage["artifacts"]:
                valid, detail = artifact_is_valid(artifact)
                if not valid:
                    stage_record["status"] = "failed"
                    raise RuntimeError(
                        f"Stage '{stage['name']}' did not produce a valid artifact: "
                        f"{artifact} ({detail})"
                    )

            stage_record["status"] = "succeeded"
            save_log()

        run_record["status"] = "succeeded"
        return_code = 0

    except Exception as exc:
        run_record["status"] = "failed"
        run_record["error"] = str(exc)
        print(f"\nERROR: {exc}", file=sys.stderr)
        return_code = 1

    finally:
        run_record["finished_at"] = datetime.now(timezone.utc).isoformat()
        run_record["duration_seconds"] = round(
            (datetime.now(timezone.utc) - datetime.fromisoformat(
                run_record["started_at"]
            )).total_seconds(),
            2,
        )
        save_log()
        print(f"\nRun status: {run_record['status']}")
        print(f"Run log   : {log_path}")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
