"""The documented Task033 file-only CLI needs neither native libraries nor models."""
import json
from pathlib import Path

from benchmark.remaining_goals.headless import nine_cli as cli


def test_configuration_and_missing_coverage_without_native(tmp_path, capsys):
    runtime, reuse = tmp_path / "runtime.json", tmp_path / "reuse.json"
    assert cli.main(["runtime-config", "--oft-repo", str(tmp_path / "oft"), "--checkpoint", str(tmp_path / "weights"),
                     "--model-python", str(tmp_path / "python"), "--out", str(runtime)]) == 0
    assert cli.main(["reuse-index", "--out", str(reuse)]) == 0
    for protocol in ("nine-normal00", "nine-mask10"):
        sources, config, budget = (tmp_path / (protocol + suffix) for suffix in ("-sources.json", "-config.json", "-budget.json"))
        assert cli.main(["sources-template", "--protocol", protocol, "--out", str(sources)]) == 0
        assert cli.main(["budget-plan", "--protocol", protocol, "--out", str(budget)]) == 0
        assert cli.main(["configure", "--protocol", protocol, "--runtime-config", str(runtime), "--sources", str(sources),
                         "--reuse-manifest", str(reuse), "--out", str(config)]) == 0
        assert json.loads(config.read_text())["population"] == "new-three"
        assert json.loads(budget.read_text())["selected_count"] == 30
    report = tmp_path / "report"
    assert cli.main(["summarize", "--reuse-manifest", str(reuse), "--out", str(report)]) == 0
    result = json.loads((report / "summary.json").read_text())
    assert set(result["conditions"]) == {"00", "10"}
    assert result["conditions"]["00"]["coverage"]["denominator"] == 90
    assert result["conditions"]["00"]["official_task_SR"]["percent"] is None
    capsys.readouterr()
