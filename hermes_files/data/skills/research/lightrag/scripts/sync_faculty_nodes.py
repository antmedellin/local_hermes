#!/usr/bin/env python3
"""Create missing LightRAG PERSON entities for committed ledger faculty.

PostgreSQL is authoritative. This script never updates, renames, merges,
removes, or assumes ownership of existing LightRAG entities.
"""

import argparse
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Department config.yaml")
    parser.add_argument("--department-id", type=int, required=True)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--dry-run", action="store_true", help="Check only; do not create entities (default)")
    actions.add_argument("--apply", action="store_true", help="Create missing PERSON entities")
    parser.add_argument(
        "--lightrag-url",
        default=os.getenv("LIGHTRAG_URL", "http://localhost:9621"),
        help="LightRAG server base URL (default: LIGHTRAG_URL or localhost:9621)",
    )
    return parser.parse_args()


def normalized_name(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def load_department_config(config_path):
    import yaml

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("Department configuration must be a YAML mapping")
    for key in ("institution", "department_name"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"Missing or empty department config field: {key}")
    return config


def load_faculty(config, department_id):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    connection = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "rag"),
        user=os.getenv("POSTGRES_USER", "rag"),
        password=os.getenv("POSTGRES_PASSWORD", "rag"),
        connect_timeout=15,
    )
    try:
        connection.set_session(readonly=True)
        with connection.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT institution, department_name FROM research.departments "
                "WHERE department_id = %s",
                (department_id,),
            )
            department = cur.fetchone()
            if not department:
                raise ValueError(f"Unknown department ID: {department_id}")
            if (
                department["institution"] != config["institution"]
                or department["department_name"] != config["department_name"]
            ):
                raise ValueError(
                    "Department ID does not match --config institution and department_name"
                )

            cur.execute(
                """
                SELECT professor_id, full_name, institution,
                       academic_title, research_interests, orcid, profile_url
                FROM research.professors
                WHERE department_id = %s
                ORDER BY professor_id
                """,
                (department_id,),
            )
            faculty = [dict(row) for row in cur.fetchall()]
            if not faculty:
                raise ValueError("No committed faculty found for this department")
            if any(not isinstance(p["full_name"], str) or not p["full_name"].strip()
                   for p in faculty):
                raise ValueError("Some faculty are missing full_name; refusing graph writes")

            # Global name collisions cannot be represented safely by a graph
            # node identified only by name. Fail before any write.
            cur.execute(
                """
                SELECT LOWER(BTRIM(full_name)) AS name_key, COUNT(*) AS n
                FROM research.professors
                WHERE LOWER(BTRIM(full_name)) = ANY(%s)
                GROUP BY LOWER(BTRIM(full_name))
                HAVING COUNT(*) > 1
                """,
                ([p["full_name"].strip().lower() for p in faculty],),
            )
            conflicts = [row["name_key"] for row in cur.fetchall()]
            if conflicts:
                raise ValueError(
                    "Ambiguous faculty names across PostgreSQL; resolve before sync: "
                    + ", ".join(conflicts)
                )
            return faculty
    finally:
        connection.close()


def request_json(base_url, path, *, payload=None):
    api_key = os.getenv("LIGHTRAG_API_KEY") or os.getenv("API_KEY")
    token = os.getenv("LIGHTRAG_AUTH_TOKEN")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        # Never echo authorization headers. Return actionable HTTP status.
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise RuntimeError(f"LightRAG HTTP {exc.code} on {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach LightRAG: {exc.reason}") from exc


def entity_exists(base_url, name):
    query = urllib.parse.urlencode({"name": name})
    result = request_json(base_url, f"/graph/entity/exists?{query}")
    if not isinstance(result, dict) or not isinstance(result.get("exists"), bool):
        raise RuntimeError(f"Unexpected entity existence response for {name!r}")
    return result["exists"]


def look_for_case_variant(base_url, name):
    """Avoid a case/whitespace-only duplicate if extraction used another casing."""
    query = urllib.parse.urlencode({"q": name, "limit": 100})
    labels = request_json(base_url, f"/graph/label/search?{query}")
    if not isinstance(labels, list):
        raise RuntimeError("Unexpected /graph/label/search response")
    for label in labels:
        if isinstance(label, str) and normalized_name(label) == normalized_name(name):
            return label
    return None


def description_for(person, config):
    parts = [
        f"{person['full_name'].strip()} is a faculty member at {config['institution']}, "
        f"in the {config['department_name']}.",
    ]
    for field, label in (
        ("academic_title", "Academic title"),
        ("research_interests", "Research interests"),
        ("orcid", "ORCID"),
        ("profile_url", "Faculty profile"),
    ):
        value = person.get(field)
        if value:
            parts.append(f"{label}: {str(value).strip()}")
    parts.append(
        f"Authoritative ledger reference: research.professors.professor_id = "
        f"{person['professor_id']}."
    )
    return "\n".join(parts)


def main():
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    if not config_path.is_file():
        raise ValueError(f"Configuration not found: {config_path}")
    if args.department_id <= 0:
        raise ValueError("--department-id must be positive")

    config = load_department_config(config_path)
    faculty = load_faculty(config, args.department_id)
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Mode: {mode}; department: {config['department_name']}", flush=True)
    print(f"PostgreSQL faculty records: {len(faculty)}", flush=True)

    created = 0
    existing = 0
    variants = 0
    planned = 0
    for person in faculty:
        name = person["full_name"].strip()
        if entity_exists(args.lightrag_url, name):
            print(f"EXISTS  {name} (identity not independently verified)", flush=True)
            existing += 1
            continue

        variant = look_for_case_variant(args.lightrag_url, name)
        if variant is not None:
            print(f"REVIEW  {name}: graph already has {variant!r}", flush=True)
            variants += 1
            continue

        if not args.apply:
            print(f"CREATE? {name} [professor_id={person['professor_id']}]", flush=True)
            planned += 1
            continue

        result = request_json(
            args.lightrag_url,
            "/graph/entity/create",
            payload={
                "entity_name": name,
                "entity_data": {
                    "entity_type": "PERSON",
                    "description": description_for(person, config),
                },
            },
        )
        if not isinstance(result, dict) or result.get("status") != "success":
            raise RuntimeError(f"LightRAG did not confirm creation of {name!r}")
        if not entity_exists(args.lightrag_url, name):
            raise RuntimeError(f"Entity {name!r} not found after successful creation")
        print(f"CREATED {name}", flush=True)
        created += 1

    print(
        f"Summary: total={len(faculty)}, created={created}, "
        f"would_create={planned}, existing={existing}, review={variants}",
        flush=True,
    )
    if variants:
        raise RuntimeError(
            f"{variants} case/whitespace name variants require identity review; "
            "no duplicate nodes were created for those records"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
