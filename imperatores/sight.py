"""Line of sight over the terrain (specification 5.3; used by belief pictures in step 3).

A target is in sight when it is within the observer's range and no ground or wood canopy
rises above the straight line from the observer's eye to the top of the target. Higher
ground sees further because ridges and woods stop blocking the view. Inside a wood, sight
is limited to a short distance.

All values are engineering assumptions in params.py. No haze, dust or weather (out of M0),
no curvature of the earth (irrelevant over a few kilometres).
"""
from __future__ import annotations

import math

import numpy as np

from .terrain import WOODS


def line_of_sight(t, P, ox, oy, eye_h, tx, ty, target_h) -> bool:
    dist = math.hypot(tx - ox, ty - oy)
    if dist > P["sight_range_max"]:
        return False
    obs_wood = t.ground_at(ox, oy) == WOODS
    tgt_wood = t.ground_at(tx, ty) == WOODS
    if (obs_wood or tgt_wood) and dist > P["sight_range_in_woods"]:
        # inside a wood you see only the nearby trees; an entity in a wood is seen only close up
        # (observers and targets at a wood's edge are treated as inside it)
        return False
    if dist < 1e-6:
        return True
    z0 = t.height_at(ox, oy) + eye_h
    z1 = t.height_at(tx, ty) + target_h
    n = max(2, int(dist / (t.cell / 2.0)))
    s = np.linspace(0.0, 1.0, n + 1)[1:-1]             # interior sample points only
    canopy = P["wood_canopy_height"]
    for f in s:
        x, y = ox + (tx - ox) * f, oy + (ty - oy) * f
        ray = z0 + (z1 - z0) * f
        ground = t.height_at(x, y)
        if t.ground_at(x, y) == WOODS:
            # a wood blocks the view unless the ray passes above its canopy; the stretch of wood
            # just around the observer or target (within the in-wood range) does not block
            near_end = min(f, 1.0 - f) * dist <= P["sight_range_in_woods"]
            if not near_end:
                ground += canopy
        if ground > ray:
            return False
    return True


def eye_height(e, P) -> float:
    return P["eye_height_horse"] if e.equipment.mobility == "horse" else P["eye_height_foot"]


def target_height(e, P) -> float:
    return P["target_height_horse"] if e.equipment.mobility == "horse" else P["target_height_foot"]
