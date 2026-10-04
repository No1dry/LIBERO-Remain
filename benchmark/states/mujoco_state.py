"""MuJoCo 状态向量的读写工具（纯函数，不依赖 robosuite，可单测）。

背景：LIBERO / robosuite 的"环境状态"是一个一维数组：

    [ time(1) | qpos(nq) | qvel(nv) | act(na, 可选) ]

``qpos`` 里依次是各 joint 的位置；对自由物体（碗、瓶子、篮子……）而言，
其 free joint 占 7 个槽位：

    [ x, y, z, qw, qx, qy, qz ]

本项目构造 satisfied 状态的核心操作就是：**改写某个自由物体的 xyz**。

设计原则
--------
本模块只处理"数组下标 + 数值"这一层，不碰仿真步进、不碰 LIBERO API，
因此可以在没有 MuJoCo 的机器上完整单测（用假的 model/data 对象）。
真正的仿真交互放在 ``benchmark/arena/`` 里。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

# MuJoCo joint type 枚举值（mjJNT_FREE == 0）。这里写成常量而不是
# `import mujoco`，是为了让本模块在没有 MuJoCo 的环境下也能导入和单测。
MJ_JNT_FREE = 0
MJ_JNT_BALL = 1
MJ_JNT_SLIDE = 2
MJ_JNT_HINGE = 3

FREE_JOINT_QPOS_DIM = 7  # x, y, z, qw, qx, qy, qz

# 单自由度关节类型（hinge / slide）—— 抽屉、柜门、旋钮都属于这一类
SINGLE_DOF_TYPES = (MJ_JNT_SLIDE, MJ_JNT_HINGE)


# ---------------------------------------------------------------------------
# MuJoCo 版本兼容层
# ---------------------------------------------------------------------------
#
# 这是本项目踩过的真实坑，值得写清楚：
#
#   mujoco >= 3.0 : model.joint_names / model.body_names / model.geom_bodyid
#                   / model.geom_type / model.geom_rbound 都是可直接索引的数组
#   mujoco 2.x    : 这些**都不存在**，必须用
#                   mujoco.mj_id2name(model, mjtObj.mjOBJ_JOINT, i)
#                   model.body(i).name / model.geom(i).bodyid / .type / .rbound
#
# 服务器上是 mujoco 2.3.7（robosuite 1.4.1 的搭配），开发机上是 3.x。
# 两边都要能跑，所以把差异全部收敛到下面这几个 helper 里，
# 其余代码只调用 helper，不直接碰版本相关的属性。


def _mujoco():
    """惰性导入 mujoco。没有 mujoco 的环境（例如纯单测）返回 None。"""
    try:
        import mujoco  # type: ignore

        return mujoco
    except Exception:  # noqa: BLE001
        return None


def _robosuite_mujoco():
    """robosuite 自带一份 mujoco binding。

    robosuite 的 ``sim.model`` 是 ``robosuite.utils.binding_utils.MjModel``，
    与 ``mujoco._structs.MjModel`` **不是同一个类型** ——
    直接把它传给 ``mujoco.mj_id2name`` 会抛
    ``TypeError: incompatible function arguments``。
    这时必须用 robosuite 自己那份 binding 来做名字查询。
    """
    try:
        from robosuite.utils import binding_utils  # type: ignore

        return binding_utils.mujoco
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# 名字表缓存
# ---------------------------------------------------------------------------
#
# 这是一个**性能关键**的缓存，不是锦上添花。
#
# 问题：``iter_joints`` / ``all_body_names`` 需要每个关节/body 的名字，而
# robosuite binding 下每个名字都要过一次 C 调用。更糟的是上层会**反复**
# 调用 ``resolve_free_joint`` / ``find_body_id`` / ``get_joint_range``
# （每个 episode 数百次），每次都重新枚举全部关节和 body。
# 实测后果：一次状态构造从 10s 涨到 33s+，160 个 episode 会拖到不可接受。
#
# 做法：按 model 对象缓存名字表。model 在一个环境实例内是不变的，
# 所以这是安全的。用 id(model) 作 key 并持有 model 引用，
# 避免对象被回收后 id 复用导致串味。

_NAME_CACHE: dict[int, tuple[Any, list[str], list[str]]] = {}
_NAME_CACHE_MAX = 32


def _name_tables(model: Any) -> tuple[list[str], list[str]]:
    """返回 (joint_names, body_names)，带缓存。"""
    key = id(model)
    hit = _NAME_CACHE.get(key)
    if hit is not None and hit[0] is model:
        return hit[1], hit[2]

    joints: list[str] = []
    if hasattr(model, "njnt"):
        names = getattr(model, "joint_names", None)
        if names is not None:
            joints = [str(n) for n in names]
        else:
            joints = [_resolve_joint_name(model, i) for i in range(int(model.njnt))]

    bodies: list[str] = []
    if hasattr(model, "nbody"):
        names = getattr(model, "body_names", None)
        if names is not None:
            bodies = [str(n) for n in names]
        else:
            bodies = [_resolve_body_name(model, i) for i in range(int(model.nbody))]

    if len(_NAME_CACHE) >= _NAME_CACHE_MAX:
        _NAME_CACHE.pop(next(iter(_NAME_CACHE)))
    _NAME_CACHE[key] = (model, joints, bodies)
    return joints, bodies


def _id2name(model: Any, obj_type: str, index: int) -> str | None:
    """按名字查询关节/body/geom，兼容原生 mujoco 与 robosuite binding。"""
    for mj in (_mujoco(), _robosuite_mujoco()):
        if mj is None:
            continue
        try:
            obj = getattr(mj.mjtObj, f"mjOBJ_{obj_type.upper()}")
            nm = mj.mj_id2name(model, obj, index)
            if nm:
                return str(nm)
        except Exception:  # noqa: BLE001
            continue
    return None


def _resolve_joint_name(model: Any, index: int) -> str:
    nm = _id2name(model, "joint", index)
    if nm:
        return nm
    try:
        return str(model.joint(index).name)
    except Exception:  # noqa: BLE001
        return f"joint_{index}"


def _resolve_body_name(model: Any, index: int) -> str:
    nm = _id2name(model, "body", index)
    if nm:
        return nm
    try:
        return str(model.body(index).name)
    except Exception:  # noqa: BLE001
        return f"body_{index}"


def task_joint_range_span(model: Any, joint_name_or_prefix: str) -> float:
    """任务关节的物理行程 (q_max - q_min)；读不到返回 nan。

    §3.5：抽屉滑轨单位是米、炉钮铰链单位是弧度，绝对值不可跨任务比较，
    必须用行程归一化成"占全行程的比例"。这里同时兼容 mujoco 2.x/3.x 与
    测试替身（它们未必有 ``joint_id2name``），统一走 :func:`joint_name`。
    """
    try:
        entry = resolve_single_dof_joint(model, joint_name_or_prefix)
    except Exception:  # noqa: BLE001
        return float("nan")
    try:
        n = int(model.njnt)
    except Exception:  # noqa: BLE001
        return float("nan")
    for i in range(n):
        try:
            if joint_name(model, i) != entry.name:
                continue
            rng = model.jnt_range[i]
            lo, hi = float(rng[0]), float(rng[1])
            return abs(hi - lo)
        except Exception:  # noqa: BLE001
            continue
    return float("nan")


def joint_name(model: Any, index: int) -> str:
    """取关节名（带缓存，见 _name_tables 的说明）。"""
    joints, _ = _name_tables(model)
    if 0 <= index < len(joints):
        return joints[index]
    return _resolve_joint_name(model, index)


def body_name(model: Any, index: int) -> str:
    """取 body 名（带缓存）。"""
    _, bodies = _name_tables(model)
    if 0 <= index < len(bodies):
        return bodies[index]
    return _resolve_body_name(model, index)


def geom_bodyid(model: Any, geom_index: int) -> int:
    arr = getattr(model, "geom_bodyid", None)
    if arr is not None:
        return int(arr[geom_index])
    return int(model.geom(geom_index).bodyid)


def geom_type(model: Any, geom_index: int) -> int:
    arr = getattr(model, "geom_type", None)
    if arr is not None:
        return int(arr[geom_index])
    return int(model.geom(geom_index).type)


def geom_rbound(model: Any, geom_index: int) -> float:
    arr = getattr(model, "geom_rbound", None)
    if arr is not None:
        return float(arr[geom_index])
    return float(model.geom(geom_index).rbound)


def geom_plane_type_id() -> int:
    """mjGEOM_PLANE 的枚举值。取不到时退回已知的 0。"""
    mj = _mujoco()
    if mj is None:
        return 0
    try:
        return int(mj.mjtGeom.mjGEOM_PLANE)
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# 状态向量的分段视图
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateLayout:
    """把扁平状态数组切成 time / qpos / qvel / act 四段。

    ``nq`` / ``nv`` / ``na`` 来自 ``model.nq`` / ``model.nv`` / ``model.na``。
    """

    nq: int
    nv: int
    na: int = 0

    @property
    def time_dim(self) -> int:
        return 1

    @property
    def qpos_slice(self) -> slice:
        return slice(self.time_dim, self.time_dim + self.nq)

    @property
    def qvel_slice(self) -> slice:
        return slice(self.time_dim + self.nq, self.time_dim + self.nq + self.nv)

    @property
    def act_slice(self) -> slice | None:
        if self.na == 0:
            return None
        start = self.time_dim + self.nq + self.nv
        return slice(start, start + self.na)

    @property
    def total_dim(self) -> int:
        return self.time_dim + self.nq + self.nv + self.na

    @classmethod
    def from_model(cls, model: Any) -> "StateLayout":
        return cls(
            nq=int(model.nq),
            nv=int(model.nv),
            na=int(getattr(model, "na", 0) or 0),
        )

    @classmethod
    def from_state(cls, state: Sequence[float], model: Any) -> "StateLayout":
        """由实际状态长度推断布局，用于校验 model 与 state 是否匹配。"""
        layout = cls.from_model(model)
        actual = len(state)
        if actual != layout.total_dim:
            raise ValueError(
                f"状态长度 {actual} 与 model 推断的 {layout.total_dim} 不一致 "
                f"(nq={layout.nq}, nv={layout.nv}, na={layout.na})。"
                "可能是 LIBERO/robosuite 版本差异，请检查 extra state 字段。"
            )
        return layout


def as_state_array(state: Sequence[float] | np.ndarray) -> np.ndarray:
    """转成 float64 的 numpy 数组（不复制语义上的所有权，只保证类型）。"""
    return np.asarray(state, dtype=np.float64).reshape(-1)


def get_qpos(state: Sequence[float] | np.ndarray, layout: StateLayout) -> np.ndarray:
    return as_state_array(state)[layout.qpos_slice]


def with_qpos(
    state: Sequence[float] | np.ndarray,
    layout: StateLayout,
    qpos: np.ndarray,
) -> np.ndarray:
    """返回一个把 qpos 替换掉的新状态数组（不修改入参）。"""
    qpos = np.asarray(qpos, dtype=np.float64).reshape(-1)
    if qpos.shape[0] != layout.nq:
        raise ValueError(f"qpos 长度应为 {layout.nq}，实际 {qpos.shape[0]}")
    out = as_state_array(state).copy()
    out[layout.qpos_slice] = qpos
    return out


# ---------------------------------------------------------------------------
# 关节索引发现
# ---------------------------------------------------------------------------


@dataclass
class JointEntry:
    name: str
    mj_type: int
    qpos_adr: int
    qpos_dim: int
    dof_adr: int
    dof_dim: int

    @property
    def is_free(self) -> bool:
        return self.mj_type == MJ_JNT_FREE


def iter_joints(model: Any) -> list[JointEntry]:
    """枚举 model 中的所有关节（兼容 mujoco 2.x / 3.x）。"""
    if not hasattr(model, "njnt"):
        raise TypeError("model 没有 njnt，无法枚举关节。")

    jnt_type = np.asarray(model.jnt_type).reshape(-1)
    qpos_adr = np.asarray(model.jnt_qposadr).reshape(-1)
    dof_adr = np.asarray(model.jnt_dofadr).reshape(-1)

    cached_joint_names, _ = _name_tables(model)

    entries: list[JointEntry] = []
    for i in range(int(model.njnt)):
        t = int(jnt_type[i])
        dim = FREE_JOINT_QPOS_DIM if t == MJ_JNT_FREE else (4 if t == MJ_JNT_BALL else 1)
        dof_dim = 6 if t == MJ_JNT_FREE else (3 if t == MJ_JNT_BALL else 1)
        entries.append(
            JointEntry(
                name=cached_joint_names[i] if i < len(cached_joint_names) else joint_name(model, i),
                mj_type=t,
                qpos_adr=int(qpos_adr[i]),
                qpos_dim=dim,
                dof_adr=int(dof_adr[i]),
                dof_dim=dof_dim,
            )
        )
    return entries


def find_free_joints(model: Any, *, prefix: str | None = None) -> list[JointEntry]:
    """找出自由物体关节（即可自由平移/旋转的物体）。

    ``prefix`` 用于按名字过滤，例如 ``"akita_black_bowl"``。
    """
    out = [j for j in iter_joints(model) if j.is_free]
    if prefix is not None:
        out = [j for j in out if j.name.startswith(prefix)]
    return out


def resolve_free_joint(model: Any, name_or_prefix: str) -> JointEntry:
    """按名字或前缀解析**唯一**的自由关节。多个匹配则报错并列候选。"""
    matches = find_free_joints(model)
    exact = [j for j in matches if j.name == name_or_prefix]
    if len(exact) == 1:
        return exact[0]
    prefixed = [j for j in matches if j.name.startswith(name_or_prefix)]
    if len(prefixed) == 1:
        return prefixed[0]
    if not prefixed:
        raise KeyError(
            f"找不到自由关节 {name_or_prefix!r}。可用: {[j.name for j in matches]}"
        )
    raise KeyError(
        f"自由关节 {name_or_prefix!r} 匹配到多个: {[j.name for j in prefixed]}，请给更精确的名字。"
    )


def find_hinge_joints(model: Any, *, prefix: str | None = None) -> list[JointEntry]:
    """找出单自由度关节（抽屉/柜门等 slide joint，以及旋钮等 hinge joint）。

    注意：LIBERO 的抽屉是 **slide** joint（mjJNT_SLIDE），不是 hinge。
    早期实现只找 hinge，会漏掉所有抽屉类任务。
    """
    out = [j for j in iter_joints(model) if j.mj_type in SINGLE_DOF_TYPES]
    if prefix is not None:
        out = [j for j in out if j.name.startswith(prefix)]
    return out


def iter_single_dof_joints(model: Any) -> list[JointEntry]:
    return [j for j in iter_joints(model) if j.mj_type in SINGLE_DOF_TYPES]


# ---------------------------------------------------------------------------
# 读写物体位姿
# ---------------------------------------------------------------------------


def get_object_pos(
    state: Sequence[float] | np.ndarray,
    model: Any,
    name_or_prefix: str,
) -> np.ndarray:
    """读取自由物体的位置 xyz。"""
    joint = resolve_free_joint(model, name_or_prefix)
    qpos = get_qpos(state, StateLayout.from_model(model))
    return np.array(qpos[joint.qpos_adr : joint.qpos_adr + 3], dtype=np.float64)


def set_object_pos(
    state: Sequence[float] | np.ndarray,
    model: Any,
    name_or_prefix: str,
    pos_xyz: Sequence[float],
    *,
    keep_quat: bool = True,
) -> np.ndarray:
    """把自由物体移动到 ``pos_xyz``，返回新状态数组。

    ``keep_quat=True`` 表示保留原有朝向（只改位置）。
    """
    pos_xyz = np.asarray(pos_xyz, dtype=np.float64).reshape(3)
    joint = resolve_free_joint(model, name_or_prefix)
    layout = StateLayout.from_model(model)
    qpos = get_qpos(state, layout).copy()

    base = joint.qpos_adr
    if keep_quat:
        quat = qpos[base + 3 : base + 7].copy()
    else:
        quat = np.array([1.0, 0.0, 0.0, 0.0])  # wxyz 单位四元数
        qpos[base + 3 : base + 7] = quat

    qpos[base + 0 : base + 3] = pos_xyz
    return with_qpos(state, layout, qpos)


def set_object_quat(
    state: Sequence[float] | np.ndarray,
    model: Any,
    name_or_prefix: str,
    quat_wxyz: Sequence[float],
) -> np.ndarray:
    """设置自由物体朝向（wxyz 四元数）。"""
    quat = np.asarray(quat_wxyz, dtype=np.float64).reshape(4)
    norm = float(np.linalg.norm(quat))
    if norm < 1e-9:
        raise ValueError("四元数范数过小")
    quat = quat / norm
    joint = resolve_free_joint(model, name_or_prefix)
    layout = StateLayout.from_model(model)
    qpos = get_qpos(state, layout).copy()
    qpos[joint.qpos_adr + 3 : joint.qpos_adr + 7] = quat
    return with_qpos(state, layout, qpos)


def set_joint_pos(
    state: Sequence[float] | np.ndarray,
    model: Any,
    joint_name_or_prefix: str,
    value: float,
) -> np.ndarray:
    """设置单自由度关节的角度（抽屉/柜门/旋钮）。"""
    joint = resolve_single_dof_joint(model, joint_name_or_prefix)
    layout = StateLayout.from_model(model)
    qpos = get_qpos(state, layout).copy()
    qpos[joint.qpos_adr] = float(value)
    return with_qpos(state, layout, qpos)


def get_joint_pos(
    state: Sequence[float] | np.ndarray,
    model: Any,
    joint_name_or_prefix: str,
) -> float:
    joint = resolve_single_dof_joint(model, joint_name_or_prefix)
    qpos = get_qpos(state, StateLayout.from_model(model))
    return float(qpos[joint.qpos_adr])


def resolve_single_dof_joint(model: Any, name_or_prefix: str) -> JointEntry:
    """按名字/前缀解析唯一的单自由度关节。

    注意 LIBERO 的抽屉是 slide joint，因此这里找的是 SINGLE_DOF_TYPES
    （hinge + slide），而不是只找 hinge。
    """
    candidates = iter_single_dof_joints(model)
    exact = [j for j in candidates if j.name == name_or_prefix]
    if len(exact) == 1:
        return exact[0]
    prefixed = [j for j in candidates if j.name.startswith(name_or_prefix)]
    if len(prefixed) == 1:
        return prefixed[0]
    if not prefixed:
        raise KeyError(
            f"找不到关节 {name_or_prefix!r}。可用单自由度关节: {[j.name for j in candidates]}"
        )
    raise KeyError(
        f"关节 {name_or_prefix!r} 匹配到多个: {[j.name for j in prefixed]}，请给更精确的名字。"
    )


def get_joint_range(model: Any, joint_name_or_prefix: str) -> tuple[float, float]:
    """读取关节的活动范围 (lo, hi)。

    注意方向：LIBERO 的抽屉 range 是 [-0.16, 0.01]，**打开对应 -0.16**（负端）。
    因此调用方绝不能假定"开 = hi"，必须两端都试（见 StateBuilder）。
    """
    joint = resolve_single_dof_joint(model, joint_name_or_prefix)

    if not (hasattr(model, "jnt_range") and hasattr(model, "njnt")):
        raise TypeError("无法读取 jnt_range：model 缺少 jnt_range / njnt。")

    idx = None
    for i in range(int(model.njnt)):
        if joint_name(model, i) == joint.name:
            idx = i
            break
    if idx is None:
        raise KeyError(f"在 model.jnt_range 中定位不到关节 {joint.name!r}")

    rng = np.asarray(model.jnt_range).reshape(int(model.njnt), 2)[idx]
    lo, hi = float(rng[0]), float(rng[1])
    if lo == 0.0 and hi == 0.0:
        raise ValueError(
            f"关节 {joint.name!r} 的 range 为 (0, 0)，说明该关节 unlimited，"
            "不能用 jnt_range 推算开度上限。"
        )
    return lo, hi


def clear_object_velocity(
    state: Sequence[float] | np.ndarray,
    model: Any,
    name_or_prefix: str,
) -> np.ndarray:
    """把自由物体的线速度/角速度清零，避免传送后带着旧速度飞出去。"""
    joint = resolve_free_joint(model, name_or_prefix)
    layout = StateLayout.from_model(model)
    out = as_state_array(state).copy()
    if layout.nv > 0:
        qvel = out[layout.qvel_slice].copy()
        qvel[joint.dof_adr : joint.dof_adr + joint.dof_dim] = 0.0
        out[layout.qvel_slice] = qvel
    return out


def clear_all_velocities(state: Sequence[float] | np.ndarray, layout: StateLayout) -> np.ndarray:
    """把整个 qvel 清零。构造状态时最安全的做法。"""
    out = as_state_array(state).copy()
    if layout.nv > 0:
        out[layout.qvel_slice] = 0.0
    return out


# ---------------------------------------------------------------------------
# 几何：推算"放在目标上面"的 z
# ---------------------------------------------------------------------------


def geom_vertical_extent(
    model: Any,
    data: Any,
    body_id: int,
) -> tuple[float, float, float]:
    """返回某 body 所有几何体在世界系下的 (z_min, z_max, z_center)。

    ``data`` 需已执行过 ``mj_forward``，否则 ``geom_xpos`` 是陈旧值。
    """
    plane_type = geom_plane_type_id()
    zs: list[tuple[float, float]] = []
    ngeom = int(model.ngeom)
    for g in range(ngeom):
        if geom_bodyid(model, g) != int(body_id):
            continue
        if geom_type(model, g) == plane_type:  # 平面无界，跳过
            continue
        center_z = float(data.geom_xpos[g][2])
        rbound = geom_rbound(model, g)
        zs.append((center_z - rbound, center_z + rbound))

    if not zs:
        # 没有几何体信息时退化为使用 body 原点
        z = float(data.xpos[body_id][2])
        return z, z, z

    z_min = min(a for a, _ in zs)
    z_max = max(b for _, b in zs)
    return z_min, z_max, 0.5 * (z_min + z_max)


def all_body_names(model: Any) -> list[str]:
    """列出所有 body 名（带缓存）。"""
    if not hasattr(model, "nbody"):
        raise TypeError("model 没有 nbody，无法枚举 body。")
    _, bodies = _name_tables(model)
    return list(bodies)


def find_body_id(model: Any, name_or_prefix: str) -> int:
    """按名字/前缀解析唯一 body id。"""
    names = all_body_names(model)

    exact = [i for i, n in enumerate(names) if n == name_or_prefix]
    if len(exact) == 1:
        return exact[0]

    prefixed = [i for i, n in enumerate(names) if n.startswith(name_or_prefix)]
    if len(prefixed) == 1:
        return prefixed[0]

    # 前缀匹配到多个时，优先 ``<prefix>_main``。
    #
    # LIBERO 的 fixture 常有多个子 body（例如 flat_stove_1 下面有
    # _main / _base / _burner），前缀解析会歧义。``_main`` 是 LIBERO 里
    # 物体主体命名的通行约定，且它的几何范围覆盖整个物体，
    # 因此用它推算"顶面高度"最稳妥。这里做确定性收敛，
    # 而不是直接把歧义抛给调用方 —— 后者会让每个新任务都要手工试名字。
    main_name = f"{name_or_prefix}_main"
    main_idx = [i for i in prefixed if names[i] == main_name]
    if len(main_idx) == 1:
        return main_idx[0]

    if not prefixed:
        raise KeyError(f"找不到 body {name_or_prefix!r}")
    raise KeyError(
        f"body {name_or_prefix!r} 匹配到多个: {[names[i] for i in prefixed]}，"
        "且其中没有唯一的 `<prefix>_main`，请给更精确的名字。"
    )


def suggest_resting_z(
    model: Any,
    data: Any,
    subject: str,
    target: str,
    *,
    clearance: float = 0.002,
) -> tuple[float, float]:
    """推算把 ``subject`` 静置在 ``target`` 上方时应有的 z。

    返回 ``(z, target_top_z)``。

    做法：``subject`` 的底面（z_min）应当落在 ``target`` 的顶面（z_max）之上
    一点点。这里用的是**当前姿态下**的包围盒，因此调用前应先把物体摆正
    （或接受轻微误差，随后靠 settle 让物理收敛）。
    """
    subject_body = find_body_id(model, subject)
    target_body = find_body_id(model, target)

    s_min, s_max, s_c = geom_vertical_extent(model, data, subject_body)
    t_min, t_max, t_c = geom_vertical_extent(model, data, target_body)

    subject_half = 0.5 * (s_max - s_min)
    # 目标当前 z 中心 -> 把 subject 的中心抬到 target 顶面之上
    z = t_max + subject_half + clearance
    return float(z), float(t_max)


# ---------------------------------------------------------------------------
# 机器人关节的显式存取（§65.2 reset artifact 约束的执行手段）
# ---------------------------------------------------------------------------


def get_robot_qpos(state: Sequence[float] | np.ndarray, layout: StateLayout, n: int = 9) -> np.ndarray:
    """取前 n 个关节位置（LIBERO 里即 7 臂 + 2 夹爪）。"""
    return np.array(get_qpos(state, layout)[:n], dtype=np.float64)


def set_robot_qpos(
    state: Sequence[float] | np.ndarray,
    layout: StateLayout,
    robot_qpos: Sequence[float],
    n: int | None = None,
) -> np.ndarray:
    """把前 n 个关节位置强制写回指定值，其余（物体）保持不变。

    为什么需要"强制"而不是"不改动就行"
    ----------------------------------
    LIBERO 的机器人是位置控制的，``mj_step`` 期间手臂仍会因重力/PD 误差
    产生 ~1e-3 rad 量级的漂移，而且漂移量取决于跑了多少步。
    satisfied 与 unsatisfied 的 settle 步数不同，于是两条路径的机器人位姿
    会出现 1e-3~1e-2 rad 的差异 —— 虽然很小，但足以让
    ``verify_robot_joints_unchanged`` 判 False，并且给 UER 引入系统性偏差。

    所以正确做法是：把官方初始状态的机器人关节当作权威值，
    在构造完成后**显式写回**，使两种 condition 的机器人位姿逐位相同。
    """
    layout = layout
    robot_qpos = np.asarray(robot_qpos, dtype=np.float64).reshape(-1)
    if n is None:
        n = robot_qpos.shape[0]
    qpos = get_qpos(state, layout).copy()
    qpos[:n] = robot_qpos[:n]
    return with_qpos(state, layout, qpos)
