"""Bind explicit R2 paths without changing legacy preparation or interpreter aliases."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


def test_runtime_config_retains_venv_alias(tmp_path,monkeypatch,capsys):
    from benchmark.remaining_goals.headless import nine_cli
    alias=tmp_path/'venv'/'bin'/'python'
    alias.parent.mkdir(parents=True)
    try:
        alias.symlink_to(sys.executable)
    except OSError:
        # Windows lacking symlink privilege: replace only the filesystem resolver
        # seam; the actual CLI/config writer still exercises the wrong resolve call.
        original=Path.resolve
        def resolve(path,*args,**kwargs):
            return original(Path(sys.executable)) if path==alias else original(path,*args,**kwargs)
        monkeypatch.setattr(Path,'resolve',resolve)
    out=tmp_path/'runtime.json'
    nine_cli.main(['runtime-config','--oft-repo',str(tmp_path/'oft'),'--checkpoint',str(tmp_path/'ckpt'),
                   '--model-python',str(alias),'--out',str(out)])
    assert json.loads(out.read_text())['runtime']['python_executable']==str(alias.absolute())
    capsys.readouterr()


def test_r2_geometry_flag_reaches_candidate_generation(monkeypatch):
    from benchmark.remaining_goals import build
    env=SimpleNamespace(sim=SimpleNamespace(model=object(),data=object()))
    monkeypatch.setattr(build,'restore_raw_state',lambda *a:None)
    options=[]
    def placement(*args,**kw): options.append(kw); return ['candidate']
    monkeypatch.setattr(build,'placement_candidates',placement)
    profile={'goals':[{'predicates':[['in','bowl','drawer_region']]}], 'in_volume_regions':['drawer_region']}
    assert build._per_goal(env,[],profile,24)==[['candidate']]
    assert options[-1]['in_volume'] is True
    profile.pop('in_volume_regions')
    build._per_goal(env,[],profile,24)
    assert 'in_volume' not in options[-1]


def test_method_selector_is_bound_and_does_not_enable_normal00(tmp_path,monkeypatch):
    from benchmark.remaining_goals.headless import selected_preparation as p, nine_planning as plan
    method='selected_A_only_bounded_settle_component_transplant_v2'
    inv=tmp_path/'inventory.json'
    inv.write_text(json.dumps(plan.sources_template('nine-mask10')))
    calls=[]
    def native(operation,task,index,origin,output,protocol,**kwargs):
        calls.append(kwargs)
        raise RuntimeError('synthetic preparation failure')
    monkeypatch.setattr(p,'_native',native)
    out=tmp_path/'new'
    r=p.prepare(inv,out,mode='prepare-missing',tasks=['bowl_drawer_close'],indices=[0],
                construction_method=method)
    assert r['construction_method']==method and calls==[{'construction_method':method}]
    with pytest.raises(ValueError,match='identity'):
        p.prepare(inv,out,continuation=True,tasks=['bowl_drawer_close'],indices=[0])
    p.prepare(inv,out,mode='prepare-missing',continuation=True,tasks=['bowl_drawer_close'],indices=[0],construction_method=method)
    assert len(calls)==1
    normal=tmp_path/'normal.json'
    normal.write_text(json.dumps(plan.sources_template('nine-normal00')))
    with pytest.raises(ValueError,match='method'):
        p.prepare(normal,tmp_path/'not-created',construction_method=method)
    assert not (tmp_path/'not-created').exists()
