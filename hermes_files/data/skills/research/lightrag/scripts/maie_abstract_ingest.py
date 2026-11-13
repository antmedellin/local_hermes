#!/usr/bin/env python3

"""
Ingest one department's paper abstracts from PostgreSQL into LightRAG.

PostgreSQL is the authoritative source.
LightRAG is the semantic search / knowledge-graph layer.

Workflow:
1. Read papers with populated abstracts.
2. Read their authors from PostgreSQL.
3. Build one canonical text document per paper.
4. Submit documents to LightRAG in batches.
5. Poll each LightRAG track until processing finishes.
6. Verify every expected document reached "processed".
7. Leave global PostgreSQL LightRAG status fields unchanged.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

import psycopg2


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "rag"),
    "user": os.getenv("POSTGRES_USER", "rag"),
    "password": os.getenv("POSTGRES_PASSWORD", "rag"),
}

# From the host, LightRAG is exposed on localhost:9621.
LIGHTRAG_URL = "http://localhost:9621"

TEXTS_URL = f"{LIGHTRAG_URL}/documents/texts"
STATUS_URL = f"{LIGHTRAG_URL}/documents/track_status"

# Keep the first production run conservative.
BATCH_SIZE = 10

# How often to check LightRAG.
POLL_SECONDS = 5

# Maximum time to wait for one batch.
MAX_WAIT_SECONDS = 900

PENDING_STATUSES = {"pending", "queued", "parsing", "processing", "analyzing"}
FAILED_STATUSES = {"failed", "failure", "error"}

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

def get_connection():
    """Open a PostgreSQL connection."""
    return psycopg2.connect(**DB_CONFIG)


def resolve_department(connection, department_id, config_path=None, slug_override=None):
    """Verify the database identity and obtain a stable slug from ledger config."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT institution, department_name FROM research.departments "
            "WHERE department_id = %s",
            (department_id,),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Department ID {department_id} does not exist in PostgreSQL.")
    institution, department_name = row
    config = None
    if config_path:
        paths = [Path(config_path).expanduser().resolve()]
    elif not slug_override:
        data_dir = Path(__file__).resolve().parents[2] / "ledger/data"
        paths = sorted(p for p in data_dir.glob("*/config.yaml")
                       if p.parent.name not in ("raw", "template"))
    else:
        paths = []
    if paths:
        import yaml
        matches = []
        for path in paths:
            with path.open("r", encoding="utf-8") as handle:
                candidate = yaml.safe_load(handle)
            if not isinstance(candidate, dict):
                if config_path:
                    raise ValueError(f"Configuration must be a mapping: {path}")
                continue
            if (candidate.get("institution"), candidate.get("department_name")) == row:
                matches.append(candidate)
        if len(matches) != 1:
            raise ValueError(
                f"Expected one config matching database department {department_id} "
                f"({department_name}); found {len(matches)}. Pass its --config path."
            )
        config = matches[0]
    slug = slug_override or (config or {}).get("department_slug")
    if config and slug_override and slug_override != config.get("department_slug"):
        raise ValueError("--department-slug does not match the department config.")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", slug):
        raise ValueError(
            "Provide a valid department_slug through --config or --department-slug."
        )
    return institution, department_name, slug


def load_abstract_papers(connection, department_id, department_slug):
    """
    Load every canonical paper that has a non-empty abstract.

    Authors are loaded through:
        papers -> authorships -> professors

    Author order comes from authorships.author_position.
    """

    sql = """
        SELECT
            p.paper_id,
            p.title,
            p.publication_year,
            p.doi,
            p.abstract,
            COALESCE(
                json_agg(
                    json_build_object(
                        'full_name', pr.full_name,
                        'author_position', a.author_position
                    )
                    ORDER BY a.author_position
                ) FILTER (WHERE pr.professor_id IS NOT NULL),
                '[]'::json
            ) AS authors
        FROM research.papers p
        LEFT JOIN research.authorships a
            ON a.paper_id = p.paper_id
        LEFT JOIN research.professors pr
            ON pr.professor_id = a.professor_id
        WHERE p.abstract IS NOT NULL
          AND TRIM(p.abstract) <> ''
          AND EXISTS (
              SELECT 1
              FROM research.authorships a2
              JOIN research.professors pr2
                ON pr2.professor_id = a2.professor_id
              WHERE a2.paper_id = p.paper_id
                AND pr2.department_id = %s
          )
        GROUP BY
            p.paper_id,
            p.title,
            p.publication_year,
            p.doi,
            p.abstract
        ORDER BY p.paper_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (department_id,))
        rows = cursor.fetchall()

    papers = []

    for row in rows:
        paper_id, title, year, doi, abstract, authors = row

        papers.append({
            "paper_id": paper_id,
            "title": title,
            "publication_year": year,
            "doi": doi,
            "abstract": abstract,
            "authors": authors,
            "file_source": f"{department_slug}-paper-{paper_id:06d}",
        })

    return papers


# ---------------------------------------------------------------------------
# Canonical LightRAG document creation
# ---------------------------------------------------------------------------

def build_document(paper):
    """
    Build the canonical text representation sent to LightRAG.
    """

    author_names = [
        author["full_name"]
        for author in paper["authors"]
        if author.get("full_name")
    ]

    authors_text = "; ".join(author_names)

    year_text = (
        str(paper["publication_year"])
        if paper["publication_year"] is not None
        else "Unknown"
    )

    doi_text = paper["doi"] if paper["doi"] else "None"

    text = (
        "Research Paper Record\n"
        "\n"
        f"Paper ID: {paper['paper_id']}\n"
        f"Title: {paper['title']}\n"
        f"Publication Year: {year_text}\n"
        f"DOI: {doi_text}\n"
        f"Authors: {authors_text}\n"
        "\n"
        "Abstract:\n"
        f"{paper['abstract']}\n"
        "\n"
        "Authoritative source:\n"
        f"PostgreSQL research.papers.paper_id = {paper['paper_id']}\n"
    )

    return text


# ---------------------------------------------------------------------------
# LightRAG HTTP helpers
# ---------------------------------------------------------------------------

def get_all_documents():
    """
    Retrieve every document currently stored in LightRAG.

    This is a read-only operation. It does not submit or modify documents.
    """

    url = f"{LIGHTRAG_URL}/documents/paginated"

    page = 1
    page_size = 10
    all_documents = []

    while True:

        payload = {
            "page": page,
            "page_size": page_size,
            "sort_field": "created_at",
            "sort_direction": "desc",
        }

        response = post_json(url, payload)

        documents = response.get("documents", [])
        pagination = response.get("pagination", {})

        if not isinstance(documents, list):
            raise RuntimeError(
                "LightRAG inventory returned an invalid documents list."
            )

        all_documents.extend(documents)

        total_pages = pagination.get("total_pages")

        print(
            f"Inventory page {page}/{total_pages}: "
            f"{len(documents)} documents"
        )

        if pagination.get("has_next") is False:
            break

        if not pagination:
            raise RuntimeError(
                "LightRAG inventory did not return pagination metadata."
            )

        if total_pages is None or page >= total_pages:
            raise RuntimeError(
                "LightRAG pagination metadata is inconsistent."
            )

        page += 1

    # Verify that we retrieved the expected number of documents.
    total_count = pagination.get("total_count")

    if total_count is not None and len(all_documents) != total_count:
        raise RuntimeError(
            f"Incomplete LightRAG inventory: "
            f"expected {total_count}, retrieved {len(all_documents)}."
        )

    return all_documents


def duplicate_original_id(document):
    """Trust explicit content-hash duplicate metadata, not an error-message guess."""
    metadata = document.get("metadata") or {}
    if (metadata.get("is_duplicate") is True
            and metadata.get("duplicate_kind") == "content_hash"):
        return metadata.get("original_doc_id")
    return None


def effective_document_status(document, by_id, seen=None):
    """A duplicate is covered only when its original is verifiably processed."""
    original_id = duplicate_original_id(document)
    if not original_id:
        return (document.get("status") or "").lower(), None
    seen = set() if seen is None else set(seen)
    if original_id in seen:
        raise RuntimeError(f"Cycle in LightRAG duplicate references: {original_id}")
    seen.add(original_id)
    original = by_id.get(original_id)
    if original is None:
        # Wait for inventory to expose the original; never assume it succeeded.
        return "pending", original_id
    status, root_id = effective_document_status(original, by_id, seen)
    return status, root_id or original_id


def documents_by_source(documents, by_id=None):
    """Coalesce repeated duplicate markers without accepting ambiguous real docs."""
    by_id = by_id if by_id is not None else {
        doc["id"]: doc for doc in documents if doc.get("id")
    }
    by_source = {}
    for document in documents:
        source = document.get("file_path")
        if not source:
            continue
        previous = by_source.get(source)
        if previous is not None:
            previous_root = duplicate_original_id(previous) or previous.get("id")
            current_root = duplicate_original_id(document) or document.get("id")
            if (not (duplicate_original_id(previous) or duplicate_original_id(document))
                    or previous_root != current_root):
                raise RuntimeError(f"Ambiguous LightRAG source identifier: {source}")
            # Same source and same original: prefer the real document if present.
            if not duplicate_original_id(previous):
                continue
        by_source[source] = document
    return by_source


def classify_existing_documents(documents, papers):
    """
    Compare PostgreSQL source identifiers against LightRAG.

    Returns:
        missing: Documents not found in LightRAG.
        processed: Documents already processed.
        pending: Documents still processing.
        failed: Documents that previously failed.
    """

    by_id = {doc["id"]: doc for doc in documents if doc.get("id")}
    existing_by_source = documents_by_source(documents, by_id)

    missing = []
    processed = []
    pending = []
    failed = []

    for paper in papers:

        source = paper["file_source"]
        document = existing_by_source.get(source)

        if document is None:
            missing.append(paper)
            continue

        status, original_id = effective_document_status(document, by_id)

        if status == "processed":
            processed.append(paper)
            if original_id:
                print(f"Shared content verified: {source} -> {original_id} (processed)")

        elif status in PENDING_STATUSES:
            pending.append((paper, status))

        elif status in FAILED_STATUSES:
            failed.append((paper, status))

        else:
            raise RuntimeError(
                f"Unrecognized LightRAG status for {source}: {status}"
            )

    return missing, processed, pending, failed

def post_json(url, payload):
    """POST JSON and return the decoded JSON response."""

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"LightRAG HTTP {error.code} from {url}\n{body}"
        ) from error


def get_json(url):
    """GET JSON and return the decoded JSON response."""

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"LightRAG HTTP {error.code} from {url}\n{body}"
        ) from error


def submit_batch(papers):
    """
    Submit one batch to /documents/texts.

    file_sources and texts are deliberately kept in the same order.
    """

    texts = [
        build_document(paper)
        for paper in papers
    ]

    file_sources = [
        paper["file_source"]
        for paper in papers
    ]

    payload = {
        "texts": texts,
        "file_sources": file_sources,
    }

    print()
    print("=" * 70)
    print(f"SUBMITTING BATCH: {len(papers)} documents")
    print("=" * 70)

    for paper in papers:
        print(
            f"  {paper['file_source']} | "
            f"{paper['title']}"
        )

    response = post_json(TEXTS_URL, payload)

    print()
    print("LightRAG response:")
    print(json.dumps(response, indent=2))

    if response.get("status") not in ("success", "partial_success"):
        raise RuntimeError(
            f"LightRAG did not accept the batch: {response}"
        )

    track_id = response.get("track_id")

    if not track_id:
        raise RuntimeError(
            "LightRAG response did not contain a track_id."
        )

    print()
    print(f"Track ID: {track_id}")

    return track_id


# ---------------------------------------------------------------------------
# Polling / verification
# ---------------------------------------------------------------------------

def poll_batch(track_id, expected_sources, known_documents=None):
    """Drain a batch to terminal states, resolving verified duplicate originals.

    Returned copies use effective statuses for verification. LightRAG records
    themselves are never rewritten or deleted.
    """
    status_url = f"{STATUS_URL}/{track_id}"
    started = time.monotonic()
    expected_sources = set(expected_sources)
    known_by_id = {doc["id"]: doc for doc in (known_documents or []) if doc.get("id")}
    announced = set()
    while True:
        documents = get_json(status_url).get("documents", [])
        if not isinstance(documents, list):
            raise RuntimeError("Track response documents must be a list.")
        known_by_id.update({doc["id"]: doc for doc in documents if doc.get("id")})
        # Refresh originals that are absent or still pending; a failed duplicate
        # marker alone must not be treated as either success or a real failure.
        if any(duplicate_original_id(doc) and
               effective_document_status(doc, known_by_id)[0] in PENDING_STATUSES
               for doc in documents):
            inventory = get_all_documents()
            known_by_id.update({doc["id"]: doc for doc in inventory if doc.get("id")})
        by_source = documents_by_source(documents, known_by_id)
        resolved = []
        for source, document in by_source.items():
            status, original_id = effective_document_status(document, known_by_id)
            result = dict(document, status=status)
            if original_id:
                result["resolved_original_doc_id"] = original_id
                original = known_by_id.get(original_id, {})
                if status in FAILED_STATUSES:
                    result["error_msg"] = original.get("error_msg") or document.get("error_msg")
                if status == "processed" and source not in announced:
                    print(f"\nShared content verified: {source} -> {original_id} (processed)")
                    announced.add(source)
            resolved.append(result)
        status_by_source = {doc["file_path"]: doc["status"] for doc in resolved}
        processed = sum(status_by_source.get(src) == "processed" for src in expected_sources)
        failed = sum(status_by_source.get(src) in FAILED_STATUSES for src in expected_sources)
        pending = sum(status_by_source.get(src) in PENDING_STATUSES for src in expected_sources)
        missing = sum(src not in status_by_source for src in expected_sources)
        print(f"\rStatus: processed={processed}/{len(expected_sources)}, "
              f"pending={pending}, failed={failed}, missing={missing}",
              end="", flush=True)
        # Wait for remaining documents even if another document has failed.
        if processed + failed == len(expected_sources):
            print()
            return resolved
        if time.monotonic() - started > MAX_WAIT_SECONDS:
            print()
            raise TimeoutError(
                f"Timed out waiting for LightRAG track {track_id}. "
                f"processed={processed}, pending={pending}, failed={failed}, "
                f"missing={missing}. Background work may still be active."
            )
        time.sleep(POLL_SECONDS)


# ---------------------------------------------------------------------------
# PostgreSQL status update
# ---------------------------------------------------------------------------

def update_database(connection, papers, documents, track_id, department_id):
    """
    Update each paper only after its corresponding LightRAG document
    has actually reached a verified terminal state.
    """

    status_by_source = {
        document.get("file_path"): document.get("status")
        for document in documents
    }

    sql = """
        UPDATE research.papers
        SET
            lightrag_track_id = %s,
            lightrag_status = %s,
            updated_at = NOW()
        WHERE paper_id = %s
          AND EXISTS (
              SELECT 1
              FROM research.authorships a
              JOIN research.professors pr
                ON pr.professor_id = a.professor_id
              WHERE a.paper_id = research.papers.paper_id
                AND pr.department_id = %s
          );
    """

    with connection.cursor() as cursor:

        for paper in papers:

            source = paper["file_source"]
            status = status_by_source.get(source)

            if status == "processed":
                db_status = "PROCESSED"
            elif status:
                db_status = status.upper()
            else:
                db_status = "MISSING"

            cursor.execute(
                sql,
                (
                    track_id,
                    db_status,
                    paper["paper_id"],
                    department_id,
                ),
            )

    connection.commit()

# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ingest one department's paper abstracts into LightRAG."
    )
    parser.add_argument("--department-id", type=int, default=1)
    parser.add_argument("--config", help="Ledger department config.yaml; verified against the database ID.")
    parser.add_argument("--department-slug", help="Stable slug when no ledger config is available.")
    parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Inspect records without submitting documents or updating PostgreSQL."
    )
    args = parser.parse_args()

    department_id = args.department_id
    if department_id <= 0:
        parser.error("--department-id must be positive.")

    connection = get_connection()

    try:
        institution, department_name, department_slug = resolve_department(
            connection, department_id, args.config, args.department_slug,
        )
        print("=" * 70)
        print(f"{department_slug.upper()} ABSTRACT → LIGHTRAG INGESTION")
        print("=" * 70)
        print(f"Department: {department_name} (ID {department_id})")
        print(f"Institution: {institution}")

        # ---------------------------------------------------------------
        # Load canonical records from PostgreSQL.
        # ---------------------------------------------------------------

        papers = load_abstract_papers(connection, department_id, department_slug)

        print()
        print(f"Papers with abstracts: {len(papers)}")

        if not papers:
            print("No papers with abstracts were found.")
            return 0


        # ---------------------------------------------------------------
        # Inventory existing LightRAG documents.
        # ---------------------------------------------------------------

        print()
        print("Inspecting existing LightRAG documents...")

        existing_documents = get_all_documents()

        if not args.dry_run:
            wait_started = time.monotonic()
            while True:
                _, _, pending_existing, _ = classify_existing_documents(existing_documents, papers)
                if not pending_existing:
                    break
                if time.monotonic() - wait_started > MAX_WAIT_SECONDS:
                    raise TimeoutError(
                        "Existing LightRAG documents are still processing or their "
                        "duplicate originals are unavailable. No new texts were submitted."
                    )
                print(f"Waiting for {len(pending_existing)} existing documents; no resubmission.", flush=True)
                time.sleep(POLL_SECONDS)
                existing_documents = get_all_documents()

        print()
        print(f"Existing LightRAG documents: {len(existing_documents)}")

        # ---------------------------------------------------------------
        # Compare PostgreSQL records against LightRAG.
        # ---------------------------------------------------------------

        missing, processed, pending, failed = (
            classify_existing_documents(
                existing_documents,
                papers,
            )
        )

        print()
        print("=" * 70)
        print("INGESTION INVENTORY")
        print("=" * 70)

        print(f"PostgreSQL papers : {len(papers)}")
        print(f"Already processed : {len(processed)}")
        print(f"Missing           : {len(missing)}")
        print(f"Pending           : {len(pending)}")
        print(f"Previously failed : {len(failed)}")

        # ---------------------------------------------------------------
        # Report pending and failed records.
        # Never silently resubmit them.
        # ---------------------------------------------------------------

        if pending:

            print()
            print("DOCUMENTS STILL PROCESSING:")

            for paper, status in pending:
                print(f"  {paper['file_source']} | {status}")

        if failed:

            print()
            print("DOCUMENTS REQUIRING REVIEW:")

            for paper, status in failed:
                print(f"  {paper['file_source']} | {status}")
                by_source = documents_by_source(existing_documents)
                document = by_source[paper["file_source"]]
                print(f"    {document.get('error_msg') or 'No error details returned.'}")

        if pending or failed:

            raise RuntimeError(
                f"Existing {department_slug.upper()} documents "
                "require review. No new documents were submitted."
            )

        # ---------------------------------------------------------------
        # Display the missing records.
        # ---------------------------------------------------------------

        print()
        print("DOCUMENTS ELIGIBLE FOR INGESTION:")

        for paper in missing:
            print(
                f"  {paper['file_source']} | "
                f"{paper['title']}"
            )

        # ---------------------------------------------------------------
        # Dry-run mode: stop before any write operation.
        # ---------------------------------------------------------------

        if args.dry_run:

            print()
            print("=" * 70)
            print("DRY RUN COMPLETE")
            print("=" * 70)

            print(f"Department       : {department_slug.upper()}")
            print(f"Already processed: {len(processed)}")
            print(f"Would submit     : {len(missing)}")

            print()
            print("No LightRAG documents were submitted.")
            print("PostgreSQL was not modified.")

            return 0

        # ---------------------------------------------------------------
        # Process only missing records.
        # ---------------------------------------------------------------

        total_processed = 0

        for start in range(0, len(missing), BATCH_SIZE):

            batch = missing[start:start + BATCH_SIZE]

            print()
            print("-" * 70)
            print(
                f"Processing missing papers "
                f"{start + 1}-{start + len(batch)} "
                f"of {len(missing)}"
            )
            print("-" * 70)

            track_id = submit_batch(batch)

            expected_sources = [
                paper["file_source"]
                for paper in batch
            ]

            documents = poll_batch(
                track_id,
                expected_sources,
                known_documents=existing_documents,
            )

            status_by_source = {
                document.get("file_path"): document.get("status")
                for document in documents
            }

            processed_sources = [
                source
                for source in expected_sources
                if status_by_source.get(source) == "processed"
            ]

            failed_sources = [
                source
                for source in expected_sources
                if status_by_source.get(source) != "processed"
            ]

            print()
            print(
                f"Batch verification: "
                f"{len(processed_sources)}/{len(expected_sources)} processed"
            )

            if failed_sources:

                print()
                print("DOCUMENTS NOT VERIFIED:")

                for source in failed_sources:
                    print(
                        f"  {source} -> "
                        f"{status_by_source.get(source, 'missing')}"
                    )
                    details = next((doc for doc in documents if doc.get("file_path") == source), {})
                    print(f"    {details.get('error_msg') or 'No error details returned.'}")

                raise RuntimeError(
                    "Batch verification failed. "
                    "No PostgreSQL status fields were modified."
                )

            # IMPORTANT:
            # Do not call update_database() here.
            #
            # research.papers.lightrag_status and
            # research.papers.lightrag_track_id are global paper fields.
            # Updating them for another department could overwrite data.

            total_processed += len(processed_sources)

        # ---------------------------------------------------------------
        # Final result.
        # ---------------------------------------------------------------

        print()
        print("=" * 70)
        print("FINAL RESULT")
        print("=" * 70)

        print(f"Already processed : {len(processed)}")
        print(f"Newly processed   : {total_processed}")
        print(f"Total {department_slug.upper()} papers : {len(papers)}")

        if total_processed != len(missing):

            print("INGESTION RESULT: FAIL")

            return 1

        print("INGESTION RESULT: PASS")

        print("PostgreSQL global LightRAG status fields were left unchanged.")

        return 0

    finally:

        connection.close()

if __name__ == "__main__":
    raise SystemExit(main())
