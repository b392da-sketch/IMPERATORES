"""Route planning over the terrain grid.

Cost is travel time, measured as "open-ground metres": the length of each piece of a path
divided by the pace factor of the cell it lies in (1 on open ground, less on rough ground,
woods and fords; streams are impassable). A piece running exactly along a grid line takes
the slower of the two cells beside it. `segment_cost` computes this exactly for a straight
segment, and the same definition is used throughout (Codex review 003, finding 6):

  * A* searches cell centres (8 neighbours). An edge between two neighbouring full cells
    costs half its length in each cell, which is exactly `segment_cost` for that edge;
    edges touching a clipped cell at the field edge use `segment_cost` itself.
    The straight-line heuristic is admissible because no pace factor exceeds 1. Stale heap
    entries are skipped.
  * The raw route is: start, the centre of the start cell, the A* centres, the centre of the
    goal cell, the goal. Every raw leg lies within one cell or two neighbouring cells.
    Partial cells at the field edge use the centre of their part on the field (finding 7).
  * Shortening replaces a run of legs by one straight leg only if that leg is passable and
    costs no more than the legs it replaces. Extension from each kept point stops at the
    first leg that fails, and is bounded, so shortening costs O(route length) checks
    (finding 10).

Slope is ignored in planning (it still slows movement). The planner knows the ground
(see terrain.py).
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from .terrain import FORD, OPEN, ROUGH, STREAM, WOODS, _cells_containing, _line_crossings, cells_on_segment

_NEIGH = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
SHORTEN_LOOKAHEAD = 64          # most raw points one straight leg may replace


def movement_class(e) -> str:
    if e.equipment.mobility == "horse":
        return "horse"
    return "formed" if e.formed else "open"


def pace_factor(P, cls: str, ground: int) -> float:
    if ground == OPEN:
        return 1.0
    if ground == STREAM:
        return 0.0
    name = {ROUGH: "rough", WOODS: "woods", FORD: "ford"}[ground]
    return P[f"pace_{name}_{cls}"]


def factor_grid(t, P, cls: str) -> np.ndarray:
    f = np.ones(t.shape)
    for g in (ROUGH, WOODS, FORD, STREAM):
        f[t.ground == g] = pace_factor(P, cls, g)
    return f


def segment_cost(t, fgrid, ax, ay, bx, by) -> float:
    """Exact travel cost of a straight segment in open-ground metres; inf if not passable."""
    if not (t.inside(ax, ay) and t.inside(bx, by)):
        return math.inf
    if any(fgrid[i, j] <= 0 for i, j in cells_on_segment(t, ax, ay, bx, by)):
        return math.inf
    L = math.hypot(bx - ax, by - ay)
    if L == 0:
        return 0.0
    ts = sorted(set([0.0, 1.0] + _line_crossings(ax, bx, t.cell) + _line_crossings(ay, by, t.cell)))
    cost = 0.0
    for s0, s1 in zip(ts, ts[1:]):
        m = (s0 + s1) / 2.0
        cells = _cells_containing(t, ax + (bx - ax) * m, ay + (by - ay) * m)
        f = min(fgrid[i, j] for i, j in cells)
        cost += (s1 - s0) * L / f
    return cost


def plan(t, P, cls: str, sx: float, sy: float, gx: float, gy: float, stats: dict | None = None):
    """Waypoints from (sx, sy) to (gx, gy), excluding the start; None if no route exists.

    Raises ValueError if the start or goal is off the field.
    """
    if not (t.inside(sx, sy) and t.inside(gx, gy)):
        raise ValueError("route start and goal must be on the field")
    fgrid = factor_grid(t, P, cls)
    start, goal = t.cell_of(sx, sy), t.cell_of(gx, gy)
    if fgrid[start] <= 0 or fgrid[goal] <= 0:
        return None
    straight = segment_cost(t, fgrid, sx, sy, gx, gy)
    if straight <= math.hypot(gx - sx, gy - sy) + 1e-9:
        if stats is not None:
            stats.update(shorten_checks=0, raw_points=2, cost=straight, raw_cost=straight)
        return [(gx, gy)]                               # open ground all the way: go straight
    ny, nx = t.shape
    centres = {}

    def ctr(cell):
        p = centres.get(cell)
        if p is None:
            p = centres[cell] = t.centre(*cell)
        return p

    part_j = nx - 1 if t.width < nx * t.cell else None
    part_i = ny - 1 if t.height < ny * t.cell else None

    def partial(cell):
        return cell[1] == part_j or cell[0] == part_i

    best = {start: 0.0}
    came: dict = {}
    count = 0
    gxc, gyc = ctr(goal)
    heap = [(math.hypot(gxc - ctr(start)[0], gyc - ctr(start)[1]), 0.0, count, start)]
    while heap:
        _, g, _, cur = heapq.heappop(heap)
        if g > best.get(cur, math.inf):
            continue                                    # stale entry
        if cur == goal:
            break
        ci, cj = cur
        fa = fgrid[ci, cj]
        ax, ay = ctr(cur)
        for di, dj in _NEIGH:
            ni, nj = ci + di, cj + dj
            if not (0 <= ni < ny and 0 <= nj < nx):
                continue
            fb = fgrid[ni, nj]
            if fb <= 0:
                continue
            if di and dj and (fgrid[ci, nj] <= 0 or fgrid[ni, cj] <= 0):
                continue                                # cannot pass a corner touching impassable cells
            nb = (ni, nj)
            bx, by = ctr(nb)
            if partial(cur) or partial(nb):
                cost = g + segment_cost(t, fgrid, ax, ay, bx, by)    # clipped edge cells: exact (finding 004/7)
            else:
                step = math.hypot(bx - ax, by - ay)
                cost = g + step / 2.0 / fa + step / 2.0 / fb
            if cost < best.get(nb, math.inf):
                best[nb] = cost
                came[nb] = cur
                count += 1
                heapq.heappush(heap, (cost + math.hypot(gxc - bx, gyc - by), cost, count, nb))
    if goal != start and goal not in came:
        return None
    cells = [goal]
    while cells[-1] != start:
        cells.append(came[cells[-1]])
    cells.reverse()
    pts = [(sx, sy)] + [ctr(c) for c in cells] + [(gx, gy)]
    raw = [pts[0]]
    for p in pts[1:]:                                   # drop zero-length legs
        if math.hypot(p[0] - raw[-1][0], p[1] - raw[-1][1]) > 1e-9:
            raw.append(p)
    leg = [segment_cost(t, fgrid, *raw[k], *raw[k + 1]) for k in range(len(raw) - 1)]
    if any(math.isinf(c) for c in leg):
        return None                                     # a raw leg grazes an impassable cell (start or goal on its edge)
    prefix = [0.0]
    for c in leg:
        prefix.append(prefix[-1] + c)
    checks = 0
    out = []
    k = 0
    while k < len(raw) - 1:
        m = k + 1
        while m + 1 < len(raw) and m + 1 - k <= SHORTEN_LOOKAHEAD:
            checks += 1
            c = segment_cost(t, fgrid, *raw[k], *raw[m + 1])
            if c <= prefix[m + 1] - prefix[k] + 1e-9:
                m += 1
            else:
                break
        out.append(raw[m])
        k = m
    if stats is not None:
        stats["shorten_checks"] = checks
        stats["raw_points"] = len(raw)
        stats["raw_cost"] = float(prefix[-1])
        stats["cost"] = float(sum(segment_cost(t, fgrid, *a, *b) for a, b in zip([(sx, sy)] + out[:-1], out)))
    return out
