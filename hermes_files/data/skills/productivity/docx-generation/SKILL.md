---
name: docx-generation
description: \"Create .docx files using python-docx via terminal.\"
version: 0.1.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [productivity, document, automation]
---

# Docx File Generation

This skill provides the procedure for creating and saving .docx files. Because the `execute_code` environment is a restricted sandbox, it does not have access to the `python-docx` library. You must use the `terminal` tool to interact with the local environment where the library is installed.

## When to Use
- Creating .docx files with specific content.
- Saving documents directly to persistent storage.

## Prerequisites
- The `python-docx` library must be installed in the environment.

## How to Run
Execute a python command via the `terminal` tool.
`python3 -c \"from docx import Document; doc = Document(); doc.add_paragraph('text'); doc.save('/opt/ai_files/file.docx')\"`

## Quick Reference
- **Primary Path:** `/opt/ai_files/`
- **Tool:** `terminal`
- **Context:** `execute_code` does NOT have `python-docx` installed.

## Procedure
1. Identify the required document content and the desired filename.
2. Construct a python command to create the document and save it.
3. Execute the command using the `terminal` tool.

## Pitfalls
- **ModuleNotFound:** `python-docx` is absent from the `execute_code` sandbox. Use `terminal`.
- **Path Issues:** Ensure target paths are absolute or relative to the intended directory.

## Verification
Run `ls -l /opt/ai_files/filename.docx` via the `terminal` tool.
