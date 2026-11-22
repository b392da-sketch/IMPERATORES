"""Line of sight over the terrain (specification 5.3; used by belief pictures in step 3).

A target is in sight when it is within the observer's range and no ground or wood canopy
rises above the straight line from the observer's eye to the top of the target. Higher
ground sees further because ridges and woods stop blocking the view. Inside a wood, sight
is limited to a short distance.

Each pair's answer depends only on that pair: the ray is sampled at a fixed spacing from
the observer, whatever other targets are checked in the same call. So adding or removing
an entity can never change whether some other pair can see each other (needed for paired
intervention tests).

All values are engineering assumptions in params.py. No haze, dust or weather (out of M0),
no curvature of the earth (irrelevant over a few kilometres).
"""
from __future__ import annotations

import numpy as np

from .terrain import WOODS


def sample_spacing(t, P) -> float:
    return t.cell * P["sight_sample_spacing_cells"]


_CHUNK_SAMPLES = 400_000          # cap on (pairs x samples) per chunk, to bound memory


def visible_pairs(t, P, ox, oy, eye_h, tx, ty, target_h) -> np.ndarray:
    """Boolean array: for each pair k, can observer k (ox, oy, eye_h) see target k (tx, ty, target_h)?

    All arguments are arrays of the same length. Each pair is sampled on its own fixed
    spacing from the observer, so its answer does not depend on the other pairs.
    """
    ox, oy, eye_h = (np.asarray(a, dtype=float) for a in (ox, oy, eye_h))
    tx, ty, target_h = (np.asarray(a, dtype=float) for a in (tx, ty, target_h))
    n = tx.shape[0]
    out = np.zeros(n, dtype=bool)
    if n == 0:
        return out
    dist = np.hypot(tx - ox, ty - oy)
    in_wood_rng = P["sight_range_in_woods"]
    ok = dist <= P["sight_range_max"]
    wood_o = t.ground_at_many(ox, oy) == WOODS
    wood_t = t.ground_at_many(tx, ty) == WOODS
    ok &= ~((wood_o | wood_t) & (dist > in_wood_rng))   # inside a wood: only nearby; into a wood: only close up
    out[ok & (dist <= 1e-6)] = True
    idx = np.nonzero(ok & (dist > 1e-6))[0]
    if idx.size == 0:
        return out
    sp = sample_spacing(t, P)
    z0_all = t.height_at_many(ox, oy) + eye_h
    z1_all = t.height_at_many(tx, ty) + target_h
    order = idx[np.argsort(dist[idx], kind="stable")]  # group similar lengths to limit padding
    start = 0
    while start < order.size:
        nmax = int(np.ceil(dist[order[min(start + 1, order.size) - 1]] / sp))
        stop = start
        while stop < order.size:
            nmax = max(nmax, int(np.ceil(dist[order[stop]] / sp)))
            if (stop - start + 1) * nmax > _CHUNK_SAMPLES and stop > start:
                break
            stop += 1
        sel = order[start:stop]
        start = stop
        d = dist[sel][:, None]
        nmax = int(np.ceil(d.max() / sp))
        s = (np.arange(1, nmax + 1) * sp)[None, :]
        valid = s < d - 1e-9
        f = np.where(valid, s / d, 0.0)
        xs = ox[sel, None] + (tx[sel, None] - ox[sel, None]) * f
        ys = oy[sel, None] + (ty[sel, None] - oy[sel, None]) * f
        z0 = z0_all[sel, None]
        ray = z0 + (z1_all[sel, None] - z0) * f
        ground = t.height_at_many(xs, ys)
        wood = t.ground_at_many(xs, ys) == WOODS
        near_end = np.minimum(s, d - s) <= in_wood_rng
        ground = ground + np.where(wood & ~near_end, P["wood_canopy_height"], 0.0)
        out[sel] = ~((ground > ray) & valid).any(axis=1)
    return out


def visible_many(t, P, ox: float, oy: float, eye_h: float,
                 txs: np.ndarray, tys: np.ndarray, tgt_hs: np.ndarray) -> np.ndarray:
    """Boolean array: which targets the observer at (ox, oy) can see."""
    txs = np.asarray(txs, dtype=float)
    n = txs.shape[0]
    return visible_pairs(t, P, np.full(n, ox), np.full(n, oy), np.full(n, eye_h), txs, tys,
                         np.broadcast_to(np.asarray(tgt_hs, dtype=float), (n,)))


def line_of_sight(t, P, ox, oy, eye_h, tx, ty, target_h) -> bool:
    return bool(visible_many(t, P, ox, oy, eye_h, np.array([tx]), np.array([ty]), np.array([target_h]))[0])


def eye_height(mobility: str, P) -> float:
    return P["eye_height_horse"] if mobility == "horse" else P["eye_height_foot"]


def target_height(mobility: str, P) -> float:
    return P["target_height_horse"] if mobility == "horse" else P["target_height_foot"]
