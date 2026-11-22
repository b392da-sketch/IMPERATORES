"""The battlefield: a grid of cells with height and ground type (specification 5.3).

Ground types: open, rough, woods, stream, ford. Stream cells can be crossed only at fords;
elsewhere they are impassable.

Scenario format ("terrain"):
  width, height, cell         metres; cell is a scenario setting and must be given
  hills:  [[x, y, peak_m, radius_m], ...]
          smooth bumps added to a flat base. Shape: a Gaussian with sigma = radius / 2, so
          the height at one radius from the centre is e**-2 (about 13.5%) of the peak, and
          the hill has effectively died away by 1.5 radius.
  rough:  [[x0, y0, x1, y1], ...]              rectangles
  woods:  [[x0, y0, x1, y1], ...]              rectangles
  stream: {"width": m, "points": [[x, y], ...]}
          a polyline. A cell is stream if its centre lies within width/2 of the line, or if
          the line passes through or touches the cell (so the barrier has no gaps however
          thin the stream). Parts of the line outside the field are clipped away.
  fords:  [[x, y, radius_m], ...]
          stream cells whose centre lies within the radius become ford. Passability is by
          whole cells, so the effective opening is whole cells (at least one cell wide);
          `ford_openings` reports it. Each ford must join the banks it lies between (open ground
          beside two opposite outer edges of the ford), or loading fails.

Heights are given at cell centres; between centres the ground is bilinear, on "patches"
whose corners are four neighbouring cell centres.

Geometry convention for segments (cells_on_segment): a cell counts as touched if the closed
square of the cell has any point in common with the closed segment, including touching only
an edge or a corner. This is conservative for barriers: a move that grazes a stream cell is
blocked. It is symmetric: a segment and its reverse touch the same cells.

Terrain is immutable once built: its arrays are read-only, so caches derived from it (for
example the coarse sight bounds) can never go stale (Codex review 004, finding 4). Tests and
tools that need an edited map build a new one with `from_arrays`.

Point rule (finding 8): a point is passable if it is on the field and no stream cell's closed
square contains it. A point on the edge of a stream cell is therefore not passable, matching
the segment rule, so nothing can stand where it could not move away from.

Assumption (M0): both armies know the ground (pre-battle reconnaissance assumed). Unknown
or misjudged terrain is outside M0. Beliefs about the enemy are another matter (step 3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

OPEN, ROUGH, WOODS, STREAM, FORD = 0, 1, 2, 3, 4
GROUND_NAMES = {OPEN: "open", ROUGH: "rough", WOODS: "woods", STREAM: "stream", FORD: "ford"}
_EPS = 1e-9


@dataclass
class Terrain:
    width: float
    height: float
    cell: float
    ground: np.ndarray            # int8 [ny, nx], one of the constants above
    elev: np.ndarray              # float [ny, nx], metres, at cell centres

    @property
    def shape(self):
        return self.ground.shape

    # ---- scalar queries --------------------------------------------------------------------
    def inside(self, x: float, y: float) -> bool:
        return 0.0 <= x <= self.width and 0.0 <= y <= self.height

    def cell_of(self, x: float, y: float) -> tuple[int, int]:
        ny, nx = self.shape
        return (min(max(int(y // self.cell), 0), ny - 1), min(max(int(x // self.cell), 0), nx - 1))

    def centre(self, i: int, j: int) -> tuple[float, float]:
        """Centre of the part of cell (i, j) that lies on the field (partial edge cells are clipped)."""
        c = self.cell
        x0, x1 = j * c, min((j + 1) * c, self.width)
        y0, y1 = i * c, min((i + 1) * c, self.height)
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def ground_at(self, x: float, y: float) -> int:
        return int(self.ground[self.cell_of(x, y)])

    def is_rough(self, x: float, y: float) -> bool:
        return self.ground_at(x, y) == ROUGH

    def height_at(self, x: float, y: float) -> float:
        return float(self.height_at_many(np.array([x], dtype=float), np.array([y], dtype=float))[0])

    def passable(self, x: float, y: float) -> bool:
        return self.inside(x, y) and all(self.ground[i, j] != STREAM for i, j in _cells_containing(self, x, y))

    def segment_passable(self, ax: float, ay: float, bx: float, by: float) -> bool:
        """True if the segment stays on the field and touches no stream cell (see convention above)."""
        if not (self.inside(ax, ay) and self.inside(bx, by)):
            return False
        return all(self.ground[i, j] != STREAM for i, j in cells_on_segment(self, ax, ay, bx, by))

    # ---- vectorised queries ------------------------------------------------------------------
    def cells_of_many(self, xs: np.ndarray, ys: np.ndarray):
        ny, nx = self.shape
        i = np.clip((ys // self.cell).astype(int), 0, ny - 1)
        j = np.clip((xs // self.cell).astype(int), 0, nx - 1)
        return i, j

    def ground_at_many(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        i, j = self.cells_of_many(xs, ys)
        return self.ground[i, j]

    def height_at_many(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Bilinear interpolation between cell centres (flat beyond the outermost centres)."""
        ny, nx = self.shape
        fx = np.clip(xs / self.cell - 0.5, 0.0, nx - 1.0)
        fy = np.clip(ys / self.cell - 0.5, 0.0, ny - 1.0)
        j0 = np.minimum(np.floor(fx).astype(int), max(nx - 2, 0))
        i0 = np.minimum(np.floor(fy).astype(int), max(ny - 2, 0))
        j1 = np.minimum(j0 + 1, nx - 1)
        i1 = np.minimum(i0 + 1, ny - 1)
        tx, ty = fx - j0, fy - i0
        e = self.elev
        top = e[i0, j0] * (1 - tx) + e[i0, j1] * tx
        bot = e[i1, j0] * (1 - tx) + e[i1, j1] * tx
        return top * (1 - ty) + bot * ty


# ---- exact segment geometry ------------------------------------------------------------------

def _line_crossings(a: float, b: float, step: float) -> list[float]:
    """Parameters t in (0, 1) where a + (b - a) t crosses a multiple of step."""
    if abs(b - a) < _EPS:
        return []
    lo, hi = min(a, b), max(a, b)
    k0 = math.floor(lo / step) + 1
    k1 = math.ceil(hi / step) - 1
    return [(k * step - a) / (b - a) for k in range(k0, k1 + 1)]


def _cells_containing(t: Terrain, x: float, y: float) -> list[tuple[int, int]]:
    """All cells whose closed square contains the point (1, 2 or 4 cells)."""
    ny, nx = t.shape
    c = t.cell
    js = {int(math.floor(x / c))}
    if abs(x / c - round(x / c)) < _EPS:
        k = int(round(x / c))
        js = {k - 1, k}
    is_ = {int(math.floor(y / c))}
    if abs(y / c - round(y / c)) < _EPS:
        k = int(round(y / c))
        is_ = {k - 1, k}
    return [(i, j) for i in sorted(is_) for j in sorted(js) if 0 <= i < ny and 0 <= j < nx]


def cells_on_segment(t: Terrain, ax: float, ay: float, bx: float, by: float) -> list[tuple[int, int]]:
    """Every cell whose closed square touches the closed segment a-b, ordered from a to b.

    Exact: the segment is split at every grid-line crossing; each piece lies in one cell (or
    runs along a grid line, touching the cells on both sides), and every crossing point and
    endpoint adds the cells meeting there.
    """
    ts = sorted(set([0.0, 1.0] + _line_crossings(ax, bx, t.cell) + _line_crossings(ay, by, t.cell)))
    out: list[tuple[int, int]] = []
    seen = set()

    def add(x, y):
        for cell in _cells_containing(t, x, y):
            if cell not in seen:
                seen.add(cell)
                out.append(cell)

    dx, dy = bx - ax, by - ay
    for k, s in enumerate(ts):
        add(ax + dx * s, ay + dy * s)
        if k + 1 < len(ts):
            m = (s + ts[k + 1]) / 2.0
            add(ax + dx * m, ay + dy * m)
    return out


def clip_segment(ax, ay, bx, by, w, h):
    """Liang-Barsky clip of segment a-b to the rectangle [0, w] x [0, h]; None if it misses."""
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, ax), (dx, w - ax), (-dy, ay), (dy, h - ay)):
        if abs(p) < _EPS:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return (ax + dx * t0, ay + dy * t0, ax + dx * t1, ay + dy * t1)


# ---- building ---------------------------------------------------------------------------------

def _rect_mask(shape, cell, r):
    x0, y0, x1, y1 = (float(v) for v in r)
    if not (x1 > x0 and y1 > y0):
        raise ValueError(f"terrain rectangle {r} has no area")
    ny, nx = shape
    m = np.zeros(shape, dtype=bool)
    m[max(int(y0 // cell), 0):min(int(math.ceil(y1 / cell)), ny),
      max(int(x0 // cell), 0):min(int(math.ceil(x1 / cell)), nx)] = True
    return m


def _segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0.0, 1.0) if L2 > 0 else np.zeros_like(px)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _components(passable: np.ndarray) -> np.ndarray:
    """4-connected components of passable cells (label array; -1 for impassable)."""
    ny, nx = passable.shape
    lab = np.full(passable.shape, -1, dtype=np.int64)
    n = 0
    for i0 in range(ny):
        for j0 in range(nx):
            if not passable[i0, j0] or lab[i0, j0] >= 0:
                continue
            stack = [(i0, j0)]
            lab[i0, j0] = n
            while stack:
                i, j = stack.pop()
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    a, b = i + di, j + dj
                    if 0 <= a < ny and 0 <= b < nx and passable[a, b] and lab[a, b] < 0:
                        lab[a, b] = n
                        stack.append((a, b))
            n += 1
    return lab


def from_arrays(width: float, height: float, cell: float, ground, elev) -> Terrain:
    """A read-only terrain from explicit arrays (copied)."""
    g = np.array(ground, dtype=np.int8, copy=True)
    e = np.array(elev, dtype=float, copy=True)
    ny, nx = int(math.ceil(height / cell)), int(math.ceil(width / cell))
    if g.shape != (ny, nx) or e.shape != (ny, nx):
        raise ValueError(f"terrain arrays must have shape {(ny, nx)}")
    if not np.isfinite(e).all():
        raise ValueError("terrain heights must be finite")
    g.flags.writeable = False
    e.flags.writeable = False
    return Terrain(width=float(width), height=float(height), cell=float(cell), ground=g, elev=e)


def _crosses_locally(closed: np.ndarray, ford: np.ndarray) -> bool:
    """True if the ford, taken as a whole, has passable ground on two opposite sides: along some
    row, open ground just left of its leftmost cell and just right of its rightmost; or along
    some column, above and below. The ford then joins the banks it lies between, however many
    cells wide the stream is (Codex review 004, finding 11)."""
    ny, nx = closed.shape
    for i in sorted(set(np.nonzero(ford)[0])):
        js = np.nonzero(ford[i])[0]
        if 0 < js.min() and js.max() < nx - 1 and closed[i, js.min() - 1] and closed[i, js.max() + 1]:
            return True
    for j in sorted(set(np.nonzero(ford)[1])):
        is_ = np.nonzero(ford[:, j])[0]
        if 0 < is_.min() and is_.max() < ny - 1 and closed[is_.min() - 1, j] and closed[is_.max() + 1, j]:
            return True
    return False


def build(spec: dict) -> Terrain:
    if "cell" not in spec:
        raise ValueError("terrain: 'cell' (metres per grid cell) must be given")
    w, h, cell = float(spec["width"]), float(spec["height"]), float(spec["cell"])
    if not (w > 0 and h > 0 and cell > 0):
        raise ValueError("terrain: width, height and cell must be positive")
    nx, ny = int(math.ceil(w / cell)), int(math.ceil(h / cell))
    shape = (ny, nx)
    jj, ii = np.meshgrid(np.arange(nx), np.arange(ny))
    cx = np.minimum((jj + 0.5) * cell, w)
    cy = np.minimum((ii + 0.5) * cell, h)

    elev = np.zeros(shape)
    for hx, hy, peak, radius in spec.get("hills", []):
        if radius <= 0:
            raise ValueError("terrain: hill radius must be positive")
        sigma = radius / 2.0
        elev += float(peak) * np.exp(-(((jj + 0.5) * cell - hx) ** 2 + ((ii + 0.5) * cell - hy) ** 2) / (2.0 * sigma ** 2))

    ground = np.full(shape, OPEN, dtype=np.int8)
    for r in spec.get("rough", []):
        ground[_rect_mask(shape, cell, r)] = ROUGH
    for r in spec.get("woods", []):
        ground[_rect_mask(shape, cell, r)] = WOODS
    t = Terrain(width=w, height=h, cell=cell, ground=ground, elev=elev)
    st = spec.get("stream")
    if st:
        pts = [(float(a), float(b)) for a, b in st["points"]]
        if len(pts) < 2:
            raise ValueError("terrain: a stream needs at least two points")
        half = float(st["width"]) / 2.0
        d = np.full(shape, np.inf)
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            d = np.minimum(d, _segment_distance(cx, cy, ax, ay, bx, by))
        stream = d <= half
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            clipped = clip_segment(ax, ay, bx, by, w, h)
            if clipped is None:
                continue                                   # this part of the stream lies off the field
            for i, j in cells_on_segment(t, *clipped):
                stream[i, j] = True
        ground[stream] = STREAM
        closed = ground != STREAM                          # passable cells with every ford closed
        for fx, fy, fr in spec.get("fords", []):
            ford = stream & (np.hypot(cx - fx, cy - fy) <= float(fr))
            if not ford.any():
                raise ValueError(f"terrain: ford at ({fx}, {fy}) does not touch the stream")
            if not _crosses_locally(closed, ford):
                raise ValueError(f"terrain: ford at ({fx}, {fy}) does not join two banks")
            ground[ford] = FORD
    elif spec.get("fords"):
        raise ValueError("terrain: fords given without a stream")
    return from_arrays(w, h, cell, ground, elev)


def ford_openings(t: Terrain) -> list[dict]:
    """The effective opening of each group of ford cells, for scenario authors."""
    lab = _components(t.ground == FORD)
    out = []
    top = int(lab.max()) if lab.size else -1
    for k in range(top + 1):
        cells = list(zip(*np.nonzero(lab == k)))
        xs = [t.centre(int(i), int(j))[0] for i, j in cells]
        ys = [t.centre(int(i), int(j))[1] for i, j in cells]
        out.append({"cells": len(cells), "centre": (float(np.mean(xs)), float(np.mean(ys))),
                    "approx_width_m": len(cells) * t.cell})
    return out
