"""Line of sight over the terrain (specification 5.3; used by belief pictures).

A target is in sight when it is within the observer's range and nothing rises above the
straight line from the observer's eye to the top of the target: neither the ground nor the
canopy of a wood. Higher ground sees further because ridges and woods stop blocking the
view. Inside a wood, sight is limited to a short distance.

Exact, not sampled (Codex review 003, finding 3). The sight line is split at every
half-cell grid line, so each piece lies inside one bilinear ground patch and one terrain
cell. On each piece, (ground + canopy) minus the sight line is a quadratic in the distance
along it; its maximum over the piece is found exactly (ends and any interior peak). No crest
or corner of a wood can slip between samples.

Woods (finding 8): the canopy of a wood blocks the view, except for the cells of the wood
the observer (or target) is standing in, contiguous with him: from inside a wood one sees
out through the trees nearby. If neither end is in a wood, every wood in between blocks.

Pair independence: each pair's answer depends only on that pair (its own breakpoints),
never on which other pairs are checked in the same call.

Values are engineering assumptions in params.py. No haze, dust or weather (out of M0), no
curvature of the earth (irrelevant over a few kilometres).
"""
from __future__ import annotations

import numpy as np

from .terrain import WOODS

_CHUNK_POINTS = 300_000          # cap on (pairs x breakpoints) per chunk, to bound memory
BLOCK_CELLS = 4                  # coarse blocks for the quick certainly-visible / certainly-blocked checks


def _blocks(t):
    """Per coarse block: an upper bound on the ground (and canopy) anywhere in the block.

    Bilinear ground at a point never exceeds the highest of the four cell centres around it,
    and those centres lie within one cell of the point, so the block maximum over the block
    widened by one cell is an upper bound. Any wood in the block adds the full canopy.
    Cached on the terrain object.
    """
    cache = getattr(t, "_sight_blocks", None)
    if cache is not None:
        return cache
    ny, nx = t.shape
    B = BLOCK_CELLS
    nby, nbx = -(-ny // B), -(-nx // B)
    pad = np.pad(t.elev, 1, mode="edge")
    wood = t.ground == WOODS
    top = np.zeros((nby, nbx))                   # upper bound on ground in the block
    low = np.zeros((nby, nbx))                   # lower bound on ground in the block
    has_wood = np.zeros((nby, nbx), dtype=bool)
    for bi in range(nby):
        for bj in range(nbx):
            i0, j0 = bi * B, bj * B
            block = pad[i0:i0 + B + 2, j0:j0 + B + 2]
            top[bi, bj] = block.max()
            low[bi, bj] = block.min()
            has_wood[bi, bj] = wood[i0:i0 + B, j0:j0 + B].any()
    t._sight_blocks = (top, low, has_wood)
    return t._sight_blocks


def _quick(t, P, ox, oy, z0, tx, ty, z1):
    """Coarse bounds on every block the sight line crosses.

    Returns (certainly_visible, certainly_blocked). Certainly visible: the line clears every
    block's upper bound (ground plus full canopy if the block has any wood). Certainly
    blocked: in some block, even the lowest ground there (ignoring woods) rises above the
    highest point of the line within that block. Everything else is checked exactly.
    """
    top, low, has_wood = _blocks(t)
    bound = top + np.where(has_wood, P["wood_canopy_height"], 0.0)
    step = t.cell * BLOCK_CELLS
    n = ox.shape[0]
    nkx = int(np.max(np.ceil(np.abs(tx - ox) / step))) + 1
    nky = int(np.max(np.ceil(np.abs(ty - oy) / step))) + 1
    ts = np.concatenate([np.zeros((n, 1)), _crossings(ox, tx, step, nkx), _crossings(oy, ty, step, nky),
                         np.ones((n, 1))], axis=1)
    ts.sort(axis=1)
    s0, s1 = ts[:, :-1], ts[:, 1:]
    sm = (s0 + s1) / 2.0
    xs = ox[:, None] + (tx - ox)[:, None] * sm
    ys = oy[:, None] + (ty - oy)[:, None] * sm
    nby, nbx = bound.shape
    bi = np.clip((ys // step).astype(int), 0, nby - 1)
    bj = np.clip((xs // step).astype(int), 0, nbx - 1)
    up = z1[:, None] >= z0[:, None]
    ray_lo = z0[:, None] + (z1 - z0)[:, None] * np.where(up, s0, s1)
    ray_hi = z0[:, None] + (z1 - z0)[:, None] * np.where(up, s1, s0)
    real = (s1 - s0) > 1e-12
    visible = ((bound[bi, bj] < ray_lo - 1e-9) | ~real).all(axis=1)
    blocked = ((low[bi, bj] > ray_hi + 1e-9) & real).any(axis=1)
    return visible, blocked


def _crossings(a, b, step, kmax):
    """Per row, parameters in (0, 1) where a + (b - a) t crosses a multiple of step; padded with 1.0."""
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    k0 = np.floor(lo / step) + 1
    k1 = np.ceil(hi / step) - 1
    k = k0[:, None] + np.arange(kmax)[None, :]
    ok = k <= k1[:, None]
    span = b - a
    with np.errstate(divide="ignore", invalid="ignore"):
        tt = (k * step - a[:, None]) / span[:, None]
    return np.where(ok & (np.abs(span)[:, None] > 1e-12), tt, 1.0)


def _chunk(t, P, ox, oy, z0, tx, ty, z1, wood_o, wood_t):
    h = t.cell / 2.0
    nkx = int(np.max(np.ceil(np.abs(tx - ox) / h))) + 1
    nky = int(np.max(np.ceil(np.abs(ty - oy) / h))) + 1
    n = ox.shape[0]
    ts = np.concatenate([np.zeros((n, 1)), _crossings(ox, tx, h, nkx), _crossings(oy, ty, h, nky),
                         np.ones((n, 1))], axis=1)
    ts.sort(axis=1)
    s0, s1 = ts[:, :-1], ts[:, 1:]
    valid = (s1 - s0) > 1e-12
    sm = (s0 + s1) / 2.0
    dx, dy = (tx - ox)[:, None], (ty - oy)[:, None]
    x0, y0 = ox[:, None], oy[:, None]

    def ground(s):
        return t.height_at_many(x0 + dx * s, y0 + dy * s)

    def ray(s):
        return z0[:, None] + (z1 - z0)[:, None] * s

    g_pts = ground(ts) - ray(ts)
    g_mid = ground(sm) - ray(sm)
    wood = (t.ground_at_many(x0 + dx * sm, y0 + dy * sm) == WOODS) & valid
    # the contiguous stretch of wood at each end that the observer or target stands in
    run_start = np.cumprod(wood | ~valid, axis=1).astype(bool) & wood & wood_o[:, None]
    rev = (wood | ~valid)[:, ::-1]
    run_end = np.cumprod(rev, axis=1)[:, ::-1].astype(bool) & wood & wood_t[:, None]
    canopy = np.where(wood & ~run_start & ~run_end, P["wood_canopy_height"], 0.0)
    g0 = g_pts[:, :-1] + canopy
    g1 = g_pts[:, 1:] + canopy
    gm = g_mid + canopy
    # quadratic through the three values: q(u) = g0 + b u + a u^2 on u in [0, 1]
    b = 4.0 * gm - 3.0 * g0 - g1
    a = 2.0 * g0 + 2.0 * g1 - 4.0 * gm
    peak = np.maximum(g0, g1)
    with np.errstate(divide="ignore", invalid="ignore"):
        u = -b / (2.0 * a)
        inner = (a < 0) & (u > 0) & (u < 1)
        peak = np.where(inner, np.maximum(peak, g0 - b * b / (4.0 * a)), peak)
    return ~((peak > 1e-9) & valid).any(axis=1)


def visible_pairs(t, P, ox, oy, eye_h, tx, ty, target_h) -> np.ndarray:
    """Boolean array: for each pair k, can observer k (ox, oy, eye_h) see target k (tx, ty, target_h)?"""
    ox, oy, eye_h = (np.asarray(a, dtype=float) for a in (ox, oy, eye_h))
    tx, ty, target_h = (np.asarray(a, dtype=float) for a in (tx, ty, target_h))
    n = tx.shape[0]
    out = np.zeros(n, dtype=bool)
    if n == 0:
        return out
    dist = np.hypot(tx - ox, ty - oy)
    in_wood_rng = P["sight_range_in_woods"]
    wood_o = t.ground_at_many(ox, oy) == WOODS
    wood_t = t.ground_at_many(tx, ty) == WOODS
    ok = dist <= P["sight_range_max"]
    ok &= ~((wood_o | wood_t) & (dist > in_wood_rng))   # inside a wood: only nearby; into a wood: only close up
    out[ok & (dist <= 1e-6)] = True
    idx = np.nonzero(ok & (dist > 1e-6))[0]
    if idx.size == 0:
        return out
    z0 = t.height_at_many(ox, oy) + eye_h
    z1 = t.height_at_many(tx, ty) + target_h
    vis, blk = _quick(t, P, ox[idx], oy[idx], z0[idx], tx[idx], ty[idx], z1[idx])
    out[idx[vis]] = True
    idx = idx[~vis & ~blk]
    if idx.size == 0:
        return out
    npts = (np.abs(tx - ox) + np.abs(ty - oy)) / (t.cell / 2.0) + 4
    order = idx[np.argsort(npts[idx], kind="stable")]  # group similar lengths to limit padding
    start = 0
    while start < order.size:
        stop = start + 1
        while stop < order.size and (stop - start + 1) * npts[order[stop]] <= _CHUNK_POINTS:
            stop += 1
        sel = order[start:stop]
        start = stop
        out[sel] = _chunk(t, P, ox[sel], oy[sel], z0[sel], tx[sel], ty[sel], z1[sel], wood_o[sel], wood_t[sel])
    return out


def visible_many(t, P, ox: float, oy: float, eye_h: float,
                 txs: np.ndarray, tys: np.ndarray, tgt_hs: np.ndarray) -> np.ndarray:
    """Boolean array: which targets the observer at (ox, oy) can see."""
    txs = np.asarray(txs, dtype=float)
    n = txs.shape[0]
    return visible_pairs(t, P, np.full(n, ox), np.full(n, oy), np.full(n, eye_h), txs, tys,
                         np.broadcast_to(np.asarray(tgt_hs, dtype=float), (n,)))


def line_of_sight(t, P, ox, oy, eye_h, tx, ty, target_h) -> bool:
    return bool(visible_pairs(t, P, [ox], [oy], [eye_h], [tx], [ty], [target_h])[0])


def eye_height(mobility: str, P) -> float:
    return P["eye_height_horse"] if mobility == "horse" else P["eye_height_foot"]


def target_height(mobility: str, P) -> float:
    return P["target_height_horse"] if mobility == "horse" else P["target_height_foot"]
