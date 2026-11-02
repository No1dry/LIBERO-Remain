"""Microwave-only dispatch and first-source gate; no native execution."""
from copy import deepcopy
import hashlib
import importlib
import json

import pytest


def fixture_inputs(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless import nine_planning as n, selected_preparation as p
    r = importlib.import_module('benchmark.remaining_goals.headless.repair033_microwave')
    old = tmp_path/'frozen-r3'; old.mkdir()
    inventory = n.sources_template('nine-mask10'); rows = []
    for item in inventory['entries']:
        if item['task_id'] not in n.NEW_TASKS:
            continue
        ready = item['task_id'] != 'mug_microwave_close'
        origin = {'manifest':str(old/f"{item['task_id']}_{item['initial_state_index']}.json"),
                  'fixture_ready':ready}
        if item['task_id']=='two_pots':
            origin.update(rgb_certificate=str(old/'old-cert.json'),rgb_certificate_sha256='a'*64)
        item['origin'] = origin
        rows.append({**deepcopy(item),'status':'ready' if ready else 'failed'})
    inventory_path = old/'sources.json'; report_path = old/'preparation_report.json'
    inventory_path.write_text(json.dumps(inventory))
    report_path.write_text(json.dumps({'schema_version':'remaining-task033-r3-v6-preparation-v1',
        'observation_profile':'named-uint8-rgb-one-level-v6','sources':rows,'policy_called':False,'model_rollouts':0}))
    monkeypatch.setattr(r,'REPORT_SHA256',hashlib.sha256(report_path.read_bytes()).hexdigest())
    monkeypatch.setattr(r,'SOURCES_SHA256',hashlib.sha256(inventory_path.read_bytes()).hexdigest())
    def inspect(protocol,task,index,origin):
        ready=bool(origin and origin.get('fixture_ready'))
        candidate=bool(origin and origin.get('fixture_candidate'))
        return {'task_id':task,'initial_state_index':index,'origin':deepcopy(origin),
            'status':'ready' if ready else 'missing' if candidate else 'failed',
            'phase':'complete' if ready else 'replay' if candidate else 'candidate',
            'candidate':'existing' if ready or candidate else 'missing',
            'operations':[],'constructed':False,'replayed':False,'actual_control_steps':0,
            'count_status':'complete','reason':None if ready else 'original failure'}
    monkeypatch.setattr(p,'_inspect',inspect)
    return r,p,inventory_path,report_path


def test_source_zero_failure_stops_remaining_nine_and_continue_does_not_retry(tmp_path,monkeypatch):
    r,p,inventory,report=fixture_inputs(tmp_path,monkeypatch)
    before=inventory.read_bytes(),report.read_bytes(); calls=[]
    def native(operation,task,index,*args,**kwargs):
        calls.append((task,index,operation)); raise RuntimeError('no valid physical candidate')
    monkeypatch.setattr(p,'_native',native)
    result=r.prepare(inventory,report,tmp_path/'new')
    assert calls==[('mug_microwave_close',0,'build')]
    assert result['counts']=={'ready':20,'failed':1,'not_attempted':9}
    assert result['stopped_after_source0'] is True
    r.prepare(inventory,report,tmp_path/'new',continuation=True)
    assert len(calls)==1 and (inventory.read_bytes(),report.read_bytes())==before


def test_first_ready_allows_only_fixed_remaining_microwaves_and_keeps_old_twenty(tmp_path,monkeypatch):
    r,p,inventory,report=fixture_inputs(tmp_path,monkeypatch)
    original=json.loads(inventory.read_text()); calls=[]
    def native(operation,task,index,origin,output,protocol,**kwargs):
        calls.append((task,index,operation,kwargs))
        return {'manifest':str(output/'manifest.json'),'fixture_ready':operation=='replay',
                'fixture_candidate':True},{'actual_control_steps':300 if operation=='replay' else 230,'count_status':'complete'}
    monkeypatch.setattr(p,'_native',native)
    result=r.prepare(inventory,report,tmp_path/'new')
    assert [(i,op) for t,i,op,k in calls]==[(i,op) for i in range(10) for op in ('build','replay')]
    assert all(t=='mug_microwave_close' and k['construction_method']==r.METHOD and
               k['observation_profile']=='named-uint8-rgb-one-level-v6' for t,i,op,k in calls)
    assert result['counts']=={'ready':30}
    combined=json.loads((tmp_path/'new/sources.json').read_text())
    assert [v for v in combined['entries'] if v['task_id']!='mug_microwave_close']==[
        v for v in original['entries'] if v['task_id']!='mug_microwave_close']
    assert len(combined['expected'])==90
    r.prepare(inventory,report,tmp_path/'new',continuation=True)
    assert len(calls)==20


def test_first_dispatch_interruption_is_unknown_and_not_retried(tmp_path,monkeypatch):
    r,p,inventory,report=fixture_inputs(tmp_path,monkeypatch)
    calls=[]
    def prepare(*args,**kw):
        calls.append(kw); raise KeyboardInterrupt('before child report exists')
    monkeypatch.setattr(p,'prepare',prepare)
    with pytest.raises(KeyboardInterrupt):
        r.prepare(inventory,report,tmp_path/'new')
    result=r.prepare(inventory,report,tmp_path/'new',continuation=True)
    assert len(calls)==1
    row=next(row for row in result['sources'] if row['task_id']=='mug_microwave_close' and row['initial_state_index']==0)
    assert row['status']=='interrupted' and row['actual_control_steps'] is None
    assert result['counts']['not_attempted']==9


def test_changed_original_never_starts_native(tmp_path,monkeypatch):
    r,p,inventory,report=fixture_inputs(tmp_path,monkeypatch)
    monkeypatch.setattr(p,'_native',lambda *a,**k:pytest.fail('unexpected native dispatch'))
    report.write_text(report.read_text()+'\n')
    with pytest.raises(ValueError,match='hash'):
        r.prepare(inventory,report,tmp_path/'no-output')
    assert not (tmp_path/'no-output').exists()


def test_missing_reused_evidence_blocks_without_rebuilding_old_twenty(tmp_path,monkeypatch):
    r,p,inventory,report=fixture_inputs(tmp_path,monkeypatch)
    inspect=p._inspect
    def missing(protocol,task,index,origin):
        row=inspect(protocol,task,index,origin)
        if task=='two_pots' and index==8:
            row.update(status='failed',reason='RGB certificate missing')
        return row
    monkeypatch.setattr(p,'_inspect',missing)
    monkeypatch.setattr(p,'_native',lambda *a,**k:pytest.fail('unexpected native dispatch'))
    with pytest.raises(ValueError,match='no longer ready'):
        r.prepare(inventory,report,tmp_path/'no-output')
    assert not (tmp_path/'no-output').exists()


def test_source_zero_replay_failure_also_stops_remaining_nine(tmp_path,monkeypatch):
    r,p,inventory,report=fixture_inputs(tmp_path,monkeypatch); calls=[]
    def native(operation,task,index,origin,output,protocol,**kwargs):
        calls.append((index,operation))
        if operation=='replay':
            raise ValueError('paired replay failed acceptance')
        return {'manifest':str(output/'manifest.json'),'fixture_candidate':True}, {
            'actual_control_steps':230,'count_status':'complete'}
    monkeypatch.setattr(p,'_native',native)
    result=r.prepare(inventory,report,tmp_path/'new')
    assert calls==[(0,'build'),(0,'replay')]
    assert result['counts']=={'ready':20,'failed':1,'not_attempted':9}
    r.prepare(inventory,report,tmp_path/'new',continuation=True)
    assert len(calls)==2


def test_remaining_interruption_keeps_unknown_and_continues_only_unattempted(tmp_path,monkeypatch):
    r,p,inventory,report=fixture_inputs(tmp_path,monkeypatch); calls=[]
    def native(operation,task,index,origin,output,protocol,**kwargs):
        calls.append((index,operation))
        if index==1:
            raise KeyboardInterrupt('native call may have begun')
        return {'manifest':str(output/'manifest.json'),'fixture_candidate':True,
                'fixture_ready':operation=='replay'}, {'actual_control_steps':300,'count_status':'complete'}
    monkeypatch.setattr(p,'_native',native)
    with pytest.raises(KeyboardInterrupt):
        r.prepare(inventory,report,tmp_path/'new')
    assert calls==[(0,'build'),(0,'replay'),(1,'build')]
    result=r.prepare(inventory,report,tmp_path/'new',continuation=True)
    assert result['counts']=={'ready':29,'interrupted':1}
    assert calls==[(0,'build'),(0,'replay'),(1,'build')]+[(i,op) for i in range(2,10) for op in ('build','replay')]
    unknown=next(row for row in result['sources'] if row['task_id']=='mug_microwave_close' and row['initial_state_index']==1)
    assert unknown['actual_control_steps'] is None
    r.prepare(inventory,report,tmp_path/'new',continuation=True)
    assert len(calls)==19


def test_r5_method_rejects_wrong_task_or_profile_before_creating_output(tmp_path):
    from benchmark.remaining_goals.headless import selected_preparation as p,nine_planning as n
    inv=tmp_path/'inventory.json'; inv.write_text(json.dumps(n.sources_template('nine-mask10')))
    for options in ({'tasks':['two_pots'],'observation_profile':'named-uint8-rgb-one-level-v6'},
                    {'tasks':['mug_microwave_close']}):
        with pytest.raises(ValueError,match='R5'):
            p.prepare(inv,tmp_path/'forbidden',indices=[0],construction_method='microwave_gravity_support_pose_transplant_v3',**options)
    assert not (tmp_path/'forbidden').exists()
