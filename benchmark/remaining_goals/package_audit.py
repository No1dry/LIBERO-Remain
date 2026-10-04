"""Candidate delivery archives and offline integrity checks (no simulator needed).

Creating a bundle checks the saved candidate contract with NumPy. Verifying an
existing ZIP uses only the Python standard library and never extracts files.
Neither operation grants release approval or proves task executability.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import zipfile


FORMAT = "remaining-goals-candidate-delivery-v1"
COLLECTION_FORMAT = "remaining-goals-candidate-collection-v1"
INDEX = "bundle_manifest.json"
TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".csv", ".txt", ".html"}
EVIDENCE_SUFFIXES = {".json", ".png", ".npy", ".md", ".csv", ".html"}
PRIVATE_HOME = re.compile(r"(?i)(?:[a-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+[^\\/\s\"'<>`]+|/(?:home|Users)/[^/\s\"'<>`]+)")
GAPS = [
    {"id": "reviewed_release", "status": "missing", "detail": "All supplied states remain legal=false candidates; no reviewed release manifest is produced."},
    {"id": "semantic_and_execution_review", "status": "not_established", "detail": "Technical stability does not establish semantic independence, visibility, reachability, or remaining-task executability."},
    {"id": "vla_experiments", "status": "not_established", "detail": "Six-model adapter readiness, checkpoint preprocessing, original-interface regressions and paired VLA results are not certified by this archive."},
    {"id": "method_comparison", "status": "not_established", "detail": "Toy policies and simulator HOLD checks are not VLA method baselines; supplied diagnostic evidence must be interpreted separately."},
    {"id": "statistical_analysis", "status": "not_established", "detail": "Preregistered dataset coverage, split decisions and clustered confidence intervals still require research review."},
    {"id": "cross_installation_replay", "status": "not_established", "detail": "Exact MuJoCo XML hashes include absolute asset paths; source, asset and compatibility fingerprints can differ after relocation. Do not bypass them."},
]


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _unique(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)


def _manifest_hash(value):
    payload = {key: item for key, item in value.items() if key != "content_hash"}
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False).encode("utf-8"))


def _safe_name(raw):
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ValueError("archive paths must be nonempty POSIX relative paths")
    posix, windows = PurePosixPath(raw), PureWindowsPath(raw)
    if (posix.is_absolute() or windows.drive or windows.root or posix.as_posix() != raw
            or any(part in ("", ".", "..") or ":" in part or part.endswith((" ", "."))
                   or any(ord(char) < 32 for char in part) for part in raw.split("/"))):
        raise ValueError(f"unsafe archive path: {raw!r}")
    if any(part.casefold() in {".git", ".aws", ".ssh", ".codex", ".agents", "__pycache__", "venv"}
           for part in posix.parts):
        raise ValueError(f"excluded private/runtime archive path: {raw!r}")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if any(part.split(".", 1)[0].casefold() in reserved for part in posix.parts):
        raise ValueError(f"reserved Windows archive path: {raw!r}")
    return raw


def _contained(root, path):
    root, path = Path(root).resolve(), Path(path)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("input path must remain within its specified project/evidence directory")
    cursor = path
    while cursor != root and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError("symlink inputs are not included in a delivery archive")
        cursor = cursor.parent
    return resolved


def _python_closure(root, seeds):
    """Include package initializers and local imports without importing code."""
    chosen, pending = set(), list(seeds)

    def add_module(module):
        parts = module.split(".")
        if not parts or parts[0] not in ("benchmark", "scripts", "tests"):
            return
        for end in range(1, len(parts) + 1):
            folder = root.joinpath(*parts[:end])
            for item in (folder.with_suffix(".py"), folder / "__init__.py"):
                if item.is_file() and item not in chosen:
                    pending.append(item)

    while pending:
        path = _contained(root, pending.pop())
        if path in chosen:
            continue
        chosen.add(path)
        module_parts = list(path.relative_to(root).with_suffix("").parts)
        add_module(".".join(module_parts[:-1]))
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=path.name)
        package = module_parts[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    add_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package[:len(package) - node.level + 1]
                    module = ".".join(base + ([node.module] if node.module else []))
                else:
                    module = node.module or ""
                add_module(module)
                for alias in node.names:
                    if alias.name != "*":
                        add_module(module + "." + alias.name)
    return chosen


def _provenance(root, *, include_upstream=True):
    """Copy no install paths; check actual upstream bytes against the pinned tree."""
    runtime_dir = root / ".runtime" / "remaining_libero"
    runtime = _read_json(runtime_dir / "runtime.json")
    tree = _read_json(runtime_dir / "upstream_tree.json")
    selected = _read_json(runtime_dir / "source_tree.json")
    setup = ast.parse((root / "scripts/setup_remaining_libero.py").read_text(encoding="utf-8"))
    commit = next(ast.literal_eval(node.value) for node in setup.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "COMMIT" for target in node.targets))
    if (runtime.get("libero_commit") != commit or selected.get("commit") != commit
            or tree.get("sha") != commit or tree.get("truncated")):
        raise ValueError("runtime/source provenance does not match the setup script's pinned commit")
    official = {entry["path"]: entry for entry in tree["tree"] if entry["type"] == "blob"}
    source = runtime_dir / f"LIBERO-{commit}"
    installed, upstream_files = [], []
    selected_paths = {entry["path"] for entry in selected["entries"]}
    actual = {p.relative_to(source).as_posix(): p for p in source.rglob("*") if p.is_file()
              and "__pycache__" not in p.parts and p.suffix != ".pyc"
              and (p.relative_to(source).as_posix().startswith("libero/libero/")
                   or p.relative_to(source).as_posix() in selected_paths)}
    for relative in sorted(selected_paths | set(actual)):
        path = _contained(source, relative)
        if relative not in official or not path.is_file():
            raise ValueError(f"missing or untracked official source asset: {relative}")
        body = path.read_bytes()
        git_sha = hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()
        if git_sha != official[relative]["sha"]:
            raise ValueError(f"modified pinned upstream file: {relative}")
        installed.append({"path": relative, "size": len(body), "sha256": _sha(body),
                          "git_blob_sha1": git_sha, "selected_profile": relative in selected_paths})
        if include_upstream:
            upstream_files.append((path, git_sha))
    license_body = (source / "LICENSE").read_bytes()
    if hashlib.sha1(f"blob {len(license_body)}\0".encode() + license_body).hexdigest() != official["LICENSE"]["sha"]:
        raise ValueError("upstream LICENSE checksum mismatch")
    safe_runtime = {key: runtime[key] for key in (
        "libero_commit", "archive_sha256", "source_method", "source_profile",
        "dependency_index_url", "requirements", "mujoco_gl") if key in runtime}
    safe_runtime.update(repository="https://github.com/Lifelong-Robot-Learning/LIBERO",
                        source_url=f"https://github.com/Lifelong-Robot-Learning/LIBERO/tree/{commit}",
                        installed_files=installed, assets_included=include_upstream,
                        notice="Pinned upstream files are included when assets_included=true; otherwise use setup to download them. Extra retained assets affect the environment fingerprint. Parent PyTorch and drivers are not bundled.")
    metadata = {"provenance/libero_runtime.json": _json_bytes(safe_runtime),
            "provenance/libero_selected_tree.json": _json_bytes(selected),
            "provenance/libero_upstream_tree.json": _json_bytes(tree),
            "provenance/LIBERO_LICENSE": license_body}
    if include_upstream:
        # A subsequent setup reuses verified blobs in their ordinary local path;
        # it still creates its own environment and runtime configuration.
        metadata[".runtime/remaining_libero/upstream_tree.json"] = _json_bytes(tree)
    return metadata, upstream_files


def _passing_observation_comparison(check, *, initial=False, returned_hash=None, reference_hash=None,
                                    float_tolerance=1e-8, camera_reference=None):
    """Validate recorded fixed RGB bounds without treating raw hash equality as a gate.

    This checks the evidence contract; it does not recompute pixel differences
    for dynamic frames whose arrays were not saved. Initial reset comparisons
    are independently recomputed from both typed artifacts during creation.
    Kept standard-library-only so offline archive verification uses it too.
    """
    def digest(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    if (not isinstance(check, dict) or check.get("matches") is not True
            or check.get("errors") != [] or check.get("mismatched_fields") != []
            or check.get("rgb_allowance_state_verified") is not True
            or any(not digest(check.get(key)) for key in (
                "returned_sha256", "fresh_sha256", "returned_non_rgb_sha256", "fresh_non_rgb_sha256"))
            or check.get("bit_exact") is not (check["returned_sha256"] == check["fresh_sha256"])
            or type(check.get("non_rgb_bit_exact")) is not bool
            or check["non_rgb_bit_exact"] != (check["returned_non_rgb_sha256"] == check["fresh_non_rgb_sha256"])
            or (initial and check["non_rgb_bit_exact"] is not True)
            or (returned_hash is not None and check["returned_sha256"] != returned_hash)
            or (reference_hash is not None and check["fresh_sha256"] != reference_hash)):
        raise ValueError("observation comparison lacks matching state-bound hashes and exact initial non-RGB evidence")
    cameras = check.get("image_diagnostics")
    if not isinstance(cameras, dict) or not cameras:
        raise ValueError("observation comparison needs per-camera fixed-bound diagnostics")
    if camera_reference is not None and (cameras.keys() != camera_reference.keys() or any(
            not isinstance(cameras[name], dict) or cameras[name].get("total_pixels") != camera_reference[name].get("total_pixels")
            for name in cameras)):
        raise ValueError("observation camera geometry differs from the saved initial artifact")
    changed, maximum = False, 0
    for name, item in cameras.items():
        if (not isinstance(name, str) or not (name.startswith("observation.images.") or name in (
                "observation.agentview_image", "observation.robot0_eye_in_hand_image"))
                or not isinstance(item, dict)
                or any(type(item.get(key)) is not int for key in (
                    "changed_pixels", "total_pixels", "max_changed_pixels", "max_abs_error"))):
            raise ValueError("invalid named RGB camera diagnostics")
        count, area, error = item["changed_pixels"], item["total_pixels"], item["max_abs_error"]
        cap = max(1, area // 10000)
        if (area < 1 or not 0 <= count <= min(area, cap) or not 0 <= error <= 1
                or item["max_changed_pixels"] != cap or item.get("max_changed_fraction") != 0.0001
                or item.get("changed_fraction") != count / area
                or item.get("bit_exact") is not (count == 0)
                or item.get("bounded_allowance_used") is not (count > 0)
                or (count == 0) != (error == 0)):
            raise ValueError("RGB diagnostics exceed or contradict the fixed one-level/area bound")
        changed = changed or count > 0
        maximum = max(maximum, error)
    error = check.get("max_abs_error")
    if (type(error) not in (int, float) or not math.isfinite(error) or error < maximum
            or error > max(maximum, 0 if initial else float_tolerance)
            or check.get("bounded_allowance_used") is not changed
            or (initial and check["bit_exact"] is not (not changed))):
        raise ValueError("observation comparison contradicts its recorded bounded differences")


def validate_replay_evidence(manifest_path, manifest, replay_path, states, observation_hashes):
    """Read-only pairing check shared by packaging, preview and orchestration.

    The manifest/states/observation hashes come from ``_candidate_pack``. Returns
    (evidence_paths, summary); coherent failures remain failures, while false
    success declarations raise ValueError. Callers enforce their own expected
    steps/repeats using the summary, not a truthy top-level report flag.
    """
    manifest_path, replay_path = Path(manifest_path), Path(replay_path)
    report = _read_json(replay_path)
    if (report.get("kind") != "candidate_formal_adapter_replay"
            or report.get("source_content_hash") != manifest["content_hash"]
            or report.get("source_manifest_sha256") != _sha(manifest_path.read_bytes())
            or report.get("policy_called") is not False or report.get("release_authorized") is not False):
        raise ValueError("replay report is not a matching, policy-free candidate replay")
    if any(type(report.get(field)) is not int or report[field] < 1 for field in ("steps", "repeats")):
        raise ValueError("replay report needs positive steps and repeats")
    expected = {episode["episode_id"]: episode for episode in manifest["episodes"]}
    rows, seen, files = report.get("episodes"), set(), {replay_path}
    frozen_observations = {}
    if any(episode.get("initial_observation") for episode in expected.values()):
        from .observation_artifact import load_observation_artifact
        from .validation import compare_observations, RGB_QUANTIZATION_AUDIT
        import numpy as np

        for identifier, episode in expected.items():
            reference = episode.get("initial_observation")
            frozen_observations[identifier] = load_observation_artifact(
                manifest_path.parent, reference, expected_digest=observation_hashes[identifier])
            files.add(_contained(manifest_path.parent, _safe_name(reference["path"])))
    if not isinstance(rows, list):
        raise ValueError("replay episodes must be a list")
    for row in rows:
        key = row.get("episode_id"), row.get("repetition")
        if (key[0] not in expected or type(key[1]) is not int or not 0 <= key[1] < report["repeats"]
                or key in seen or row.get("initial_mask") != expected[key[0]]["initial_mask"]
                or row.get("source_legal") is not False or type(row.get("technical_acceptance")) is not bool):
            raise ValueError("unknown, repeated, or inconsistent replay episode")
        seen.add(key)
        raw = _safe_name(row.get("audit_path"))
        audit_path = _contained(replay_path.parent, raw)
        audit = _read_json(audit_path)
        if audit.get("technical_acceptance") is not row["technical_acceptance"]:
            raise ValueError("replay audit acceptance differs from its report")
        actual_reference = audit.get("reset_initial_observation")
        recomputed = None
        if actual_reference is not None and key[0] in frozen_observations:
            comparison = audit.get("reset_observation_comparison")
            if not isinstance(comparison, dict):
                raise ValueError("saved replay observation needs its construction comparison")
            actual_observation = load_observation_artifact(audit_path.parent, actual_reference,
                expected_digest=comparison.get("returned_sha256"))
            files.add(_contained(audit_path.parent, _safe_name(actual_reference["path"])))
            recomputed = compare_observations(actual_observation, frozen_observations[key[0]], atol=0,
                require_non_rgb_exact=True,
                refresh_state_unchanged=row.get("reset_checks", {}).get("saved_state_exact") is True,
                **RGB_QUANTIZATION_AUDIT)
            if recomputed != comparison:
                raise ValueError("recorded reset comparison differs from independently recomputed observation artifacts")
        if row["technical_acceptance"] and (audit.get("completed_steps") != report["steps"] or audit.get("error") is not None):
            raise ValueError("passing replay did not complete its requested window")
        if row["technical_acceptance"]:
            trace, checks = audit.get("trace"), audit.get("checks")
            if (not isinstance(trace, list) or len(trace) != report["steps"] + 1
                    or any(not isinstance(item, dict) for item in trace)
                    or [item.get("step") for item in trace] != list(range(report["steps"] + 1))
                    or audit.get("requested_steps") != report["steps"]
                    or not isinstance(checks, dict)
                    or checks.get("validation_window_complete") is not True
                    or checks.get("snapshot_contract_valid") is not True
                    or any(value is False for value in checks.values())
                    or row.get("checks") != checks or row.get("error") is not None
                    or any(item.get("goals") != expected[key[0]]["initial_mask"]
                           or not isinstance(item.get("checks"), dict)
                           or any(value is False for value in item["checks"].values()) for item in trace)):
                raise ValueError("passing replay audit lacks a complete, consistently checked trace window")
            initial = trace[0]
            reset = row.get("reset_checks", {})
            artifact = expected[key[0]].get("initial_observation")
            required_reset = ("saved_state_exact", "initial_mask_exact", "construction_observation_matches", "initial_non_rgb_exact") if artifact else (
                "saved_state_exact", "initial_mask_exact", "construction_observation_exact")
            if (not isinstance(reset, dict) or any(reset.get(field) is not True for field in required_reset)
                    or audit.get("formal_reset_checks") != reset or initial.get("step") != 0
                    or initial.get("goals") != expected[key[0]]["initial_mask"]
                    or initial.get("state") != states[key[0]].tolist()
                    or (not artifact and initial.get("observation_check", {}).get("returned_sha256") != observation_hashes[key[0]])):
                raise ValueError("passing replay audit is not bound to the saved candidate state/observation")
            if artifact:
                comparison = audit.get("reset_observation_comparison")
                if recomputed is None:
                    raise ValueError("passing replay is missing its actual initial observation artifact")
                if (not all(value is True for value in reset.values())
                        or np.asarray(initial.get("state"), dtype="<f8").tobytes() !=
                        np.asarray(states[key[0]], dtype="<f8").tobytes()
                        or initial["checks"].get("initial_non_rgb_bit_exact") is not True):
                    raise ValueError("passing replay lacks exact initial state/non-RGB reset evidence")
                if initial["observation_check"].get("returned_non_rgb_sha256") != comparison.get("returned_non_rgb_sha256"):
                    raise ValueError("initial non-RGB digest differs from the saved actual observation artifact")
                _passing_observation_comparison(comparison, initial=True,
                    returned_hash=initial.get("observation_check", {}).get("returned_sha256"),
                    reference_hash=observation_hashes[key[0]])
                for item in trace:
                    if item["checks"].get("rgb_allowance_state_verified") is not True:
                        raise ValueError("passing replay requires verified non-stepping observation state")
                    _passing_observation_comparison(item.get("observation_check"), initial=item["step"] == 0,
                        float_tolerance=audit.get("limits", {}).get("observation_tolerance", 1e-8),
                        camera_reference=comparison["image_diagnostics"])
        files.add(audit_path)
        files.update(audit_path.parent.glob("*.png"))
    complete = len(seen) == len(expected) * report["repeats"]
    passed = complete and bool(rows) and report.get("error") is None and all(row["technical_acceptance"] for row in rows)
    if type(report.get("technical_acceptance")) is not bool or report["technical_acceptance"] != passed:
        raise ValueError("replay aggregate acceptance is inconsistent with coverage and audits")
    return files, {"technical_acceptance": passed, "complete": complete, "records": len(rows),
                   "passed_records": sum(row["technical_acceptance"] for row in rows),
                   "expected_records": len(expected) * report["repeats"],
                   "requested_steps": report["steps"], "repeats": report["repeats"]}


# Kept while callers migrate; the public helper has the same arguments/return.
_replay_evidence = validate_replay_evidence


def _delivery_readme(tracks, gaps, include_upstream, additional_evidence):
    evidence_links = "\n".join(f"- [{name}]({name})" for name in additional_evidence) or "- 未额外提供 doctor、预览或诊断报告。"
    track_lines, commands = [], []
    for track in tracks:
        coverage, replay = track["coverage"], track["replay"]
        track_lines.append(f"- **{track['suite']}**：{coverage['tasks']} 个任务、{coverage['groups']} 个配对来源组、{coverage['episodes']} 个候选；"
                           f"独立回放 {replay['records']}/{replay['expected_records']}，通过 {replay['passed_records']}，技术验收 {replay['technical_acceptance']}。"
                           f" [manifest]({track['candidate_manifest']}) / [回放报告]({track['replay_report']})")
        commands.append(f"python scripts/preview_remaining_candidates.py --manifest {track['candidate_manifest']} "
                        f"--replay {track['replay_report']} --out reports/local_preview_{track['suite']}.html")
    track_summary, preview_commands = "\n".join(track_lines), "\n".join(commands)
    return f"""# Remaining Goals 候选交付包

本 ZIP 是源码、候选状态与技术验收证据的交付快照，**不是审定发布数据集，也不是 VLA 成功率报告**。
各 suite 保留独立 manifest、回放验收、评测分数和 checkpoint 归一化配置，不合并 episode 或跨 suite 汇总成功率：

{track_summary}

## 离线核验与入口

解压到任意目录后，在该目录运行（ZIP 核验仅需 Python 3.10+ 标准库）：

```text
python scripts/package_remaining_benchmark.py verify --zip PATH_TO_THIS_ZIP
python scripts/package_remaining_benchmark.py verify --directory .
```

`bundle_manifest.json` 为全部其他文件记录 SHA-256、大小和角色，自身用规范化内容哈希保护。
完整性检查不是发布批准、来源签名或物理验收，不会把 legal=false 改为 true。
新观测协议保存构造与每次回放实际返回的 typed NPZ 初帧，原始 RGB 和非 RGB 数值均不被替换。
创建交付包时用 NumPy 解码双方工件，独立重算固定 RGB 边界及非 RGB 位级一致性，并核对完整比较记录；
标准库离线 verify 校验工件字节 SHA、引用和观测摘要绑定及诊断界限的一致性，不重新解码像素或运行仿真。
未保存每个动态步骤的全图；其观测一致性依据冻结验收器留下的哈希、界限诊断和非步进状态检查。
确认依赖后可运行 `python -m pytest tests -q`；NumPy/Pytest 需自行安装。
真实环境需 Python 3.10 与现有 PyTorch，先运行 `scripts/setup_remaining_libero.py`，再运行 doctor。
venv、模型权重和个人运行配置不在包内。上游官方源码/资产是否包含：{include_upstream}。
包含时位于 `.runtime/remaining_libero/LIBERO-COMMIT/`，setup 会复用已校验文件；不包含时安装器按固定 commit 下载。
官方上游目录保留公开原文与原始 Git blob 校验值，不改写其源码、资产或许可证。

各轨道可分别生成预览：

```text
{preview_commands}
```

正式评测 CLI 会拒绝尚未审查的候选。不要改 legal 字段来绕过验收。

本次显式选择的 doctor、预览或额外诊断证据（doctor 引用的 PNG 随报告附带并校验 SHA-256）：

{evidence_links}

## 移动安装目录的限制

MuJoCo XML 当前采用精确字节哈希，其中包含绝对资产路径。新安装目录、操作系统、渲染栈、兼容记录、额外保留资产或源码变更都可能改变锁。
此包可便携传输与离线核验，**不保证这些冻结状态在任意新目录直接回放**。
若锁不匹配，按固定官方初态和同一构造协议重新构建、验收并冻结新的候选包，保留迁移记录；不得关闭模型、资产或环境哈希检查。
`provenance/libero_runtime.json` 记录当时实际官方文件的清单与哈希（含 profile 之外被保留的资源），不含本机 Python/用户目录。
文档或额外证据若含个人目录，交付副本会脱敏并在文件条目标明原始 SHA-256；候选 manifest 不做此类改写。
已有规范中的 a4/a5 等历史排障链接可能仅在原项目目录可用；本包不为这些历史链接复制无关旧数据。
本次交付以本页指定的 manifest、回放报告、上列 doctor/预览及逐文件清单为准。

## 研究发布缺项

""" + "\n".join(f"- {gap['id']} ({gap['status']}): {gap['detail']}" for gap in gaps) + "\n"


def _inspect_track(root, state_pack, replay_report):
    """Bind exactly one suite to its own immutable candidate and replay files."""
    from .replay_candidates import _candidate_pack

    state_pack = _contained(root, state_pack)
    manifest_path = state_pack / "manifest.candidates.json" if state_pack.is_dir() else state_pack
    if manifest_path.name != "manifest.candidates.json":
        raise ValueError("only manifest.candidates.json is supported; this tool does not publish releases")
    manifest, groups, states, observation_hashes = _candidate_pack(manifest_path)
    suites = {episode["suite"] for episode in manifest["episodes"]}
    if len(suites) != 1:
        raise ValueError("each state pack must contain exactly one suite; use separate tracks")
    construction_path = manifest_path.parent / "construction_report.json"
    construction = _read_json(construction_path)
    if (construction.get("kind") != "real_libero_candidate_construction" or construction.get("toy") is not False
            or construction.get("environment") != manifest["environment"]
            or construction.get("candidate_episodes") != len(manifest["episodes"])
            or construction.get("complete_groups") != len(groups)):
        raise ValueError("construction report does not describe the supplied candidate pack")
    for name, expected_hash in construction.get("builder_sources_sha256", {}).items():
        if not isinstance(name, str) or _safe_name(name) != Path(name).name or Path(name).suffix != ".py":
            raise ValueError("unexpected builder source in construction report")
        if _sha((root / "benchmark/remaining_goals" / name).read_bytes()) != expected_hash:
            raise ValueError(f"current source differs from the frozen construction evidence: {name}")
    compatibility = manifest["environment"].get("lock", {}).get("compatibility", {})
    for field, name in (("bridge_source_sha256", "libero_env.py"), ("source_sha256", "libero_compat.py")):
        if field in compatibility and _sha((root / "benchmark/remaining_goals" / name).read_bytes()) != compatibility[field]:
            raise ValueError(f"current source differs from the frozen environment identity: {name}")
    replay_path = _contained(root, replay_report)
    replay_files, replay = validate_replay_evidence(manifest_path, manifest, replay_path, states, observation_hashes)
    coverage = {"episodes": len(manifest["episodes"]), "groups": len(groups),
                "tasks": len({episode["task_id"] for episode in manifest["episodes"]})}
    suite = next(iter(suites))
    summary = {"track_id": suite, "suite": suite,
               "candidate_manifest": manifest_path.relative_to(root).as_posix(),
               "candidate_content_hash": manifest["content_hash"],
               "environment_fingerprint": manifest["environment"]["fingerprint"],
               "replay_report": replay_path.relative_to(root).as_posix(),
               "coverage": coverage, "replay": replay}
    return {"summary": summary, "manifest": manifest, "manifest_path": manifest_path,
            "construction_path": construction_path, "replay_files": replay_files}


def create_bundle(root, state_pack, replay_report, output, *, evidence=(), include_upstream=True):
    """Package one or several separately validated suites, sharing source/assets.

    Existing scalar arguments retain the original single-pack archive format.
    Lists/tuples are paired by position; no candidate manifests are merged.
    """
    root = Path(root).resolve()
    packs = list(state_pack) if isinstance(state_pack, (list, tuple)) else [state_pack]
    reports = list(replay_report) if isinstance(replay_report, (list, tuple)) else [replay_report]
    if not packs or len(packs) != len(reports):
        raise ValueError("state-pack and replay arguments must have matching nonzero counts, paired by order")
    inspected = [_inspect_track(root, pack, report) for pack, report in zip(packs, reports)]
    tracks = [track["summary"] for track in inspected]
    if len({track["suite"] for track in tracks}) != len(tracks):
        raise ValueError("each suite may appear only once in a delivery collection")
    if len({track["environment_fingerprint"] for track in tracks}) != 1:
        raise ValueError("delivery tracks must share one frozen runtime fingerprint and provenance")
    seeds = list((root / "benchmark/remaining_goals").rglob("*.py"))
    seeds += list((root / "scripts").glob("*remaining*.py"))
    seeds += list((root / "tests").glob("test_remaining*.py"))
    seeds += list((root / "tests").glob("test_prepare_remaining*.py"))
    for optional in ("tests/__init__.py", "tests/conftest.py"):
        if (root / optional).is_file():
            seeds.append(root / optional)
    source_files = _python_closure(root, seeds)
    payload, records = {}, {}

    def add(name, body, role, *, redact=False, immutable=False, public_upstream=False):
        name = _safe_name(name)
        if name == INDEX or name.casefold() in {entry.casefold() for entry in payload}:
            raise ValueError(f"duplicate archive destination: {name}")
        original = body
        if Path(name).suffix in TEXT_SUFFIXES and not public_upstream:
            text = body.decode("utf-8-sig")
            original_text = text
            if redact and not immutable:
                # Keep references to copied evidence usable after extraction;
                # JSON stores backslashes escaped, whereas Markdown may not.
                spellings = {str(root), root.as_posix(), json.dumps(str(root), ensure_ascii=False)[1:-1]}
                for prefix in sorted(spellings, key=len, reverse=True):
                    text = text.replace(prefix, ".")
            if PRIVATE_HOME.search(text):
                if immutable or not redact:
                    raise ValueError(f"private local user path in immutable/source file: {name}")
                text = PRIVATE_HOME.sub("LOCAL_USER_HOME", text)
            if text != original_text:
                body = text.encode("utf-8")
            if Path(name).suffix == ".json":
                json.loads(text)  # Redaction must not break the evidence format.
        payload[name] = body
        records[name] = {"path": name, "sha256": _sha(body), "size": len(body), "role": role}
        if body != original:
            records[name].update(transformation="local_path_redaction_and_relativization", source_sha256=_sha(original))

    def add_file(path, role, **kwargs):
        path = _contained(root, path)
        name = path.relative_to(root).as_posix()
        if name in payload:
            return
        add(name, path.read_bytes(), role, **kwargs)

    for path in sorted(source_files):
        add_file(path, "source_or_test")
    # Only benchmark documentation belongs in the public artifact. Research
    # notes and plans may coexist in a development checkout but are not inputs
    # to installation, construction, replay, or evaluation.
    documents = [root / relative for relative in ("README.md", "THIRD_PARTY_NOTICES.md", "data/README.md")]
    documents += sorted((root / "docs").glob("remaining_goals_*.md"))
    for path in documents:
        if path.is_file():
            add_file(path, "documentation", redact=True)
    for relative in ("pyproject.toml", "requirements-dev.txt", ".gitignore", ".gitattributes", "CITATION.cff"):
        path = root / relative
        if path.is_file():
            add_file(path, "project_metadata")
    config_root = root / "configs/remaining_goals"
    for path in config_root.rglob("*"):
        relative = path.relative_to(config_root)
        # Local overrides can contain machine paths or credentials. Omit the
        # entire local directory and per-file overrides before reading bytes;
        # public runtime examples remain ordinary versioned configurations.
        if relative.parts[0].casefold() == "local" or path.name.casefold().endswith(".local.json"):
            continue
        if path.is_file() and path.suffix in (".json", ".yaml", ".yml", ".md"):
            add_file(path, "configuration", redact=True)
    for track in inspected:
        manifest, manifest_path = track["manifest"], track["manifest_path"]
        candidate_files = {manifest_path, track["construction_path"]}
        for episode in manifest["episodes"]:
            candidate_files.add(_contained(manifest_path.parent, episode["state_path"]))
            if episode.get("initial_observation"):
                candidate_files.add(_contained(manifest_path.parent, _safe_name(episode["initial_observation"]["path"])))
            audit_path = _contained(manifest_path.parent, episode["construction"]["technical_audit"])
            if not (audit_path.parent / "start.png").is_file():
                raise ValueError("candidate is missing its initial visual review frame")
            candidate_files.add(audit_path)
            candidate_files.update(p for p in audit_path.parent.iterdir() if p.is_file() and p.suffix in (".json", ".png", ".npz"))
        # Keep attempted/rejected construction audits too; never select by policy
        # success. Unreferenced states, checkpoints and unrelated files are omitted.
        candidate_files.update(p for p in (manifest_path.parent / "validation").rglob("*")
                               if p.is_file() and p.suffix in (".json", ".png", ".npz"))
        # A successful mask in a later rejected joint attempt can still have an
        # observation artifact. Preserve and validate this evidence without
        # counting it as a selected candidate.
        for path in list(candidate_files):
            if path.suffix == ".json":
                record = _read_json(path)
                if isinstance(record, dict) and record.get("initial_observation"):
                    from .observation_artifact import load_observation_artifact
                    reference = record["initial_observation"]
                    digest = record.get("trace", [{}])[0].get("observation_check", {}).get("returned_sha256")
                    if not digest:
                        raise ValueError("construction observation artifact lacks an initial audit digest")
                    load_observation_artifact(manifest_path.parent, reference, expected_digest=digest)
                    candidate_files.add(_contained(manifest_path.parent, _safe_name(reference["path"])))
        for path in sorted(candidate_files):
            add_file(path, "candidate_state_and_construction_evidence", redact=True, immutable=path == manifest_path)
        for path in sorted(track["replay_files"]):
            add_file(path, "independent_replay_evidence", redact=True)
    for path in sorted((root / "reports").glob("remaining_goals_runtime_packages_*.json"))[-1:]:
        add_file(path, "runtime_dependency_inventory", redact=True)
    for supplied in evidence:
        supplied = _contained(root, supplied)
        files = [supplied] if supplied.is_file() else sorted(p for p in supplied.rglob("*") if p.is_file())
        if not files:
            raise ValueError("requested evidence path is empty")
        for path in files:
            if path.suffix not in EVIDENCE_SUFFIXES - {".npy"}:
                raise ValueError("extra evidence accepts JSON/PNG/Markdown/CSV/HTML only, not logs, weights or executables")
            add_file(path, "additional_evidence_not_policy_certification", redact=True)
            if path.suffix == ".json":
                extra = _read_json(path)
                if isinstance(extra, dict) and extra.get("schema_version") == "remaining-libero-doctor-v1":
                    for snapshot in extra.get("snapshots", []):
                        for image in snapshot.get("images", {}).values():
                            frame = _contained(root, image["path"])
                            if frame.suffix != ".png" or _sha(frame.read_bytes()) != image["sha256"]:
                                raise ValueError("doctor frame path/checksum mismatch")
                            add_file(frame, "runtime_doctor_frame")
    provenance, official_files = _provenance(root, include_upstream=include_upstream)
    for name, body in provenance.items():
        add(name, body, "pinned_upstream_provenance", redact=True)
    for path, expected_git_sha in official_files:
        path = _contained(root, path)
        body = path.read_bytes()
        if hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest() != expected_git_sha:
            raise ValueError("official source changed during packaging; stop concurrent installation and retry")
        add(path.relative_to(root).as_posix(), body, "verified_public_upstream_source_or_asset", public_upstream=True)
    gaps = [dict(gap) for gap in GAPS]
    license_path = root / "LICENSE"
    if license_path.is_file():
        add_file(license_path, "project_license")
    else:
        gaps.append({"id": "project_license", "status": "missing", "detail": "No project-level LICENSE was supplied. LIBERO's license does not license all original project code or separately sourced assets."})
    additional = sorted(name for name, row in records.items() if row["role"] == "additional_evidence_not_policy_certification")
    add("DELIVERY_README.md", _delivery_readme(tracks, gaps, include_upstream, additional).encode("utf-8"), "delivery_instructions")
    index = {"format": FORMAT if len(tracks) == 1 else COLLECTION_FORMAT, "artifact_stage": "technical_candidates_not_release",
             "release_authorized": False, "policy_benchmark_certified": False,
             "tracks": tracks,
             "suite_evaluation_contract": "Separate manifests, scores and checkpoint normalization; no pooled cross-suite success rate.",
             "upstream_files_included": bool(include_upstream),
             "research_release_gaps": gaps, "files": [records[name] for name in sorted(records)],
             "integrity_scope": "Every ZIP payload file except this self-hashed index; checksums are not signatures."}
    if len(tracks) == 1:
        index.update({key: tracks[0][key] for key in (
            "candidate_manifest", "candidate_content_hash", "replay_report", "coverage", "replay")})
    index["content_hash"] = _manifest_hash(index)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload[name])
        archive.writestr(INDEX, _json_bytes(index))
    return verify_bundle(output)


def _validate_index(index):
    if (index.get("format") not in (FORMAT, COLLECTION_FORMAT) or index.get("content_hash") != _manifest_hash(index)
            or index.get("artifact_stage") != "technical_candidates_not_release"
            or index.get("release_authorized") is not False
            or index.get("policy_benchmark_certified") is not False):
        raise ValueError("invalid, modified, or non-candidate bundle manifest")
    entries, folded = {}, set()
    for row in index.get("files", []):
        name = _safe_name(row.get("path"))
        if name == INDEX or name.casefold() in folded:
            raise ValueError("duplicate or self-referential bundle manifest entry")
        if (type(row.get("size")) is not int or row["size"] < 0 or not isinstance(row.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None):
            raise ValueError("invalid bundle file size or checksum")
        entries[name] = row
        folded.add(name.casefold())
    if index["format"] == FORMAT:
        tracks = [index]
        if "tracks" in index:
            if (not isinstance(index["tracks"], list) or len(index["tracks"]) != 1
                    or any(index["tracks"][0].get(key) != index.get(key) for key in (
                        "candidate_manifest", "candidate_content_hash", "replay_report", "coverage", "replay"))):
                raise ValueError("single-pack track metadata contradicts its backward-compatible fields")
    else:
        tracks = index.get("tracks")
        if not isinstance(tracks, list) or len(tracks) < 2:
            raise ValueError("collection needs at least two independent suite tracks")
        if any(key in index for key in ("coverage", "replay", "candidate_manifest", "candidate_content_hash", "replay_report")):
            raise ValueError("collection must not impersonate a pooled single-suite report")
    seen_suites, seen_manifests, seen_reports = set(), set(), set()
    for track in tracks:
        if not entries or track.get("candidate_manifest") not in entries or track.get("replay_report") not in entries:
            raise ValueError("bundle manifest does not identify included candidate and replay evidence")
        if index["format"] == COLLECTION_FORMAT:
            suite = track.get("suite")
            if (not isinstance(suite, str) or not suite.strip() or track.get("track_id") != suite
                    or suite in seen_suites or track["candidate_manifest"] in seen_manifests
                    or track["replay_report"] in seen_reports):
                raise ValueError("collection repeats a suite, manifest or replay report")
            seen_suites.add(suite)
            seen_manifests.add(track["candidate_manifest"])
            seen_reports.add(track["replay_report"])
    if index["format"] == COLLECTION_FORMAT and len({track.get("environment_fingerprint") for track in tracks}) != 1:
        raise ValueError("collection tracks have inconsistent runtime fingerprints")
    return entries


def _verify_track_bindings(index, read):
    """Check track labels and report links offline, without importing NumPy."""
    def relative(parent_file, path):
        return _safe_name((PurePosixPath(parent_file).parent / _safe_name(path)).as_posix())

    def reference_bytes(parent_file, reference, digest):
        if (not isinstance(reference, dict) or reference.get("format") != "remaining-observation-npz-v1"
                or reference.get("observation_sha256") != digest
                or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise ValueError("archive observation artifact digest/format binding differs")
        name = relative(parent_file, reference.get("path"))
        if PurePosixPath(name).suffix != ".npz" or _sha(read(name)) != reference.get("sha256"):
            raise ValueError("archive observation artifact byte hash differs from its reference")
        return name

    tracks = index.get("tracks", [index])
    for track in tracks:
        raw = read(track["candidate_manifest"])
        manifest = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique)
        if (manifest.get("content_hash") != _manifest_hash(manifest)
                or manifest["content_hash"] != track.get("candidate_content_hash")):
            raise ValueError("track candidate content hash mismatch")
        episodes = manifest.get("episodes", [])
        suites = {episode["suite"] for episode in episodes}
        if len(suites) != 1 or ("suite" in track and suites != {track["suite"]}):
            raise ValueError("track suite does not match its separately frozen manifest")
        if (any(episode.get("construction", {}).get("legal") is not False for episode in episodes)
                or ("environment_fingerprint" in track and track["environment_fingerprint"] != manifest["environment"]["fingerprint"])):
            raise ValueError("track changed candidate approval or runtime identity")
        coverage = {"episodes": len(episodes), "tasks": len({episode["task_id"] for episode in episodes}),
                    "groups": len({(episode["task_id"], episode["source_id"], episode["pose_id"]) for episode in episodes})}
        if coverage != track["coverage"]:
            raise ValueError("track coverage differs from its own manifest")
        observation_digests = {}
        for episode in episodes:
            reference = episode.get("initial_observation")
            if reference:
                construction_path = relative(track["candidate_manifest"], episode["construction"]["technical_audit"])
                construction = json.loads(read(construction_path).decode("utf-8-sig"), object_pairs_hook=_unique)
                digest = construction["trace"][0]["observation_check"]["returned_sha256"]
                reference_bytes(track["candidate_manifest"], reference, digest)
                if construction.get("initial_observation", reference) != reference:
                    raise ValueError("construction observation reference differs from its manifest")
                observation_digests[episode["episode_id"]] = digest
        report = json.loads(read(track["replay_report"]).decode("utf-8-sig"), object_pairs_hook=_unique)
        if (report.get("source_content_hash") != manifest["content_hash"]
                or report.get("source_manifest_sha256") != _sha(raw)
                or report.get("policy_called") is not False or report.get("release_authorized") is not False):
            raise ValueError("track replay is bound to a different manifest or authority")
        expected = {episode["episode_id"]: episode for episode in episodes}
        rows = report["episodes"]
        seen = set()
        for row in rows:
            key = row["episode_id"], row["repetition"]
            if (key[0] not in expected or type(key[1]) is not int or not 0 <= key[1] < report["repeats"]
                    or key in seen or row.get("initial_mask") != expected[key[0]]["initial_mask"]
                    or type(row.get("technical_acceptance")) is not bool or row.get("source_legal") is not False):
                raise ValueError("track replay contains duplicate or foreign episodes")
            seen.add(key)
            if key[0] in observation_digests:
                audit_path = relative(track["replay_report"], row["audit_path"])
                audit = json.loads(read(audit_path).decode("utf-8-sig"), object_pairs_hook=_unique)
                if audit.get("technical_acceptance") is not row["technical_acceptance"]:
                    raise ValueError("archive replay audit acceptance differs from its report")
                comparison = audit.get("reset_observation_comparison")
                actual = audit.get("reset_initial_observation")
                if actual is not None:
                    reference_bytes(audit_path, actual, comparison.get("returned_sha256") if isinstance(comparison, dict) else None)
                    if comparison.get("fresh_sha256") != observation_digests[key[0]]:
                        raise ValueError("archive reset comparison is bound to a different construction observation")
                if row["technical_acceptance"]:
                    trace = audit.get("trace", [])
                    reset = row.get("reset_checks", {})
                    if (not actual or audit.get("error") is not None or row.get("error") is not None
                            or audit.get("requested_steps") != report["steps"] or audit.get("completed_steps") != report["steps"]
                            or len(trace) != report["steps"] + 1
                            or [item.get("step") for item in trace] != list(range(report["steps"] + 1))
                            or row.get("checks") != audit.get("checks")
                            or any(reset.get(field) is not True for field in (
                                "saved_state_exact", "initial_mask_exact", "construction_observation_matches", "initial_non_rgb_exact"))
                            or any(value is not True for value in reset.values()) or audit.get("formal_reset_checks") != reset
                            or audit.get("checks", {}).get("validation_window_complete") is not True
                            or audit.get("checks", {}).get("snapshot_contract_valid") is not True
                            or any(value is False for value in audit.get("checks", {}).values())):
                        raise ValueError("archive passing replay lacks its complete reset/trace evidence")
                    _passing_observation_comparison(comparison, initial=True,
                        returned_hash=trace[0].get("observation_check", {}).get("returned_sha256"),
                        reference_hash=observation_digests[key[0]])
                    if trace[0]["observation_check"].get("returned_non_rgb_sha256") != comparison.get("returned_non_rgb_sha256"):
                        raise ValueError("archive initial non-RGB digest differs from its reset comparison")
                    for item in trace:
                        if (item.get("goals") != expected[key[0]]["initial_mask"]
                                or any(value is False for value in item.get("checks", {}).values())
                                or item.get("checks", {}).get("rgb_allowance_state_verified") is not True
                                or (item["step"] == 0 and item["checks"].get("initial_non_rgb_bit_exact") is not True)):
                            raise ValueError("archive passing replay trace has invalid checks or goal masks")
                        _passing_observation_comparison(item.get("observation_check"), initial=item["step"] == 0,
                            float_tolerance=audit.get("limits", {}).get("observation_tolerance", 1e-8),
                            camera_reference=comparison["image_diagnostics"])
        complete = len(seen) == len(episodes) * report["repeats"]
        passed = complete and bool(rows) and report.get("error") is None and all(row["technical_acceptance"] for row in rows)
        summary = {"technical_acceptance": passed, "complete": complete, "records": len(rows),
                   "passed_records": sum(row["technical_acceptance"] for row in rows),
                   "expected_records": len(episodes) * report["repeats"],
                   "requested_steps": report["steps"], "repeats": report["repeats"]}
        if report.get("technical_acceptance") is not passed or summary != track["replay"]:
            raise ValueError("track replay summary differs from its independent report")


def verify_bundle(path):
    """Verify a ZIP without extracting, or strictly verify an extracted directory."""
    path = Path(path)
    if path.is_dir():
        index = _read_json(path / INDEX)
        entries = _validate_index(index)
        actual = set()
        for file in path.rglob("*"):
            if file.is_symlink():
                raise ValueError("symlink found in extracted bundle")
            if file.is_file():
                actual.add(_safe_name(file.relative_to(path).as_posix()))
        if actual != set(entries) | {INDEX}:
            raise ValueError("bundle has missing or unlisted files (verify before running Python and creating caches)")
        for name, row in entries.items():
            body = (path / name).read_bytes()
            if len(body) != row["size"] or _sha(body) != row["sha256"]:
                raise ValueError(f"bundle checksum/size mismatch: {name}")
        _verify_track_bindings(index, lambda name: (path / name).read_bytes())
    else:
        with zipfile.ZipFile(path) as archive:
            names, folded = set(), set()
            for info in archive.infolist():
                name = _safe_name(info.filename)
                if (name.casefold() in folded or info.is_dir() or info.flag_bits & 1
                        or stat.S_ISLNK(info.external_attr >> 16)):
                    raise ValueError("duplicate, directory, encrypted or symlink ZIP entry")
                names.add(name)
                folded.add(name.casefold())
            if INDEX not in names:
                raise ValueError("ZIP has no bundle manifest")
            index = json.loads(archive.read(INDEX).decode("utf-8"), object_pairs_hook=_unique)
            entries = _validate_index(index)
            if names != set(entries) | {INDEX}:
                raise ValueError("ZIP has missing or unlisted payload files")
            for name, row in entries.items():
                info = archive.getinfo(name)
                if info.file_size != row["size"]:
                    raise ValueError(f"bundle size mismatch: {name}")
                digest = hashlib.sha256()
                with archive.open(name) as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                if digest.hexdigest() != row["sha256"]:
                    raise ValueError(f"bundle checksum mismatch: {name}")
            _verify_track_bindings(index, archive.read)
    result = {"valid": True, "format": index["format"], "content_hash": index["content_hash"],
            "files": len(entries), "payload_bytes": sum(row["size"] for row in entries.values()),
            "artifact_stage": index["artifact_stage"], "release_authorized": False,
            "research_release_gaps": index["research_release_gaps"]}
    if index["format"] == FORMAT:
        result.update(coverage=index["coverage"], replay=index["replay"])
    else:
        result["tracks"] = index["tracks"]
    return result
