"""Pure geometry regression for the recorded 90-degree drawer In region.

The fixture uses the pinned cabinet region/floor dimensions. It abstracts the
compiled world pose; it is not a native replay or proof of physical stability.
"""
from copy import deepcopy

import numpy as np
import pytest

from benchmark.remaining_goals.construction import placement_candidates
from tests.test_remaining_construction import scene


@pytest.fixture
def drawer_volume(scene):
    model, data, base = scene
    # Cabinet XML rotates local x into world -z. The region local z is horizontal.
    rotation = np.array([[0., 0., 1.], [0., 1., 0.], [-1., 0., 0.]])
    model.site_size[0] = [.02993, .07561, .10224]
    data.site_xmat[0] = rotation.ravel()
    center = data.site_xpos[0].copy()
    model.geom_size[0] = [.00401, .08095, .10696]
    data.geom_xmat[0] = rotation.ravel()
    data.geom_xpos[0] = center + [.00020, -.00080, -.03019]
    # A vertical thin wall has a horizontal top cap, but is not a floor.
    model.geom_size[1] = [.00356, .08095, .03214]
    data.geom_xpos[1] = center + [.105, 0., 0.]
    # Upright test object fits the shallow volume. Preserve its original pose.
    model.geom_size[6] = [.022, .024, .02]
    return model, data, base


def candidates(fixture, **kwargs):
    model, data, base = fixture
    return placement_candidates(base, model, data, "a", "basket_contain_region",
                                in_volume=True, clearances=[.002], **kwargs)


def test_rotated_In_uses_owned_floor_normal_and_preserves_original_world_pose(drawer_volume):
    model, data, base = drawer_volume
    before, before_data = base.copy(), deepcopy(vars(data))
    result = candidates(drawer_volume)
    assert result
    first = result[0]
    assert first["diagnostics"]["method"] == "oriented_in_volume_world_gravity_v1"
    assert first["diagnostics"]["support_geom_id"] == 0
    assert first["diagnostics"]["support_world_z"] == pytest.approx(.07382)
    assert first["placements"][0]["position"][2] == pytest.approx(.08582)
    assert first["diagnostics"]["physics_validated"] is False
    assert first["diagnostics"]["predicate_verified"] is False
    for candidate in result:
        local_origin = data.site_xmat[0].reshape(3, 3).T @ (
            np.asarray(candidate["placements"][0]["position"]) - data.site_xpos[0])
        assert np.all(np.abs(local_origin) < model.site_size[0])
        np.testing.assert_array_equal(candidate["state"][7:11], base[7:11])
        np.testing.assert_array_equal(candidate["state"][28:34], base[28:34])
        protected = sorted(set(range(base.size)) - set(candidate["allowed_indices"]))
        np.testing.assert_array_equal(candidate["state"][protected], base[protected])
    np.testing.assert_array_equal(base, before)
    for field, original in before_data.items():
        np.testing.assert_array_equal(getattr(data, field), original)


def test_open_drawer_translation_moves_volume_and_its_owned_support(drawer_volume):
    model, data, _ = drawer_volume
    original = candidates(drawer_volume)[0]
    shift = np.array([.07, -.15, .03])
    data.site_xpos[0] += shift
    data.geom_xpos[:3] += shift
    moved = candidates(drawer_volume)[0]
    np.testing.assert_allclose(moved["placements"][0]["position"],
                               np.asarray(original["placements"][0]["position"]) + shift)


def test_yawed_container_still_checks_full_oriented_volume(drawer_volume):
    model, data, base = drawer_volume
    theta = np.deg2rad(37.)
    yaw = np.array([[np.cos(theta), -np.sin(theta), 0.],
                    [np.sin(theta), np.cos(theta), 0.], [0., 0., 1.]])
    center = data.site_xpos[0].copy()
    data.site_xmat[0] = (yaw @ data.site_xmat[0].reshape(3, 3)).ravel()
    for geom in (0, 1, 2):
        data.geom_xpos[geom] = center + yaw @ (data.geom_xpos[geom] - center)
        data.geom_xmat[geom] = (yaw @ data.geom_xmat[geom].reshape(3, 3)).ravel()
    result = candidates(drawer_volume)
    assert result
    for candidate in result:
        position = np.asarray(candidate["placements"][0]["position"])
        corners = np.array([[x, y, z] for x in (-.022, .022) for y in (-.024, .024)
                            for z in (-.01, .03)])
        local = (corners + position - center) @ data.site_xmat[0].reshape(3, 3)
        assert np.all(np.abs(local) <= model.site_size[0] - .001)
        np.testing.assert_array_equal(candidate["state"][7:11], base[7:11])


def test_wall_caps_and_other_bodies_do_not_substitute_for_the_floor(drawer_volume):
    model, data, _ = drawer_volume
    model.geom_bodyid[0] = 4  # The old floor now belongs to an unrelated stove.
    data.geom_xpos[1, :2] = data.site_xpos[0, :2]  # Wall cap under the origin.
    with pytest.raises(ValueError, match="floor"):
        candidates(drawer_volume)


def test_rotating_support_plane_past_five_degrees_cannot_be_hidden_by_In(drawer_volume):
    _, data, _ = drawer_volume
    angle = np.deg2rad(6.)
    tilt = np.array([[1., 0., 0.], [0., np.cos(angle), -np.sin(angle)],
                     [0., np.sin(angle), np.cos(angle)]])
    data.geom_xmat[0] = (tilt @ data.geom_xmat[0].reshape(3, 3)).ravel()
    with pytest.raises(ValueError, match="floor"):
        candidates(drawer_volume)


def test_legacy_and_On_never_opt_into_volume_semantics(drawer_volume):
    model, data, base = drawer_volume
    for relation in ("in", "on"):
        with pytest.raises(ValueError, match="tilted/inverted"):
            placement_candidates(base, model, data, "a", "basket_contain_region", relation=relation)
    with pytest.raises(ValueError, match="In"):
        candidates(drawer_volume, relation="on")


def test_rotated_region_containment_excludes_object_too_tall_for_volume(drawer_volume):
    model, _, _ = drawer_volume
    model.geom_size[6, 2] = .08
    assert candidates(drawer_volume) == []


def test_floor_must_cover_collision_footprint_not_only_object_origin(drawer_volume):
    model, _, _ = drawer_volume
    model.geom_size[0, 1:] = [.010, .010]
    assert candidates(drawer_volume) == []


def test_mesh_floor_bounds_cannot_be_used_as_an_invented_plane(drawer_volume):
    model, _, _ = drawer_volume
    model.geom_type[0] = 7
    model.geom_dataid = np.array([0, -1, -1, -1, -1, -1, -1, -1])
    model.mesh_vertadr = np.array([0])
    model.mesh_vertnum = np.array([8])
    model.mesh_vert = np.array([[x, y, z] for x in (-.004, .004)
                                for y in (-.081, .081) for z in (-.107, .107)])
    with pytest.raises(ValueError, match="floor"):
        candidates(drawer_volume)
