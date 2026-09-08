---
name: kanban-troubleshooting
title: KanbanTroubleshooting
description: "Troubleshoot data mismatches between local and remote view."
---

# Troubleshooting Kanban View Discrepancies
The term "troubleshooting" refers to resolving data mismatches between the local Hermes dashboard and the backend database. This skill ensures consistent visibility across different interface layers.

## When to Use
- When a task appears as "unassigned" or "missing" on the dashboard.
- When local counts differ from remote tracking.
- When the `herms kanban` command yields inconsistent results.
- When a task's status does not sync with the server.

## Prerequisites
- `herms` CLI installed.
- Access to the local `kanban.db`.

## How to Run
Use standard commands to synchronize state:
- View local items: `herms kanban list`
- Check status: `herms kanban list --status ready`
- Check specific task: `herms kanban show <task_id>`
- Audit backend: `python3 -m hermes_cli.kanban_db_connect list`

## Quick Reference
- **Audit Boards**: `python3 -m hermes_cli.kanban_db_connect list_boards`
- **Sync ID**: `python3 -m hermes_cli.kanban_db_connect list`
- **Manual Re-assign**: `herms kanban assign <id> <profile>`

## Procedure
1. **Identify the Drift**: Compare the output of a `kanban_list` filter (e.g., `status='running'`) against the expected status of the task.
2. **Refresh Context**: Execute `kanban_show(task_id=...)` for the specific card to refresh the full state and detail.
3. **Track Events**: Check the `comment` thread and `recent_events` (via `kanban_show`) to find where the last state change occurred.
4. **Analyze Transitions**:
    - For \"Stuck\" tasks, compare `_started_at` and `_completed_at`.
    - For \"Dependency\" issues, check both child and parent IDs.
5. **Fix State**:
    - For timeouts, use `kanban_block(reason='timeout_manual_reset')`.
    - For mismatch logs, use `kanban_comment`.
6. **Validation**: Re-run `kanban_list` to confirm.

## Pitfalls
- **Stale Data**: `kanban_list` may be cached; use `kanban_show` before acting.
- **Concurrency**: Avoid rapid updates to the same card in consecutive turns.
- **Reporting**: `kanban_block` is for structural errors, not for ambiguity.

## Verification
Run `kanban_show` on target ID; `status` must match.
