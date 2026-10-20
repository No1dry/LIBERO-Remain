"""File-only authorization for the task011 SOG10 -> LIBERO90 experiment.

This is a declared checkpoint source, not verification of all weight bytes or
evidence of policy performance. No model/native libraries are imported here.
"""
from copy import deepcopy
from pathlib import Path
import re

FACTORY = "benchmark.remaining_goals.adapters.openvla_oft:make_policy"
REPO_REVISION = "e4287e94541f459edc4feabc4e181f537cd569a8"
SOG10_SOURCE = {"repository": "moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10",
                "revision": "638918f3d1c2e43a39a8a20772bdb8b91835e4b7"}
TRAINING_SUITES = ["libero_spatial", "libero_object", "libero_goal", "libero_10"]
INFERENCE_SOURCES = ("experiments/robot/libero/run_libero_eval.py", "experiments/robot/libero/libero_utils.py",
                     "experiments/robot/openvla_utils.py", "experiments/robot/robot_utils.py")
TRANSFER = {"schema_version": "remaining-oft-suite-transfer-v1",
            "checkpoint_training_suites": TRAINING_SUITES,
            "normalization_suite": "libero_10", "normalization_key": "libero_10_no_noops",
            "evaluation_track": "libero_90_zero_shot"}


def validate_suite_transfer(config):
    """Return the sole allowed explicit transfer, or None for ordinary configs."""
    if not isinstance(config, dict):
        raise ValueError("policy config must be a JSON object")
    options = config.get("adapter_options", {})
    if not isinstance(options, dict):
        raise ValueError("adapter_options must be a JSON object")
    if "suite_transfer" not in options:
        return None
    value = options["suite_transfer"]
    if not isinstance(value, dict) or value != TRANSFER:
        raise ValueError("unsupported explicit OFT suite_transfer contract")
    if (config.get("model_id") != "openvla_oft" or config.get("policy_factory") != FACTORY
            or config.get("suite") != "libero_90" or options.get("suite") != "libero_90"
            or config.get("checkpoint_source") != SOG10_SOURCE or "finish" in config):
        raise ValueError("suite_transfer requires plain official SOG10 OFT on LIBERO90, without a FINISH head")
    if options.get("repo_revision", REPO_REVISION) != REPO_REVISION:
        raise ValueError("suite_transfer requires the pinned official OFT source revision")
    for key in ("checkpoint_suite", "normalization_suite", "unnorm_key"):
        if key in options:
            raise ValueError("suite_transfer is the only explicit normalization selector; conflicting flat fields are forbidden")
    return deepcopy(value)


def is_sog10(config):
    return config.get("checkpoint_source") == SOG10_SOURCE


def validate_policy_metadata(config, metadata):
    """Bind the worker's actual OFT normalization to the declared two-track job.

    Called after loading but before any rollout. Digests identify statistics and
    small component/config files; they do not claim full checkpoint verification.
    """
    transfer = validate_suite_transfer(config)
    suite = config.get("suite")
    if (config.get("model_id") != "openvla_oft" or config.get("policy_factory") != FACTORY
            or not is_sog10(config) or suite not in {"libero_10", "libero_90"}
            or config.get("adapter_options", {}).get("suite") != suite or "finish" in config
            or suite == "libero_90" and transfer is None):
        raise ValueError("task011 requires explicitly bound plain SOG10 OFT metadata")
    if not isinstance(metadata, dict):
        raise ValueError("policy metadata must be a JSON object")
    expected = {"model": "openvla_oft", "suite": suite, "evaluation_suite": suite,
                "checkpoint_source": SOG10_SOURCE, "checkpoint_training_suites": TRAINING_SUITES,
                "normalization_suite": "libero_10",
                "evaluation_track": "libero_90_zero_shot" if transfer else "libero_10_primary",
                "explicit_stop": False, "action_chunk": 8, "repo_commit": REPO_REVISION,
                "suite_transfer": transfer}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("actual OFT worker suite/track/source/action metadata differs from configuration")
    key = metadata.get("unnorm_key")
    if key not in ({transfer["normalization_key"]} if transfer else {"libero_10", "libero_10_no_noops"}):
        raise ValueError("actual OFT normalization key differs from the declared SOG10 statistics")
    for field in ("dataset_statistics_sha256", "normalization_statistics_sha256"):
        if not isinstance(metadata.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", metadata[field]):
            raise ValueError("actual OFT statistics byte/content identity is missing")
    for field in ("inference_source_sha256", "component_checkpoint_sha256"):
        hashes = metadata.get(field)
        if (not isinstance(hashes, dict) or not hashes
                or any(not isinstance(name, str) or not isinstance(digest, str)
                       or not re.fullmatch(r"[0-9a-f]{64}", digest) for name, digest in hashes.items())):
            raise ValueError("actual OFT inference source/component byte identity is missing")
    if set(metadata["inference_source_sha256"]) != set(INFERENCE_SOURCES):
        raise ValueError("actual OFT inference source inventory is incomplete")
    components = metadata["component_checkpoint_sha256"]
    if (len(components) != 2 or any(sum(component in name and "checkpoint" in name for name in components) != 1
                                  for component in ("action_head", "proprio_projector"))):
        raise ValueError("actual OFT action/proprio component inventory is ambiguous or incomplete")
    options = config["adapter_options"]
    expected_inference = {"center_crop": options.get("center_crop", True),
        "load_in_8bit": options.get("load_in_8bit", False), "load_in_4bit": options.get("load_in_4bit", False),
        "use_l1_regression": True, "use_diffusion": False, "use_film": False,
        "num_images_in_input": 2, "use_proprio": True, "num_open_loop_steps": 8, "lora_rank": 32}
    if metadata.get("inference_configuration") != expected_inference:
        raise ValueError("actual OFT inference configuration differs from the original action path")
    checkpoint = config["adapter_options"].get("checkpoint")
    if not isinstance(checkpoint, str) or metadata.get("checkpoint") != str(Path(checkpoint).expanduser().resolve()):
        raise ValueError("actual OFT checkpoint path differs from configured weights")
    return deepcopy(metadata)


def validate_sog10_pair(primary, extension):
    """Check two explicit configurations reuse one checkpoint and action path."""
    transfer = validate_suite_transfer(extension)
    if (transfer is None or validate_suite_transfer(primary) is not None or primary.get("suite") != "libero_10"
            or extension.get("suite") != "libero_90"):
        raise ValueError("task011 requires primary LIBERO10 plus explicit LIBERO90 extension")
    identities = []
    for config in (primary, extension):
        options = config.get("adapter_options", {})
        execution = config.get("execution", {})
        if (config.get("model_id") != "openvla_oft" or config.get("policy_factory") != FACTORY
                or not is_sog10(config) or options.get("suite") != config["suite"] or "finish" in config
                or options.get("repo_revision", REPO_REVISION) != REPO_REVISION
                or options.get("center_crop", True) is not True
                or options.get("load_in_8bit", False) is not False or options.get("load_in_4bit", False) is not False
                or execution.get("max_chunk_steps") != 8 or execution.get("random_seed") != 7
                or options.get("seed", 7) != 7):
            raise ValueError("task011 must retain pinned SOG10 source, crop, full precision, chunk8 and seed7")
        identity = {"checkpoint_source": deepcopy(SOG10_SOURCE), "repo_revision": REPO_REVISION,
                    "center_crop": True, "load_in_8bit": False, "load_in_4bit": False,
                    "action_chunk": 8, "random_seed": 7}
        for key in ("repo_path", "checkpoint"):
            value = options.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"task011 requires a local {key}")
            identity[key] = str(Path(value).expanduser().resolve())
        identities.append(identity)
    if identities[0] != identities[1]:
        raise ValueError("primary and extension must use the same OFT checkpoint/source/action configuration")
    return identities[0]
