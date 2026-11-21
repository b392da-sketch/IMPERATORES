"""Route planning over the terrain grid.

A* over cells (8 neighbours) minimising travel time for the entity's movement class, then
the route is shortened by cutting corners where a straight segment is no slower ground
than what it replaces. Stream cells away from fords are impassable. Slope is ignored in
planning (it still slows movement); the planner knows the ground (see terrain.py).

Deterministic: ties are broken by a fixed counter, so the same inputs give the same route.
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from .terrain import FORD, OPEN, ROUGH, STREAM, WOODS, cells_on_segment

_NEIGH = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


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


def _segment_ok(t, fgrid, ax, ay, bx, by, min_factor) -> bool:
    """Exact: every cell the segment passes through is on ground at least as quick as min_factor."""
    if not (t.inside(ax, ay) and t.inside(bx, by)):
        return False
    return all(fgrid[i, j] >= min_factor and fgrid[i, j] > 0 for i, j in cells_on_segment(t, ax, ay, bx, by))


def plan(t, P, cls: str, sx: float, sy: float, gx: float, gy: float) -> list[tuple[float, float]] | None:
    """Waypoints from (sx, sy) to (gx, gy), excluding the start; None if no route exists."""
    fgrid = factor_grid(t, P, cls)
    start, goal = t.cell_of(sx, sy), t.cell_of(gx, gy)
    if fgrid[goal] <= 0:
        return None
    if _segment_ok(t, fgrid, sx, sy, gx, gy, 1.0):
        return [(gx, gy)]                               # open ground all the way: go straight
    ny, nx = t.shape
    c = t.cell
    best = {start: 0.0}
    came: dict = {}
    count = 0
    heap = [(0.0, count, start)]
    while heap:
        _, _, cur = heapq.heappop(heap)
        if cur == goal:
            break
        ci, cj = cur
        for di, dj in _NEIGH:
            ni, nj = ci + di, cj + dj
            if not (0 <= ni < ny and 0 <= nj < nx):
                continue
            f = fgrid[ni, nj]
            if f <= 0:
                continue
            if di and dj and (fgrid[ci, nj] <= 0 or fgrid[ni, cj] <= 0):
                continue                                # no slipping diagonally between impassable cells
            step = c * (1.4142135623730951 if di and dj else 1.0)
            cost = best[cur] + step / min(f, fgrid[ci, cj] if fgrid[ci, cj] > 0 else f)
            nb = (ni, nj)
            if cost < best.get(nb, math.inf):
                best[nb] = cost
                came[nb] = cur
                gi, gj = goal
                h = c * math.hypot(gi - ni, gj - nj)    # admissible: open ground is the fastest
                count += 1
                heapq.heappush(heap, (cost + h, count, nb))
    if goal not in came and goal != start:
        return None
    cells = [goal]
    while cells[-1] != start:
        cells.append(came[cells[-1]])
    cells.reverse()
    pts = [(sx, sy)] + [t.centre(i, j) for i, j in cells[1:-1]] + [(gx, gy)]
    # shorten: from each kept point, jump to the furthest later point reachable on ground no
    # slower than the slowest ground on the stretch it replaces
    out = []
    k = 0
    while k < len(pts) - 1:
        nxt = k + 1
        for m in range(len(pts) - 1, k + 1, -1):
            stretch = [fgrid[t.cell_of(*p)] for p in pts[k:m + 1]]
            if _segment_ok(t, fgrid, *pts[k], *pts[m], min(stretch)):
                nxt = m
                break
        out.append(pts[nxt])
        k = nxt
    return out
