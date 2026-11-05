"""R3 exact queue, identity and interruption checks without native execution."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_task033_r2_repair_plan import fixture_inputs

V6 = 'named-uint8-rgb-one-level-v6'


def setup_r3(tmp_path, monkeypatch, blocked=False):
    r2, inventory, report = fixture_inputs(tmp_path, monkeypatch)
    r3 = importlib.import_module('benchmark.remaining_goals.headless.repair033_v6')
    inspected = r2.preparation._inspect
    def inspect(protocol, task, index, origin):
        row = inspected(protocol, task, index, origin)
        if origin.get('fixture_derived'):
            row['status'] = 'ready'
        return row
    monkeypatch.setattr(r2.preparation, '_inspect', inspect)
    derived = []
    def derive(task, index, origin, output, protocol='nine-mask10'):
        derived.append((task, index))
        state = 'ready' if index in (0, 2, 8) else 'needs_replay' if index == 7 else 'needs_build'
        if blocked and index == 2:
            state = 'blocked'
        chosen = {**origin, 'fixture_derived': state == 'ready'}
        result = {'status': state, 'origin': chosen, 'original_origin': deepcopy(origin),
                  'reason': 'synthetic stored evidence boundary', 'required_native_steps': 300 if index == 7 else None}
        output = Path(output)
        output.mkdir(parents=True)
        (output/'derivation_report.json').write_text(json.dumps(result), encoding='utf-8')
        return result
    monkeypatch.setattr(r3, '_derive_source', derive)
    return r3, inventory, report, derived


def test_plan_derives_only_five_rgb_gaps_preserves_legacy_and_full_population(tmp_path, monkeypatch):
    r3, inventory, report, derived = setup_r3(tmp_path, monkeypatch)
    before = inventory.read_bytes(), report.read_bytes()
    monkeypatch.setattr(r3.preparation, '_native', lambda *a, **k: pytest.fail('file planning invoked native'))
    plan = r3.plan_repairs(inventory, report, tmp_path/'plan')
    assert derived == [('two_pots', i) for i in [0, 2, 7, 8, 9]]
    actions = {(r['task_id'], r['initial_state_index']): r['action'] for r in plan['sources']}
    assert [i for (task, i), a in actions.items() if a == 'reuse_only'] == [1, 3, 4, 5, 6]
    assert [i for (task, i), a in actions.items() if a == 'derived_ready'] == [0, 2, 8]
    assert actions['two_pots', 7] == 'replay' and actions['two_pots', 9] == 'build'
    assert sum(a == 'repair' for a in actions.values()) == 20
    assert plan['observation_profile'] == V6 and plan['counts']['native_sources'] == 22
    assert len(json.loads((tmp_path/'plan/sources.json').read_text())['expected']) == 90
    assert (inventory.read_bytes(), report.read_bytes()) == before


def test_prepare_routes_only_needed_sources_with_v6_and_keeps_blocked(tmp_path, monkeypatch):
    r3, inventory, report, _ = setup_r3(tmp_path, monkeypatch, blocked=True)
    r3.plan_repairs(inventory, report, tmp_path/'plan')
    calls = []
    def prepare(inv, out, **options):
        task, index = options['tasks'][0], options['indices'][0]
        calls.append((task, index, options))
        return {'sources': [{'task_id': task, 'initial_state_index': index,
                            'status': 'failed', 'origin': None, 'actual_control_steps': None}],
                'model_rollouts': 0, 'policy_called': False}
    monkeypatch.setattr(r3.preparation, 'prepare', prepare)
    result = r3.prepare_repairs(tmp_path/'plan/repair_plan.json', tmp_path/'prepared')
    assert len(calls) == 22 and {i for t, i, _ in calls if t == 'two_pots'} == {7, 9}
    assert all(c[2]['observation_profile'] == V6 for c in calls)
    assert next(c[2]['mode'] for c in calls if c[:2] == ('two_pots', 7)) == 'replay-missing'
    assert next(r for r in result['sources'] if (r['task_id'], r['initial_state_index']) == ('two_pots', 2))['action'] == 'blocked'
    assert len(result['sources']) == 30 and result['model_rollouts'] == 0


def test_plan_derivation_hash_and_original_output_isolation_fail_closed(tmp_path, monkeypatch):
    r3, inventory, report, _ = setup_r3(tmp_path, monkeypatch)
    r3.plan_repairs(inventory, report, tmp_path/'plan')
    monkeypatch.setattr(r3.preparation, 'prepare', lambda *a, **k: pytest.fail('invalid plan invoked preparation'))
    with pytest.raises(ValueError, match='overlap'):
        r3.prepare_repairs(tmp_path/'plan/repair_plan.json', inventory.parent/'bad')
    path = tmp_path/'plan/derivations/two_pots_s00/derivation_report.json'
    path.write_text(path.read_text()+'\n')
    with pytest.raises(ValueError, match='derivation'):
        r3.prepare_repairs(tmp_path/'plan/repair_plan.json', tmp_path/'prepared')


def test_preparation_binds_profile_and_forwards_certificate(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless import selected_preparation as p, nine_planning as n
    inv = tmp_path/'inventory.json'
    inventory = n.sources_template('nine-mask10')
    entry = next(r for r in inventory['entries'] if r['task_id'] == 'two_pots' and r['initial_state_index'] == 7)
    entry['origin'] = {'manifest': 'original.json', 'rgb_certificate': 'candidate-cert.json'}
    inv.write_text(json.dumps(inventory))
    seen = []
    def inspect(protocol, task, index, origin):
        return {'task_id':task, 'initial_state_index':index, 'origin':origin,
                'status':'missing', 'phase':'replay', 'candidate':'existing',
                'operations':[], 'constructed':False, 'replayed':False}
    def native(operation, task, index, origin, output, protocol, **options):
        seen.append((operation, origin, options))
        raise RuntimeError('controlled native-boundary failure')
    monkeypatch.setattr(p, '_inspect', inspect)
    monkeypatch.setattr(p, '_native', native)
    kwargs = dict(tasks=['two_pots'], indices=[7], mode='replay-missing', observation_profile=V6)
    result = p.prepare(inv, tmp_path/'out', **kwargs)
    assert result['observation_profile'] == V6
    assert seen[0][0] == 'replay' and seen[0][2]['observation_profile'] == V6
    assert seen[0][1]['rgb_certificate'] == str((tmp_path/'candidate-cert.json').resolve())
    with pytest.raises(ValueError, match='identity'):
        p.prepare(inv, tmp_path/'out', continuation=True, tasks=['two_pots'], indices=[7])
    p.prepare(inv, tmp_path/'out', continuation=True, **kwargs)
    assert len(seen) == 1


def test_queue_continue_visits_remaining_gaps_without_retrying_any_attempt(tmp_path, monkeypatch):
    r3, inventory, report, _ = setup_r3(tmp_path, monkeypatch)
    original_inspect = r3.preparation._inspect
    def inspect(protocol, task, index, origin):
        row = original_inspect(protocol, task, index, origin)
        row.update(operations=[], constructed=False, replayed=False,
                   phase='replay' if (task, index)==('two_pots', 7) else 'candidate',
                   candidate='existing' if (task, index)==('two_pots', 7) else 'missing')
        return row
    monkeypatch.setattr(r3.preparation, '_inspect', inspect)
    r3.plan_repairs(inventory, report, tmp_path/'plan')
    calls = []
    def native(operation, task, index, origin, output, protocol, **options):
        calls.append((task, index, operation))
        if len(calls) == 1:
            raise KeyboardInterrupt('controlled interruption')
        raise RuntimeError('preserve failed first attempt')
    monkeypatch.setattr(r3.preparation, '_native', native)
    with pytest.raises(KeyboardInterrupt):
        r3.prepare_repairs(tmp_path/'plan/repair_plan.json', tmp_path/'prepared')
    r3.prepare_repairs(tmp_path/'plan/repair_plan.json', tmp_path/'prepared', continuation=True)
    assert len(calls) == len(set(calls)) == 22
    assert ('two_pots', 7, 'replay') in calls and ('two_pots', 9, 'build') in calls
    r3.prepare_repairs(tmp_path/'plan/repair_plan.json', tmp_path/'prepared', continuation=True)
    assert len(calls) == 22


def test_native_bridge_keeps_v6_and_candidate_certificate_on_paired_replay(tmp_path, monkeypatch):
    from benchmark.remaining_goals.headless import selected_preparation as p
    calls = []
    def replay(manifest, output, *, task, index, protocol, observation_profile, rgb_certificate):
        calls.append((manifest, task, index, protocol, observation_profile, rgb_certificate))
        Path(output).mkdir()
        result = {'technical_acceptance': True}
        (Path(output)/'replay_report.json').write_text(json.dumps(result))
        return result
    owner = SimpleNamespace(step=lambda *a, **k: pytest.fail('native step is forbidden'))
    modules = {'benchmark.remaining_goals.selected_replay': SimpleNamespace(replay=replay),
               'benchmark.remaining_goals.replay_candidates': SimpleNamespace(ReplayAuditEnv=owner)}
    monkeypatch.setattr(p.importlib, 'import_module', lambda name: modules[name])
    origin, ledger = p._native('replay', 'two_pots', 7,
        {'manifest':'original.json', 'rgb_certificate':'candidate.json'}, tmp_path/'paired', 'nine-mask10',
        construction_method=p.R2_METHOD, observation_profile=V6)
    assert calls == [('original.json','two_pots',7,'nine-mask10',V6,'candidate.json')]
    assert origin['rgb_certificate'] == 'candidate.json' and Path(origin['candidate_replay']).is_file()
    assert ledger['observation_profile'] == V6 and ledger['actual_control_steps'] == 0
