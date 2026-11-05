"""CPU-only abstraction of pinned LIBERO collision boxes, not physical proof."""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.microwave_candidates import microwave_candidates
from benchmark.states import mujoco_state as ms


# All 39 collision boxes from pinned 8f1084e... white_yellow_mug.xml, in
# (position, wxyz quaternion, half-size) order. Visual mesh is excluded.
MUG_BOXES = [
    ([0.06406, -0.0, 0.05598], [1.0, -0.0, -0.0, -0.0], [0.00412, 0.00876, 0.02924]),
    ([0.04022, 0.0, 0.02629], [0.63072, 0.0, -0.77601, 0.0], [0.00413, 0.00876, 0.02493]),
    ([0.04641, 0.0, 0.07965], [0.74473, -0.0, 0.66737, -0.0], [0.00411, 0.00876, 0.02172]),
    ([0.02428, -0.001, 0.05934], [0.99786, -0.0, 0.06541, -0.0], [0.00412, 0.00876, 0.04361]),
    ([0.02168, 0.01468, 0.05934], [0.01223, 0.98027, 0.18655, -0.06426], [0.00412, 0.00876, 0.04361]),
    ([0.01459, 0.02702, 0.05934], [0.02282, 0.93515, 0.34816, -0.0613], [0.00412, 0.00876, 0.04361]),
    ([0.00383, 0.03634, 0.05934], [0.05661, 0.49992, -0.8636, 0.03277], [0.00413, 0.00876, 0.04361]),
    ([-0.00868, 0.04141, 0.05934], [0.04134, 0.77326, 0.6307, -0.05069], [0.00412, 0.00876, 0.04361]),
    ([-0.02322, 0.04219, 0.05934], [0.04942, 0.65373, 0.7539, -0.04285], [0.00412, 0.00876, 0.04361]),
    ([-0.03613, 0.03851, 0.05934], [0.5264, -0.05557, 0.03451, 0.84772], [0.00412, 0.00876, 0.04361]),
    ([-0.04594, 0.03217, 0.05934], [0.05978, 0.40487, 0.91203, -0.02654], [0.00413, 0.00876, 0.04361]),
    ([-0.05444, 0.02216, 0.05934], [0.259, -0.06317, 0.01698, 0.96366], [0.00412, 0.00876, 0.04361]),
    ([-0.05951, 0.00987, 0.05934], [0.06505, 0.10512, 0.99231, -0.00689], [0.00412, 0.00876, 0.04361]),
    ([-0.06044, -0.0045, 0.05934], [0.06466, 0.06527, 0.00424, -0.99576], [0.00413, 0.00876, 0.04361]),
    ([-0.05654, -0.0183, 0.05934], [0.06362, -0.2317, 0.97059, 0.01519], [0.00412, 0.00876, 0.04361]),
    ([-0.04863, -0.02964, 0.05934], [0.38651, 0.0603, 0.02533, -0.91996], [0.00413, 0.00876, 0.04361]),
    ([-0.03703, -0.03808, 0.05934], [0.05516, -0.53632, 0.84148, 0.03516], [0.00412, 0.00876, 0.04361]),
    ([-0.0222, -0.0423, 0.05934], [0.68004, 0.04787, 0.04458, -0.73025], [0.00413, 0.00876, 0.04361]),
    ([-0.00773, -0.04118, 0.05934], [0.03955, -0.79478, 0.60337, 0.0521], [0.00412, 0.00876, 0.04361]),
    ([0.00471, -0.03578, 0.05934], [0.03072, -0.88092, 0.46872, 0.05775], [0.00412, 0.00876, 0.04361]),
    ([0.01547, -0.02593, 0.05934], [0.02035, -0.94832, 0.31051, 0.06216], [0.00412, 0.00876, 0.04361]),
    ([0.02184, -0.01422, 0.05934], [0.01035, -0.98528, 0.15795, 0.06459], [0.00412, 0.00876, 0.04361]),
    ([0.01284, -0.001, 0.0106], [0.95039, -0.0, 0.31107, -0.0], [0.00407, 0.00876, 0.01028]),
    ([0.00804, 0.01661, 0.0106], [0.0914, 0.90843, 0.27925, -0.29735], [0.00407, 0.00876, 0.01028]),
    ([-0.00359, 0.0274, 0.0106], [0.80691, -0.16435, 0.26412, 0.50212], [0.00407, 0.00876, 0.01028]),
    ([-0.02029, 0.03097, 0.0106], [0.63771, -0.23063, 0.20873, 0.70468], [0.00407, 0.00876, 0.01028]),
    ([-0.034, 0.02672, 0.0106], [0.14973, 0.83305, -0.45745, 0.27267], [0.00407, 0.00876, 0.01028]),
    ([-0.04548, 0.0148, 0.0106], [0.21896, -0.30271, 0.07166, 0.92482], [0.00407, 0.00876, 0.01028]),
    ([-0.04922, -0.0011, 0.0106], [0.01047, -0.94985, -0.032, -0.3109], [0.00407, 0.00876, 0.01028]),
    ([-0.04438, -0.01667, 0.0106], [0.28029, 0.29724, 0.09175, -0.90811], [0.00407, 0.00876, 0.01028]),
    ([-0.03258, -0.02751, 0.0106], [0.26346, -0.50529, 0.80493, 0.16539], [0.00407, 0.00876, 0.01028]),
    ([-0.0177, -0.03104, 0.0106], [0.21464, -0.68791, 0.65575, 0.22518], [0.00407, 0.00876, 0.01028]),
    ([-0.00302, -0.02709, 0.0106], [0.82754, 0.15297, 0.27086, -0.46735], [0.00407, 0.00876, 0.01028]),
    ([0.00801, -0.01666, 0.0106], [0.91668, 0.08211, 0.30004, -0.25086], [0.00407, 0.00876, 0.01028]),
    ([-0.01819, -0.0, 0.00274], [0.5, 0.5, -0.5, 0.5], [0.0025, 0.01861, 0.01861]),
    ([-0.01819, -0.0221, 0.00274], [0.70711, 0.0, 0.70711, 0.0], [0.0025, 0.00383, 0.01861]),
    ([-0.01819, 0.0221, 0.00274], [0.70711, 0.0, 0.70711, 0.0], [0.0025, 0.00383, 0.01861]),
    ([-0.0412, -0.0, 0.00274], [0.50359, -0.49638, 0.5036, 0.49638], [0.0025, 0.00383, 0.0186]),
    ([0.0046, -0.0, 0.00274], [0.50359, -0.49638, 0.5036, 0.49638], [0.0025, 0.00383, 0.0186]),
]


def rotation(q):
    w, x, y, z = np.asarray(q) / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def corners(position, quat, half):
    return np.asarray(list(product((-1., 1.), repeat=3))) * half @ rotation(quat).T + position


class Model(SimpleNamespace):
    def site_name2id(self, name):
        return self.site_names.index(name)


@pytest.fixture
def microwave():
    # Actual shell boxes and heating_region; door is open at its unchanged hinge.
    shell = [([-.158, .0115, .0935], [.0145, .09955, .0935]),
             ([.118, .0115, .0935], [.0545, .09955, .0935]),
             ([-.0405, .0955, .0935], [.1035, .015, .0935]),
             ([-.04, -.0035, .1775], [.1035, .0845, .0095]),
             ([-.04, -.004, .012], [.1035, .084, .012]),
             ([.13, -.0985, .0935], [.0425, .012, .0935])]
    base_quat = np.array([np.cos(.2), 0., np.sin(.2), 0.])
    qpos = np.r_[.37, -1.5, -.4, .3, .2, base_quat]
    door_rotation = rotation([np.cos(-.75), 0., 0., np.sin(-.75)])
    door_origin = np.array([-.1725, -.088, .096])
    door_center = door_origin + door_rotation @ [.1295, -.013, 0.]
    positions = [p for p, _ in shell] + [door_center.tolist()]
    matrices = [np.eye(3)] * 6 + [door_rotation]
    sizes = [s for _, s in shell] + [[.1295, .012, .0925]]
    # The three real door-handle collision capsules also remain obstacles.
    handle_rotation = rotation([np.cos(1.57/2), np.sin(1.57/2), 0., 0.])
    for position, axes, size in [([.2375, -.054, 0.], np.eye(3), [.01, .065, 0.]),
                               ([.2375, -.0375, .065], handle_rotation, [.01, .015, 0.]),
                               ([.2375, -.0375, -.065], handle_rotation, [.01, .015, 0.])]:
        positions.append(door_origin + door_rotation @ position)
        matrices.append(door_rotation @ axes)
        sizes.append(size)
    for p, q, s in MUG_BOXES:
        positions.append(qpos[2:5] + rotation(base_quat) @ p)
        matrices.append(rotation(base_quat) @ rotation(q))
        sizes.append(s)
    model = Model(nq=9, nv=8, na=1, njnt=3, nbody=5, nsite=1, ngeom=len(sizes),
        joint_names=['robot0_joint', 'microwave_1_microjoint', 'white_yellow_mug_1_joint'],
        body_names=['world', 'robot', 'microwave_1_main', 'microwave_1_door', 'white_yellow_mug_1_main'],
        jnt_type=np.array([3, 3, 0]), jnt_qposadr=np.array([0, 1, 2]),
        jnt_dofadr=np.array([0, 1, 2]), jnt_bodyid=np.array([1, 3, 4]),
        body_parentid=np.array([0, 0, 0, 2, 0]),
        geom_bodyid=np.array([2]*6 + [3]*4 + [4]*len(MUG_BOXES)),
        geom_type=np.array([6]*7 + [3]*3 + [6]*len(MUG_BOXES)), geom_size=np.array(sizes),
        geom_contype=np.array([0]*10 + [1]*len(MUG_BOXES)),
        geom_conaffinity=np.ones(len(sizes), dtype=int),
        geom_margin=np.array([.001]*10 + [0.]*len(MUG_BOXES)),
        site_names=['microwave_1_heating_region'], site_type=np.array([6]),
        site_bodyid=np.array([2]), site_size=np.array([[.12, .0835, .08]]))
    body_matrices = np.tile(np.eye(3), (5, 1, 1))
    body_matrices[3], body_matrices[4] = door_rotation, rotation(base_quat)
    data = SimpleNamespace(qpos=qpos.copy(), geom_xpos=np.array(positions),
        geom_xmat=np.array(matrices).reshape(-1, 9),
        body_xpos=np.array([[0., 0., 0.], [1., 1., 1.], [0., 0., 0.], door_origin, qpos[2:5]]),
        body_xmat=body_matrices.reshape(-1, 9),
        site_xpos=np.array([[0., .01, .096]]), site_xmat=np.eye(3).reshape(1, 9))
    base = np.r_[2.5, qpos, np.arange(8)/100 + .01, .91]
    return model, data, base


def candidate_vertices(candidate):
    pose = candidate['state'][3:10]
    local = np.concatenate([corners(np.array(p), q, np.array(s)) for p, q, s in MUG_BOXES])
    return local @ rotation(pose[3:]).T + pose[:3]


def test_actual_collision_boxes_fit_support_and_volume_with_four_interleaved_poses(microwave):
    model, data, base = microwave
    result = microwave_candidates(base, model, data)
    assert len(result) == 24
    assert [c['diagnostics']['pose_index'] for c in result[:4]] == [0, 1, 2, 3]
    assert len(MUG_BOXES) == 39
    for candidate in result:
        diag = candidate['diagnostics']
        assert diag['method'] == 'microwave_gravity_support_pose_transplant_v3'
        assert diag['physics_validated'] is False
        assert diag['predicate_verified'] is False
        assert diag['support_geom_id'] == 4
        assert diag['support_margin'] == .001
        assert len(diag['bottom_geom_ids']) == 5
        # The slightly tilted edge boxes extend below the central flat bottom.
        assert diag['object_bottom_offset'] == pytest.approx(-.0000972932738408)
        assert len(diag['obstacle_aabb_clearances']) == 9
        vertices = candidate_vertices(candidate)
        assert vertices[:, 0].min() >= -.1435 + .001 - 1e-12
        assert vertices[:, 0].max() <= .0635 - .001 + 1e-12
        assert vertices[:, 1].min() >= -.088 + .001 - 1e-12
        assert vertices[:, 1].max() <= .08 - .001 + 1e-12
        assert vertices[:, 2].min() == pytest.approx(.024 + .002)
        assert np.all(np.abs(vertices-data.site_xpos[0]) <= model.site_size[0]-.001+1e-12)
        np.testing.assert_allclose(rotation(candidate['state'][6:10])[:, 2], [0, 0, 1], atol=1e-12)
        np.testing.assert_allclose(candidate['placements'][0]['aabb_min'], vertices.min(axis=0))
        np.testing.assert_allclose(candidate['placements'][0]['aabb_max'], vertices.max(axis=0))
        assert diag['minimum_obstacle_aabb_clearance'] >= .001 - 1e-12


def test_orientation_recomputes_all_39_box_bounds_instead_of_old_tilted_aabb(microwave):
    model, data, base = microwave
    result = microwave_candidates(base, model, data)
    first, second = result[:2]
    extent0 = np.ptp(candidate_vertices(first), axis=0)
    extent1 = np.ptp(candidate_vertices(second), axis=0)
    np.testing.assert_allclose(extent0[:2], extent1[1::-1], atol=1e-12)
    assert abs(extent0[0] - extent0[1]) > .03
    assert first['state'][5] != pytest.approx(base[5])
    for candidate in result:
        np.testing.assert_allclose(candidate['diagnostics']['collision_world_extent'],
                                   np.ptp(candidate_vertices(candidate), axis=0))


def test_only_A_seven_qpos_change_all_qvel_and_inputs_are_bitwise_preserved(microwave):
    model, data, base = microwave
    before_base, before_data, before_model = base.copy(), deepcopy(vars(data)), deepcopy(vars(model))
    result = microwave_candidates(base, model, data)
    for candidate in result:
        assert candidate['allowed_indices'] == list(range(3, 10)) + list(range(12, 18))
        assert candidate['edited_joints'] == ['white_yellow_mug_1_joint']
        protected = list(range(3)) + list(range(10, len(base)))
        np.testing.assert_array_equal(candidate['state'][protected], base[protected])
        assert candidate['diagnostics']['seed_velocity_preserved'] is True
    np.testing.assert_array_equal(base, before_base)
    for name, value in before_data.items():
        np.testing.assert_array_equal(getattr(data, name), value)
    for name, value in before_model.items():
        np.testing.assert_array_equal(getattr(model, name), value)


@pytest.mark.parametrize('change', ['wall_cap', 'too_narrow', 'blocked_door', 'unknown_mug'])
def test_fail_closed_on_wrong_support_unknown_collision_or_no_clear_volume(microwave, change):
    model, data, base = microwave
    if change == 'wall_cap':
        model.geom_size[4] = [.012, .084, .1035]
        with pytest.raises(ValueError, match='floor'):
            microwave_candidates(base, model, data)
    elif change == 'unknown_mug':
        model.geom_type[-1] = 7
        with pytest.raises(ValueError, match='box'):
            microwave_candidates(base, model, data)
    else:
        if change == 'too_narrow':
            model.site_size[0, 0] = .02
        else:
            data.geom_xpos[6] = [-.04, -.004, .07]
            data.geom_xmat[6] = np.eye(3).ravel()
            model.geom_size[6] = [.1035, .084, .07]
        assert microwave_candidates(base, model, data) == []


def test_candidate_limit_is_bounded_and_mismatched_data_is_rejected(microwave):
    model, data, base = microwave
    assert len(microwave_candidates(base, model, data, max_candidates=5)) == 5
    assert len(microwave_candidates(base, model, data, max_candidates=100)) == 24
    data.qpos[0] += .1
    with pytest.raises(ValueError, match='data.qpos'):
        microwave_candidates(base, model, data)


def test_translated_yawed_support_and_independently_oriented_region_remain_correct(microwave):
    model, data, base = microwave
    yaw = rotation([np.cos(np.pi/4), 0., 0., np.sin(np.pi/4)])
    shift = np.array([.3, -.2, .8])
    for geom in range(10):
        data.geom_xpos[geom] = yaw @ data.geom_xpos[geom] + shift
        data.geom_xmat[geom] = (yaw @ data.geom_xmat[geom].reshape(3, 3)).ravel()
    for body in (2, 3):
        data.body_xpos[body] = yaw @ data.body_xpos[body] + shift
        data.body_xmat[body] = (yaw @ data.body_xmat[body].reshape(3, 3)).ravel()
    # Same physical volume with site axes permuted by 90deg: In membership
    # axes are not automatically reinterpreted as a support/gravity normal.
    site_axes = np.array([[0., 0., 1.], [0., 1., 0.], [-1., 0., 0.]])
    data.site_xpos[0] = yaw @ data.site_xpos[0] + shift
    data.site_xmat[0] = (yaw @ site_axes).ravel()
    model.site_size[0] = model.site_size[0, [2, 1, 0]]
    result = microwave_candidates(base, model, data)
    assert len(result) == 24
    for candidate in result:
        vertices = candidate_vertices(candidate)
        local = (vertices - data.site_xpos[0]) @ data.site_xmat[0].reshape(3, 3)
        assert np.all(np.abs(local) <= model.site_size[0]-.001+1e-12)
        assert vertices[:, 2].min() == pytest.approx(.024 + .002 + shift[2])
        assert candidate['diagnostics']['support_geom_id'] == 4
