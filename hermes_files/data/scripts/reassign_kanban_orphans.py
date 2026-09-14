#!/usr/bin/env python3
"""No-agent cron watchdog: reassign kanban tasks whose assignee is not a real
profile (dispatcher silently never claims those) back to the 'default' profile.
Prints nothing (silent tick) unless it actually reassigned something or hit an error.
"""
import json
import subprocess
import sys

FALLBACK_ASSIGNEE = "default"
TERMINAL_STATUSES = {"done", "archived"}


def run(args, timeout=60):
    return subprocess.run(
        ["hermes", *args], capture_output=True, text=True, timeout=timeout
    )


def valid_profiles():
    result = run(["profile", "list"])
    if result.returncode != 0:
        return None
    names = set()
    for line in result.stdout.splitlines():
        name = line.strip().lstrip("*").strip()
        if name:
            names.add(name)
    return names


def load_tasks():
    result = run(["kanban", "list", "--json"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        data = data.get("tasks", [])
    return data if isinstance(data, list) else None


def main():
    profiles = valid_profiles()
    if not profiles:
        # Can't safely determine valid profiles this tick — do nothing rather than guess.
        return 0

    tasks = load_tasks()
    if tasks is None:
        print("reassign-kanban-orphans: could not parse `hermes kanban list --json`", file=sys.stderr)
        return 1

    orphan_ids = []
    for task in tasks:
        status = task.get("status")
        assignee = task.get("assignee")
        task_id = task.get("id") or task.get("task_id")
        if not task_id or status in TERMINAL_STATUSES:
            continue
        if assignee and assignee not in profiles and assignee != FALLBACK_ASSIGNEE:
            orphan_ids.append(task_id)

    if not orphan_ids:
        return 0

    result = run(["kanban", "reassign", *orphan_ids, FALLBACK_ASSIGNEE])
    if result.returncode != 0:
        print(
            f"reassign-kanban-orphans: failed to reassign {orphan_ids}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    print(f"Reassigned {len(orphan_ids)} orphaned kanban task(s) to '{FALLBACK_ASSIGNEE}': {', '.join(orphan_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
