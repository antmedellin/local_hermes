#!/usr/bin/env python3

"""
Upload a research paper to LightRAG.

The PDF is uploaded to LightRAG, which handles:
    - parser routing
    - MinerU processing
    - OCR
    - image processing
    - table processing
    - equation processing
    - chunking
    - entity/relation extraction
    - Qdrant vector indexing
    - Neo4j graph indexing

Usage:
    python3 lightrag_ingest.py /path/to/paper.pdf

The script automatically adds the LightRAG MinerU parser hint:
    [mineru-iteP]

Example:
    python3 lightrag_ingest.py /opt/ai_files/papers/paper.pdf
"""

import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error


LIGHTRAG_URL = "http://local-hermes-lightrag-1:9621"

UPLOAD_URL = f"{LIGHTRAG_URL}/documents/upload"

STATUS_URL = f"{LIGHTRAG_URL}/documents/track_status"


def build_multipart(file_path):
    """
    Build the multipart/form-data request required by LightRAG.
    """

    boundary = uuid.uuid4().hex

    original_filename = os.path.basename(file_path)

    # Add the MinerU parser hint if it is not already present.
    #
    # i = image processing
    # t = table processing
    # e = equation processing
    # P = paragraph semantic chunking
    #
    # This allows LightRAG's parser routing configuration to select
    # MinerU without requiring additional API options.
    if "[mineru-iteP]" not in original_filename:
        filename = (
            os.path.splitext(original_filename)[0]
            + ".[mineru-iteP]"
            + os.path.splitext(original_filename)[1]
        )
    else:
        filename = original_filename

    with open(file_path, "rb") as f:
        file_data = f.read()

    body = bytearray()

    body.extend(f"--{boundary}\r\n".encode())

    body.extend(
        (
            f'Content-Disposition: form-data; '
            f'name="file"; filename="{filename}"\r\n'
        ).encode()
    )

    body.extend(b"Content-Type: application/pdf\r\n\r\n")

    body.extend(file_data)

    body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())

    content_type = f"multipart/form-data; boundary={boundary}"

    return bytes(body), content_type


def upload_document(file_path):
    """
    Upload the PDF to LightRAG.
    """

    body, content_type = build_multipart(file_path)

    request = urllib.request.Request(
        UPLOAD_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "Accept": "application/json",
        },
    )

    try:

        with urllib.request.urlopen(request, timeout=120) as response:

            response_body = response.read().decode("utf-8")

            return json.loads(response_body)

    except urllib.error.HTTPError as error:

        error_body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        print(
            f"LightRAG upload failed: HTTP {error.code}",
            file=sys.stderr,
        )

        print(error_body, file=sys.stderr)

        sys.exit(1)

    except urllib.error.URLError as error:

        print(
            f"Could not connect to LightRAG: {error}",
            file=sys.stderr,
        )

        sys.exit(1)


def get_status(track_id):
    """
    Retrieve the current LightRAG processing status.
    """

    url = f"{STATUS_URL}/{track_id}"

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
        },
    )

    try:

        with urllib.request.urlopen(request, timeout=30) as response:

            response_body = response.read().decode("utf-8")

            return json.loads(response_body)

    except urllib.error.HTTPError as error:

        print(
            f"Status request failed: HTTP {error.code}",
            file=sys.stderr,
        )

        return None

    except urllib.error.URLError as error:

        print(
            f"Could not connect to LightRAG: {error}",
            file=sys.stderr,
        )

        return None


def extract_status(response):
    #extract the processing status from the LightRAG response.

    if not response:
        return None

    # Direct status field
    if "status" in response:
        return response["status"]

    # Status inside data
    data = response.get("data")

    if isinstance(data, dict):
        if "status" in data:
            return data["status"]

    # LightRAG document tracking response
    documents = response.get("documents")

    if isinstance(documents, list) and documents:
        first_document = documents[0]

        if isinstance(first_document, dict):
            return first_document.get("status")

    # Status summary fallback
    status_summary = response.get("status_summary")

    if isinstance(status_summary, dict):

        if status_summary.get("processed", 0) > 0:
            return "processed"

        if status_summary.get("failed", 0) > 0:
            return "failed"

    return None


def wait_for_completion(track_id):
    """
    Poll LightRAG until processing finishes.
    """

    print()
    print(f"Track ID: {track_id}")
    print("Waiting for LightRAG processing...")

    while True:

        response = get_status(track_id)

        if response is None:

            time.sleep(5)

            continue

        status = extract_status(response)

        print(f"Status: {status}")

        if status:

            normalized = str(status).lower()

            if normalized in {
                "processed",
                "completed",
                "success",
                "done",
            }:

                print()
                print("Document successfully indexed.")

                return True

            if normalized in {
                "failed",
                "error",
            }:

                print()
                print(
                    "Document ingestion failed.",
                    file=sys.stderr,
                )

                print(
                    json.dumps(
                        response,
                        indent=2,
                    ),
                    file=sys.stderr,
                )

                return False

        time.sleep(5)


def main():

    if len(sys.argv) != 2:

        print(
            "Usage: python3 lightrag_ingest.py /path/to/paper.pdf",
            file=sys.stderr,
        )

        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.isfile(file_path):

        print(
            f"File does not exist: {file_path}",
            file=sys.stderr,
        )

        sys.exit(1)

    if not file_path.lower().endswith(".pdf"):

        print(
            "Error: the LightRAG research ingestion script currently "
            "expects a PDF file.",
            file=sys.stderr,
        )

        sys.exit(1)

    file_size = os.path.getsize(file_path)

    print(f"Paper: {file_path}")

    print(
        f"Size: {file_size / (1024 * 1024):.2f} MB"
    )

    print("Parser: MinerU")

    print("Processing: images + tables + equations")

    print("Chunking: paragraph semantic")

    print()
    print("Uploading to LightRAG...")

    result = upload_document(file_path)

    print()
    print("LightRAG response:")

    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    track_id = (
        result.get("track_id")
        or result.get("trackId")
        or result.get("id")
    )

    if not track_id:

        print()
        print(
            "LightRAG did not return a track ID."
        )

        return

    success = wait_for_completion(track_id)

    if not success:

        sys.exit(1)


if __name__ == "__main__":

    main()