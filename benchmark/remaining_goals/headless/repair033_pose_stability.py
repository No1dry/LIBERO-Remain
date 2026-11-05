"""R7 opt-in A-pose admission using the unchanged R5 first-source queue.

USER-STARTED native preparation only. The R3 inventory supplies the original
twenty accepted origins; the exact reviewed R5 failure is bound as pre-revision
evidence. No old result is regraded, retried in place or made into a certificate.
"""
from pathlib import Path
import argparse
import json

from . import repair033_microwave as r5, selected_preparation as preparation
from .nine_planning import NEW_TASKS, file_sha, read_json
from ..stability import PROFILE
from ..validation import V6_PROFILE

REPORT_SCHEMA = 'remaining-task033-r7-pose-preparation-v1'
REVISION_REPORT_SHA256 = 'd0ca805413e78cd9fbfee212b1d8b66f93d802f90969f37ad3b0dbd9193b4fcb'


def reviewed_revision(path, entries):
    path = Path(path).resolve()
    if file_sha(path) != REVISION_REPORT_SHA256:
        raise ValueError('R7 revision report hash differs from the reviewed R5 bytes')
    report = read_json(path)
    if (report.get('schema_version') != r5.SCHEMA or report.get('protocol') != 'nine-mask10'
            or report.get('construction_method') != r5.METHOD or report.get('stability_profile') is not None
            or report.get('observation_profile') != V6_PROFILE
            or report.get('original_inventory_sha256') != r5.SOURCES_SHA256
            or report.get('original_report_sha256') != r5.REPORT_SHA256
            or report.get('counts') != {'ready':20, 'failed':1, 'not_attempted':9}
            or report.get('policy_called') is not False or report.get('model_rollouts') != 0
            or report.get('source0_dispatched') is not True or report.get('stopped_after_source0') is not True):
        raise ValueError('R7 pre-revision evidence differs from the reviewed R5 scope/result')
    expected = {(task, i) for task in NEW_TASKS for i in range(10)}
    seen = set()
    for row in report.get('sources', []):
        key = row.get('task_id'), row.get('initial_state_index')
        if key not in expected or key in seen:
            raise ValueError('R7 pre-revision source population differs')
        seen.add(key)
        wanted = 'ready' if key[0] != r5.TASK else 'failed' if key[1] == 0 else 'not_attempted'
        if row.get('status') != wanted:
            raise ValueError('R7 pre-revision source status differs')
        if key[0] != r5.TASK and preparation._origin(row.get('origin'), path.parent) != entries.get(key):
            raise ValueError('R7 must reuse the same twenty accepted origins and certificates')
    if seen != expected:
        raise ValueError('R7 pre-revision report must retain the original thirty-source population')
    return {'revision_report': str(path), 'revision_report_sha256': REVISION_REPORT_SHA256}


def prepare(inventory_path, report_path, revision_report_path, output, *, continuation=False):
    return r5.prepare(inventory_path, report_path, output, continuation=continuation,
                      stability_profile=PROFILE, revision_report_path=revision_report_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('prepare', help='USER-STARTED: new R7 directory; source0 must be truly ready before 1..9')
    run.add_argument('--inventory', required=True, type=Path)
    run.add_argument('--preparation-report', required=True, type=Path)
    run.add_argument('--revision-report', required=True, type=Path)
    run.add_argument('--out', required=True, type=Path)
    run.add_argument('--continue', dest='continuation', action='store_true')
    args = parser.parse_args(argv)
    result = prepare(args.inventory, args.preparation_report, args.revision_report, args.out,
                     continuation=args.continuation)
    print(json.dumps({'report':str(args.out/'microwave_repair_report.json'), 'counts':result['counts'],
                      'stability_profile':PROFILE, 'stopped_after_source0':result['stopped_after_source0']},
                     ensure_ascii=False))
    return 0 if result['counts'] == {'ready':30} else 2


if __name__ == '__main__':
    raise SystemExit(main())
