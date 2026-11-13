#!/usr/bin/env python3
"""Initialize the ledger skill from the local_hermes checkout (Python 3.8+).

Suggested location: hermes_files/data/skills/research/ledger/initialize_ledger.py
Run from the repository root:
    python3 hermes_files/data/skills/research/ledger/initialize_ledger.py
Or specify the checkout explicitly:
    python3 initialize_ledger.py --repo /path/to/local_hermes

Requires Docker access and an already-running PostgreSQL Compose service.
Reuses an existing .venv. Each run installs requirements and reapplies schema.sql;
whether schema reapplication is safe depends on the SQL file itself.
"""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import venv


SKILL_PATH = Path("hermes_files/data/skills/research/ledger")


def is_repo(path):
    return all((path / SKILL_PATH / name).is_file()
               for name in ("requirements.txt", "schema.sql"))


def find_repo(explicit=None):
    if explicit is not None:
        root = explicit.expanduser().resolve()
        if not is_repo(root):
            raise RuntimeError(
                "Repository must contain {} and schema.sql".format(
                    root / SKILL_PATH / "requirements.txt"
                )
            )
        return root
    # Works from the checkout, its parent, or when this script lives in the skill.
    for start in (Path.cwd().resolve(), Path(__file__).resolve().parent):
        for parent in (start, *start.parents):
            for candidate in (parent, parent / "local_hermes"):
                if is_repo(candidate):
                    return candidate
    raise RuntimeError("Cannot locate local_hermes; pass --repo /path/to/local_hermes")


def run(command, **kwargs):
    print("+ " + " ".join(shlex.quote(str(part)) for part in command), flush=True)
    return subprocess.run([str(part) for part in command], check=True, **kwargs)


def find_container(docker, network, explicit=None):
    result = run(
        [docker, "ps", "--filter", "label=com.docker.compose.service=postgres",
         "--filter", "network=" + network, "--format", "{{.ID}}"],
        capture_output=True, text=True,
    )
    containers = result.stdout.split()
    if explicit:
        actual_id = run(
            [docker, "inspect", "--format", "{{.Id}}", explicit],
            capture_output=True, text=True,
        ).stdout.strip()
        if not actual_id or not any(actual_id.startswith(cid) for cid in containers):
            raise RuntimeError(
                "Selected container must be running, have the postgres Compose "
                "service label, and belong to network " + network
            )
        return actual_id
    if not containers:
        raise RuntimeError(
            "No running postgres Compose service on network {}. "
            "Start your Compose stack first, or set --network.".format(network)
        )
    if len(containers) != 1:
        raise RuntimeError(
            "Multiple PostgreSQL containers matched: {}. "
            "Choose one with --container NAME_OR_ID.".format(", ".join(containers))
        )
    return containers[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="Path to the local_hermes checkout")
    parser.add_argument("--network", default="local-hermes_backend")
    parser.add_argument("--container", help="Select one matching PostgreSQL container")
    parser.add_argument("--db-user", default="rag")
    parser.add_argument("--db-name", default="rag")
    args = parser.parse_args()

    try:
        root = find_repo(args.repo)
        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("Docker CLI is missing or is not on PATH")
        container = find_container(docker, args.network, args.container)
        run([docker, "exec", container, "psql", "-X", "-w",
             "-U", args.db_user, "-d", args.db_name,
             "-v", "ON_ERROR_STOP=1", "-c", "SELECT 1;"], cwd=root)

        env_dir = root / "hermes_files/ai_files/.venv"
        python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not env_dir.exists():
            print("Creating virtual environment: {}".format(env_dir), flush=True)
            env_dir.parent.mkdir(parents=True, exist_ok=True)
            venv.EnvBuilder(with_pip=True).create(env_dir)
        elif not (env_dir / "pyvenv.cfg").is_file() or not python.is_file():
            raise RuntimeError(
                "Existing .venv is incomplete or incompatible with this OS: {}. "
                "Move it aside and rerun.".format(env_dir)
            )

        # Use the venv interpreter directly; activation cannot persist in the caller.
        run([python, "-m", "pip", "install", "-r",
             root / SKILL_PATH / "requirements.txt"], cwd=root)
        schema = root / SKILL_PATH / "schema.sql"
        print("Applying schema: {}".format(schema), flush=True)
        with schema.open("rb") as sql:
            run([docker, "exec", "-i", container, "psql", "-X", "-w",
                 "-U", args.db_user, "-d", args.db_name,
                 "-v", "ON_ERROR_STOP=1", "--single-transaction", "--file=-"],
                stdin=sql, cwd=root)
        print("Ledger initialization completed.")
        print("Virtual environment: {}".format(env_dir))
        if os.name != "nt":
            print("To activate in your shell: source {}".format(
                shlex.quote(str(env_dir / "bin/activate"))))
        return 0
    except subprocess.CalledProcessError as exc:
        print("Initialization failed (exit code {}).".format(exc.returncode), file=sys.stderr)
        if exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as exc:
        print("Initialization failed: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
