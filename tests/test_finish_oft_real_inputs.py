"""Fixed OFT call-shape regressions without real model weights or simulation.

224-pixel crops and twelve fused channels exercise the actual input ABI. The
small fake backbone still returns its original 56-token action-head input.
"""
from copy import deepcopy
from io import BytesIO
import random

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from benchmark.remaining_goals.finish import data, model, oft, schema
from benchmark.remaining_goals.observation_artifact import (
    load_observation_artifact, save_observation_artifact,
)
from benchmark.remaining_goals.policy_transport import read_frame, write_frame
from tests.test_remaining_finish_model import FakeBase, FakeModel, artifact, identities


@pytest.fixture(autouse=True)
def one_cpu_thread():
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


def storage(value):
    if isinstance(value, torch.Tensor):
        tensor = value.detach().cpu().contiguous()
        return str(tensor.dtype), tuple(tensor.shape), tensor.view(torch.uint8).numpy().tobytes()
    array = np.asarray(value)
    return str(array.dtype), array.shape, array.tobytes(order="C")


class RecordingModel(FakeModel):
    def __init__(self):
        super().__init__()
        self.received = []

    def predict_action(self, *, input_ids, attention_mask, pixel_values, proprio, action_head):
        arguments = {"input_ids": input_ids, "attention_mask": attention_mask,
                     "pixel_values": pixel_values, "proprio": proprio}
        self.received.append({"arguments": arguments, "before": {key: storage(value) for key, value in arguments.items()}})
        assert isinstance(proprio, np.ndarray) and proprio.shape in {(8,), (1, 8)}
        assert input_ids.dtype == torch.int64 and attention_mask.dtype == torch.bool
        assert pixel_values.dtype == torch.bfloat16 and pixel_values.shape == (1, 12, 224, 224)
        return super().predict_action(**arguments, action_head=action_head)


class RealShapeBase(FakeBase):
    def __init__(self):
        super().__init__()
        self.model = RecordingModel()


def real_shape_observation(*, proprio_shape=(8,), proprio_dtype=np.float64):
    grid = np.arange(224 * 224 * 3, dtype=np.uint32).reshape(224, 224, 3)
    return {
        "image": ((grid * 13 + 17) % 256).astype(np.uint8),
        "wrist_image": ((grid[::-1] * 7 + 71) % 256).astype(np.uint8),
        "proprio": np.array([.1, -.2, .3, .4, -.5, .6, .035, -.025], dtype=proprio_dtype).reshape(proprio_shape),
    }


def assert_arguments_unchanged(base):
    for call in base.model.received:
        assert {key: storage(value) for key, value in call["arguments"].items()} == call["before"]


def assert_rng_equal(left, right):
    assert left["python"] == right["python"]
    assert left["numpy"][0] == right["numpy"][0] and left["numpy"][2:] == right["numpy"][2:]
    np.testing.assert_array_equal(left["numpy"][1], right["numpy"][1])
    assert torch.equal(left["torch"], right["torch"])
    assert left["cuda"] is right["cuda"] is None


def next_random_values():
    return random.random(), float(np.random.random()), float(torch.rand(()))


@pytest.mark.parametrize("proprio_shape,proprio_dtype", [((8,), np.float64), ((1, 8), np.float32)])
def test_real_224_call_capture_envelope_hash_and_typed_input_roundtrip(tmp_path, proprio_shape, proprio_dtype):
    base = RealShapeBase()
    feature = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    head, saved = artifact(tmp_path)
    policy = oft.FinishOFTPolicy.from_feature_policy(feature, head=head, artifact=saved, threshold=.5)
    observation = real_shape_observation(proprio_shape=proprio_shape, proprio_dtype=proprio_dtype)
    before_observation = {key: storage(value) for key, value in observation.items()}
    original_processor = base.processor
    base_hash = model.module_state_sha256(oft._modules(base))
    try:
        original_actions = base.predict(observation, "original full instruction")
        call_counts = base.model.calls, base.action_head.calls, original_processor.calls
        result = policy.predict(observation, "original full instruction")
        assert (base.model.calls, base.action_head.calls, original_processor.calls) == tuple(
            value + increment for value, increment in zip(call_counts, (1, 1, 2)))
        assert result["candidate_actions"].shape == (8, 7)
        assert storage(result["candidate_actions"]) == storage(original_actions)
        # Pass the complete reply through the exact isolated-worker wire codec.
        stream = BytesIO()
        write_frame(stream, {"ok": True, "result": result})
        stream.seek(0)
        reply = read_frame(stream)
        assert reply["ok"] is True and stream.read() == b""
        validated = schema.validate_policy_result(reply["result"])
        assert storage(validated["candidate_actions"]) == storage(original_actions)

        evidence = validated["input_evidence"]
        actual = base.model.received[-1]["arguments"]
        assert storage(evidence["tensors"]["input_ids"]) == storage(actual["input_ids"].numpy())
        assert schema.input_sha256(evidence) == schema.input_sha256(result["input_evidence"])
        assert evidence["tensors"]["proprio"].shape == proprio_shape
        assert evidence["tensor_dtypes"] == {
            "input_ids": "torch.int64", "attention_mask": "torch.bool",
            "pixel_values": "torch.bfloat16", "proprio": "numpy." + np.dtype(proprio_dtype).name,
        }
        assert evidence["tensors"]["pixel_values"].shape == (1, 12, 224, 224)
        assert evidence["tensors"]["pixel_values"].dtype == np.uint16
        assert evidence["tensors"]["pixel_values"].tobytes() == actual["pixel_values"].view(torch.uint16).numpy().tobytes()
        assert evidence["tensors"]["attention_mask"].dtype == np.uint8
        assert evidence["tensors"]["attention_mask"].tobytes() == actual["attention_mask"].to(torch.uint8).numpy().tobytes()
        assert storage(evidence["tensors"]["proprio"]) == storage(actual["proprio"])
        for source, camera in (("image", "agentview"), ("wrist_image", "wrist")):
            assert evidence["crops"][camera].shape == (224, 224, 3)
            assert storage(evidence["crops"][camera]) == storage(observation[source])

        digest = schema.input_sha256(evidence)
        arrays = {"tensors": evidence["tensors"], "crops": evidence["crops"]}
        reference = save_observation_artifact(tmp_path, "inputs/actual_224.npz", arrays)
        decoded = load_observation_artifact(tmp_path, reference, expected_digest=reference["observation_sha256"])
        # Exercise the same row reader used by feature-cache load/export; dtype
        # metadata and schema are not squeezed into the numeric NPZ container.
        row = {"input_artifact": reference, "input_tensor_dtypes": deepcopy(evidence["tensor_dtypes"]),
               "input_sha256": digest}
        restored = data._input_evidence(tmp_path, row)
        assert schema.input_sha256(restored) == digest
        for section in ("tensors", "crops"):
            for key, value in arrays[section].items():
                assert storage(decoded[section][key]) == storage(value)
                assert storage(restored[section][key]) == storage(value)
        changed = deepcopy(restored)
        changed["tensors"]["pixel_values"][0, 0, 0, 0] ^= np.uint16(1)
        assert schema.input_sha256(changed) != digest

        assert_arguments_unchanged(base)
        assert base.model.received[0]["before"] == base.model.received[1]["before"]
        assert {key: storage(value) for key, value in observation.items()} == before_observation
        assert base.processor is original_processor
        assert "predict_action" not in vars(base.model) and "predict_action" not in vars(base.action_head)
        assert model.module_state_sha256(oft._modules(base)) == base_hash
        model.assert_frozen(oft._modules(base))
    finally:
        policy.close()
    assert base.closed is True


def test_real_shape_capture_consumes_exactly_original_rng_and_continues_sequence():
    base = RealShapeBase()
    base.model.random = True
    policy = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    observation = real_shape_observation()
    initial_rng = oft._rng_state()
    try:
        original = base.predict(observation, "same task")
        expected_rng = oft._rng_state()
        expected_following = next_random_values()
        oft._restore_rng(initial_rng)
        captured = policy.predict_features(observation, "same task")
        assert storage(captured["candidate_actions"]) == storage(original)
        assert_rng_equal(oft._rng_state(), expected_rng)
        assert next_random_values() == expected_following
        assert base.model.calls == base.action_head.calls == 2 and base.processor.calls == 4
        assert_arguments_unchanged(base)
    finally:
        policy.close()


@pytest.mark.parametrize("failure", ["model", "action"])
def test_real_shape_original_exception_restores_hooks_and_preserves_rng_continuation(failure):
    base = RealShapeBase()
    base.model.random = True
    policy = oft.OFTFeaturePolicy.from_base(base, identity=identities()["base_identity"])
    original_processor = base.processor
    original_action_method = base.action_head.predict_action
    observation = real_shape_observation()

    def original_action_failure(actions_hidden_states):
        base.action_head.calls += 1
        raise RuntimeError("original fake L1 failure")

    if failure == "model":
        base.model.fail = True
        message = "synthetic original forward failure"
    else:
        base.action_head.predict_action = original_action_failure
        message = "original fake L1 failure"
    initial_rng = oft._rng_state()
    try:
        with pytest.raises(RuntimeError, match=message):
            base.predict(observation, "same task")
        expected_rng = oft._rng_state()
        expected_following = next_random_values()
        oft._restore_rng(initial_rng)
        with pytest.raises(RuntimeError, match=message):
            policy.predict_features(observation, "same task")
        assert_rng_equal(oft._rng_state(), expected_rng)
        assert next_random_values() == expected_following
        assert base.model.calls == 2 and base.processor.calls == 4
        assert base.action_head.calls == (0 if failure == "model" else 2)
        assert base.processor is original_processor and "predict_action" not in vars(base.model)
        if failure == "action":
            assert base.action_head.predict_action is original_action_failure
            del base.action_head.predict_action
        else:
            assert "predict_action" not in vars(base.action_head)
        base.model.fail = False
        assert base.action_head.predict_action == original_action_method
        result = policy.predict_features(observation, "working after original failure")
        assert result["candidate_actions"].shape == (8, 7)
        assert base.model.calls == 3 and base.processor.calls == 6
        assert_arguments_unchanged(base)
    finally:
        policy.close()
    assert base.closed is True
