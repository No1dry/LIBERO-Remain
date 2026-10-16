"""CPU-only regression for actual OFT 8D inputs; no model/simulator calls."""
from copy import deepcopy

import numpy as np
import pytest

from benchmark.remaining_goals.finish.schema import INPUT_SCHEMA, input_sha256, validate_input_evidence


def evidence(proprio_shape=(8,), pixel_shape=(1, 12, 4, 4)):
    # BF16 payload contains ordinary values, signed zero and a finite subnormal.
    bits = np.array([0x3F80, 0xBF80, 0x8000, 0x0001], dtype=np.uint16)
    pixels = np.resize(bits, pixel_shape)
    return {"schema_version": INPUT_SCHEMA,
        "tensors": {"input_ids": np.array([[1, 7, 56, 2]], dtype=np.int64),
                    "attention_mask": np.array([[1, 1, 1, 0]], dtype=np.uint8),
                    "pixel_values": pixels,
                    "proprio": np.arange(np.prod(proprio_shape), dtype=np.float64).reshape(proprio_shape)},
        "tensor_dtypes": {"input_ids": "torch.int64", "attention_mask": "torch.bool",
                          "pixel_values": "torch.bfloat16", "proprio": "numpy.float64"},
        "crops": {"agentview": np.zeros((4, 4, 3), dtype=np.uint8),
                  "wrist": np.full((4, 4, 3), 127, dtype=np.uint8)}}


def assert_context(error, name, shape, dtype):
    message = str(error.value)
    assert message.startswith(name + ": expected shape=")
    assert "; actual shape=" in message and "dtype=" in message and "source_dtype=" in message
    assert str(shape) in message and dtype in message
    return message


@pytest.mark.parametrize("dimension,channels", [(7, 6), (7, 12), (8, 6), (8, 12)])
def test_original_four_cells_now_follow_8d_contract(dimension, channels):
    # R8's frozen implementation accepted both 7D cases and rejected both 8D
    # cases; channel count was never the error. This asserts the corrected grid.
    item = evidence((dimension,), (1, channels, 4, 4))
    if dimension == 7:
        with pytest.raises(ValueError) as error:
            validate_input_evidence(item)
        assert_context(error, "proprio", (7,), "float64")
    else:
        checked = validate_input_evidence(item)
        assert checked["tensors"]["proprio"].shape == (8,)
        assert checked["tensors"]["pixel_values"].shape[1] == channels


@pytest.mark.parametrize("shape", [(8,), (1, 8)])
def test_actual_12_channel_224_input_preserves_all_bytes_and_source_dtypes(shape):
    item = evidence(shape, (1, 12, 224, 224))
    item["crops"] = {name: np.full((224, 224, 3), index, dtype=np.uint8)
                     for index, name in enumerate(("agentview", "wrist"))}
    before = deepcopy(item)
    checked = validate_input_evidence(item)
    assert checked["schema_version"] == "remaining-finish-input-v1" == INPUT_SCHEMA
    assert checked["tensor_dtypes"] == item["tensor_dtypes"]
    for key in ("tensors", "crops"):
        for name, original in before[key].items():
            actual = checked[key][name]
            assert actual.dtype == original.dtype and actual.shape == original.shape
            assert actual.tobytes() == original.tobytes() == item[key][name].tobytes()
            assert not np.shares_memory(actual, item[key][name])
    assert input_sha256(checked) == input_sha256(item)
    changed = deepcopy(checked)
    changed["tensors"]["pixel_values"].flat[0] ^= np.uint16(1)
    assert input_sha256(changed) != input_sha256(checked)
    changed = deepcopy(checked)
    changed["tensor_dtypes"]["proprio"] = "torch.float64"
    assert input_sha256(changed) != input_sha256(checked)


@pytest.mark.parametrize("shape", [(7,), (9,), (1, 7), (1, 9), (2, 8), (8, 1), (1, 1, 8), (), (0, 8)])
def test_wrong_proprio_size_rank_or_batch_is_rejected(shape):
    item = evidence(shape)
    with pytest.raises(ValueError) as error:
        validate_input_evidence(item)
    message = assert_context(error, "proprio", shape, "float64")
    assert "(8,) or (1, 8)" in message


@pytest.mark.parametrize("shape", [(12, 4, 4), (1, 2, 6, 4, 4, 1), (2, 12, 4, 4), (0, 12, 4, 4)])
def test_wrong_pixel_rank_or_batch_reports_pixel_metadata(shape):
    with pytest.raises(ValueError) as error:
        validate_input_evidence(evidence(pixel_shape=shape))
    message = assert_context(error, "pixel_values", shape, "uint16")
    assert "rank 4 or 5" in message and "batch 1" in message


@pytest.mark.parametrize("shape", [(1, 1, 2, 2), (1, 3, 2, 2), (1, 6, 2, 2), (1, 2, 6, 2, 2)])
def test_existing_toy_channels_and_rank_five_remain_supported(shape):
    assert validate_input_evidence(evidence(pixel_shape=shape))["tensors"]["pixel_values"].shape == shape


@pytest.mark.parametrize("name", ["proprio", "pixel_values"])
@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf])
def test_nonfinite_numeric_input_is_rejected_without_dumping_tensor_values(name, invalid):
    item = evidence()
    original = item["tensors"][name]
    item["tensors"][name] = np.full(original.shape, 987654321.125, dtype=np.float64)
    item["tensors"][name].flat[-1] = invalid
    item["tensor_dtypes"][name] = "numpy.float64"
    with pytest.raises(ValueError) as error:
        validate_input_evidence(item)
    message = assert_context(error, name, original.shape, "float64")
    assert "987654321.125" not in message and "finite" in message


@pytest.mark.parametrize("name", ["proprio", "pixel_values"])
@pytest.mark.parametrize("dtype", [np.float32, np.complex64, object, np.bool_])
def test_wrong_storage_or_non_numeric_dtype_is_rejected(name, dtype):
    item = evidence()
    shape = item["tensors"][name].shape
    item["tensors"][name] = np.zeros(shape, dtype=dtype)
    with pytest.raises(ValueError) as error:
        validate_input_evidence(item)
    assert_context(error, name, shape, np.dtype(dtype).name)


@pytest.mark.parametrize("name", ["proprio", "pixel_values"])
@pytest.mark.parametrize("label", ["numpy.float128", "cupy.float32", "float32", "numpy.bfloat16"])
def test_unknown_source_dtype_is_not_made_valid_by_the_shape_fix(name, label):
    item = evidence()
    item["tensor_dtypes"][name] = label
    with pytest.raises(ValueError) as error:
        validate_input_evidence(item)
    assert_context(error, name, item["tensors"][name].shape, item["tensors"][name].dtype.name)


@pytest.mark.parametrize("bits", [0x7F80, 0xFF80, 0x7FC1, 0xFFC1])
def test_bf16_nan_and_infinity_bits_are_still_rejected(bits):
    item = evidence()
    item["tensors"]["pixel_values"].flat[0] = np.uint16(bits)
    with pytest.raises(ValueError) as error:
        validate_input_evidence(item)
    message = assert_context(error, "pixel_values", (1, 12, 4, 4), "uint16")
    assert "NaN or infinity" in message and "torch.bfloat16" in message


@pytest.mark.parametrize("label", [np.array([987654321.125]), {"secret": 987654321.125}, "numpy." + "secret" * 30])
def test_malformed_dtype_label_never_formats_arbitrary_payload(label):
    item = evidence()
    item["tensor_dtypes"]["proprio"] = label
    with pytest.raises(ValueError) as error:
        validate_input_evidence(item)
    message = assert_context(error, "proprio", (8,), "float64")
    assert "987654321.125" not in message and "secret" not in message


def test_nonarray_input_does_not_format_values_or_user_repr():
    class PrivatePayload:
        def __repr__(self):
            raise AssertionError("must never represent input values")
    item = evidence()
    item["tensors"]["proprio"] = PrivatePayload()
    with pytest.raises(ValueError) as error:
        validate_input_evidence(item)
    assert "<not ndarray: PrivatePayload>" in str(error.value)


@pytest.mark.parametrize("change", ["tensor_extra", "crop_extra", "label_missing", "wrong_version", "ids_batch", "mask_value", "mask_storage"])
def test_other_input_contract_restrictions_are_unchanged(change):
    item = evidence()
    if change == "tensor_extra":
        item["tensors"]["goal_mask"] = np.array([1, 0])
    elif change == "crop_extra":
        item["crops"]["state"] = np.zeros((4, 4, 3), dtype=np.uint8)
    elif change == "label_missing":
        del item["tensor_dtypes"]["proprio"]
    elif change == "wrong_version":
        item["schema_version"] = "remaining-finish-input-v2"
    elif change == "ids_batch":
        item["tensors"]["input_ids"] = np.zeros((2, 4), dtype=np.int64)
    elif change == "mask_value":
        item["tensors"]["attention_mask"][0, 0] = 2
    elif change == "mask_storage":
        item["tensors"]["attention_mask"] = item["tensors"]["attention_mask"].astype(np.bool_)
    with pytest.raises(ValueError):
        validate_input_evidence(item)
