"""Task033 R3: file-only v6 derivation, then explicitly user-started minimal work.

The original reviewed five/25 split and all original files are immutable.
Each selected native source has its own resumable preparation report; no policy
is loaded here, and no old ready or historical task enters the native queue.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import argparse
import json

from . import repair033_sources as r2, selected_preparation as preparation
from .nine_planning import canonical_hash, file_sha, read_json, read_sources
from .workflow import write_json
from ..validation import V6_PROFILE

SCHEMA = 'remaining-task033-r3-v6-repair-plan-v1'
REPORT_SCHEMA = 'remaining-task033-r3-v6-preparation-v1'
DERIVED_ACTIONS = {'ready': 'derived_ready', 'needs_replay': 'replay',
                   'needs_build': 'build', 'blocked': 'blocked'}
NATIVE_ACTIONS = ('repair', 'replay', 'build')


def _derive_source(*args, **kwargs):
    from .rgb_revalidation import derive_source
    return derive_source(*args, **kwargs)


def _inventory(value, entries):
    result = {**deepcopy(value), 'entries': [
        {'task_id': task, 'initial_state_index': index, 'origin': deepcopy(origin)}
        for (task, index), origin in entries.items()]}
    result.pop('content_hash', None)
    result['content_hash'] = canonical_hash(result)
    return result


def plan_repairs(inventory_path, report_path, output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('new R3 plan output required; old evidence must remain unchanged')
    # Reuse the exact reviewed report validation, population and old-ready guard.
    original = r2.plan_repairs(inventory_path, report_path, output/'reviewed_v4')
    inventory, entries = read_sources(original['sources_path'], 'nine-mask10')
    rows = []
    for old in original['sources']:
        row = deepcopy(old)
        task, index = row['task_id'], row['initial_state_index']
        if row['action'] == 'rgb_review_blocked':
            directory = output/'derivations'/f'{task}_s{index:02d}'
            result = _derive_source(task, index, entries[task, index], directory, protocol='nine-mask10')
            if result.get('status') not in DERIVED_ACTIONS:
                raise ValueError('unsupported recorded-evidence derivation status')
            row.update(action=DERIVED_ACTIONS[result['status']], reason=result.get('reason'),
                       required_native_steps=result.get('required_native_steps'),
                       derivation=str(directory/'derivation_report.json'),
                       derivation_sha256=file_sha(directory/'derivation_report.json'))
            if result.get('origin'):
                entries[task, index] = deepcopy(result['origin'])
            row['current'] = preparation._inspect('nine-mask10', task, index, entries[task, index])
            if row['action'] == 'derived_ready' and row['current']['status'] != 'ready':
                raise ValueError('derived source did not pass the formal offline source reader')
        rows.append(row)
    write_json(output/'sources.json', _inventory(inventory, entries))
    counts = Counter(row['action'] for row in rows)
    plan = {'schema_version': SCHEMA, 'protocol': 'nine-mask10', 'observation_profile': V6_PROFILE,
            'construction_method': r2.METHOD,
            'original_plan': str(output/'reviewed_v4/repair_plan.json'),
            'original_plan_sha256': file_sha(output/'reviewed_v4/repair_plan.json'),
            'sources_path': str(output/'sources.json'), 'sources_sha256': file_sha(output/'sources.json'),
            'sources': rows, 'reuse_issues': original['reuse_issues'],
            'counts': {**dict(counts), 'reviewed_failures': 25, 'selected': 30,
                       'native_sources': sum(counts[a] for a in NATIVE_ACTIONS)},
            'policy_called': False, 'model_rollouts': 0, 'new_native_steps': 0,
            'evidence_scope': 'file-only classification; ready requires explicit complete evidence',
            'note': '00, historical six and the five original ready sources never enter native work.'}
    plan['plan_sha256'] = canonical_hash(plan)
    write_json(output/'repair_plan.json', plan)
    return plan


def _checked_plan(path, output):
    path, output = Path(path).resolve(), Path(output).resolve()
    plan = read_json(path)
    if (plan.get('schema_version') != SCHEMA or plan.get('protocol') != 'nine-mask10'
            or plan.get('observation_profile') != V6_PROFILE or plan.get('construction_method') != r2.METHOD
            or plan.get('plan_sha256') != canonical_hash({k:v for k,v in plan.items() if k!='plan_sha256'})):
        raise ValueError('R3 plan identity/profile/hash mismatch')
    for key in ('original_plan', 'sources'):
        name = 'sources_path' if key == 'sources' else key
        if file_sha(plan[name]) != plan[key+'_sha256']:
            raise ValueError('R3 plan reference changed: '+key)
    original = read_json(plan['original_plan'])
    if (original.get('schema_version') != r2.SCHEMA
            or original.get('original_report_sha256') != r2.REVIEWED_REPORT_SHA256
            or original.get('plan_sha256') != canonical_hash({k:v for k,v in original.items() if k!='plan_sha256'})):
        raise ValueError('original reviewed plan identity changed')
    for key in ('original_inventory', 'original_report', 'sources'):
        name = 'sources_path' if key == 'sources' else key
        if file_sha(original[name]) != original[key+'_sha256']:
            raise ValueError('original reviewed source changed: '+key)
    inventory, entries = read_sources(plan['sources_path'], 'nine-mask10')
    r2._isolate(output, r2._history_roots(original['original_inventory'], original['original_report'], entries)|{path.parent})
    expected = {(t,i) for t in (*r2.PHYSICAL_TASKS, 'two_pots') for i in range(10)}
    seen = set()
    for row in plan['sources']:
        key = row['task_id'], row['initial_state_index']
        if key not in expected or key in seen:
            raise ValueError('R3 plan cannot add duplicate/foreign source')
        seen.add(key)
        if key[0] in r2.PHYSICAL_TASKS:
            wanted = 'repair'
        elif key[1] in r2.READY_POTS:
            wanted = 'reuse_only'
        else:
            if file_sha(row['derivation']) != row['derivation_sha256']:
                raise ValueError('RGB derivation report changed')
            result = read_json(row['derivation'])
            wanted = DERIVED_ACTIONS.get(result.get('status'))
            if result.get('origin') and result['origin'] != entries[key]:
                raise ValueError('RGB derivation origin changed')
            origin = entries[key]
            if origin and origin.get('rgb_certificate'):
                if file_sha(origin['rgb_certificate']) != origin.get('rgb_certificate_sha256'):
                    raise ValueError('RGB certificate byte hash changed after planning')
                from .rgb_revalidation import inspect_certified_candidate
                inspect_certified_candidate(key[0], key[1], origin['manifest'], origin['rgb_certificate'],
                                             protocol='nine-mask10')
                if wanted == 'derived_ready':
                    from .scoped_sources import resolve_source
                    resolve_source('nine-mask10', key[0], key[1], origin)
        if row['action'] != wanted:
            raise ValueError('R3 action differs from the reviewed/derived evidence')
    if seen != expected:
        raise ValueError('R3 plan must retain all original thirty sources')
    return plan, inventory, entries


def prepare_repairs(plan_path, output, *, continuation=False):
    output = Path(output).resolve()
    plan, inventory, entries = _checked_plan(plan_path, output)
    report_path = output/'preparation_report.json'
    if output.exists():
        if not continuation:
            raise FileExistsError('output exists; explicit continuation required')
        report = read_json(report_path)
        if (report.get('schema_version') != REPORT_SCHEMA or report.get('plan_sha256') != plan['plan_sha256']
                or report.get('observation_profile') != V6_PROFILE):
            raise ValueError('R3 continuation identity mismatch')
        for row in report['sources']:
            if row.get('origin'):
                entries[row['task_id'], row['initial_state_index']] = deepcopy(row['origin'])
    else:
        output.mkdir(parents=True)
        report = {'schema_version': REPORT_SCHEMA, 'plan_sha256': plan['plan_sha256'],
                  'observation_profile': V6_PROFILE, 'policy_called': False, 'model_rollouts': 0, 'sources': []}
    rows = {(r['task_id'], r['initial_state_index']): r for r in report['sources']}

    def persist():
        report['sources'] = list(rows.values())
        report['counts'] = dict(Counter(row['status'] for row in rows.values()))
        preparation._write(report_path, report)
        preparation._write(output/'sources.json', _inventory(inventory, entries))

    for item in plan['sources']:
        task, index = key = item['task_id'], item['initial_state_index']
        if key not in rows:
            rows[key] = {**preparation._inspect('nine-mask10', task, index, entries[key]), 'action': item['action']}
    persist()
    for item in plan['sources']:
        task, index = key = item['task_id'], item['initial_state_index']
        if item['action'] not in NATIVE_ACTIONS:
            rows[key] = {**preparation._inspect('nine-mask10', task, index, entries[key]), 'action': item['action']}
            persist()
            continue
        destination = output/'sources'/task/f'source_{index:02d}'
        child_report = destination/'preparation_report.json'
        if rows[key].get('dispatch_started') and not child_report.is_file():
            rows[key].update(status='interrupted', actual_control_steps=None, count_status='unknown',
                reason='Dispatched preparation has no child report; preserve unknown progress without retry.')
            persist()
            continue
        # Each source owns one immutable inventory identity and its own persisted
        # operation ledger. The existing R2 continuation guard avoids retries.
        rows[key].update(status='running', actual_control_steps=None, count_status='unknown',
                         dispatch_started=True, preparation_report=str(child_report))
        persist()
        result = preparation.prepare(plan['sources_path'], destination,
            mode='replay-missing' if item['action']=='replay' else 'prepare-missing',
            tasks=[task], indices=[index], protocol='nine-mask10', construction_method=r2.METHOD,
            observation_profile=V6_PROFILE, allow_failed_retry=False, replace_failed_originals=True,
            continuation=continuation and destination.exists())
        if len(result['sources']) != 1 or (result['sources'][0]['task_id'], result['sources'][0]['initial_state_index']) != key:
            raise ValueError('per-source preparation returned a different identity')
        rows[key] = {**result['sources'][0], 'action': item['action'],
                     'dispatch_started': True, 'preparation_report': str(child_report)}
        if rows[key].get('origin'):
            entries[key] = deepcopy(rows[key]['origin'])
        persist()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan', help='FILE ONLY: derive sufficient old evidence and classify exact gaps')
    plan.add_argument('--inventory', required=True, type=Path)
    plan.add_argument('--preparation-report', required=True, type=Path)
    plan.add_argument('--out', required=True, type=Path)
    run = commands.add_parser('prepare', help='USER STARTED: execute only the required new native operations')
    run.add_argument('--plan', required=True, type=Path)
    run.add_argument('--out', required=True, type=Path)
    run.add_argument('--continue', dest='continuation', action='store_true')
    args = parser.parse_args(argv)
    result = (plan_repairs(args.inventory, args.preparation_report, args.out) if args.command=='plan'
              else prepare_repairs(args.plan, args.out, continuation=args.continuation))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.command == 'prepare':
        return 0 if len(result['sources'])==30 and all(r['status']=='ready' for r in result['sources']) else 2
    return 2 if result['reuse_issues'] or result['counts'].get('blocked', 0) else 0


if __name__ == '__main__':
    raise SystemExit(main())
