"""Perception: observers update their belief pictures from what they can see (specification 5.4).

Reads:  entity positions, side, function, mobility, fit, order, facing; commander positions;
        terrain; params. Never writes the true state.
Writes: w.beliefs (contacts and own-entity knowledge); w.belief_trace.
Random: keyed draws on stream "perception", one set per (observer, target, cycle), so a
        sighting's errors depend only on that pair and cycle (rng.keyed_normals).

Every `perception_interval_s`:
  * every entity with men still fit (its officer) and every living commander looks;
  * an entity's officer notes bodies within `officer_attention_range`; commanders watch to
    the limit of sight;
  * a body in line of sight is recorded with errors that grow with distance: position,
    numbers, and (close up) its order. What kind of troops it is, and its facing, can be
    told only within `recognise_range`; beyond, only horse or foot within
    `horse_foot_range`; beyond that, only "troops".
"""
from __future__ import annotations

import hashlib

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

    obs = [(e.id, e.x, e.y, e.equipment.mobility, P["officer_attention_range"], e)
           for e in w.entities if e.fit > 0]
    obs += [(c.id, c.x, c.y, c.mobility, P["sight_range_max"], None) for c in w.commanders if c.alive]
    oid = np.array([o[0] for o in obs], dtype=np.int64)
    ox = np.array([o[1] for o in obs])
    oy = np.array([o[2] for o in obs])
    oeye = np.array([sight.eye_height(o[3], P) for o in obs])
    oatt = np.array([o[4] for o in obs])

    for o in obs:                                        # an officer knows his own entity exactly
        own = o[5]
        if own is not None:
            w.beliefs[own.id].own = {"id": own.id, "x": own.x, "y": own.y, "facing": own.facing,
                                     "fit": own.fit, "wounded": own.wounded, "dead": own.dead,
                                     "fled": own.fled, "captured": own.captured, "fatigue": own.fatigue,
                                     "order": own.order, "resolve": own.resolve,
                                     "task": own.task.get("kind", "")}

    # every candidate (observer, target) pair at once
    dist = np.hypot(tx[None, :] - ox[:, None], ty[None, :] - oy[:, None])
    cand = (tid[None, :] != oid[:, None]) & (dist <= oatt[:, None])
    oi, ti = np.nonzero(cand)
    h = hashlib.sha256(w.belief_trace.encode())
    h.update(np.int64(w.tick).tobytes())
    if oi.size:
        vis = sight.visible_pairs(t, P, ox[oi], oy[oi], oeye[oi], tx[ti], ty[ti], th[ti])
        oi, ti = oi[vis], ti[vis]
    if oi.size:
        d = dist[oi, ti]
        z = keyed_normals(w.seed, "perception", [oid[oi], tid[ti], np.full(oi.size, cycle, dtype=np.int64)], 4)
        pos_sd = P["pos_error_per_km"] * d / 1000.0
        ex = np.clip(tx[ti] + z[:, 0] * pos_sd, 0.0, t.width)
        ey = np.clip(ty[ti] + z[:, 1] * pos_sd, 0.0, t.height)
        str_sd = P["strength_error_base"] + P["strength_error_per_km"] * d / 1000.0
        est = np.maximum(0, np.rint(tfit[ti] * (1.0 + z[:, 2] * str_sd))).astype(np.int64)
        oest = np.clip(torder[ti] + z[:, 3] * P["order_error"], 0.0, 1.0)
        recog = d <= P["recognise_range"]
        hf = d <= P["horse_foot_range"]
        ordv = d <= P["order_visible_range"]
        for k in range(oi.size):
            i = ti[k]
            if recog[k]:
                kind, facing = tkind[i], float(tfacing[i])
            elif hf[k]:
                kind, facing = ("horse" if thorse[i] else "foot"), None
            else:
                kind, facing = "troops", None
            belief_mod.observe(w.beliefs[int(oid[oi[k]])],
                               {"id": int(tid[i]), "side": tside[i], "kind": kind,
                                "x": float(ex[k]), "y": float(ey[k]), "pos_err": float(pos_sd[k]),
                                "strength": int(est[k]), "order": float(oest[k]) if ordv[k] else None,
                                "facing": facing, "seen_t": w.tick})
        for a in (oid[oi], tid[ti], ex, ey, est, oest):
            h.update(np.ascontiguousarray(a).tobytes())
    w.belief_trace = h.hexdigest()
