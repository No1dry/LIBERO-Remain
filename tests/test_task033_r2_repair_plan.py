"""R2 uses the reviewed failed indices; accepted or RGB-blocked sources never run."""
import hashlib
import importlib
import json
from pathlib import Path
from copy import deepcopy

import pytest


def fixture_inputs(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless import nine_planning as p
    r = importlib.import_module('benchmark.remaining_goals.headless.repair033_sources')
    old = tmp_path / 'frozen-aedfe169'
    old.mkdir()
    rows, entries = [], []
    for e in p.expected_episodes('nine-mask10'):
        if e['task_id'] not in p.NEW_TASKS:
            entries.append({'task_id': e['task_id'], 'initial_state_index': e['initial_state_index'], 'origin': None})
            continue
        index, task = e['initial_state_index'], e['task_id']
        ready = task == 'two_pots' and index in [1, 3, 4, 5, 6]
        origin = {'manifest': str(old / task / f'{index}.json'), 'fixture_ready': ready}
        rows.append({'task_id': task, 'initial_state_index': index, 'status': 'ready' if ready else 'failed',
                     'origin': origin, 'reason': None if ready else 'original physical failure'})
        entries.append({'task_id': task, 'initial_state_index': index, 'origin': origin})
    inventory = old / 'sources.json'
    report = old / 'preparation_report.json'
    inventory.write_text(json.dumps({'schema_version':p.SOURCES_SCHEMA,'protocol':'nine-mask10',
                                    'expected':p.expected_episodes('nine-mask10'),'entries':entries}))
    report.write_text(json.dumps({'schema_version':'remaining-headless-selected-preparation-v1',
        'protocol':'nine-mask10','expected':p.expected_episodes('nine-mask10'),'sources':rows,
        'policy_called':False,'model_rollouts':0}))
    monkeypatch.setattr(r,'REVIEWED_REPORT_SHA256',hashlib.sha256(report.read_bytes()).hexdigest())
    def inspect(protocol, task, index, origin):
        return {'task_id':task,'initial_state_index':index,'origin':deepcopy(origin),
                'status':'ready' if origin['fixture_ready'] else 'failed','reason':'recorded original result'}
    monkeypatch.setattr(r.preparation, '_inspect', inspect)
    return r, inventory, report


def test_plan_keeps_five_ready_and_blocks_rgb_without_native(tmp_path, monkeypatch):
    r, inventory, report = fixture_inputs(tmp_path, monkeypatch)
    old_bytes = (inventory.read_bytes(), report.read_bytes())
    monkeypatch.setattr(r.preparation,'_native',lambda *a,**k:pytest.fail('file plan cannot invoke native'))
    out = tmp_path / 'r2'
    plan = r.plan_repairs(inventory,report,out)
    assert plan['counts'] == {'reviewed_failures':25,'repair_executable':20,'rgb_review_blocked':5,'reuse_only':5}
    assert [row['initial_state_index'] for row in plan['sources'] if row['action']=='reuse_only'] == [1,3,4,5,6]
    assert [row['initial_state_index'] for row in plan['sources'] if row['action']=='rgb_review_blocked'] == [0,2,7,8,9]
    assert len(json.loads((out/'sources.json').read_text())['expected']) == 90
    assert (inventory.read_bytes(),report.read_bytes()) == old_bytes
    assert not plan['policy_called'] and plan['model_rollouts']==0


def test_prepare_selects_only_twenty_and_binds_v2_without_touching_old(tmp_path, monkeypatch):
    r, inventory, report = fixture_inputs(tmp_path,monkeypatch)
    root = tmp_path/'r2'
    r.plan_repairs(inventory,report,root)
    calls=[]
    def prepare(inv,out,**kw):
        calls.append(kw)
        return {'sources':[],'policy_called':False,'model_rollouts':0}
    monkeypatch.setattr(r.preparation,'prepare',prepare)
    r.prepare_repairs(root/'repair_plan.json',tmp_path/'new-physical-output')
    assert len(calls)==1
    assert calls[0]['tasks']==['bowl_drawer_close','mug_microwave_close']
    assert calls[0]['indices']==list(range(10))
    assert calls[0]['protocol']=='nine-mask10' and calls[0]['allow_failed_retry'] is False
    assert calls[0]['replace_failed_originals'] is True
    assert calls[0]['construction_method']=='selected_A_only_bounded_settle_component_transplant_v2'


def test_changed_reviewed_report_or_history_overlap_is_rejected(tmp_path,monkeypatch):
    r,inventory,report=fixture_inputs(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='overlap'):
        r.plan_repairs(inventory,report,report.parent/'new-output')
    report.write_text(report.read_text()+'\n')
    with pytest.raises(ValueError,match='report'):
        r.plan_repairs(inventory,report,tmp_path/'r2')
    assert not (tmp_path/'r2').exists()


def test_missing_ready_evidence_is_not_reclassified_as_repair(tmp_path,monkeypatch):
    r,inventory,report=fixture_inputs(tmp_path,monkeypatch)
    original=r.preparation._inspect
    def inspect(protocol,task,index,origin):
        row=original(protocol,task,index,origin)
        if task=='two_pots' and index==3: row.update(status='missing',reason='old evidence missing')
        return row
    monkeypatch.setattr(r.preparation,'_inspect',inspect)
    plan=r.plan_repairs(inventory,report,tmp_path/'r2')
    row=next(x for x in plan['sources'] if x['task_id']=='two_pots' and x['initial_state_index']==3)
    assert row['action']=='reuse_only' and row['current']['status']=='missing'
    assert len(plan['reuse_issues'])==1 and plan['counts']['repair_executable']==20
