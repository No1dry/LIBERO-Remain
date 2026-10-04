"""Pure state-construction checks; these do not establish LIBERO physics validity."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.remaining_goals.construction import (
    _fair_candidate_product,
    combine_goal_candidates,
    joint_candidates,
    object_support_geometry,
    placement_candidates,
    region_geometry,
    state_diff_whitelist,
)
from benchmark.states import mujoco_state as ms


class Model(SimpleNamespace):
    def site_name2id(self, name):
        return self.site_names.index(name) if name in self.site_names else -1


@pytest.fixture
def scene():
    model = Model(
        nq=24, nv=21, na=1, njnt=6, nbody=11, ngeom=8, nsite=2,
        joint_names=["robot0_joint", "gripper0_joint", "stove_button", "a_joint", "b_joint", "c_joint"],
        body_names=["world", "robot", "gripper", "stove", "burner", "button", "basket", "a", "a_child", "b", "c"],
        jnt_type=np.array([3, 2, 3, 0, 0, 0]),
        jnt_qposadr=np.array([0, 1, 2, 3, 10, 17]),
        jnt_dofadr=np.array([0, 1, 2, 3, 9, 15]),
        jnt_bodyid=np.array([1, 2, 5, 7, 9, 10]),
        jnt_limited=np.array([1, 1, 1, 0, 0, 0]),
        jnt_range=np.array([[-1., 1.], [0., .04], [-.005, 2.1], [0., 0.], [0., 0.], [0., 0.]]),
        body_parentid=np.array([0, 0, 1, 0, 3, 3, 0, 0, 7, 0, 0]),
        # Basket floor, wall, visual mesh; burner base/top; button; a and b.
        geom_bodyid=np.array([6, 6, 6, 4, 4, 5, 7, 9]),
        geom_type=np.array([6, 6, 7, 6, 6, 6, 6, 5]),
        geom_contype=np.array([1, 1, 0, 1, 1, 1, 1, 1]),
        geom_conaffinity=np.array([1, 1, 0, 1, 1, 1, 1, 1]),
        geom_size=np.array([[.08, .08, .01], [.08, .01, .08], [9., 9., 9.],
                            [.095, .095, .02], [.095, .095, .0005], [.2, .2, .2],
                            [.022, .024, .04], [.033, .04, 0.]]),
        site_names=["basket_contain_region", "stove_cook_region"],
        site_type=np.array([6, 6]), site_bodyid=np.array([6, 4]),
        site_size=np.array([[.06108, .06108, .06949], [.075, .075, .0025]]),
    )
    qpos = np.array([.12, .025, -.002,
                     -.2, 0., .1, 1., 0., 0., 0.,
                     -.4, .1, .13, 1., 0., 0., 0.,
                     -.5, .4, .15, 1., 0., 0., 0.])
    base = np.r_[1.25, qpos, np.arange(model.nv) / 100 + .01, .91]
    data = SimpleNamespace(
        qpos=qpos.copy(),
        geom_xpos=np.array([[.5, .1, .03], [.5, .18, .11], [.5, .1, .1],
                            [1., 0., .8], [1., 0., .825], [1., 0., 1.3],
                            [-.2, 0., .11], [-.4, .1, .15]]),
        geom_xmat=np.tile(np.eye(3).reshape(1, 9), (model.ngeom, 1)),
        site_xpos=np.array([[.5, .1, .1], [1., 0., .8]]),
        site_xmat=np.tile(np.eye(3).reshape(1, 9), (model.nsite, 1)),
    )
    return model, data, base


def placements(scene, name="a", **kwargs):
    model, data, base = scene
    return placement_candidates(base, model, data, name, "basket_contain_region", **kwargs)


def test_candidates_are_pure_and_explicitly_unvalidated(scene):
    model, data, base = scene
    old_base, old_data = base.copy(), deepcopy(data)
    result = placements(scene)
    assert len(result) == 24
    np.testing.assert_array_equal(base, old_base)
    for key, value in vars(data).items():
        np.testing.assert_array_equal(value, getattr(old_data, key))
    for candidate in result:
        assert candidate["diagnostics"]["status"] == "candidate"
        assert candidate["diagnostics"]["physics_validated"] is False
        assert candidate["diagnostics"]["predicate_verified"] is False
        assert candidate["diagnostics"]["diff"]["valid"] is True
        assert candidate["allowed_indices"] == [4, 5, 6, 7, 8, 9, 10, 28, 29, 30, 31, 32, 33]
        # Whitelist permits only this object's settled full pose and velocity.
        # Candidate seeds themselves still preserve the original quaternion.
        np.testing.assert_array_equal(candidate["state"][7:11], base[7:11])
        assert candidate["diagnostics"]["seed_orientation_preserved"] is True
        protected = sorted(set(range(len(base))) - set(candidate["allowed_indices"]))
        np.testing.assert_array_equal(candidate["state"][protected], base[protected])
        np.testing.assert_array_equal(candidate["state"][28:34], 0.)
    result[0]["state"][4] += 1.
    assert result[0]["state"][4] != result[1]["state"][4]


def test_support_height_uses_bottom_offset_and_excludes_basket_walls(scene):
    candidate = placements(scene, clearances=[.002])[0]
    np.testing.assert_allclose(candidate["placements"][0]["position"], [.5, .1, .072])
    assert candidate["diagnostics"]["object_bottom_offset"] == pytest.approx(-.03)
    assert candidate["diagnostics"]["support_world_z"] == pytest.approx(.04)


def test_stove_collision_top_not_site_center_or_unrelated_knob(scene):
    model, data, base = scene
    candidate = placement_candidates(base, model, data, "a", "stove_cook_region",
                                     relation="on", clearances=[.002])[0]
    np.testing.assert_allclose(candidate["placements"][0]["position"], [1., 0., .8575])
    assert candidate["diagnostics"]["support_world_z"] == pytest.approx(.8255)


def test_on_allows_overhanging_geometry_but_in_does_not_expand_container(scene):
    model, data, base = scene
    model.geom_size[6, :2] = [.18, .12]  # Long handle / broad pan overhangs support.
    assert placement_candidates(base, model, data, "a", "basket_contain_region", relation="in") == []
    candidate = placement_candidates(base, model, data, "a", "stove_cook_region", relation="on")[0]
    assert candidate["diagnostics"]["origin_only_search"]
    assert not candidate["diagnostics"]["full_collision_footprint_contained"]
    assert candidate["diagnostics"]["physics_validated"] is False
    np.testing.assert_allclose(candidate["placements"][0]["position"][:2], data.site_xpos[1, :2])


def test_object_support_uses_actual_collision_top_and_preserves_support_state(scene):
    model, data, base = scene
    data.body_xmat = np.tile(np.eye(3).ravel(), (model.nbody, 1))
    model.geom_size[7] = [.09, .01, 0.]  # A thin round plate represented by b.
    before = base.copy()
    candidates = placement_candidates(base, model, data, "a", "b", relation="on", target_kind="object")
    assert candidates
    candidate = candidates[0]
    assert candidate["placements"][0]["region"] == "b"  # No fabricated region site.
    assert candidate["placements"][0]["target_kind"] == "object"
    assert candidate["diagnostics"]["support_world_z"] == pytest.approx(.16)
    np.testing.assert_allclose(candidate["placements"][0]["position"], [-.4, .1, .192])
    for item in candidates:
        assert np.linalg.norm(np.asarray(item["placements"][0]["position"])[:2] - base[11:13]) < .03
        support_indices = list(range(11, 18)) + list(range(34, 40))
        np.testing.assert_array_equal(item["state"][support_indices], base[support_indices])
    np.testing.assert_array_equal(base, before)


def test_object_support_rejects_inverted_support_and_unsupported_relation(scene):
    model, data, base = scene
    data.body_xmat = np.tile(np.eye(3).ravel(), (model.nbody, 1))
    data.body_xmat[9] = np.diag([1., -1., -1.]).ravel()
    with pytest.raises(ValueError, match="tilted/inverted object supports"):
        object_support_geometry(base, model, data, "b")
    with pytest.raises(ValueError, match="object targets require On"):
        placement_candidates(base, model, data, "a", "b", relation="in", target_kind="object")
    with pytest.raises(ValueError, match="itself"):
        placement_candidates(base, model, data, "a", "a", relation="on", target_kind="object")


def test_descendant_collision_geometry_contributes_to_object_height(scene):
    model, data, _ = scene
    model.geom_bodyid[6] = 8
    assert placements(scene)[0]["diagnostics"]["object_bottom_offset"] == pytest.approx(-.03)


def test_rotated_basket_floor_uses_vertical_half_extent_not_radius(scene):
    model, data, _ = scene
    # The official basket floor has its thin local x extent rotated onto world z.
    model.geom_size[0] = [.0085, .0724, .07658]
    data.geom_xmat[0] = np.array([[0., 0., 1.], [0., 1., 0.], [-1., 0., 0.]]).ravel()
    candidate = placements(scene, clearances=[.002])[0]
    assert candidate["diagnostics"]["support_world_z"] == pytest.approx(.0385)
    assert candidate["placements"][0]["position"][2] == pytest.approx(.0705)


def test_compiled_collision_mesh_bounds_ignore_visual_mesh(scene):
    model, _, _ = scene
    model.geom_type[6] = 7
    model.geom_dataid = np.array([-1, -1, -1, -1, -1, -1, 0, -1])
    model.mesh_vertadr = np.array([0])
    model.mesh_vertnum = np.array([8])
    model.mesh_vert = np.array([[x, y, z] for x in [-.02, .02]
                               for y in [-.025, .025] for z in [-.05, .05]])
    candidate = placements(scene, clearances=[.002])[0]
    assert candidate["diagnostics"]["object_bottom_offset"] == pytest.approx(-.04)
    assert candidate["placements"][0]["position"][2] == pytest.approx(.082)


def test_native_named_accessors_work_without_wrapper_arrays(scene):
    model, data, base = scene
    hidden = {"jnt_bodyid", "jnt_limited", "jnt_range", "body_parentid",
              "geom_bodyid", "geom_type", "geom_contype", "geom_conaffinity", "geom_size",
              "site_type", "site_size", "site_bodyid"}
    native = SimpleNamespace(**{name: value for name, value in vars(model).items() if name not in hidden})
    native.body = lambda index: SimpleNamespace(parentid=model.body_parentid[index])
    native.joint = lambda index: SimpleNamespace(bodyid=model.jnt_bodyid[index],
                                                limited=model.jnt_limited[index], range=model.jnt_range[index])
    native.geom = lambda index: SimpleNamespace(**{name[5:]: getattr(model, name)[index]
                                                   for name in hidden if name.startswith("geom_")})

    def site(index):
        index = model.site_name2id(index) if isinstance(index, str) else index
        return SimpleNamespace(id=index, type=model.site_type[index], size=model.site_size[index],
                               bodyid=model.site_bodyid[index])

    native.site = site
    original = placements(scene)[0]
    result = placement_candidates(base, native, data, "a", "basket_contain_region")[0]
    np.testing.assert_array_equal(original["state"], result["state"])
    np.testing.assert_array_equal(joint_candidates(base, model, "stove")[0]["state"],
                                  joint_candidates(base, native, "stove")[0]["state"])


def test_yaw_rotated_region_preserves_world_orientation(scene):
    model, data, base = scene
    rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    data.site_xmat[0] = rotation.ravel()
    candidate = placements(scene, reservation_objects=["a", "b"], clearances=[.002])[0]
    local = candidate["diagnostics"]["candidate_local_origin"]
    np.testing.assert_allclose(candidate["placements"][0]["position"], data.site_xpos[0] + rotation @ local)
    np.testing.assert_array_equal(candidate["state"][7:11], base[7:11])
    np.testing.assert_allclose(local[:2], [.03608, .03808])


def test_real_settled_basket_tilt_uses_full_frame_and_keeps_object_orientation(scene):
    model, data, base = scene
    # Basket wxyz from the real basket_s000_00/base audit. The quaternion is
    # normalized here only to construct the synthetic site's rotation matrix.
    quat = np.array([.7071047489484427, -.001694990886756773,
                     .0016949888166217914, .7071047503965487])
    w, x, y, z = quat / np.linalg.norm(quat)
    rotation = np.array([
        [1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
        [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
        [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)],
    ])
    center = data.site_xpos[0].copy()
    data.site_xmat[0] = rotation.ravel()
    # Rotate only basket collision geometry, leaving the placed object upright.
    for geom in (0, 1, 2):
        data.geom_xpos[geom] = center + rotation @ (data.geom_xpos[geom] - center)
        data.geom_xmat[geom] = rotation.ravel()
    candidate = placements(scene, reservation_objects=["a", "b"], clearances=[.002])[0]
    diagnostics = candidate["diagnostics"]
    assert np.rad2deg(diagnostics["region_tilt_rad"]) == pytest.approx(.275, abs=.001)
    assert diagnostics["region_tilt_limit_rad"] == pytest.approx(np.deg2rad(5.))
    assert diagnostics["gravity_settle_required"] is True
    assert diagnostics["physics_validated"] is False
    assert diagnostics["predicate_verified"] is False
    # Independently bound all box corners in the measured basket frame.
    corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    corners = corners * model.geom_size[6] + data.geom_xpos[6] - base[4:7]
    local_corners = corners @ rotation
    top, bottom = local_corners.max(axis=0), local_corners.min(axis=0)
    xy = model.site_size[0, :2] - .001 - top[:2]
    expected_local = np.r_[xy, -.06 - bottom[2] + .002]
    expected_support = center + rotation @ np.r_[xy, -.06]
    np.testing.assert_allclose(diagnostics["candidate_local_origin"], expected_local, atol=1e-12)
    np.testing.assert_allclose(candidate["placements"][0]["position"], center + rotation @ expected_local)
    np.testing.assert_allclose(diagnostics["support_world_position"], expected_support)
    assert diagnostics["support_world_z"] == pytest.approx(expected_support[2])
    assert abs(expected_support[2] - (center[2] - .06)) > 1e-5
    np.testing.assert_array_equal(candidate["state"][7:11], base[7:11])


@pytest.mark.parametrize("degrees", [0., 5.])
def test_region_tilt_limit_is_inclusive(scene, degrees):
    model, data, _ = scene
    angle = np.deg2rad(degrees)
    c, s = np.cos(angle), np.sin(angle)
    data.site_xmat[0] = np.array([[1., 0., 0.], [0., c, -s], [0., s, c]]).ravel()
    region = region_geometry(model, data, "basket_contain_region")
    assert region["region_tilt_rad"] == pytest.approx(angle)
    assert region["region_tilt_limit_rad"] == pytest.approx(np.deg2rad(5.))


@pytest.mark.parametrize("degrees", [5.0001, 20., 90., 180.])
def test_region_tilt_above_five_degrees_fails_before_candidate_search(scene, degrees):
    _, data, _ = scene
    angle = np.deg2rad(degrees)
    c, s = np.cos(angle), np.sin(angle)
    data.site_xmat[0] = np.array([[1., 0., 0.], [0., c, -s], [0., s, c]]).ravel()
    with pytest.raises(ValueError, match="tilted/inverted.*region_tilt_rad=.*region_tilt_limit_rad="):
        placements(scene)


def test_four_masks_use_same_base_and_reserved_slots(scene):
    model, _, base = scene
    a = placements(scene, reservation_objects=["a", "b"], clearances=[.002])
    b = placements(scene, "b", reservation_objects=["a", "b"], clearances=[.002])
    outputs = {mask: combine_goal_candidates(base, model, [a, b], list(mask))
               for mask in [(False, False), (True, False), (False, True), (True, True)]}
    zero = outputs[(False, False)]
    assert len(zero) == 1 and zero[0]["allowed_indices"] == []
    np.testing.assert_array_equal(zero[0]["state"], base)
    assert zero[0]["state"] is not base
    both = outputs[(True, True)][0]
    assert len(both["placements"]) == 2
    for goal, single_mask in [(0, (True, False)), (1, (False, True))]:
        np.testing.assert_array_equal(both["placements"][goal]["position"],
                                      outputs[single_mask][0]["placements"][0]["position"])
    assert both["diagnostics"]["placement_pairs"][0]["horizontal_center_distance"] > .08
    for candidates in outputs.values():
        for candidate in candidates:
            assert candidate["diagnostics"]["diff"]["valid"]
            assert candidate["diagnostics"]["base_state_sha256"] == a[0]["diagnostics"]["base_state_sha256"]


def test_diagonal_cylinder_aabb_overlap_is_not_called_physical_collision(scene):
    model, _, base = scene
    model.geom_type[6] = 5
    model.geom_size[6] = [.033, .04, 0.]
    a = placements(scene, reservation_objects=["a", "b"], clearances=[.002])
    b = placements(scene, "b", reservation_objects=["a", "b"], clearances=[.002])
    combined = combine_goal_candidates(base, model, [a, b], [True, True])
    pair = combined[0]["diagnostics"]["placement_pairs"][0]
    assert pair["horizontal_center_distance"] > .066
    assert pair["aabb_overlap"] is True
    assert pair["actual_contacts_checked"] is False


def test_shared_region_requires_matching_reservation_plan(scene):
    model, _, base = scene
    a = placements(scene, reservation_objects=["a", "b"], clearances=[.002])
    b = placements(scene, "b", reservation_objects=["a", "b"], clearances=[.002])
    assert combine_goal_candidates(base, model, [[a[0]], [b[1]]], [True, True]) == []
    assert combine_goal_candidates(base, model, [[a[0]], [b[0]]], [True, True])
    # Independent center placements cannot masquerade as a reserved multi-object layout.
    assert combine_goal_candidates(base, model, [placements(scene), placements(scene, "b")],
                                   [True, True]) == []


def test_combining_stove_and_moka_edits_preserves_unselected_coordinates(scene):
    model, data, base = scene
    knob = joint_candidates(base, model, "stove")
    moka = placement_candidates(base, model, data, "a", "stove_cook_region", relation="on")
    candidates = combine_goal_candidates(base, model, [knob, moka], [True, True], max_candidates=7)
    assert len(candidates) == 7
    assert candidates[0]["edited_joints"] == ["stove_button", "a_joint"]
    assert candidates[0]["allowed_indices"] == [3, 4, 5, 6, 7, 8, 9, 10, 27, 28, 29, 30, 31, 32, 33]


def test_candidate_order_is_repeatable_and_cap_is_exact(scene):
    first, second = placements(scene, max_candidates=5), placements(scene, max_candidates=5)
    assert len(first) == len(second) == 5
    for a, b in zip(first, second):
        np.testing.assert_array_equal(a["state"], b["state"])
        assert a["diagnostics"] == b["diagnostics"]


def test_too_large_object_has_no_candidate(scene):
    model, _, _ = scene
    model.geom_size[6, 0] = .1
    assert placements(scene) == []


def test_no_interior_support_does_not_invent_plane(scene):
    model, data, _ = scene
    data.geom_xpos[0, 2] = .2
    assert placements(scene) == []


def test_all_candidate_root_positions_inside_region(scene):
    model, data, _ = scene
    for candidate in placements(scene, reservation_objects=["a", "b"]):
        local = np.array(candidate["diagnostics"]["candidate_local_origin"])
        assert np.all(np.abs(local) <= model.site_size[0] + 1e-12)
        assert candidate["placements"][0]["position"][2] > .04


def test_base_must_match_forwarded_data_qpos(scene):
    _, data, _ = scene
    data.qpos[0] += .01
    with pytest.raises(ValueError, match="differs from base_state"):
        placements(scene)


@pytest.mark.parametrize("mutation,match", [
    (lambda m, d: m.site_type.__setitem__(0, 2), "box region"),
    (lambda m, d: m.site_size.__setitem__((0, 0), 0.), "positive horizontal"),
    (lambda m, d: d.site_xmat.__setitem__(0, np.diag([1., -1., -1.]).ravel()), "tilted/inverted"),
    (lambda m, d: d.site_xmat.__setitem__((0, 0), 2.), "orthonormal"),
    (lambda m, d: m.geom_type.__setitem__(6, 1), "unsupported collision"),
    (lambda m, d: m.geom_contype.__setitem__(slice(None), 0) or m.geom_conaffinity.__setitem__(slice(None), 0), "no finite collision"),
])
def test_unsupported_geometry_fails_explicitly(scene, mutation, match):
    model, data, _ = scene
    mutation(model, data)
    with pytest.raises(ValueError, match=match):
        placements(scene)


def test_unknown_site_and_robot_edits_fail(scene):
    model, data, base = scene
    with pytest.raises(ValueError, match="unknown region"):
        region_geometry(model, data, "absent")
    with pytest.raises(ValueError, match="robot or gripper"):
        joint_candidates(base, model, "robot0_joint")
    with pytest.raises(ValueError, match="robot or gripper"):
        joint_candidates(base, model, "gripper0_joint")


@pytest.mark.parametrize("kwargs", [
    {"max_candidates": 0}, {"max_candidates": True}, {"max_candidates": 1.5},
    {"relation": "above"}, {"clearances": []}, {"clearances": [-.001]},
    {"clearances": [float("nan")]}, {"horizontal_margin": -1.},
    {"reservation_objects": []}, {"reservation_objects": ["a", "a"]},
])
def test_invalid_placement_requests_fail(scene, kwargs):
    with pytest.raises(ValueError):
        placements(scene, **kwargs)


def test_joint_search_covers_mechanical_interior_without_direction_guess(scene):
    model, _, base = scene
    model.jnt_range[2] = [-2., 1.]
    outputs = joint_candidates(base, model, "stove", sample_count=5)
    values = [item["diagnostics"]["chosen_value"] for item in outputs]
    assert values == [-.5, -1., 0., -1.5, .5]
    for item in outputs:
        assert item["allowed_indices"] == [3, 27]
        assert item["state"][27] == 0.
        assert item["diagnostics"]["opening_direction_assumed"] is False
        assert item["diagnostics"]["predicate_verified"] is False
        np.testing.assert_array_equal(np.delete(item["state"], [3, 27]), np.delete(base, [3, 27]))


def test_documented_negative_predicate_range_is_intersected(scene):
    model, _, base = scene
    model.jnt_range[2] = [-2., 1.]
    outputs = joint_candidates(base, model, "stove", predicate_range=[-3., -1.3],
                               predicate_range_source="official object.is_open", sample_count=3)
    assert len(outputs) == 3
    for item in outputs:
        assert -2. < item["state"][3] < -1.3
        assert item["diagnostics"]["sample_interval"] == [-2., -1.3]
        assert item["diagnostics"]["predicate_range"] == [-3., -1.3]


@pytest.mark.parametrize("kwargs,match", [
    ({"sample_count": 0}, "positive integer"),
    ({"predicate_range": [.5, 1.]}, "documented"),
    ({"predicate_range": [1., 0.], "predicate_range_source": "test"}, "strictly increasing"),
    ({"predicate_range": [-2., -1.], "predicate_range_source": "test"}, "no nonempty"),
])
def test_invalid_joint_requests_fail(scene, kwargs, match):
    model, _, base = scene
    with pytest.raises(ValueError, match=match):
        joint_candidates(base, model, "stove", **kwargs)


@pytest.mark.parametrize("limited,limits", [(0, [-1., 1.]), (1, [0., 0.]), (1, [1., -1.]), (1, [0., float("inf")])])
def test_unbounded_or_invalid_joint_range_fails(scene, limited, limits):
    model, _, base = scene
    model.jnt_limited[2] = limited
    model.jnt_range[2] = limits
    with pytest.raises(ValueError):
        joint_candidates(base, model, "stove")


def test_composition_rejects_different_base_conflicting_whitelists_and_hidden_edits(scene):
    model, _, base = scene
    a = placements(scene)
    other_base = base.copy()
    other_base[0] += .1
    foreign = joint_candidates(other_base, model, "stove")
    with pytest.raises(ValueError, match="different base"):
        combine_goal_candidates(base, model, [foreign], [True])
    with pytest.raises(ValueError, match="overlapping state whitelists"):
        combine_goal_candidates(base, model, [[a[0]], [a[1]]], [True, True])
    corrupted = deepcopy(a[0])
    corrupted["state"][1] += .01
    with pytest.raises(ValueError, match="unexpected state edit"):
        combine_goal_candidates(base, model, [[corrupted]], [True])


@pytest.mark.parametrize("mask", [[1, 0], [True], [], [True, False, True], "10"])
def test_composition_requires_exact_boolean_mask(scene, mask):
    model, _, base = scene
    with pytest.raises(ValueError, match="one boolean per goal"):
        combine_goal_candidates(base, model, [[], []], mask)


def test_empty_selected_candidate_set_remains_empty(scene):
    model, _, base = scene
    assert combine_goal_candidates(base, model, [[], []], [True, False]) == []


@pytest.mark.parametrize("lengths", [(9, 24), (24, 9), (2, 3, 4), (1, 3), (4,), ()])
def test_fair_product_is_complete_unique_and_covers_each_component_in_first_diagonal(lengths):
    import itertools

    lists = [list(range(length)) for length in lengths]
    result = list(_fair_candidate_product(lists))
    assert len(result) == len(set(result))
    assert set(result) == set(itertools.product(*lists))
    assert result == list(_fair_candidate_product(lists))
    if lengths:
        first = result[:max(lengths)]
        for index, length in enumerate(lengths):
            assert {indices[index] for indices in first} == set(range(length))


def test_joint_plus_placement_budget_covers_all_nine_joint_values(scene):
    model, _, base = scene
    articulations = joint_candidates(base, model, "stove", sample_count=9)
    positions = placements(scene, max_candidates=24)
    combined = combine_goal_candidates(base, model, [articulations, positions], [True, True], max_candidates=24)
    assert len(combined) == 24
    searched_values = {item["diagnostics"]["goal_edits"][0]["chosen_value"] for item in combined}
    assert searched_values == {item["diagnostics"]["chosen_value"] for item in articulations}
    assert all(item["diagnostics"]["diff"]["valid"] for item in combined)


def test_settled_target_quaternions_are_matched_exactly_without_copying_other_bodies(scene):
    from benchmark.remaining_goals.build import _matched_states

    model, data, base = scene
    a = placement_candidates(base, model, data, "a", "basket_contain_region", reservation_objects=["a", "b"])
    b = placement_candidates(base, model, data, "b", "basket_contain_region", reservation_objects=["a", "b"])
    candidate = combine_goal_candidates(base, model, [a, b], [True, True])[0]
    settled = candidate["state"].copy()
    settled[7:11] = [np.cos(.1), np.sin(.1), 0., 0.]
    settled[14:18] = [np.cos(.2), 0., np.sin(.2), 0.]
    settled[28:40] = np.arange(12) * .0001
    # Settling can move the robot or another object/support; these coordinates
    # must never leak into any matched start through the target's whitelist.
    settled[1] += .001
    settled[18:25] += .001
    matched, components = _matched_states(base, settled, model, [a, b], candidate)
    for bits, item in matched.items():
        for goal, quat_slice in enumerate((slice(7, 11), slice(14, 18))):
            expected = settled if bits[goal] == "1" else base
            np.testing.assert_array_equal(item["state"][quat_slice], expected[quat_slice])
        np.testing.assert_array_equal(item["state"][18:25], base[18:25])
        assert item["state"][1] == base[1]
    assert set(range(7, 11)).issubset(components[0]["indices"])
    assert set(range(14, 18)).issubset(components[1]["indices"])


def test_exact_diff_identifies_time_robot_act_and_quaternion_edits(scene):
    model, _, base = scene
    edited = base.copy()
    edited[[0, 1, 7, -1]] += .5
    diff = state_diff_whitelist(base, edited, model, [7])
    assert diff["valid"] is False
    assert diff["unexpected_indices"] == [0, 1, len(base) - 1]
    assert [entry["name"] for entry in diff["changed"]] == ["time", "robot0_joint[0]", "a_joint[3]", "act[0]"]


def test_diff_handles_ball_joint_qpos_and_qvel_dimensions():
    model = Model(nq=4, nv=3, na=1, njnt=1, nbody=1, joint_names=["ball"], body_names=["world"],
                  jnt_type=np.array([1]), jnt_qposadr=np.array([0]), jnt_dofadr=np.array([0]))
    base, edited = np.zeros(9), np.zeros(9)
    edited[[4, 7, 8]] = 1.
    audit = state_diff_whitelist(base, edited, model, [4, 7])
    assert audit["unexpected_indices"] == [8]
    assert [change["name"] for change in audit["changed"]] == ["ball[3]", "ball[2]", "act[0]"]
    assert [change["segment"] for change in audit["changed"]] == ["qpos", "qvel", "act"]


@pytest.mark.parametrize("indices", [[True], [-1], [999], [1.5]])
def test_invalid_whitelist_indices_fail(scene, indices):
    model, _, base = scene
    with pytest.raises(ValueError, match="valid integer"):
        state_diff_whitelist(base, base, model, indices)


@pytest.mark.parametrize("mutation", [lambda x: x[:-1], lambda x: np.where(np.arange(len(x)) == 0, np.nan, x)])
def test_malformed_states_are_not_accepted(scene, mutation):
    model, _, base = scene
    with pytest.raises(ValueError):
        joint_candidates(mutation(base), model, "stove")
