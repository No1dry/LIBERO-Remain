"""Explicit fake-only preflight/CLI checks, no simulator/model assets."""
import json

import pytest

from benchmark.remaining_goals.finish import cli, workflow
from tests.test_finish_runner import Env, episode


class PreflightEnv(Env):
    closed = False

    def close(self):
        self.closed = True


def source(monkeypatch, tmp_path):
    ep = episode()
    ep['task_id'] = 'basket'
    manifest = {'episodes':[ep], 'environment':{'name':'fake'}}
    monkeypatch.setattr(workflow, 'load_source', lambda config: (manifest, tmp_path/'source.json'))
    return ep


def test_user_preflight_uses_four_hold_intervals_and_closes(monkeypatch, tmp_path):
    ep = source(monkeypatch, tmp_path)
    env = PreflightEnv()
    out = tmp_path/'preflight'
    result = cli.preflight({}, ep['episode_id'], out, env_factory=lambda config:env)
    assert result['status'] == 'recorded' and result['model_calls'] == 0
    assert [r['step'] for r in result['trace']] == list(range(5))
    assert env.resets == env.begins == 1 and env.holds == env.steps == 4 and env.closed
    assert (out/'initial.npz').is_file()
    with pytest.raises(FileExistsError):
        cli.preflight({}, ep['episode_id'], out, env_factory=lambda config:env)


@pytest.mark.parametrize('problem', ['mask', 'hold', 'step', 'interrupt'])
def test_user_preflight_preserves_partial_and_closes(monkeypatch, tmp_path, problem):
    ep = source(monkeypatch, tmp_path)
    env = PreflightEnv(wrong_initial=problem=='mask', fail_step=2 if problem=='step' else None)
    if problem == 'hold':
        env.begin_hold = lambda: None
    if problem == 'interrupt':
        def interrupt():
            raise KeyboardInterrupt()
        env.hold_action = interrupt
    out = tmp_path/'preflight'
    result = cli.preflight({}, ep['episode_id'], out, env_factory=lambda config:env)
    assert result['status'] == 'technical_error' and env.closed
    assert result['trace'][0]['step'] == 0
    assert json.loads((out/'preflight.json').read_text())['error']
    assert env.steps == (1 if problem == 'step' else 0)


@pytest.mark.parametrize('status,code', [('completed',0),('error',2),('insufficient',2),('interrupted',130)])
def test_feature_cli_preserves_worker_status(monkeypatch, tmp_path, status, code):
    from benchmark.remaining_goals.finish import data_commands
    monkeypatch.setattr(data_commands, 'feature_export_command', lambda *args:{'status':status})
    assert cli.main(['export-features','--audit','unused','--runtime-config','unused','--out',str(tmp_path/'out')]) == code
