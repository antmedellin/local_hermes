#!/bin/sh
# Creates the Kanban board for a literature review: one board per project,
# 9 cards chained parent -> child so they run strictly in order.
#
# Usage:   create_board.sh <project-slug> <seed-arxiv-id>
# Test:    ASSIGNEE=human create_board.sh <test-slug> <seed-arxiv-id>
#          (assignee "human" is not a real profile, so no worker runs anything)
set -e

SLUG="$1"
SEED="$2"
if [ -z "$SLUG" ] || [ -z "$SEED" ]; then
  echo "Usage: create_board.sh <project-slug> <seed-arxiv-id>"
  exit 1
fi

ASSIGNEE="${ASSIGNEE:-default}"
ROOT="/opt/ai_files/$SLUG"
SKILL_DIR="/opt/data/skills/research/literature_review"
KB="hermes kanban --board $SLUG"
COMMON="--assignee $ASSIGNEE --workspace dir:$ROOT --skill research/literature_review"

if hermes kanban boards list | grep -q " $SLUG "; then
  echo "Board $SLUG already exists (cards already on it are kept, not duplicated)"
else
  hermes kanban boards create "$SLUG" --default-workdir "$ROOT" \
    --description "Literature review seeded from arXiv $SEED"
  echo "Board created: $SLUG"
fi

# card <phase-key> <parent-id or -> <title> <body> [extra flags...]
# Prints the new card id. The idempotency key makes reruns return the same card.
card() {
  key="$1"; parent="$2"; title="$3"; body="$4"; shift 4
  pflag=""
  [ "$parent" != "-" ] && pflag="--parent $parent"
  $KB create "$title" --body "$body" $pflag \
      --idempotency-key "$SLUG-$key" --json "$@" \
    | grep -o '"id": "t_[0-9a-f]*"' | head -1 | cut -d'"' -f4
}

RUN="Run every command from the project root $ROOT. Use .venv/bin/python, never python3 or execute_code."

C1=$(card p1-setup - "1. Set up project" \
"Run exactly this command:
$SKILL_DIR/scripts/setup_project.sh $SLUG

Done when: the output ends with 'Setup complete: $ROOT'.
Do not create folders or the venv by hand." $COMMON)
echo "1. Setup            $C1"

C2=$(card p2-discover "$C1" "2. Discover papers from seed $SEED" \
"$RUN

Run exactly this command:
.venv/bin/python scripts/discover_papers.py --seed $SEED

Done when: documents/manifests/manifest.tsv exists. Put the three counts it prints in your completion summary.
Do not search for papers any other way and do not edit manifest.tsv. A human reviews it next." $COMMON)
echo "2. Discover         $C2"

G=$(card gate-review "$C2" "HUMAN: review manifest.tsv" \
"For a person, not a worker. This card is assigned to 'human' so no worker claims it.

1. Open $ROOT/documents/manifests/manifest.tsv
2. Delete any row whose paper is off-topic for the review
3. Complete this card:
   hermes kanban --board $SLUG complete <this card id> --summary \"manifest reviewed\"

The Download card waits until this card is done." --assignee human)
echo "   HUMAN review     $G"

C3=$(card p3-download "$G" "3. Download PDFs" \
"$RUN

Run exactly this command:
.venv/bin/python scripts/download_papers.py

Done when: the final line prints the Downloaded / Already had / Failed counts. Put that line in your completion summary. Failures are acceptable; do not try other sources." $COMMON)
echo "3. Download         $C3"

C4=$(card p4-ingest "$C3" "4. Ingest PDFs into LightRAG" \
"$RUN

Ingest every PDF in documents/renamed/, one call per file:
for f in documents/renamed/*.pdf; do .venv/bin/python scripts/document_ingest.py \"\$f\"; done

An 'HTTP 409 ... (Status: processed)' reply means that paper is already ingested. That is success, not an error. Do not delete or re-upload it.

Done when: every PDF in documents/renamed/ was either uploaded or returned 409 processed. List any other failures in your summary." \
  $COMMON --skill research/lightrag --max-runtime 12h)
echo "4. Ingest           $C4"

C5=$(card p5-outline "$C4" "5. Query LightRAG and draft the outline" \
"$RUN

Query LightRAG with:
.venv/bin/python scripts/document_rag_search.py \"<question>\"

Ask about the main themes, methods, findings, and open problems of the corpus. Write the outline to writing/outlines/outline.md using the Survey Structure in the skill.

Rules: use only what LightRAG returns. Under every section heading, list the papers (first author, year) that support it. Never add a paper that is not in documents/manifests/manifest.tsv.

Done when: writing/outlines/outline.md exists and every section lists its supporting papers." $COMMON)
echo "5. Outline          $C5"

C6=$(card p6-draft "$C5" "6. Draft manuscript sections" \
"$RUN

Copy the .tex file from templates/IEEE_Conference_Template/ to writing/drafts/main.tex, then write each section of writing/outlines/outline.md into it.

Rules: query LightRAG with scripts/document_rag_search.py for each section and write only from those results. Cite with \\\\cite{key}, using keys you will define in bibliography/references.bib. Never cite a paper that is not in documents/manifests/manifest.tsv.

Done when: every outline section has text in writing/drafts/main.tex." $COMMON)
echo "6. Draft            $C6"

C7=$(card p7-bib "$C6" "7. Verify citations and compile the bibliography" \
"$RUN

Write bibliography/references.bib with one entry for every \\\\cite key used in writing/drafts/main.tex. Take author, year, and title from documents/manifests/manifest.tsv only. Never invent metadata.

Done when: every \\\\cite key in main.tex has a matching entry in references.bib and every entry matches a manifest row. List any key you could not match in your summary." $COMMON)
echo "7. Bibliography     $C7"

C8=$(card p8-review "$C7" "8. Compile and smoke test" \
"$RUN

Run:
$SKILL_DIR/bin/tectonic writing/drafts/main.tex
.venv/bin/python scripts/smoke_test.py

Done when: main.pdf is produced and the smoke test passes. Put the page count, citation count, and any warnings in your summary." $COMMON)
echo "8. Compile/test     $C8"

echo
echo "Board $SLUG ready. Card 1 starts on the next dispatcher pass."
echo "Watch it with: hermes kanban --board $SLUG list"
