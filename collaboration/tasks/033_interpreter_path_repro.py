"""CPU reproduction: interpreter paths must retain their virtual-environment alias."""
import json
from pathlib import Path
import sys

from benchmark.remaining_goals.headless import nine_cli


def test_runtime_config_retains_venv_python_alias(tmp_path, capsys):
    interpreter = tmp_path / 'model-venv' / 'bin' / 'python'
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    output = tmp_path / 'runtime.json'
    assert nine_cli.main(['runtime-config', '--oft-repo', str(tmp_path / 'oft'),
                          '--checkpoint', str(tmp_path / 'checkpoint'),
                          '--model-python', str(interpreter), '--out', str(output)]) == 0
    capsys.readouterr()
    actual = json.loads(output.read_text())['runtime']['python_executable']
    assert actual == str(interpreter.absolute()), (
        'Resolving the executable symlink discards the virtual-environment prefix: '
        f'{actual!r} != {str(interpreter.absolute())!r}'
    )
