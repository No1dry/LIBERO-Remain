"""Persist dynamic provider evidence with tiny files; no physical validation."""
from copy import deepcopy
import json

import pytest

from benchmark.remaining_goals.finish import data
from tests.finish_domain_helpers import FakeProvider, make_assets


class EvidenceFailure(ValueError):
    def __init__(self, evidence):
        super().__init__("synthetic layout mismatch: geom_bodyid")
        self.evidence = deepcopy(evidence)


class MetadataProvider(FakeProvider):
    def __init__(self, fail_at=None, fail_close=False, invalid_metadata=False):
        super().__init__()
        self.fail_at = fail_at
        self.fail_close = fail_close
        self.invalid_metadata = invalid_metadata
        self.metadata = {"test_only": True, "physics_validated": False,
            "demo_model_compatibility": {"scope": "synthetic-metadata-test", "loads": []}}

    def restore_demonstration(self, state, model_xml=None):
        attempt = len(self.restore_calls) + 1
        evidence = {"classification": "rejected" if attempt == self.fail_at else "synthetic",
            "attempt": attempt,
            "layout_diff": {"geom_bodyid": {"baseline": [1, 2], "loaded": [1, 3]}}}
        self.metadata["demo_model_compatibility"]["loads"].append(evidence)
        if attempt == self.fail_at:
            raise EvidenceFailure(evidence)
        return super().restore_demonstration(state, model_xml=model_xml)

    def close(self):
        super().close()
        self.metadata["closed"] = True
        if self.invalid_metadata:
            self.metadata["invalid"] = float("nan")
        if self.fail_close:
            raise RuntimeError("synthetic close failure")


def audit_with(tmp_path, provider):
    config = make_assets(tmp_path / "assets")
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, out=out, provider_factory=lambda _: provider)
    assert json.loads((out / "audit.json").read_text(encoding="utf-8")) == report
    assert provider.closed
    assert report["audit_sha256"] == data.canonical_hash(
        {key: value for key, value in report.items() if key != "audit_sha256"})
    return out, report


def test_dynamic_model_evidence_survives_close_and_is_bound_into_cache_identity(tmp_path):
    provider = MetadataProvider()
    out, report = audit_with(tmp_path, provider)
    assert report["status"] == "ready_for_feature_export"
    assert report["provider_identity"]["closed"] is True
    assert len(report["provider_identity"]["demo_model_compatibility"]["loads"]) == 70
    data.validate_audit(report, base_dir=out)
    identities = data._identities(report, {"checkpoint": "synthetic-test-only"})
    assert identities["data_identity"]["audit_sha256"] == report["audit_sha256"]
    provider.metadata["demo_model_compatibility"]["loads"].clear()
    assert len(report["provider_identity"]["demo_model_compatibility"]["loads"]) == 70
    report["provider_identity"]["demo_model_compatibility"]["loads"][0]["attempt"] = -1
    with pytest.raises(ValueError, match="hash mismatch"):
        data.validate_audit(report, base_dir=out)


@pytest.mark.parametrize("fail_at,expected_rows", [(1, 0), (3, 2)])
def test_failed_model_attempt_retains_specific_diff_and_partial_rows(tmp_path, fail_at, expected_rows):
    provider = MetadataProvider(fail_at=fail_at)
    _, report = audit_with(tmp_path, provider)
    assert report["status"] == "insufficient" and len(report["rows"]) == expected_rows
    issue = next(item for item in report["issues"] if item["reason"] == "audit_error")
    evidence = issue["model_compatibility"]
    assert evidence["classification"] == "rejected"
    assert evidence["layout_diff"]["geom_bodyid"] == {"baseline": [1, 2], "loaded": [1, 3]}
    assert report["provider_identity"]["demo_model_compatibility"]["loads"][-1] == evidence
    assert report["provider_identity"]["closed"] is True


def test_close_failure_does_not_drop_accumulated_model_evidence(tmp_path):
    provider = MetadataProvider(fail_close=True)
    _, report = audit_with(tmp_path, provider)
    assert report["status"] == "insufficient"
    assert any(item["reason"] == "provider_close_error" for item in report["issues"])
    assert len(report["provider_identity"]["demo_model_compatibility"]["loads"]) == 70


def test_invalid_final_metadata_cannot_mark_audit_ready_or_prevent_partial_save(tmp_path):
    provider = MetadataProvider(invalid_metadata=True)
    _, report = audit_with(tmp_path, provider)
    assert report["status"] == "insufficient" and len(report["rows"]) == 70
    assert any(item["reason"] == "provider_metadata_error" for item in report["issues"])
    assert "invalid" not in report["provider_identity"]


def test_constructor_failure_preserves_compatibility_evidence_without_provider(tmp_path):
    config = make_assets(tmp_path / "assets")
    evidence = {"classification": "rejected", "layout_diff": {"nq": {"baseline": 65, "loaded": 66}}}
    def factory(_):
        raise EvidenceFailure(evidence)
    out = tmp_path / "audit"
    report = data.audit_demonstrations(config, out=out, provider_factory=factory)
    assert report["status"] == "insufficient" and not report["rows"]
    assert report["issues"][0]["model_compatibility"] == evidence
    assert json.loads((out / "audit.json").read_text(encoding="utf-8")) == report
