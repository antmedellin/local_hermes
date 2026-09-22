#!/bin/sh
# Creates a literature review project: folders, scripts, templates, venv, LaTeX.
# Usage: setup_project.sh <project-slug>
set -e
export UV_LINK_MODE=copy

SLUG="$1"
if [ -z "$SLUG" ]; then
  echo "Usage: setup_project.sh <project-slug>"
  exit 1
fi

SKILL_DIR="/opt/data/skills/research/literature_review"
ROOT="/opt/ai_files/$SLUG"
echo "Project root: $ROOT"

for d in documents/downloads documents/renamed documents/manifests \
         documents/processed documents/offtopic \
         writing/drafts writing/outlines writing/tables writing/figures \
         notes/literature notes/experiments notes/synthesis \
         bibliography scripts templates; do
  mkdir -p "$ROOT/$d"
done
echo "Folders created"

cp -n "$SKILL_DIR"/scripts/*.py "$ROOT/scripts/"
echo "Scripts copied (existing files kept)"

if [ -d "$SKILL_DIR/templates" ]; then
  cp -rn "$SKILL_DIR/templates/." "$ROOT/templates/"
  echo "Templates copied"
fi

# LaTeX compiler (tectonic), installed once into the skill folder
TECTONIC="$SKILL_DIR/bin/tectonic"
if [ ! -x "$TECTONIC" ]; then
  mkdir -p "$SKILL_DIR/bin"
  (cd "$SKILL_DIR/bin" && curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh)
fi
"$TECTONIC" --version && echo "LaTeX (tectonic) OK"

cd "$ROOT"
if [ ! -x .venv/bin/python ]; then
  uv venv .venv
fi
uv pip install --python .venv/bin/python -r "$SKILL_DIR/requirements.txt"

.venv/bin/python -c "import requests, arxiv, habanero, semanticscholar, matplotlib; print('Dependencies OK')"
echo "Setup complete: $ROOT"