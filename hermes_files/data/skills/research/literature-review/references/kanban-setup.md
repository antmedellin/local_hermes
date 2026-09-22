# Kanban Setup for Literature Reviews

How to create, run, check, and fix the Kanban board for a literature review.

## Quick start

1. Pick a project slug (kebab-case, e.g. `capacity-constrained-learning`) and a seed arXiv ID.
2. Create the board:

```bash
docker exec -u hermes hermes /opt/data/skills/research/literature_review/scripts/create_board.sh <project-slug> <seed-arxiv-id>
```

3. Card 1 starts on the next dispatcher pass. Watch progress:

```bash
docker exec -u hermes hermes hermes kanban --board <project-slug> list
```

4. When the HUMAN review card turns `ready`, review the manifest and complete that card (see "Human review gate").

To test without running anything, prefix the assignee:

```bash
docker exec -u hermes -e ASSIGNEE=human hermes /opt/data/skills/research/literature_review/scripts/create_board.sh <test-slug> <seed-arxiv-id>
```

Remove a test board with `hermes kanban boards rm <test-slug>`.

## How the chain works

- One board per project. Each board has its own queue and dispatcher, so reviews never mix.
- On this Kanban, **parent means "must finish first."** A card stays `todo` until every parent is `done`, then moves to `ready`, then a worker claims it.
- The cards form a straight chain. Each card's only parent is the card before it:

```text
1. Setup -> 2. Discover -> HUMAN review -> 3. Download -> 4. Ingest
  -> 5. Outline -> 6. Draft -> 7. Bibliography -> 8. Compile and test
```

- There is no umbrella parent card. An umbrella parent blocks all of its children until the parent itself is done, which stalls the whole board.

## The cards

| Card | Runs | Done when |
|---|---|---|
| 1. Setup | `setup_project.sh <slug>` | Output ends with `Setup complete` |
| 2. Discover | `discover_papers.py --seed <id>` | `manifest.tsv` exists |
| HUMAN review | A person | Person completes the card |
| 3. Download | `download_papers.py` | Counts line printed |
| 4. Ingest | `document_ingest.py` per PDF | Every PDF uploaded or 409 processed |
| 5. Outline | `document_rag_search.py` queries | `writing/outlines/outline.md` with sources per section |
| 6. Draft | `document_rag_search.py` per section | Every section written in `writing/drafts/main.tex` |
| 7. Bibliography | Writes `references.bib` from the manifest | Every `\cite` key matched |
| 8. Compile and test | `tectonic`, `smoke_test.py` | `main.pdf` produced, smoke test passes |

Every worker card uses assignee `default`, workspace `dir:/opt/ai_files/<slug>`, and skill `research/literature_review`. The Ingest card also loads `research/lightrag` and has a 12 hour runtime cap.

## Human review gate

Discovery can pull in off-topic papers. The gate stops the chain so a person checks the list before anything downloads.

- The gate card is assigned to `human`. That is not a real profile, so no worker ever claims it.
- When it turns `ready`:
  1. Open `/opt/ai_files/<slug>/documents/manifests/manifest.tsv`
  2. Delete any off-topic rows
  3. Complete the card:

```bash
docker exec -u hermes hermes hermes kanban --board <slug> complete <gate-card-id> --summary "manifest reviewed"
```

Do not use `--initial-status blocked` as a hold. Tested: the dispatcher still picked the card up.

## Rules for any card you create by hand

- **Skill names are folder paths:** `research/literature_review`, `research/lightrag`. The name `research/literature-review` (category plus the hyphenated name that `skills list` shows) does not resolve, and the worker silently runs without the skill.
- **Never use `--triage`.** Triage hands the card to a specifier model that rewrites or empties the body.
- **Write a full body:** project root, the exact command, and what "done" means. One-line bodies were the main cause of confused workers.
- **Assignee must be a real profile** (`default`), except the human gate. Unknown names sit in `ready` forever.
- **Set parents at creation** with `--parent <id>`, or add them later with `hermes kanban link`.
- **Use `--idempotency-key`** so rerunning a script returns the existing card instead of a duplicate.

Template:

```bash
docker exec -u hermes hermes hermes kanban --board <slug> create "<title>" \
  --body "<full instructions>" \
  --assignee default \
  --workspace dir:/opt/ai_files/<slug> \
  --skill research/literature_review \
  --parent <previous-card-id> \
  --idempotency-key <slug>-<short-name>
```

## Checking and fixing cards

All commands start with `docker exec -u hermes hermes hermes kanban --board <slug>`.

| Goal | Command |
|---|---|
| See all cards and statuses | `list` |
| See exactly what a worker sees | `context <id>` |
| See skills, parents, events | `show <id>` |
| Read the worker's log | `log <id>` |
| See each attempt's outcome | `runs <id>` |
| Push a stuck card to ready | `promote <id>` |
| Stop a running worker | `reclaim <id>`, then `block <id>` |
| Mark a card done by hand | `complete <id> --summary "..."` |
| Remove a card | `archive <id>` |

## Cautions

- Don't start a board while a large ingest is running. Workers and ingest share the GPU.
- Cards 5 to 8 are writing tasks for the model. Check `outline.md` and `main.tex` before trusting later cards.
