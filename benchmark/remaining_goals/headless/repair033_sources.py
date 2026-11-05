"""R2 failed-source handoff; RGB acceptance changes remain review-only.

`plan` is file-only. `prepare` is an explicit user-started native operation for
the twenty drawer/microwave failures; it never invokes a policy or retries RGB.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json

from . import selected_preparation as preparation
from .nine_planning import expected_episodes, read_sources, canonical_hash, file_sha, read_json
from .workflow import write_json

SCHEMA = 'remaining-task033-r2-repair-plan-v1'
REVIEWED_REPORT_SHA256 = 'cfe54054a85148e36e39a88dacd5658ef367f526a0970f7079d7a2586661d01e'
METHOD = 'selected_A_only_bounded_settle_component_transplant_v2'
READY_POTS = (1, 3, 4, 5, 6)
RGB_GAPS = (0, 2, 7, 8, 9)
PHYSICAL_TASKS = ('bowl_drawer_close', 'mug_microwave_close')


def _isolate(output, roots):
    output = Path(output).resolve()
    if any(output == root or root in output.parents or output in root.parents for root in roots):
        raise ValueError('new output overlaps original evidence or the frozen repair plan')


def _history_roots(inventory, report, entries):
    roots = {Path(inventory).resolve().parent, Path(report).resolve().parent}
    for origin in entries.values():
        for key in ('manifest', 'candidate_replay', 'initialization'):
            if origin and origin.get(key):
                roots.add(Path(origin[key]).resolve().parent)
    return roots


def plan_repairs(inventory_path, report_path, output):
    inventory_path, report_path, output = map(lambda p: Path(p).resolve(), (inventory_path, report_path, output))
    inventory, entries = read_sources(inventory_path, 'nine-mask10')
    _isolate(output, _history_roots(inventory_path, report_path, entries))
    if output.exists():
        raise FileExistsError('repair plan output already exists; original evidence is immutable')
    if file_sha(report_path) != REVIEWED_REPORT_SHA256:
        raise ValueError('preparation report differs from the R2 reviewed report bytes')
    report = read_json(report_path)
    if (report.get('schema_version') != preparation.REPORT_SCHEMA or report.get('protocol') != 'nine-mask10'
            or report.get('expected') != expected_episodes('nine-mask10')
            or report.get('policy_called') is not False or report.get('model_rollouts') != 0):
        raise ValueError('reviewed preparation report identity/protocol differs')
    expected = {(t, i) for t in (*PHYSICAL_TASKS, 'two_pots') for i in range(10)}
    rows = {}
    for row in report.get('sources', []):
        key = row.get('task_id'), row.get('initial_state_index')
        if key not in expected or key in rows:
            raise ValueError('reviewed report contains duplicate/foreign source')
        ready = key[0] == 'two_pots' and key[1] in READY_POTS
        if row.get('status') != ('ready' if ready else 'failed'):
            raise ValueError('reviewed source status differs from the approved five/25 split')
        if preparation._origin(row.get('origin'), report_path.parent) != entries.get(key):
            raise ValueError('source inventory does not reference the reviewed original source')
        rows[key] = row
    if set(rows) != expected:
        raise ValueError('reviewed report must contain exactly the new thirty sources')
    selected, issues = [], []
    for episode in expected_episodes('nine-mask10'):
        task, index = key = episode['task_id'], episode['initial_state_index']
        if key not in expected:
            continue
        origin = entries[key]
        action = 'reuse_only' if task == 'two_pots' and index in READY_POTS else 'rgb_review_blocked' if task == 'two_pots' else 'repair'
        current = preparation._inspect('nine-mask10', task, index, origin)
        if action == 'reuse_only' and current['status'] != 'ready':
            issues.append({'task_id':task, 'initial_state_index':index, 'reason':current.get('reason')})
        selected.append({'task_id':task, 'initial_state_index':index, 'action':action,
            'original':deepcopy(rows[key]), 'current':current,
            'reason': 'no native retry before an explicit RGB policy adjudication' if action == 'rgb_review_blocked' else None})
    composite = {**deepcopy(inventory), 'entries':[
        {'task_id':t,'initial_state_index':i,'origin':deepcopy(origin)} for (t,i),origin in entries.items()]}
    composite.pop('content_hash',None)
    composite['content_hash'] = canonical_hash(composite)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'sources.json',composite)
    for source,name in ((report_path,'original_preparation_report.json'),(inventory_path,'original_sources.json')):
        (output/name).write_bytes(source.read_bytes())
    result = {'schema_version':SCHEMA, 'protocol':'nine-mask10', 'construction_method':METHOD,
        'source_commit':'aedfe1692004d46488dd7544353ba4f58b60d51d',
        'original_inventory':str(inventory_path),'original_inventory_sha256':file_sha(inventory_path),
        'original_report':str(report_path),'original_report_sha256':file_sha(report_path),
        'sources_path':str(output/'sources.json'),'sources_sha256':file_sha(output/'sources.json'),
        'sources':selected,'reuse_issues':issues,
        'counts':{'reviewed_failures':25,'repair_executable':20,'rgb_review_blocked':5,'reuse_only':5},
        'policy_called':False,'model_rollouts':0,'simulation_created':False,
        'note':'00 and historical six are not selected. Five RGB gaps require review; this plan is not source acceptance.'}
    result['plan_sha256'] = canonical_hash(result)
    write_json(output/'repair_plan.json',result)
    return result


def prepare_repairs(plan_path, output, *, continuation=False):
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = read_json(plan_path)
    if (plan.get('schema_version') != SCHEMA or plan.get('protocol') != 'nine-mask10'
            or plan.get('construction_method') != METHOD or plan.get('plan_sha256') != canonical_hash(
                {k:v for k,v in plan.items() if k!='plan_sha256'})):
        raise ValueError('repair plan schema/method/hash differs')
    for key in ('original_inventory','original_report','sources'):
        name = 'sources_path' if key=='sources' else key
        if file_sha(plan[name]) != plan[key+'_sha256']:
            raise ValueError('repair source references changed: '+key)
    if plan['original_report_sha256'] != REVIEWED_REPORT_SHA256:
        raise ValueError('repair plan does not bind the reviewed R2 preparation report')
    _, entries = read_sources(plan['sources_path'],'nine-mask10')
    roots = _history_roots(plan['original_inventory'],plan['original_report'],entries)
    _isolate(output,roots|{plan_path.parent})
    required = {(t,i):'repair' if t in PHYSICAL_TASKS else 'reuse_only' if i in READY_POTS else 'rgb_review_blocked'
                for t in (*PHYSICAL_TASKS,'two_pots') for i in range(10)}
    chosen = {(r['task_id'],r['initial_state_index']):r['action'] for r in plan['sources']}
    if len(plan['sources'])!=30 or chosen!=required:
        raise ValueError('repair plan cannot promote accepted/RGB/old sources to native work')
    return preparation.prepare(plan['sources_path'],output,mode='prepare-missing',
        tasks=list(PHYSICAL_TASKS),indices=list(range(10)),protocol='nine-mask10',
        construction_method=METHOD,allow_failed_retry=False,replace_failed_originals=True,continuation=continuation)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    plan=sub.add_parser('plan',help='file-only inventory of all25 gaps and five read-only accepted sources')
    plan.add_argument('--inventory',required=True,type=Path)
    plan.add_argument('--preparation-report',required=True,type=Path)
    plan.add_argument('--out',required=True,type=Path)
    run=sub.add_parser('prepare',help='USER-STARTED: prepare only the20 drawer/microwave failed sources')
    run.add_argument('--plan',required=True,type=Path)
    run.add_argument('--out',required=True,type=Path)
    run.add_argument('--continue',dest='continuation',action='store_true')
    args=parser.parse_args(argv)
    result=plan_repairs(args.inventory,args.preparation_report,args.out) if args.command=='plan' else prepare_repairs(
        args.plan,args.out,continuation=args.continuation)
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    if args.command=='prepare':
        return 0 if len(result['sources'])==20 and all(r['status']=='ready' for r in result['sources']) else 2
    return 2 if result['reuse_issues'] else 0


if __name__=='__main__':
    raise SystemExit(main())
