"""Perception: observers update their belief pictures from what they can see (specification 5.4).

Reads:  entity positions, side, function, mobility, fit, order, facing; commander positions;
        terrain; params. Never writes the true state.
Writes: w.beliefs, only through belief.apply_sightings (which validates and hashes every change).
Random: keyed draws on stream "perception", one set per (observer, target, cycle), so a
        sighting's errors depend only on that pair and cycle (rng.keyed_normals).

Every `perception_interval_s`:
  * every entity with men still fit (its officer) and every living commander looks;
  * an entity's officer notes bodies within `officer_attention_range` (a radius, not a facing
    sector); commanders watch to the limit of sight;
  * a body in line of sight is recorded with errors that grow with distance: position,
    numbers, and (close up) its order. Its kind and facing can be told only within
    `recognise_range`, facing to the nearest `facing_resolution_deg`; beyond, only horse or
    foot within `horse_foot_range`; beyond that, only "troops".
  * The observer's idea of the position error (`pos_err`) is derived from the distance at
    which he perceives the body, rounded to a metre, never from the true distance
    (Codex review 004, finding 6).
  * A body with no men fit is not seen; its last contact stays as it was (stale).
"""
from __future__ import annotations

import math

import numpy as np

from .. import belief as belief_mod
from .. import sight
from ..rng import keyed_normals


def _interval_ticks(P) -> int:
    return max(1, int(round(P["perception_interval_s"] / P["tick_seconds"])))


def ensure_beliefs(w) -> None:
    for e in w.entities:
        w.beliefs.setdefault(e.id, belief_mod.Belief(owner=e.id))
    for c in w.commanders:
        w.beliefs.setdefault(c.id, belief_mod.Belief(owner=c.id))


def step(w) -> None:
    P = w.params
    every = _interval_ticks(P)
    if w.tick % every:
        return
    cycle = w.tick // every
    ensure_beliefs(w)
    t = w.terrain

    targets = [e for e in w.entities if e.fit > 0]
    if not targets:
        return
    tid = np.array([e.id for e in targets], dtype=np.int64)
    tx = np.array([e.x for e in targets])
    ty = np.array([e.y for e in targets])
    th = np.array([sight.target_height(e.equipment.mobility, P) for e in targets])
    tside = [e.side for e in targets]
    tkind = [e.function for e in targets]
    thorse = [e.equipment.mobility == "horse" for e in targets]
    tfit = np.array([e.fit for e in targets], dtype=float)
    torder = np.array([e.order for e in targets])
    tfacing = np.array([e.facing for e in targets])

    obs = [(e.id, e.x, e.y, e.equipment.mobility, P["officer_attention_range"]) for e in w.entities if e.fit > 0]
    obs += [(c.id, c.x, c.y, c.mobility, P["sight_range_max"]) for c in w.commanders if c.alive]
    oid = np.array([o[0] for o in obs], dtype=np.int64)
    ox = np.array([o[1] for o in obs])
    oy = np.array([o[2] for o in obs])
    oeye = np.array([sight.eye_height(o[3], P) for o in obs])
    oatt = np.array([o[4] for o in obs])

    dist = np.hypot(tx[None, :] - ox[:, None], ty[None, :] - oy[:, None])
    cand = (tid[None, :] != oid[:, None]) & (dist <= oatt[:, None])
    oi, ti = np.nonzero(cand)
    if oi.size:
        vis = sight.visible_pairs(t, P, ox[oi], oy[oi], oeye[oi], tx[ti], ty[ti], th[ti])
        oi, ti = oi[vis], ti[vis]
    if not oi.size:
        return
    d = dist[oi, ti]
    z = keyed_normals(w.seed, "perception", [oid[oi], tid[ti], np.full(oi.size, cycle, dtype=np.int64)], 4)
    pos_sd = P["pos_error_per_km"] * d / 1000.0
    ex = np.clip(tx[ti] + z[:, 0] * pos_sd, 0.0, t.width)
    ey = np.clip(ty[ti] + z[:, 1] * pos_sd, 0.0, t.height)
    perceived = np.hypot(ex - ox[oi], ey - oy[oi])
    pos_err = np.rint(P["pos_error_per_km"] * perceived / 1000.0)
    str_sd = P["strength_error_base"] + P["strength_error_per_km"] * d / 1000.0
    est = np.maximum(0, np.rint(tfit[ti] * (1.0 + z[:, 2] * str_sd))).astype(np.int64)
    oest = np.clip(torder[ti] + z[:, 3] * P["order_error"], 0.0, 1.0)
    recog = d <= P["recognise_range"]
    hf = d <= P["horse_foot_range"]
    ordv = d <= P["order_visible_range"]
    res = math.radians(P["facing_resolution_deg"])
    kinds, facings = [], np.full(oi.size, np.nan)
    for k in range(oi.size):
        i = ti[k]
        if recog[k]:
            kinds.append(tkind[i])
            facings[k] = math.remainder(round(tfacing[i] / res) * res, 2 * math.pi)
        elif hf[k]:
            kinds.append("horse" if thorse[i] else "foot")
        else:
            kinds.append("troops")
    belief_mod.apply_sightings(w, oid[oi], tid[ti], [tside[i] for i in ti], kinds, ex, ey, pos_err, est,
                               np.where(ordv, oest, np.nan), facings, recog)
