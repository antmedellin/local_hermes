#!/usr/bin/env python3

"""Clef Decision Engine
************************
Communicates w/ Clef-Flash through Ollama System One

Responsibilities: 
    1. Submit structured identity-evaluation requests.
    2. Validate the response structure.
    3. Preserve model probabilities and confidence as raw metadata.
    4. Return a normalized response for the evaluation layer.

Important safeguards:
    - Does not access PostgreSQL
    - Does not modify reconciliation files
    - Does not assign faculty IDs
    - DOes not make final identity decisions
"""
import json
import urllib.request
import urllib.error

#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Configuration:::
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

DEFAULT_ENDPOINT = "http://localhost:11434/v1/systemone"
DEFAULT_MODEL = "clef-flash"
DEFAULT_TIMEOUT = 120

# ============================================================
# ALLOWED MODEL DECISIONS
# ============================================================

IDENTITY_CHOICES = {
    "same_person",
    "different_person",
    "insufficient_evidence",
}


# ============================================================
# SYSTEM INSTRUCTIONS
# ============================================================

SYSTEM_INSTRUCTIONS = """
You are evaluating authorship identity records for an academic
research ledger.

Your task is to assess whether a publication author and a
current faculty member represent the same person.

Use only the evidence explicitly supplied in the request.

Important rules:

1. Similar names alone do not establish identity.

2. A matching faculty ID is relevant evidence, but it must
   be considered alongside the author name and any conflicting
   information.

3. A missing middle name, middle initial, accent, or minor
   spelling variation may be consistent with the same person.

4. A conflicting surname or substantially different name
   requires caution.

5. Publication-level faculty associations must not be treated
   as independent confirmation when they originate from the
   same underlying source record.

6. Do not invent biographical information, publication
   associations, identities, or faculty IDs.

7. If the supplied evidence does not establish identity,
   choose insufficient_evidence.

8. Do not recommend changing the original source data.

Your answer must use the supplied identity choices.
"""


# ============================================================
# REQUEST BUILDER
# ============================================================

def build_request(evidence, model=DEFAULT_MODEL):
    """
    Construct a System One request.

    evidence should be a JSON-serializable dictionary containing
    the author, candidate faculty, publication, and reconciliation
    information.
    """

    return {
        "model": model,

        "state": {
            "identity_evaluation": evidence,
        },

        "questions": {
            "identity": {
                "type": "choice",

                "instructions": (
                    "Evaluate whether the publication author and "
                    "candidate faculty member represent the same "
                    "researcher. Consider conflicting information "
                    "and evidence provenance."
                ),

                "criteria": {
                    "same_person": (
                        "The supplied evidence supports that both "
                        "records identify the same researcher."
                    ),

                    "different_person": (
                        "The supplied evidence supports that these "
                        "records identify different researchers."
                    ),

                    "insufficient_evidence": (
                        "The supplied evidence is insufficient to "
                        "establish whether these records identify "
                        "the same researcher."
                    ),
                },
            }
        },
    }


# ============================================================
# RESPONSE VALIDATION
# ============================================================

def validate_response(response):
    """
    Validate the minimum expected System One response structure.

    The model's confidence and probabilities are preserved as
    returned. They are not interpreted as calibrated accuracy.
    """

    if not isinstance(response, dict):
        raise ValueError("System One response must be a JSON object.")

    answers = response.get("answers")

    if not isinstance(answers, dict):
        raise ValueError("System One response is missing answers.")

    identity = answers.get("identity")

    if not isinstance(identity, dict):
        raise ValueError("System One response is missing identity answer.")

    choice = identity.get("choice")

    if choice not in IDENTITY_CHOICES:
        raise ValueError(
            f"Unexpected identity choice: {choice!r}"
        )

    probabilities = identity.get("probabilities", {})

    if not isinstance(probabilities, dict):
        probabilities = {}

    return {
        "model": response.get("model"),

        "choice": choice,

        "confidence": identity.get("confidence"),

        "probabilities": probabilities,

        "usage": response.get("usage"),

        "raw_response": response,
    }

# ============================================================
# SYSTEM ONE REQUEST
# ============================================================
def evaluate_identity(
    evidence,
    endpoint=DEFAULT_ENDPOINT,
    model=DEFAULT_MODEL,
    timeout=DEFAULT_TIMEOUT,
):
    """
    Submit an identity evaluation to Ollama System One.

    Returns a validated, normalized response.

    Raises an exception if the endpoint is unavailable,
    the request fails, or the response is invalid.
    """
    payload = build_request(
        evidence=evidence,
        model=model,
    )
    request_data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=request_data,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(
            f"System One HTTP error {exc.code}: {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not connect to System One: {exc.reason}"
        ) from exc
    try:
        parsed_response = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "System One returned invalid JSON."
        ) from exc
    return validate_response(parsed_response)

# ============================================================
# BASIC CONNECTION TEST
# ============================================================
if __name__ == "__main__":
    test_evidence = {
        "author": {
            "name": "Horacio Vazquez",
            "faculty_id": "1451316",
        },
        "candidate_faculty": {
            "name": "Horacio Vasquez",
            "faculty_id": "1451316",
        },
        "publication": {
            "title": (
                "Simple device for electromagnetic interference "
                "shielding effectiveness measurement"
            ),
            "year": 2009,
        },
        "reconciliation": {
            "classification": "HIGH_SIMILARITY",
            "mapped_faculty_id": "1451316",
            "confidence": "MEDIUM",
            "evidence": (
                "Faculty ID matches and name similarity is high."
            ),
        },
    }
    print("=" * 65)
    print("CLEF SYSTEM ONE CONNECTION TEST")
    print("=" * 65)

    try:
        result = evaluate_identity(test_evidence)
        print(json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ))
    except Exception as exc:
        print(f"ERROR: {exc}")
