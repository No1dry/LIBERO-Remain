"""R7 opt-in dispatch and immutable old evidence; all native work is faked."""
from copy import deepcopy
import hashlib
import importlib
import json

import pytest

from tests.test_task033_r5_queue import fixture_inputs

PROFILE = 'active-free-object-pose-stability-v7'


def inputs(tmp_path, monkeypatch):
    r7 = importlib.import_module('benchmark.remaining_goals.headless.repair033_pose_stability')
    r5, p, inv, report = fixture_inputs(tmp_path, monkeypatch)
    def failed(*a, **kw):
        raise ValueError('reviewed R5 physical failure')
    monkeypatch.setattr(p, '_native', failed)
    r5.prepare(inv, report, tmp_path/'prior-r5')
    revision = tmp_path/'prior-r5/microwave_repair_report.json'
    monkeypatch.setattr(r7, 'REVISION_REPORT_SHA256', hashlib.sha256(revision.read_bytes()).hexdigest())
    return r7, r5, p, inv, report, revision


def test_v7_reuses_twenty_and_binds_revision_without_changing_old_results(tmp_path, monkeypatch):
    r7, r5, p, inv, report, revision = inputs(tmp_path, monkeypatch)
    old_bytes = [path.read_bytes() for path in (inv, report, revision)]
    original = json.loads(inv.read_text()); calls = []
    def native(op, task, index, origin, output, protocol, **kw):
        calls.append((op, task, index, deepcopy(kw)))
        return {'manifest':str(output/'manifest.json'), 'fixture_candidate':True,
                'fixture_ready':op=='replay'}, {'actual_control_steps':300,'count_status':'complete'}
    monkeypatch.setattr(p, '_native', native)
    result = r7.prepare(inv, report, revision, tmp_path/'new-r7')
    assert result['counts']=={'ready':30} and result['stability_profile']==PROFILE
    assert result['revision_report_sha256']==hashlib.sha256(old_bytes[2]).hexdigest()
    assert [(index, op) for op, task, index, kw in calls]==[(i, op) for i in range(10) for op in ('build','replay')]
    assert all(task==r5.TASK and kw=={'construction_method':r5.METHOD,
        'observation_profile':'named-uint8-rgb-one-level-v6','stability_profile':PROFILE}
        for op, task, index, kw in calls)
    combined=json.loads((tmp_path/'new-r7/sources.json').read_text())
    assert [e for e in combined['entries'] if e['task_id']!=r5.TASK]==[
        e for e in original['entries'] if e['task_id']!=r5.TASK]
    assert len(combined['expected'])==90
    assert [path.read_bytes() for path in (inv,report,revision)]==old_bytes
    assert (tmp_path/'new-r7/pre_revision_report.json').read_bytes()==old_bytes[2]
    r7.prepare(inv, report, revision, tmp_path/'new-r7', continuation=True)
    assert len(calls)==20


def test_v7_first_failure_stops_nine_and_continuation_never_retries(tmp_path,monkeypatch):
    r7,r5,p,inv,report,revision=inputs(tmp_path,monkeypatch); calls=[]
    def failed(op,task,index,*a,**kw):
        calls.append((index,op)); raise ValueError('pose or other physical criterion failed')
    monkeypatch.setattr(p,'_native',failed)
    result=r7.prepare(inv,report,revision,tmp_path/'new')
    assert result['counts']=={'ready':20,'failed':1,'not_attempted':9}
    assert result['stopped_after_source0'] is True and calls==[(0,'build')]
    r7.prepare(inv,report,revision,tmp_path/'new',continuation=True)
    assert calls==[(0,'build')]


def test_v7_revision_byte_change_stops_before_output_and_native(tmp_path,monkeypatch):
    r7,r5,p,inv,report,revision=inputs(tmp_path,monkeypatch)
    revision.write_bytes(revision.read_bytes()+b'\n')
    monkeypatch.setattr(p,'_native',lambda *a,**kw:pytest.fail('must not start native'))
    with pytest.raises(ValueError,match='revision.*hash'):
        r7.prepare(inv,report,revision,tmp_path/'new')
    assert not (tmp_path/'new').exists()


def test_v7_cannot_retry_inside_reviewed_r5_directory(tmp_path,monkeypatch):
    r7,r5,p,inv,report,revision=inputs(tmp_path,monkeypatch)
    original=revision.read_bytes()
    monkeypatch.setattr(p,'_native',lambda *a,**kw:pytest.fail('must not start native'))
    with pytest.raises(ValueError,match='overlap'):
        r7.prepare(inv,report,revision,revision.parent,continuation=True)
    assert revision.read_bytes()==original


def test_v7_continuation_cannot_change_profile(tmp_path,monkeypatch):
    r7,r5,p,inv,report,revision=inputs(tmp_path,monkeypatch)
    r7.prepare(inv,report,revision,tmp_path/'new')
    monkeypatch.setattr(p,'_native',lambda *a,**kw:pytest.fail('must not start native'))
    with pytest.raises(ValueError,match='identity'):
        p.prepare(inv,tmp_path/'new/preparation',mode='prepare-missing',tasks=[r5.TASK],indices=[0],
            protocol='nine-mask10',construction_method=r5.METHOD,observation_profile='named-uint8-rgb-one-level-v6',
            replace_failed_originals=True,continuation=True)


@pytest.mark.parametrize('options', [
    {'tasks':['two_pots']}, {'observation_profile':None},
    {'construction_method':'selected_A_only_bounded_settle_component_transplant_v2'},
    {'stability_profile':'unknown-profile'},
])
def test_v7_wrong_scope_is_rejected_before_output(tmp_path,monkeypatch,options):
    r5,p,inv,report=fixture_inputs(tmp_path,monkeypatch)
    kw={'tasks':[r5.TASK],'indices':[0],'protocol':'nine-mask10','construction_method':r5.METHOD,
        'observation_profile':'named-uint8-rgb-one-level-v6','stability_profile':PROFILE,**options}
    monkeypatch.setattr(p,'_native',lambda *a,**kw:pytest.fail('must not start native'))
    with pytest.raises(ValueError):
        p.prepare(inv,tmp_path/'invalid',mode='prepare-missing',**kw)
    assert not (tmp_path/'invalid').exists()
