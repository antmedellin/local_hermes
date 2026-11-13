# Research Ledger: Human and Hermes Operations Guide

This guide is the operating procedure for the current department-ingestion scripts.
Humans can copy the commands below. Hermes agents should follow the execution
contract in [Agent execution contract](#agent-execution-contract) and use the same
commands, flags, logs, and completion checks.

PostgreSQL is the authoritative structured ledger. LightRAG provides retrieval
and knowledge-graph processing for the paper abstracts selected from PostgreSQL.
An accepted LightRAG request is not evidence that its documents finished processing.

## Contents

- [Scope and paths](#scope-and-paths)
- [Setup and preflight](#setup-and-preflight)
- [Department configuration](#department-configuration)
- [Run recipes](#run-recipes)
- [Flags and compatibility](#flags-and-compatibility)
- [Pipeline stages and artifacts](#pipeline-stages-and-artifacts)
- [Validation manifests and approval](#validation-manifests-and-approval)
- [Department identity and LightRAG behavior](#department-identity-and-lightrag-behavior)
- [Logs and completion checks](#logs-and-completion-checks)
- [Recovery and troubleshooting](#recovery-and-troubleshooting)
- [Agent execution contract](#agent-execution-contract)
- [Maintenance boundaries](#maintenance-boundaries)

## Scope and paths

All shell examples run **on the host, from the `local_hermes` repository root**.
The root is commonly `~/local_hermes`; substitute the actual checkout if different.
An agent running inside a container must first establish a working execution
context with access to this checkout, its dependencies, PostgreSQL, and LightRAG.
Do not assume container `localhost` reaches host services.

| Item | Repository-relative path |
|---|---|
| This guide | `hermes_files/data/skills/research/ledger/README.md` |
| Ledger scripts | `hermes_files/data/skills/research/ledger/scripts/` |
| Department configs and artifacts | `hermes_files/data/skills/research/ledger/data/<slug>/` |
| Dependencies | `hermes_files/data/skills/research/ledger/requirements.txt` |
| Schema | `hermes_files/data/skills/research/ledger/schema.sql` |
| Python environment | `hermes_files/ai_files/.venv/` |
| Abstract ingestion script | `hermes_files/data/skills/research/lightrag/scripts/maie_abstract_ingest.py` |

Despite its filename, the updated `maie_abstract_ingest.py` supports departments
identified through PostgreSQL and their ledger configs. Keep this filename until
all callers are updated together.

Current department folders include `cive`, `csci`, `ece`, `ies`, and `maie`.
The batch runner discovers immediate subfolders containing `config.yaml` and
excludes `raw` and `template`. It does not discover departments from university
websites or generate missing department configs.

The automated path covers discovery, enrichment, reconciliation, ledger import,
and **abstract** ingestion. It does not automatically download or ingest PDFs,
populate topic tables, or perform retrieval-quality tests.

## Setup and preflight

### First-time initialization

Start the repository's PostgreSQL service before initialization. Start LightRAG
before requesting LightRAG ingestion. Use the repository's existing service setup;
this guide does not assume container names or a particular Compose launch command.

```bash
cd ~/local_hermes
docker ps
python3 hermes_files/data/skills/research/ledger/scripts/initialize_ledger.py
source hermes_files/ai_files/.venv/bin/activate
python -c "import psycopg2, yaml; print('Ledger dependencies OK')"
```

The initializer creates or reuses `hermes_files/ai_files/.venv`, installs ledger
requirements, and applies `schema.sql` with `ON_ERROR_STOP` in one transaction.
It finds the running PostgreSQL Compose service by its service label and network
`local-hermes_backend`; zero or multiple matches stop initialization. Use
`initialize_ledger.py --help` for network, container, repository, and database
options. A matching existing schema can emit normal `already exists, skipping`
notices. Initialization is not needed before every ingestion run.

If Python reports that `venv` or `ensurepip` is unavailable, install the appropriate
Python venv package for the host before rerunning initialization.

### Subsequent sessions

```bash
cd ~/local_hermes
source hermes_files/ai_files/.venv/bin/activate
python -c "import sys; print(sys.executable)"
```

The executable should be inside `hermes_files/ai_files/.venv`. Agents can avoid
shell activation by invoking `./hermes_files/ai_files/.venv/bin/python` directly;
child stages use the parent's `sys.executable`.

Verify that the checkout contains matching updated versions of:

- `ingest_department.py` and `ingest_all_departments.py`;
- `db_dry_run.py` and `import.py` with `--allow-count-mismatch` support;
- `validation_manifest.py` with timestamped backups and `--auto-approve`;
- `maie_abstract_ingest.py` with config-based department resolution.

Use each script's `--help` to confirm the installed options when versions differ.

### Connections

| Setting | Current behavior |
|---|---|
| PostgreSQL host-side defaults | `localhost:5432`, database/user/password `rag` |
| PostgreSQL overrides for importer, batch ID lookup, department ID lookup, and updated abstract ingester | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| Database dry run | Uses its own `DB_CONFIG`; check that file when changing connections |
| LightRAG API | Updated abstract script currently uses `http://localhost:9621` |
| Initializer connectivity check | Executes `psql` inside the selected Docker container |

A successful initializer check does not establish host-side Python connectivity.
The abstract script does not currently expose a LightRAG URL, token, or workspace
CLI flag. Configure its connection code for other execution environments; do not
invent unsupported flags. Never include passwords or tokens in shared logs.

## Department configuration

Each department needs its own `data/<slug>/config.yaml`. Keep the folder name,
`department_slug`, and output path consistent. Use the existing source-compatible
config or `data/template/config.yaml` as the starting point if present. Review its
source selectors before running discovery; changing just the department name is
not enough to select the correct roster.

| Field | Requirement |
|---|---|
| `institution` | Matches the institution stored in PostgreSQL |
| `department_name` | Full department name; matches PostgreSQL identity |
| `department_slug` | Stable lowercase slug; abstract ingestion accepts letters/digits separated by hyphens or underscores |
| `department_url` | Official department URL |
| `faculty_url` | Official roster URL |
| `output_directory` | Prefer `hermes_files/data/skills/research/ledger/data/<slug>` relative to repository root |
| `sources.faculty` | Source-specific settings in the format expected by discovery/enrichment/import |
| `validation` | Mapping; `{}` supports preparation, but direct import without a manifest needs its required count keys |
| `validation_manifest` | Set to `validation_manifest.json` to import using the generated manifest's counts and approval |

The orchestrator accepts a mapping or list for `sources.faculty`, but the current
importer accesses it as a mapping. Use a mapping for workflows that include import,
and preserve the fields required by the source-specific scripts.

Recommended identity/output portion, to merge into a real source config:

```yaml
institution: University of Texas Rio Grande Valley
department_name: Department of Civil Engineering
department_slug: cive
department_url: <official department URL>
faculty_url: <official faculty URL>
output_directory: hermes_files/data/skills/research/ledger/data/cive
validation_manifest: validation_manifest.json
validation: {}
# Keep the working sources.faculty mapping from this department's config.
```

This excerpt is not a complete runnable source configuration. Do not invent
faculty, publication, or expected-count data to fill it out.

Use the canonical repository-relative output path. The orchestrator recognizes
legacy `ledger/data/...` paths, but every child script may not normalize them in
the same way. The manifest generator always writes `validation_manifest.json`
inside the configured output directory; avoid configuring a different manifest
filename unless the writer and callers are updated together.

## Run recipes

Commands below assume setup is complete and the virtual environment is active.
The full-run examples explicitly enable artifact replacement, count warnings,
manifest auto-approval, PostgreSQL writes, and LightRAG writes. Choose the recipe
that matches the requested scope. Omit `--allow-count-mismatch` for strict baseline
count comparisons; use the manual manifest workflow if auto-approval is unwanted.

### Preview a full department run

```bash
python hermes_files/data/skills/research/ledger/scripts/ingest_department.py \
  --config hermes_files/data/skills/research/ledger/data/cive/config.yaml \
  --allow-count-mismatch \
  --allow-db-write \
  --allow-overwrite \
  --auto-approve \
  --allow-lightrag-write \
  --plan
```

`--plan` validates configuration and shows stages without running them. The
LightRAG command may show `<lookup-after-import>` because no database lookup is
performed in plan mode. A plan cannot prove network or database availability.

### Full run for one department

```bash
python hermes_files/data/skills/research/ledger/scripts/ingest_department.py \
  --config hermes_files/data/skills/research/ledger/data/cive/config.yaml \
  --allow-count-mismatch \
  --allow-db-write \
  --allow-overwrite \
  --auto-approve \
  --allow-lightrag-write
```

Replace `cive` with the selected department folder. Department IDs are resolved
from PostgreSQL after import. No fixed mapping such as CIVE=4 or MAIE=1 is used.

### Full run for every configured department

```bash
python hermes_files/data/skills/research/ledger/scripts/ingest_all_departments.py \
  --allow-count-mismatch \
  --allow-db-write \
  --allow-overwrite \
  --auto-approve \
  --allow-lightrag-write
```

Add `--plan` to preview. The batch runs departments sequentially. For each, it
runs the ledger pipeline first; after success, it looks up the actual database ID
and invokes the child orchestrator in LightRAG-only mode. Failed departments are
recorded and remaining departments continue. Add `--stop-on-error` to stop at the
first failure. A batch failure does not roll back departments already committed.

### Selected departments or retry a failed subset

```bash
python hermes_files/data/skills/research/ledger/scripts/ingest_all_departments.py \
  --departments cive csci ece ies \
  --allow-count-mismatch \
  --allow-db-write \
  --allow-overwrite \
  --auto-approve \
  --allow-lightrag-write
```

This reruns preparation and ledger import for the subset. It is not a resume from
the last completed stage. For a LightRAG-only failure, use the next recipe instead.

### LightRAG only after a successful ledger import

```bash
python hermes_files/data/skills/research/ledger/scripts/ingest_department.py \
  --config hermes_files/data/skills/research/ledger/data/cive/config.yaml \
  --lightrag-only \
  --allow-lightrag-write
```

The ID is looked up from the config's institution and department name. An explicit
`--department-id 6` can override lookup, but the abstract script still verifies
that the selected database department matches the config. IDs are database data;
never guess them or reuse an old installation's mapping.

### Ledger import without LightRAG

Use the full single-department or batch command and omit `--allow-lightrag-write`.
The log should show `LightRAG: DISABLED`. Successful ledger import alone does not
create LightRAG documents.

### Preparation without database access

```bash
python hermes_files/data/skills/research/ledger/scripts/ingest_department.py \
  --config hermes_files/data/skills/research/ledger/data/cive/config.yaml \
  --prepare-only \
  --allow-overwrite
```

This writes local artifacts and may query upstream sources. It skips database dry
run, import, and LightRAG. For normal execution without `--prepare-only`, omitting
write flags still runs preparation and the read-only database check; it is not a
no-op or a plan.

### Refresh source caches

Add `--refresh` to a single-department or batch preparation/full run. It is forwarded
to `enrich_faculty.py`; it is not a general cache purge or LightRAG reingestion flag.

## Flags and compatibility

| Flag | Scripts | Meaning |
|---|---|---|
| `--config PATH` | Department, manifest, dry run, import, abstract | Select config; abstract also requires the correct database ID when called directly |
| `--plan` | Department, batch | Preview without executing pipeline stages |
| `--prepare-only` | Department | Local/source preparation only; no database checks/writes |
| `--allow-db-write` | Department, batch | Enable PostgreSQL import |
| `--allow-lightrag-write` | Department, batch | Enable abstract ingestion |
| `--allow-overwrite` | Department, batch | Allow replacement of existing expected preparation artifacts |
| `--allow-count-mismatch` | Department, batch, dry run, import | Warn on configured/manifest baseline count differences; preserve other checks |
| `--auto-approve` | Department, batch | Generate and auto-approve a fresh manifest immediately before import |
| `--auto-approve --write` | Manifest | Write a fresh approved manifest directly |
| `--lightrag-only` | Department | Skip preparation and ledger import |
| `--department-id N` | Department, abstract | Explicit database ID for LightRAG |
| `--department-slug SLUG` | Abstract | Stable source slug when no ledger config is available |
| `--dry-run` | Abstract | Inspect PostgreSQL and LightRAG inventory without submitting or updating data |
| `--write` | Manifest | Write instead of only printing the report |
| `--departments SLUG ...` | Batch | Restrict discovered configs to selected folders |
| `--stop-on-error` | Batch | Stop after the first failed department |
| `--repo PATH` | Batch, initializer | Explicit checkout location |

Compatibility rules:

- Orchestrator `--auto-approve` requires `--allow-db-write`, including in plans.
- Standalone manifest `--auto-approve` requires `--write`.
- Full-run `--allow-lightrag-write` requires `--allow-db-write`.
- Department `--lightrag-only` requires `--allow-lightrag-write`; it cannot be
  combined with `--prepare-only` or `--allow-db-write`.
- `--prepare-only` cannot be combined with database or LightRAG writes.
- The batch runner has no `--lightrag-only`, `--prepare-only`, or automatic
  `--resume` flag. Use the department runner for those partial workflows.

## Pipeline stages and artifacts

The single-department orchestrator executes these stages in order. All scripts
in this table receive `--config`; LightRAG also receives the resolved database ID.

| Order | Script | Result / role |
|---|---|---|
| 1 | `discover_faculty.py` | `faculty.json`: department roster |
| 2 | `enrich_faculty.py` | `faculty_enriched.json`; source responses may be cached in `raw/` |
| 3 | `normalize.py` | `faculty_normalized.json`: normalized faculty/publications |
| 4 | `key_reconcile.py` | Source identity/key reconciliation diagnostics |
| 5 | `reconcile.py` | Faculty/publication reconciliation diagnostics |
| 6 | `reconcile_authorship.py` | `authorship_reconciliation.json` |
| 7 | `build_reconciled.py` | `faculty_reconciled.json` |
| 8 | `validate.py` | `validation_report.json` |
| 9 | `db_dry_run.py` | Read-only schema, canonicalization, relationship, and count checks |
| 10, if auto-approve enabled | `validation_manifest.py --write --auto-approve` | Fresh hashes/counts/approval in `validation_manifest.json`; backs up old manifest |
| 11, if database writes enabled | `import.py` | Department, professor, canonical paper, and authorship rows |
| 12, if LightRAG enabled | `maie_abstract_ingest.py` in sibling LightRAG scripts folder | Inventory, submit missing abstracts, poll and verify |

Preparation-only skips stages 9–12. Manual manifest review is outside the
orchestrator's automatic stage sequence. Diagnostics can contain warnings even
when their script exits successfully; inspect the relevant report when evaluating
source quality. The orchestrator validates declared JSON outputs for existence
and parseability; that is not an independent guarantee of their research accuracy.

Generated department artifacts belong under `ledger/data/<slug>/`, not under
`ledger/` or `ledger/scripts/`. The batch summary belongs directly under `ledger/data/`.
The canonical filenames are `faculty_normalized.json` and `faculty_reconciled.json`;
older examples using `normalized.json`, `reconciled.json`, or `publications.json`
do not describe the current orchestrated outputs.

## Validation manifests and approval

Set `validation_manifest: validation_manifest.json` in the department config to
make the importer use the manifest's expected counts and approval. Without this
setting, the importer reads the `validation` mapping instead; merely creating a
manifest does not change that selection. The database dry run still uses the
config's `validation` mapping.

The manifest records hashes of `faculty_reconciled.json` and
`authorship_reconciliation.json` plus these expected counts:

- `expected_faculty_count`
- `expected_publication_count`
- `expected_unique_dm_record_count`
- `expected_reconciliation_decision_count`
- `expected_canonical_publication_count`
- `expected_publication_merge_group_count`
- `expected_department_author_occurrence_count`
- `expected_canonical_authorship_count`

Source publications, canonical papers, source author occurrences, and canonical
authorships are different quantities. Duplicate records can legitimately collapse
to one paper or relationship. Never substitute a canonical count for a source count.
Expected counts are dataset-specific; do not copy historic MAIE numbers into another config.

`--allow-count-mismatch` downgrades baseline count differences to warnings. It
does not bypass manifest approval, hash matching, schema checks, authorship
classification rules, relationship checks, or final database verification.

### Automatic approval

The full-run `--auto-approve` stage runs **after preparation and the database dry
run, immediately before import**. The old manifest is preserved as
`validation_manifest.<UTC-timestamp>.bak.json`; the new current file is written
as `validation_manifest.json`.

The approval record includes:

```json
{
  "reviewer": "<current operating-system username>",
  "approved_at_utc": "<UTC timestamp>",
  "method": "auto_approve_cli",
  "auto_approved": true,
  "requested_by_user": true
}
```

This records an explicit CLI request for automatic approval. It is not evidence
of a separate human review, and the username identifies the account running the
script. If Hermes runs under a service account, that account will be recorded.
The department log also records `auto_approve_requested_by_user`.

Standalone generation and auto-approval:

```bash
python hermes_files/data/skills/research/ledger/scripts/validation_manifest.py \
  --config hermes_files/data/skills/research/ledger/data/cive/config.yaml \
  --write \
  --auto-approve
```

### Manual review and approval

1. Finish preparation and run the database dry run; inspect the artifacts.
2. Generate a pending manifest with `validation_manifest.py --config ... --write`
   and omit `--auto-approve`.
3. Review its counts, classification breakdown, duplicate groups, and occurrence
   comparisons. Set `status` to `approved` and `approval` to an object containing
   `reviewer` and `approved_at_utc`; an explicit `method: manual_review` can record
   how approval occurred. Leave automatic-approval claims out of a manual record.
4. Run the importer directly, without regenerating preparation artifacts:

```bash
python hermes_files/data/skills/research/ledger/scripts/import.py \
  --config hermes_files/data/skills/research/ledger/data/cive/config.yaml
```

Add `--allow-count-mismatch` only when accepting known baseline count differences.
Then use the LightRAG-only recipe if requested. Regenerating source artifacts after
approval changes their hashes and requires a new manifest and approval.

## Department identity and LightRAG behavior

The ledger identifies departments by `institution` and `department_name`. Numeric
`department_id` values are assigned by PostgreSQL and may differ across installations.
The current orchestration resolves them from the database; no MAIE=1, CIVE=4,
CSCI=3, or other static mapping should be introduced.

The abstract ingester verifies the database ID against the supplied config and
uses its stable slug for `file_sources`, formatted as `<slug>-paper-<paper_id:06d>`
(for example, `cive-paper-000123`). Keep slugs stable to preserve inventory matching.
An abstract-script call without a config can search sibling ledger configs for a
matching database identity; supplying the config explicitly is preferred. Its
standalone ID default is still `1`, so always pass the actual ID when invoking
that script directly. The department runner handles this for you.

The script selects papers with nonempty abstracts and at least one author in the
selected department. It includes title, year, DOI, known authors, abstract, and
PostgreSQL paper ID in each text document. It does not restrict abstracts to papers
without PDFs. Authors come from stored ledger authorships and need not represent
every external coauthor of the original publication.

Current processing behavior:

- Inventory is read from `/documents/paginated` and matched by `file_path` against
  each expected source identifier.
- Already `processed` sources are skipped; only missing sources are submitted.
- Explicit `content_hash` duplicate metadata is resolved through `original_doc_id`.
  A department source is covered only if the referenced original is verified as
  `processed` in LightRAG. The original ID is printed for audit; the failed duplicate
  marker itself is not rewritten, deleted, or described as newly processed.
- Existing pending sources are awaited by refreshing inventory, without resubmission,
  up to the batch wait limit. `parsing` is a normal intermediate state too. Unavailable
  duplicate originals remain pending and eventually time out rather than being assumed
  successful. A dry run reports these states without waiting.
- Genuine failed sources still block new submissions after existing pending work has
  finished. Their returned error messages are printed for diagnosis.
- Missing texts are sent to `/documents/texts` in batches of 10. Each returned
  track is polled through `/documents/track_status/<track_id>` every 5 seconds,
  for up to 900 seconds per batch.
- Every expected source must be processed or covered by a verified processed
  duplicate original. The script waits for the rest of a submitted batch to reach
  terminal states even if one source fails. HTTP acceptance, a track ID, or a
  temporarily empty status response is not final success. A timeout can still leave
  background work active; use batch `--stop-on-error` to prevent advancing after it.
- Zero eligible abstracts is a successful no-op, not proof of a populated corpus.
- Global `research.papers.lightrag_status` and `lightrag_track_id` are deliberately
  left unchanged. Use LightRAG inventory, track responses, and run output for status.

The same paper can belong to multiple departments. Source names are department
scoped, while text bodies may be identical for a shared paper. LightRAG can create
failed duplicate markers for these submissions. The ingester follows explicit
content-hash duplicate metadata to verify the existing original, so a shared paper
need not be processed again. It does not alter text to defeat content deduplication.
Repeated markers for the same source/original are tolerated; conflicting identities
still stop the run for review.
Processed inventory does not by itself detect changed abstract content under an
existing source ID; updating already-ingested content requires a separate policy.

## Logs and completion checks

| Log | Location / meaning |
|---|---|
| Department run | `ledger/data/<slug>/ingest_run_<UTC-run-id>.json` |
| Batch summary | `ledger/data/ingest_all_run_<UTC-run-id>.json` |
| Manifest history | `ledger/data/<slug>/validation_manifest.<UTC-timestamp>.bak.json` |
| Child output / track IDs | Terminal output; capture it when persistent diagnostic detail is needed |

Batch entries record `folder`, `status`, `stage` (`ledger` or `lightrag`), errors,
and the department ID when resolved for LightRAG. Department logs contain commands,
return codes, stage timing/status, and the overall error when available. They do
not embed full stdout/stderr. A lookup failure can occur before a stage record is
appended; inspect the department-level error too.

Read a known log:

```bash
python -m json.tool <path-to-run-log.json>
```

To preserve full terminal output in addition to JSON logs, Bash users/agents can
run a selected recipe with this pattern:

```bash
set -o pipefail
# Replace the command with the selected recipe and its flags.
python hermes_files/data/skills/research/ledger/scripts/ingest_all_departments.py \
  --plan 2>&1 | tee /tmp/ledger-plan.log
```

`pipefail` preserves the pipeline's failure status instead of reporting only
`tee` success. Copy diagnostics to a durable project location if needed.

Completion requires checking the requested scope:

| Scope | Required evidence |
|---|---|
| Plan | Exit 0 and displayed intended stages; no claim that ingestion ran |
| Preparation | Stages succeeded and expected JSON artifacts exist/parse |
| Ledger import | Import committed, authorship relationship verification passed, final department counts passed |
| Abstract ingestion | Inventory and batch verification show all eligible sources processed, or an explicit zero-abstract no-op |
| Full department | Both ledger and requested LightRAG stages succeeded |
| Batch | Every requested department succeeded; `not_run` is empty |
| Retrieval readiness | Separate document-specific query returns the correct source and abstract facts |

A batch exits nonzero if any department fails. A final department's `Run status:
succeeded` does not mean the entire batch succeeded. Report successful, failed,
and unrun departments separately. A LightRAG failure occurs after the ledger
import has committed; there is no cross-system transaction or global batch rollback.

## Recovery and troubleshooting

| Symptom | Action |
|---|---|
| `LightRAG: DISABLED` | Add `--allow-lightrag-write` to a full run, or use LightRAG-only after ledger success |
| Hardcoded `Supported department IDs are ...` error | Install the generalized abstract script and matching orchestrator; never substitute an incorrect ID |
| Manifest is stale | Preparation changed a hashed artifact. Regenerate/approve after preparation, then import directly, or use the full auto-approve recipe |
| Manifest is pending review | Review it or explicitly request `--auto-approve`; do not falsify a manual approval |
| Baseline counts differ | Compare source changes and canonicalization. If accepted, use `--allow-count-mismatch`; schema and relationship failures remain blocking |
| Post-import authorships exceed expectation | Inspect existing links and duplicate papers, particularly missing years; do not disable the final verification or delete unrelated data |
| Multiple undated papers share a title | Updated importer stops with paper IDs. Review and reconcile duplicates before retrying |
| Existing artifact overwrite refused | Inspect existing output; use `--allow-overwrite` for an intended rerun |
| Existing LightRAG sources pending | LightRAG-only waits without resubmission; inspect the existing tracks if it times out |
| Existing LightRAG sources failed | Confirmed content-hash duplicates reuse a verified processed original. For other failures, inspect service errors and repair through the supported workflow |
| LightRAG polling timed out | Inspect the existing track; background processing may continue. Do not blindly resubmit |
| Department failed at `ledger` in batch | Inspect that department's log and child terminal output; LightRAG was not attempted for it |
| Department failed at `lightrag` in batch | Ledger already succeeded. Retry LightRAG-only rather than repeating discovery/import |
| PostgreSQL connection fails | Check host/port and caller execution context; initializer's in-container connection test is separate |
| Missing dependency | Use the documented venv and rerun dependency installation |

A ledger import uses a PostgreSQL transaction and rolls back on failure; earlier
successful stages and earlier committed runs remain. The importer now reuses
existing same-title undated papers rather than relying on a unique constraint
with a null year. It still stops on multiple existing undated matches. Do not
claim that reruns can resolve every historical duplicate or dataset discrepancy.

For LightRAG inventory inspection without submitting documents, use the actual
ID from a log/database lookup (the ID below is only an example):

```bash
python hermes_files/data/skills/research/lightrag/scripts/maie_abstract_ingest.py \
  --config hermes_files/data/skills/research/ledger/data/cive/config.yaml \
  --department-id 6 \
  --dry-run
```

Dry run still queries the database and LightRAG, resolves duplicate references,
and reports blocking pending/genuinely failed sources. It is different from the orchestrator's offline `--plan`.

## Agent execution contract

This section tells Hermes how to operate the same workflow. It does not implement
a separate scheduler or agent plugin. Invoke the repository's scripts through a
terminal with the execution context established in preflight.

### Inputs to resolve

| Input | Accepted values / resolution |
|---|---|
| Repository | Existing checkout containing ledger scripts and department configs |
| Department scope | One config, explicit folder list, or all discovered configs |
| Operation | Plan, prepare, ledger, full, or LightRAG-only |
| Source refresh | Cached enrichment by default; `--refresh` when requested |
| Existing artifacts | Replace only when an intended rerun includes that scope |
| Baseline count differences | Strict by default; pass the override when authorized |
| Manifest approval | Manual or explicit user-requested auto-approval |
| Database and LightRAG writes | Include only the stages authorized by the task |

### Execution procedure

1. Resolve scope and reuse decisions already authorized in the conversation or
   applicable standing instructions. Do not ask for the same approval again.
   If a necessary scope decision is missing, identify that decision specifically;
   read-only inspection and planning can proceed.
2. Confirm the host/container context, checkout root, venv, required scripts, and
   target configs. Use actual source settings; do not fabricate missing data.
3. Select the matching run recipe. For multi-department work, use the batch runner
   unless the task only requires LightRAG recovery. Do not launch concurrent writers
   against the same department or run a second copy while the first is active.
4. A plan can validate the intended stage list without database access. In execution,
   use the documented write and approval flags according to the authorized scope.
5. Run from the repository root using the venv's Python. Keep the process/session
   available while it runs; stream or capture diagnostics and retain any track IDs.
   Do not interpret tool-call timeout alone as pipeline failure or start a duplicate run.
6. Inspect exit status plus department/batch logs. If a child fails, use its underlying
   error, not just `returned non-zero exit status`, to select a recovery action.
7. Retry the smallest failed scope. Preserve committed ledger data and processed
   LightRAG sources. Do not bypass schema, identity, hash, or relationship checks
   merely to obtain a success status.
8. Report the completion record below. Distinguish no-op, submitted, processed,
   and retrieval-tested outcomes. Do not claim unperformed retrieval verification.

### Suggested completion record

Use this schema for an agent's final report or an external automation consumer.
It is a reporting convention, not a file automatically produced by the scripts.
Populate values from observed logs and evidence; use `not_checked` when needed.

```json
{
  "operation": "full",
  "requested_departments": ["cive", "csci"],
  "succeeded": [],
  "failed": [],
  "not_run": [],
  "logs": [],
  "auto_approval_requested": false,
  "count_mismatches_allowed": false,
  "lightrag_result": "not_checked",
  "retrieval_verification": "not_checked",
  "next_action": null
}
```

A request to run once does not create a recurring schedule. Scheduling is separate
from these scripts; preserve the same interpreter, working directory, authorized
flags, and logs if a user separately requests unattended recurring runs.

## Maintenance boundaries

- Keep raw source identifiers and authorship provenance. The current importer
  allows `EXACT`, `NAME_VARIANT`, `INITIAL_VARIANT`, and `NAME_WITHOUT_DM_ID`;
  historical mismatches and review-only classifications are not silently imported.
- Preserve available research-interest metadata. Topic assignment and its evidence
  require a separate implemented step; topic tables are not populated by this runbook.
- Core import does not create `research.documents` or `research.ingestion_runs` rows.
  Zero counts there do not prove LightRAG abstract ingestion failed.
- Abstract ingestion does not prove full-text access. Answers must stay within the
  evidence actually ingested. PDF acquisition/ingestion is a separate workflow;
  verify its script and CLI before using it.
- Retrieval verification is separate from processing status. Test a known paper's
  title, authors, and abstract facts using the deployed retrieval interface and
  record the cited source. Do not invent unverified search CLI commands.
- `final_integrity.py` is not in the orchestrated stage list. Legacy helper scripts
  may retain MAIE-specific paths or counts; inspect/generalize them before applying
  them to other departments. Do not add them to automated runs based on filename alone.
- The child scripts and JSON logs are the implementation reference when local code
  differs from this guide. Update this README alongside CLI or filename changes.
