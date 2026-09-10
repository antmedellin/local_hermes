#lightrag_ingest.py
#!/usr/bin/env python3

"""
Upload a document to LightRAG for indexing.

LightRAG handles:
    PDF parsing
    MinerU processing
    OCR
    tables
    equations
    images
    chunking
    entity/relation extraction
    Qdrant vector storage
    Neo4j graph storage

Usage:
    python3 lightrag_ingest.py /path/to/paper.pdf

Example:
    python3 lightrag_ingest.py /opt/ai_files/papers/example.pdf
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


def make_multipart_form(file_path):
    """
    Build the multipart/form-data request body manually.

    We avoid external Python packages such as requests so that
    this script can run with the standard Python installation.
    """

    boundary = uuid.uuid4().hex
    filename = os.path.basename(file_path)

    with open(file_path, "rb") as f:
        file_data = f.read()

    body = bytearray()

    # File field
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    body.extend(b"Content-Type: application/pdf\r\n\r\n")
    body.extend(file_data)
    body.extend(b"\r\n")

    # Parser options.
    #
    # [mineru-iteP] tells LightRAG to use the MinerU parser.
    # i = image processing
    # t = table processing
    # e = equation processing
    #
    # The ! option is intentionally NOT used because we want
    # LightRAG to perform entity/relation extraction.
    #
    options = json.dumps({
        "file_name": filename,
        "parser": "mineru",
        "parse_method": "auto",
        "enable_image_processing": True,
        "enable_table_processing": True,
        "enable_equation_processing": True,
    })

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        b'Content-Disposition: form-data; name="options"\r\n\r\n'
    )
    body.extend(options.encode())
    body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())

    content_type = f"multipart/form-data; boundary={boundary}"

    return bytes(body), content_type


def upload_document(file_path):
    """
    Upload a document to LightRAG.

    Returns the JSON response from LightRAG.
    """

    body, content_type = make_multipart_form(file_path)

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
            response_data = response.read().decode("utf-8")
            return json.loads(response_data)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")

        print(
            f"LightRAG returned HTTP {e.code}:",
            file=sys.stderr,
        )
        print(error_body, file=sys.stderr)

        sys.exit(1)

    except urllib.error.URLError as e:
        print(
            f"Could not connect to LightRAG: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def get_status(track_id):
    """
    Query LightRAG for the current processing status.
    """

    url = f"{LIGHTRAG_URL}/documents/track_status/{track_id}"

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        print(
            f"Status request failed with HTTP {e.code}",
            file=sys.stderr,
        )
        return None

    except urllib.error.URLError as e:
        print(
            f"Could not query LightRAG status: {e}",
            file=sys.stderr,
        )
        return None


def wait_for_completion(track_id):
    """
    Poll LightRAG until document processing finishes.
    """

    print(f"Tracking ID: {track_id}")
    print("Waiting for LightRAG ingestion to finish...")

    while True:
        status_response = get_status(track_id)

        if status_response is None:
            time.sleep(5)
            continue

        print(json.dumps(status_response, indent=2))

        # LightRAG may return the status in different nested structures.
        status = (
            status_response.get("status")
            or status_response.get("data", {}).get("status")
        )

        if status in ("processed", "completed", "success"):
            print("\nDocument successfully indexed.")
            return True

        if status in ("failed", "error"):
            print("\nDocument ingestion failed.", file=sys.stderr)
            return False

        time.sleep(5)


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python3 lightrag_ingest.py /path/to/document.pdf",
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
            "Warning: this script is intended primarily for PDF research papers.",
            file=sys.stderr,
        )

    print(f"Uploading: {file_path}")

    result = upload_document(file_path)

    print("\nLightRAG upload response:")
    print(json.dumps(result, indent=2))

    # LightRAG normally returns a tracking ID for asynchronous ingestion.
    track_id = (
        result.get("track_id")
        or result.get("trackId")
        or result.get("id")
    )

    if not track_id:
        print(
            "\nNo tracking ID was returned.",
            file=sys.stderr,
        )
        print(
            "The document may have been processed synchronously.",
            file=sys.stderr,
        )
        return

    success = wait_for_completion(track_id)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()