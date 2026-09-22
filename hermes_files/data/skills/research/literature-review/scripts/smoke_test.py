#!/usr/bin/env python3
"""Smoke test for the literature review / survey workflow."""

from __future__ import annotations

import argparse
import py_compile
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    ROOT / "SKILL.md",
    ROOT / "references" / "checklists.md",
    ROOT / "references" / "phase5-paper-drafting.md",
    ROOT / "templates" / "README.md",
    ROOT / "templates" / "IEEE_Conference_Template" / "main.tex",
    ROOT / "templates" / "IEEE_Conference_Template" / "IEEE.bib",
    ROOT / "scripts" / "document_ingest.py",
    ROOT / "scripts" / "document_rag_search.py",
    ROOT / "scripts" / "document_rescan.py",
    ROOT / "scripts" / "normalize_paper_filename.py",
    ROOT / "scripts" / "build_manifest_from_arxiv_ids.py",
    ROOT / "scripts" / "create_kanban_board.py",
    ROOT / "scripts" / "check_bib_math_escapes.py",
    ROOT / "scripts" / "compile_latex.py",
]

PYTHON_SCRIPTS = [
    ROOT / "scripts" / "document_ingest.py",
    ROOT / "scripts" / "document_rag_search.py",
    ROOT / "scripts" / "document_rescan.py",
    ROOT / "scripts" / "normalize_paper_filename.py",
    ROOT / "scripts" / "build_manifest_from_arxiv_ids.py",
    ROOT / "scripts" / "create_kanban_board.py",
    ROOT / "scripts" / "check_bib_math_escapes.py",
    ROOT / "scripts" / "compile_latex.py",
]

DEPENDENCIES = [
    "arxiv",
    "semanticscholar",
    "requests",
    "habanero",
    "numpy",
    "scipy",
    "matplotlib",
]

BANNED_SURVEY_TERMS = [
    "NeurIPS",
    "ICML",
    "ICLR",
    "ACL",
    "AAAI",
    "COLM",
    "camera-ready",
    "double-blind",
    "submission",
]


def check_required_files() -> list[str]:
    errors: list[str] = []

    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"Missing required file: {path}")

    return errors


def check_python_imports() -> list[str]:
    errors: list[str] = []

    for module_name in DEPENDENCIES:
        try:
            __import__(module_name)
        except Exception as error:  # pragma: no cover - smoke test path
            errors.append(f"Missing import {module_name}: {error}")

    return errors


def check_python_syntax() -> list[str]:
    errors: list[str] = []

    for path in PYTHON_SCRIPTS:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as error:
            errors.append(f"Syntax error in {path}: {error.msg}")

    return errors


def check_template_files() -> list[str]:
    errors: list[str] = []
    main_tex = (ROOT / "templates" / "IEEE_Conference_Template" / "main.tex").read_text()
    bib_file = (ROOT / "templates" / "IEEE_Conference_Template" / "IEEE.bib").read_text()

    if "thebibliography" in main_tex:
        errors.append("Template main.tex still contains an inline thebibliography block")

    if "\\bibliography{IEEE}" not in main_tex:
        errors.append("Template main.tex does not reference IEEE.bib")

    for key in ["b1", "b2", "b3", "b4", "b5", "b6", "b7"]:
        if not re.search(rf"@\w+\{{{re.escape(key)},", bib_file):
            errors.append(f"Bibliography key missing: {key}")

    return errors


def check_survey_only_language() -> list[str]:
    errors: list[str] = []
    survey_files = [
        ROOT / "SKILL.md",
        ROOT / "references" / "phase5-paper-drafting.md",
        ROOT / "references" / "checklists.md",
        ROOT / "references" / "reviewer-guidelines.md",
        ROOT / "references" / "sources.md",
    ]

    for path in survey_files:
        contents = path.read_text()

        for term in BANNED_SURVEY_TERMS:
            if term in contents:
                errors.append(f"Survey-only language violation in {path.name}: {term}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the literature review / survey workflow.")
    parser.add_argument(
        "--live-light-rag",
        action="store_true",
        help="Also try a live LightRAG query using the query script.",
    )
    args = parser.parse_args()

    errors = []
    errors.extend(check_required_files())
    errors.extend(check_python_imports())
    errors.extend(check_python_syntax())
    errors.extend(check_template_files())
    errors.extend(check_survey_only_language())

    if args.live_light_rag:
        import subprocess

        command = [sys.executable, str(ROOT / "scripts" / "document_rag_search.py"), "survey", "workflow"]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            errors.append("Live LightRAG query failed")

    if errors:
        print("Smoke test failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())