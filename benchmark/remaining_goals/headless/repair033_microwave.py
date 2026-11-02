"""R5 microwave-only preparation: source 0 must be ready before sources 1..9.

This is a USER-STARTED native command. It binds the reviewed R3 bytes, reuses
the twenty accepted origins, and delegates physical work/ledgers to the existing
selected preparation worker. No policy, retry-failed switch, or partial eval.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import argparse
import json

from . import repair033_sources as r2, selected_preparation as preparation
from .nine_planning import NEW_TASKS, file_sha, read_json, read_sources, canonical_hash
from ..validation import V6_PROFILE

SCHEMA = 'remaining-task033-r5-microwave-preparation-v1'
REPORT_SHA256 = '195c8a38c8bb8f4683cf0a4d3925348b5f08e64941621b3379a0ffec57a61f04'
SOURCES_SHA256 = '3454ee8a1a776f357a05511c98e12bd9e8c63aba548a0db9f6eb8a32aec6369e'
METHOD = preparation.R5_METHOD
TASK = 'mug_microwave_close'


def _inputs(inventory_path, report_path, output):
    if file_sha(report_path) != REPORT_SHA256 or file_sha(inventory_path) != SOURCES_SHA256:
        raise ValueError('R5 original report/inventory hash differs from reviewed R3 bytes')
    inventory, entries = read_sources(inventory_path, 'nine-mask10')
    roots = r2._history_roots(inventory_path, report_path, entries)
    roots.update(Path(o['rgb_certificate']).resolve().parent for o in entries.values()
                 if o and o.get('rgb_certificate'))
    r2._isolate(output, roots)
    original = read_json(report_path)
    if (original.get('schema_version') != 'remaining-task033-r3-v6-preparation-v1'
            or original.get('observation_profile') != V6_PROFILE
            or original.get('policy_called') is not False or original.get('model_rollouts') != 0):
        raise ValueError('R5 original preparation identity differs')
    expected = {(task, i) for task in NEW_TASKS for i in range(10)}
    rows = {}
    for row in original.get('sources', []):
        key = row.get('task_id'), row.get('initial_state_index')
        if key not in expected or key in rows:
            raise ValueError('R5 original report has duplicate/foreign sources')
        wanted = 'failed' if key[0] == TASK else 'ready'
        if (row.get('status') != wanted or
                preparation._origin(row.get('origin'), report_path.parent) != entries.get(key)):
            raise ValueError('R5 original source differs from the reviewed twenty/ten split')
        # File-only checks include referenced replay/certificates. Missing old
        # evidence is a blocker, never authorization to reconstruct an old source.
        if wanted == 'ready' and preparation._inspect('nine-mask10', *key, entries[key])['status'] != 'ready':
            raise ValueError(f'R5 reused source is no longer ready: {key}')
        rows[key] = deepcopy(row)
    if set(rows) != expected:
        raise ValueError('R5 original report must contain exactly the new thirty sources')
    return inventory, entries, rows


def prepare(inventory_path, report_path, output, *, continuation=False):
    inventory_path, report_path, output = (Path(p).resolve() for p in (inventory_path, report_path, output))
    inventory, entries, original_rows = _inputs(inventory_path, report_path, output)
    identity = {'schema_version': SCHEMA, 'protocol': 'nine-mask10', 'construction_method': METHOD,
                'observation_profile': V6_PROFILE, 'original_inventory': str(inventory_path),
                'original_inventory_sha256': SOURCES_SHA256, 'original_report': str(report_path),
                'original_report_sha256': REPORT_SHA256}
    path = output/'microwave_repair_report.json'
    child = output/'preparation'
    child_report = child/'preparation_report.json'
    if output.exists():
        if not continuation:
            raise FileExistsError('R5 output exists; use explicit --continue, never overwrite history')
        report = read_json(path)
        if any(report.get(key) != value for key, value in identity.items()):
            raise ValueError('R5 continuation identity mismatch')
        rows = {(row['task_id'], row['initial_state_index']): row for row in report['sources']}
        if len(report['sources']) != 30 or set(rows) != set(original_rows):
            raise ValueError('R5 continuation population differs')
    else:
        output.mkdir(parents=True, exist_ok=False)
        for source, name in ((inventory_path, 'original_sources.json'),
                             (report_path, 'original_preparation_report.json')):
            (output/name).write_bytes(source.read_bytes())
        report = {**identity, 'policy_called': False, 'model_rollouts': 0,
                  'source0_dispatched': False, 'stopped_after_source0': True,
                  'note': 'Old twenty reused; only microwave 0..9 may receive new native operations.'}
        rows = {}
        for key, row in original_rows.items():
            rows[key] = {'task_id': key[0], 'initial_state_index': key[1],
                         'origin': deepcopy(entries[key]), 'original': row,
                         'status': 'not_attempted' if key[0] == TASK else 'ready',
                         'action': 'repair' if key[0] == TASK else 'reuse_only',
                         'operations': [], 'actual_control_steps': 0, 'count_status': 'complete'}

    def persist():
        report['sources'] = list(rows.values())
        report['counts'] = dict(Counter(row['status'] for row in rows.values()))
        preparation._write(path, report)
        combined = {**deepcopy(inventory), 'entries': [
            {'task_id': task, 'initial_state_index': index, 'origin': deepcopy(origin)}
            for (task, index), origin in entries.items()]}
        combined.pop('content_hash', None)
        combined['content_hash'] = canonical_hash(combined)
        preparation._write(output/'sources.json', combined)

    def sync():
        if child_report.is_file():
            value = read_json(child_report)
            if (value.get('schema_version') != preparation.REPORT_SCHEMA or
                    value.get('inventory_sha256') != SOURCES_SHA256 or
                    value.get('construction_method') != METHOD or value.get('protocol') != 'nine-mask10' or
                    value.get('observation_profile') != V6_PROFILE or value.get('replace_failed_originals') is not True):
                raise ValueError('R5 child preparation identity differs')
            seen = set()
            for row in value['sources']:
                key = row['task_id'], row['initial_state_index']
                if key not in rows or key[0] != TASK or key in seen:
                    raise ValueError('R5 child preparation contains a foreign/duplicate source')
                seen.add(key)
                rows[key] = {**rows[key], **deepcopy(row)}
                if any(op.get('status') == 'running' for op in row.get('operations', [])):
                    rows[key].update(status='interrupted', actual_control_steps=None, count_status='unknown')
                if row.get('origin'):
                    entries[key] = deepcopy(row['origin'])
        # Dispatch intent with no child evidence cannot be silently retried.
        if report['source0_dispatched'] and rows[TASK, 0]['status'] == 'not_attempted':
            rows[TASK, 0].update(status='interrupted', actual_control_steps=None, count_status='unknown',
                                reason='source0 dispatched without a recoverable child row; preserve this output')
        report['stopped_after_source0'] = rows[TASK, 0]['status'] != 'ready'
        persist()

    def run(indices):
        try:
            preparation.prepare(inventory_path, child, mode='prepare-missing', tasks=[TASK], indices=indices,
                                protocol='nine-mask10', construction_method=METHOD,
                                observation_profile=V6_PROFILE, replace_failed_originals=True,
                                allow_failed_retry=False, continuation=child.exists())
        finally:
            sync()

    # Restore previously recorded native origins before serializing a resume.
    for key, row in rows.items():
        if key[0] == TASK and row.get('origin'):
            entries[key] = deepcopy(row['origin'])
    if report['source0_dispatched']:
        sync()
        if rows[TASK, 0]['status'] == 'interrupted':
            return report
    report['source0_dispatched'] = True
    persist()  # durable intent precedes any native-boundary call
    run([0])  # continuation uses the existing ledger; attempted failures are not retried
    if rows[TASK, 0]['status'] == 'ready':
        run(list(range(1, 10)))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('prepare', help='USER-STARTED: source0 gate, then only the remaining nine microwaves')
    run.add_argument('--inventory', required=True, type=Path)
    run.add_argument('--preparation-report', required=True, type=Path)
    run.add_argument('--out', required=True, type=Path)
    run.add_argument('--continue', dest='continuation', action='store_true')
    args = parser.parse_args(argv)
    result = prepare(args.inventory, args.preparation_report, args.out, continuation=args.continuation)
    print(json.dumps({'report': str(args.out/'microwave_repair_report.json'), 'counts': result['counts'],
                      'stopped_after_source0': result['stopped_after_source0']}, ensure_ascii=False))
    return 0 if result['counts'] == {'ready': 30} else 2


if __name__ == '__main__':
    raise SystemExit(main())
