"""Tiny CPU-only tensors/fake OFT calls; never load VLA weights or real data."""
from copy import deepcopy
import json
import random
from types import SimpleNamespace

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from benchmark.remaining_goals.finish import model, oft, training


@pytest.fixture(autouse=True)
def one_cpu_thread():
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


def identities():
    return {name: {"synthetic": True, "id": name} for name in model.IDENTITY_FIELDS}


def artifact(tmp_path, *, identity=None, dimension=4):
    value = identities()
    if identity is not None:
        value["base_identity"] = identity
    head = model.FinishHead(dimension)
    with torch.no_grad():
        for parameter in head.parameters():
            parameter.zero_()
        head.net[3].bias.fill_(4)
    manifest = model.save_head_artifact(tmp_path / "head", head, identities=value,
                                       training={"synthetic": True, "epoch": 0, "seed": 7})
    return head, manifest


def test_pool_accepts_only_exact_action_tokens_and_detaches_fp32():
    hidden = torch.arange(2 * 56 * 4, dtype=torch.bfloat16).reshape(2, 56, 4).requires_grad_()
    before = hidden.detach().clone()
    value = model.pool_action_hidden(hidden)
    assert value.dtype == torch.float32 and not value.requires_grad
    torch.testing.assert_close(value, hidden.detach().float().mean(dim=1), rtol=0, atol=0)
    torch.testing.assert_close(hidden, before, rtol=0, atol=0)
    for bad in (torch.zeros(1, 57, 4), torch.zeros(56, 4), torch.zeros(1, 56, 0),
                torch.zeros(1, 56, 4, dtype=torch.int64), torch.full((1, 56, 4), float("nan"))):
        with pytest.raises(ValueError):
            model.pool_action_hidden(bad)


def test_head_architecture_and_safe_roundtrip_do_not_consume_rng(tmp_path):
    head, manifest = artifact(tmp_path)
    assert [type(layer) for layer in head.net] == [torch.nn.LayerNorm, torch.nn.Linear,
                                                 torch.nn.GELU, torch.nn.Linear]
    assert not any(isinstance(layer, torch.nn.Dropout) for layer in head.modules())
    state = torch.get_rng_state().clone()
    loaded, saved = model.load_head_artifact(tmp_path / "head", expected_base_identity=identities()["base_identity"])
    assert torch.equal(torch.get_rng_state(), state)
    assert manifest == saved
    features = torch.randn(3, 4, requires_grad=True)
    torch.testing.assert_close(loaded(features), head(features), rtol=0, atol=0)
    loaded(features).sum().backward()
    assert features.grad is None
    assert all(parameter.dtype == torch.float32 for parameter in loaded.parameters())
    with pytest.raises(ValueError, match="base checkpoint"):
        model.load_head_artifact(tmp_path / "head", expected_base_identity={"another": True})
    with pytest.raises(FileExistsError):
        model.save_head_artifact(tmp_path / "head", head, identities=identities(), training={"synthetic": True})


@pytest.mark.parametrize("field", ["weights", "feature_version", "identity", "unsafe_path"])
def test_bad_head_artifacts_fail_closed(tmp_path, field):
    _, manifest = artifact(tmp_path)
    if field == "weights":
        with (tmp_path / "head/head.npz").open("ab") as stream:
            stream.write(b"modified")
    else:
        if field == "feature_version":
            manifest["architecture"]["feature_version"] = "wrong-feature"
        elif field == "identity":
            manifest["identities"]["split_identity"]["id"] = "test-leak"
        else:
            manifest["weights"]["path"] = "../head.npz"
        manifest["artifact_sha256"] = model.canonical_hash({k: v for k, v in manifest.items() if k != "artifact_sha256"})
        (tmp_path / "head/head.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        model.load_head_artifact(tmp_path / "head")


def test_head_training_only_uses_training_class_weight_and_preserves_frozen_base(tmp_path):
    base = {"backbone": torch.nn.Sequential(torch.nn.Linear(4, 4), torch.nn.Dropout(0.7)),
            "action_head": torch.nn.Linear(4, 7), "projector": torch.nn.Linear(7, 4)}
    original = model.module_state_sha256(base)
    generator = np.random.default_rng(6)
    x = generator.normal(size=(8, 4)).astype(np.float32)
    train_y = np.array([1, 1, 0, 0, 0, 0, 0, 0], dtype=np.uint8)
    val_y = np.array([1, 1, 1, 1], dtype=np.uint8)
    outer_rng = torch.get_rng_state().clone()
    result = training.train_head(x, train_y, x[:4], val_y, tmp_path / "training",
                                 identities=identities(), config={"epochs": 3, "batch_size": 4}, base_modules=base)
    assert torch.equal(torch.get_rng_state(), outer_rng)
    assert result["training"]["pos_weight"] == 3.0
    assert result["training"]["base_parameter_sha256_before"] == original
    assert result["training"]["base_parameter_sha256_after"] == original == model.module_state_sha256(base)
    model.assert_frozen(base)
    selected = min(result["training"]["epochs"], key=lambda row: row["validation_bce"])
    assert result["training"]["best_epoch"] == selected["epoch"]
    head, _ = model.load_head_artifact(tmp_path / "training/head")
    with torch.inference_mode():
        unweighted = torch.nn.functional.binary_cross_entropy_with_logits(head(torch.from_numpy(x[:4])),
                                                                          torch.from_numpy(val_y.astype(np.float32)))
    assert result["training"]["best_validation_bce"] == pytest.approx(float(unweighted))


def test_validation_tie_selects_earlier_epoch(tmp_path, monkeypatch):
    # A no-op optimizer creates exact equal checkpoints, without inventing scores.
    monkeypatch.setattr(torch.optim.AdamW, "step", lambda self: None)
    features = np.arange(16, dtype=np.float32).reshape(4, 4)
    result = training.train_head(features, [0, 0, 0, 1], features, [1, 0, 1, 0], tmp_path / "train",
                                 identities=identities(), config={"epochs": 3})
    assert len({row["validation_bce"] for row in result["training"]["epochs"]}) == 1
    assert result["training"]["best_epoch"] == 1


def test_training_artifact_records_base_parameter_mutation_and_never_saves_head(tmp_path, monkeypatch):
    base = {"action": torch.nn.Linear(4, 7)}
    real_step = torch.optim.AdamW.step

    def corrupt(self, *args, **kwargs):
        with torch.no_grad():
            base["action"].weight[0, 0] += 1
        return real_step(self, *args, **kwargs)

    monkeypatch.setattr(torch.optim.AdamW, "step", corrupt)
    features = np.ones((2, 4), np.float32)
    with pytest.raises(ValueError, match="base parameter/buffer bytes"):
        training.train_head(features, [0, 1], features, [0, 1], tmp_path / "training",
                            identities=identities(), config={"epochs": 1}, base_modules=base)
    progress = json.loads((tmp_path / "training/training.json").read_text())
    assert progress["status"] == "error" and not (tmp_path / "training/head").exists()


def test_train_from_cache_requires_audited_train_validation_only(tmp_path, monkeypatch):
    from benchmark.remaining_goals.finish import data
    calls = []
    cache = {"features": np.arange(32, dtype=np.float32).reshape(8, 4),
             "labels": np.array([0, 1] * 4, dtype=np.uint8),
             "rows": [{"split": "train" if i < 4 else "validation"} for i in range(8)],
             "identities": identities()}

    def load(path, *, allowed_splits):
        calls.append((path, allowed_splits))
        return deepcopy(cache)

    monkeypatch.setattr(data, "load_feature_cache", load)
    result = training.train_from_cache("synthetic-cache", tmp_path / "training", config={"epochs": 1})
    assert calls == [("synthetic-cache", ["train", "validation"])]
    assert result["identities"] == identities()
    assert result["training"]["input_shapes"] == {"training": [4, 4], "validation": [4, 4]}
    cache["rows"][0]["split"] = "remain_test"
    with pytest.raises(ValueError, match="train and validation"):
        training.train_from_cache("synthetic-cache", tmp_path / "bad", config={"epochs": 1})
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("config", [{"epochs": 51}, {"seed": True}, {"learning_rate": float("nan")},
                                    {"device": "cudaBogus"}, {"unknown": 1}])
def test_invalid_training_configuration_fails_before_output(tmp_path, config):
    with pytest.raises(ValueError):
        training.train_head(np.ones((2, 4), np.float32), [0, 1], np.ones((2, 4), np.float32), [0, 1],
                            tmp_path / "training", identities=identities(), config=config)
    assert not (tmp_path / "training").exists()


@pytest.mark.parametrize("labels", [[0, 0], [1, 1], [0, None], [0, 0.5]])
def test_missing_or_invalid_training_class_never_uses_validation_to_fill_it(tmp_path, labels):
    with pytest.raises(ValueError):
        training.train_head(np.ones((2, 4), np.float32), labels, np.ones((2, 4), np.float32), [0, 1],
                            tmp_path / "train", identities=identities(), config={"epochs": 1})
    assert not (tmp_path / "train").exists()


class FakeProcessor:
    def __init__(self):
        self.calls = 0

    def __call__(self, prompt, crop):
        self.calls += 1
        return {"input_ids": torch.tensor([[1, 2, 3]]),
                "attention_mask": torch.ones((1, 3), dtype=torch.bool),
                "pixel_values": torch.from_numpy(np.asarray(crop).copy()).permute(2, 0, 1)[None].to(torch.bfloat16)}


class FakeL1(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.scale = torch.nn.Parameter(torch.tensor(0.01))
        self.calls = 0

    def predict_action(self, actions_hidden_states):
        self.calls += 1
        return actions_hidden_states.reshape(1, 8, 7, 4).mean(-1) * self.scale


class FakeModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        values = torch.arange(60 * 4, dtype=torch.float32).reshape(60, 4)
        values[:2] = 1e6  # prompt/patch stand-ins must not enter pooling
        values[58:] = -1e6  # EOS stand-ins must not enter pooling
        self.hidden = torch.nn.Parameter(values)
        self.calls = 0
        self.fail = False
        self.random = False

    def predict_action(self, *, input_ids, attention_mask, pixel_values, proprio, action_head):
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic original forward failure")
        hidden = self.hidden[None, 2:58]
        if self.random:
            hidden = hidden + torch.rand(()) + random.random() + np.random.random()
        action = action_head.predict_action(hidden)
        return action, hidden


class FakeBase:
    def __init__(self):
        self.model, self.action_head = FakeModel(), FakeL1()
        self.proprio_projector, self.noisy_action_projector = torch.nn.Linear(7, 4), None
        self.processor = FakeProcessor()
        self.resets = 0

    def reset(self):
        self.resets += 1

    def predict(self, observation, instruction):
        a = self.processor(instruction, observation["image"])
        b = self.processor(instruction, observation["wrist_image"])
        a["pixel_values"] = torch.cat([a["pixel_values"], b["pixel_values"]], dim=1)
        with torch.inference_mode():
            action, _ = self.model.predict_action(**a, proprio=observation["proprio"].copy(), action_head=self.action_head)
        return action[0].cpu().numpy().astype(np.float64)

    def close(self):
        self.closed = True


def observation():
    return {"image": np.full((4, 4, 3), 19, np.uint8),
            "wrist_image": np.full((4, 4, 3), 73, np.uint8), "proprio": np.arange(7, dtype=np.float64)}


def test_same_original_forward_captures_only_action_hidden_actual_tensors_and_crops():
    base = FakeBase()
    feature = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    original_processor = base.processor
    before = model.module_state_sha256(oft._modules(base))
    obs = observation()
    expected = base.predict(deepcopy(obs), "original task")
    result = feature.predict_features(obs, "original task")

    np.testing.assert_array_equal(result["candidate_actions"], expected)
    assert base.model.calls == base.action_head.calls == 2
    assert base.processor is original_processor and base.processor.calls == 4
    assert "predict_action" not in vars(base.model) and "predict_action" not in vars(base.action_head)
    np.testing.assert_array_equal(result["features"], base.model.hidden[None, 2:58].detach().mean(1).numpy())
    evidence = result["input_evidence"]
    assert set(evidence["tensors"]) == {"input_ids", "attention_mask", "pixel_values", "proprio"}
    assert evidence["tensor_dtypes"]["pixel_values"] == "torch.bfloat16"
    assert evidence["tensors"]["pixel_values"].dtype == np.uint16
    assert evidence["tensor_dtypes"]["attention_mask"] == "torch.bool"
    assert evidence["tensors"]["attention_mask"].dtype == np.uint8
    assert evidence["tensor_dtypes"]["proprio"] == "numpy.float64"
    np.testing.assert_array_equal(evidence["crops"]["agentview"], obs["image"])
    np.testing.assert_array_equal(evidence["crops"]["wrist"], obs["wrist_image"])
    evidence["crops"]["agentview"][:] = 0
    assert (obs["image"] == 19).all()
    assert model.module_state_sha256(oft._modules(base)) == before
    model.assert_frozen(oft._modules(base))


def test_capture_restores_methods_and_processor_after_forward_error():
    base = FakeBase()
    feature = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    processor = base.processor
    base.model.fail = True
    with pytest.raises(RuntimeError, match="original forward"):
        feature.predict_features(observation(), "task")
    assert base.processor is processor
    assert "predict_action" not in vars(base.model) and "predict_action" not in vars(base.action_head)


def test_finish_branch_does_not_change_candidates_and_rejects_wrong_dimension(tmp_path):
    base = FakeBase()
    feature = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    head, saved = artifact(tmp_path)
    finish = oft.FinishOFTPolicy.from_feature_policy(feature, head=head, artifact=saved, threshold=0.5)
    expected = base.predict(observation(), "full task")
    result = finish.predict(observation(), "full task")
    assert result["head_decision"] == "finish" and result["p"] >= 0.5
    np.testing.assert_array_equal(result["candidate_actions"], expected)
    assert result["head_identity"]["artifact_sha256"] == saved["artifact_sha256"]
    # Neither evaluator-only field is consumed by this wrapper/head.
    altered = {**observation(), "hidden_evaluator_truth": [False, False], "hidden_mask": "00"}
    assert finish.predict(altered, "full task")["p"] == result["p"]
    finish.head = model.FinishHead(5)
    with pytest.raises(ValueError, match="head input"):
        finish.predict(observation(), "full task")


def test_real_envelope_schema_accepts_actual_capture_dtype_contract(tmp_path):
    from benchmark.remaining_goals.finish.schema import validate_policy_result
    base = FakeBase()
    feature = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    head, saved = artifact(tmp_path)
    finish = oft.FinishOFTPolicy.from_feature_policy(feature, head=head, artifact=saved, threshold=0.5)
    result = finish.predict(observation(), "original task")
    validated = validate_policy_result(result)
    np.testing.assert_array_equal(validated["candidate_actions"], result["candidate_actions"])


def test_32_cpu_parity_pairs_restore_all_rng_and_preserve_original_actions(tmp_path):
    base = FakeBase()
    base.model.random = True
    feature = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    head, saved = artifact(tmp_path)
    finish = oft.FinishOFTPolicy.from_feature_policy(feature, head=head, artifact=saved, threshold=0.5)
    rows = [{"input_id": f"synthetic-{i:02d}", "split": "validation", "observation": observation(),
             "instruction": "original task"} for i in range(32)]
    before = oft._rng_state()
    report = oft.parity_inputs(base, finish, rows)
    after = oft._rng_state()
    assert report["passed"] is True and report["max_abs_error"] == 0
    assert report["original_calls"] == report["shadow_calls"] == 32
    assert base.model.calls == base.action_head.calls == 64 and base.processor.calls == 128
    assert before["python"] == after["python"]
    np.testing.assert_array_equal(before["numpy"][1], after["numpy"][1])
    assert torch.equal(before["torch"], after["torch"])
    with pytest.raises(ValueError, match="validation"):
        oft.parity_inputs(base, finish, [{**row, "split": "remain_test"} for row in rows])
    assert base.model.calls == 64


def test_same_worker_parity_pair_and_aggregator(tmp_path):
    base = FakeBase()
    base.model.random = True
    feature = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    head, saved = artifact(tmp_path)
    pair = oft.ParityOFTPolicy.__new__(oft.ParityOFTPolicy)
    pair.shadow = oft.FinishOFTPolicy.from_feature_policy(feature, head=head, artifact=saved, threshold=0.5)
    result = oft.parity_inputs(None, pair, [{"input_id": "fixture", "split": "validation",
                                           "observation": observation(), "instruction": "task"}], required_count=1)
    assert result["passed"] is True and result["max_abs_error"] == 0
    assert base.model.calls == base.action_head.calls == 2
