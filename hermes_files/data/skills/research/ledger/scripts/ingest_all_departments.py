#!/usr/bin/env python3
"""Run configured ledger departments sequentially using the active Python environment.

Place beside ingest_department.py. Child scripts retain their validation policies.
LightRAG uses the existing ingestion script; its department-ID handling must support
all target departments. This wrapper does not change its document selection rules.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

LEDGER = Path('hermes_files/data/skills/research/ledger')


def find_repo(explicit):
    if explicit:
        candidates = [explicit.expanduser().resolve()]
    else:
        candidates = []
        for start in (Path.cwd().resolve(), Path(__file__).resolve().parent):
            for parent in (start, *start.parents):
                candidates.extend((parent, parent / 'local_hermes'))
    for candidate in candidates:
        if (candidate / LEDGER / 'scripts/ingest_department.py').is_file():
            return candidate
    raise ValueError('Cannot locate checkout. Pass --repo /path/to/local_hermes')


def discover_configs(data_dir, departments=None):
    if departments:
        if any(Path(name).name != name or name in ('raw', 'template', '.', '..')
               for name in departments):
            raise ValueError('Use department folder names, excluding raw and template')
        paths = [data_dir / name / 'config.yaml' for name in dict.fromkeys(departments)]
        for path in paths:
            if not path.is_file():
                raise ValueError('Missing department config: ' + str(path))
    else:
        paths = sorted(p for p in data_dir.glob('*/config.yaml')
                       if p.parent.name not in ('raw', 'template'))
    if not paths:
        raise ValueError('No department config.yaml files found in ' + str(data_dir))
    return paths


def lookup_department_id(config):
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        dbname=os.getenv('POSTGRES_DB', 'rag'),
        user=os.getenv('POSTGRES_USER', 'rag'),
        password=os.getenv('POSTGRES_PASSWORD', 'rag'),
        connect_timeout=15,
    )
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT department_id FROM research.departments '
                'WHERE institution = %s AND department_name = %s',
                (config['institution'], config['department_name']),
            )
            rows = cursor.fetchall()
        if len(rows) != 1:
            raise ValueError('Expected exactly one database department for {!r}; found {}'.format(
                config['department_name'], len(rows)))
        return rows[0][0]
    finally:
        conn.close()


def run(command, repo):
    print('+ ' + ' '.join(shlex.quote(str(x)) for x in command), flush=True)
    subprocess.run([str(x) for x in command], cwd=repo, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--departments', nargs='+', help='Selected department folder names; default: all configs')
    parser.add_argument('--plan', action='store_true', help='Validate each child plan; no database access or writes')
    parser.add_argument('--stop-on-error', action='store_true')
    for flag in ('allow-count-mismatch', 'allow-db-write', 'allow-overwrite', 'auto-approve', 'refresh'):
        parser.add_argument('--' + flag, action='store_true')
    parser.add_argument('--allow-lightrag-write', action='store_true',
                        help='After each successful ledger import, ingest its abstracts using the looked-up department ID')
    args = parser.parse_args()
    if args.auto_approve and not args.allow_db_write:
        parser.error('--auto-approve requires --allow-db-write')
    if args.allow_lightrag_write and not args.allow_db_write:
        parser.error('--allow-lightrag-write requires --allow-db-write')
    try:
        import yaml
        repo = find_repo(args.repo)
        data_dir = repo / LEDGER / 'data'
        configs = discover_configs(data_dir, args.departments)
        # Validate department identities before starting any work.
        loaded = []
        for path in configs:
            config = yaml.safe_load(path.read_text(encoding='utf-8'))
            if not isinstance(config, dict) or not all(config.get(k) for k in
                    ('institution', 'department_name', 'department_slug')):
                raise ValueError('Missing department identity fields: ' + str(path))
            loaded.append((path, config))
    except (ImportError, OSError, ValueError) as exc:
        parser.error(str(exc))
    child = repo / LEDGER / 'scripts/ingest_department.py'
    record = {'started_at': datetime.now(timezone.utc).isoformat(),
              'plan_only': args.plan, 'departments': []}
    log = data_dir / ('ingest_all_run_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')

    def save():
        if not args.plan:
            log.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')

    for path, config in loaded:
        print('\n===== {} ({}) ====='.format(config['department_name'], path.parent.name), flush=True)
        result = {'folder': path.parent.name, 'config': str(path), 'status': 'running',
                  'stage': 'ledger', 'started_at': datetime.now(timezone.utc).isoformat()}
        record['departments'].append(result)
        save()
        try:
            command = [sys.executable, child, '--config', path]
            for flag in ('allow-count-mismatch', 'allow-db-write', 'allow-overwrite', 'auto-approve', 'refresh'):
                if getattr(args, flag.replace('-', '_')):
                    command.append('--' + flag)
            if args.plan:
                command.append('--plan')
            run(command, repo)
            if args.allow_lightrag_write:
                result['stage'] = 'lightrag'
                if args.plan:
                    print('LightRAG: after ledger import, look up this department by institution/name; '
                          'run --lightrag-only --allow-lightrag-write --department-id LOOKED_UP_ID', flush=True)
                else:
                    save()
                    department_id = lookup_department_id(config)
                    result['department_id'] = department_id
                    save()
                    run([sys.executable, child, '--config', path, '--lightrag-only',
                         '--allow-lightrag-write', '--department-id', str(department_id)], repo)
            result['status'] = 'planned' if args.plan else 'succeeded'
        except (Exception, KeyboardInterrupt) as exc:
            result['status'] = 'failed'
            result['error'] = str(exc) or type(exc).__name__
            print('FAILED {}: {}'.format(path.parent.name, result['error']), file=sys.stderr, flush=True)
            if isinstance(exc, KeyboardInterrupt) or args.stop_on_error:
                result['finished_at'] = datetime.now(timezone.utc).isoformat()
                save()
                break
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
    failed = any(r['status'] == 'failed' for r in record['departments'])
    record['status'] = 'failed' if failed else ('planned' if args.plan else 'succeeded')
    record['finished_at'] = datetime.now(timezone.utc).isoformat()
    record['not_run'] = [p.parent.name for p, _ in loaded[len(record['departments']):]]
    save()
    print('\nDepartment results:', flush=True)
    for result in record['departments']:
        print('  {}: {}'.format(result['folder'], result['status']))
    if record['not_run']:
        print('  Not run: ' + ', '.join(record['not_run']))
    if not args.plan:
        print('Batch log: ' + str(log))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
