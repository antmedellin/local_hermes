#!/usr/bin/env python3

"""
Ingest MAIE paper abstracts from PostgreSQL into LightRAG.

PostgreSQL is the authoritative source.
LightRAG is the semantic search / knowledge-graph layer.

Workflow:
1. Read papers with populated abstracts.
2. Read their authors from PostgreSQL.
3. Build one canonical text document per paper.
4. Submit documents to LightRAG in batches.
5. Poll each LightRAG track until processing finishes.
6. Verify every expected document reached "processed".
7. Update research.papers with LightRAG status information.
"""

import json
import sys
import time
import urllib.error
import urllib.request

import psycopg2


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "rag",
    "user": "rag",
    "password": "rag",
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


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

def get_connection():
    """Open a PostgreSQL connection."""
    return psycopg2.connect(**DB_CONFIG)


def load_abstract_papers(connection):
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
        GROUP BY
            p.paper_id,
            p.title,
            p.publication_year,
            p.doi,
            p.abstract
        ORDER BY p.paper_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
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
            "file_source": f"maie-paper-{paper_id:06d}",
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

def poll_batch(track_id, expected_sources):
    """
    Poll LightRAG until every expected source has a terminal status.

    Returns the final document records.
    """

    status_url = f"{STATUS_URL}/{track_id}"

    started = time.time()

    expected_sources = set(expected_sources)

    while True:

        result = get_json(status_url)

        documents = result.get("documents", [])

        status_by_source = {
            document.get("file_path"): document.get("status")
            for document in documents
        }

        processed = sum(
            1
            for source in expected_sources
            if status_by_source.get(source) == "processed"
        )

        failed = sum(
            1
            for source in expected_sources
            if status_by_source.get(source) in (
                "failed",
                "failure",
                "error",
            )
        )

        missing = sum(
            1
            for source in expected_sources
            if source not in status_by_source
        )

        print(
            f"\rStatus: processed={processed}/"
            f"{len(expected_sources)}, "
            f"failed={failed}, "
            f"missing={missing}",
            end="",
            flush=True,
        )

        # Everything has reached a terminal state.
        if processed + failed + missing == len(expected_sources):

            print()

            return documents

        if time.time() - started > MAX_WAIT_SECONDS:
            print()

            raise TimeoutError(
                f"Timed out waiting for LightRAG track {track_id}"
            )

        time.sleep(POLL_SECONDS)


# ---------------------------------------------------------------------------
# PostgreSQL status update
# ---------------------------------------------------------------------------

def update_database(connection, papers, documents, track_id):
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
        WHERE paper_id = %s;
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
                ),
            )

    connection.commit()


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():

    print("=" * 70)
    print("MAIE ABSTRACT → LIGHTRAG INGESTION")
    print("=" * 70)

    connection = get_connection()

    try:

        # ---------------------------------------------------------------
        # Load canonical records from PostgreSQL.
        # ---------------------------------------------------------------

        papers = load_abstract_papers(connection)

        print()
        print(f"Papers with abstracts: {len(papers)}")

        if not papers:
            print("No papers with abstracts were found.")
            return 1

        # ---------------------------------------------------------------
        # Show what we are about to ingest.
        # ---------------------------------------------------------------

        print()
        print("First few documents:")

        for paper in papers[:5]:
            print(
                f"  {paper['file_source']} | "
                f"{paper['title']}"
            )

        # ---------------------------------------------------------------
        # Process batches.
        # ---------------------------------------------------------------

        total_processed = 0

        for start in range(0, len(papers), BATCH_SIZE):

            batch = papers[
                start:start + BATCH_SIZE
            ]

            track_id = submit_batch(batch)

            expected_sources = [
                paper["file_source"]
                for paper in batch
            ]

            documents = poll_batch(
                track_id,
                expected_sources,
            )

            # -----------------------------------------------------------
            # Verify this batch before updating PostgreSQL.
            # -----------------------------------------------------------

            status_by_source = {
                document.get("file_path"):
                    document.get("status")
                for document in documents
            }

            processed = [
                source
                for source in expected_sources
                if status_by_source.get(source) == "processed"
            ]

            failed = [
                source
                for source in expected_sources
                if status_by_source.get(source) != "processed"
            ]

            print()
            print(
                f"Batch verification: "
                f"{len(processed)}/{len(expected_sources)} processed"
            )

            if failed:

                print()
                print("FAILED DOCUMENTS:")

                for source in failed:
                    print(
                        f"  {source} -> "
                        f"{status_by_source.get(source)}"
                    )

                raise RuntimeError(
                    "Batch verification failed. "
                    "PostgreSQL was NOT updated for this batch."
                )

            # -----------------------------------------------------------
            # Only now update PostgreSQL.
            # -----------------------------------------------------------

            update_database(
                connection,
                batch,
                documents,
                track_id,
            )

            total_processed += len(processed)

            print(
                f"PostgreSQL updated for "
                f"{len(processed)} papers."
            )

        # ---------------------------------------------------------------
        # Final verification.
        # ---------------------------------------------------------------

        print()
        print("=" * 70)
        print("FINAL RESULT")
        print("=" * 70)
        print(f"Expected papers : {len(papers)}")
        print(f"Processed        : {total_processed}")

        if total_processed != len(papers):
            print("INGESTION RESULT: FAIL")
            return 1

        print("INGESTION RESULT: PASS")

        return 0

    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())