"""The battlefield: a grid of cells with height and ground type (specification 5.3).

Ground types: open, rough, woods, stream, ford. Stream cells can be crossed only at fords;
elsewhere they are impassable. Heights are given at cell centres and interpolated.

Scenario format ("terrain"):
  width, height, cell         metres; cell is a scenario setting and must be given
  hills:  [[x, y, peak_m, radius_m], ...]      smooth bumps added to a flat base
  rough:  [[x0, y0, x1, y1], ...]              rectangles
  woods:  [[x0, y0, x1, y1], ...]              rectangles
  stream: {"width": m, "points": [[x, y], ...]}   a polyline
  fords:  [[x, y, radius_m], ...]              where the stream can be crossed

Assumption (M0): both armies know the ground (pre-battle reconnaissance assumed). Unknown
or misjudged terrain is outside M0. Beliefs about the enemy are another matter (step 3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

OPEN, ROUGH, WOODS, STREAM, FORD = 0, 1, 2, 3, 4
GROUND_NAMES = {OPEN: "open", ROUGH: "rough", WOODS: "woods", STREAM: "stream", FORD: "ford"}


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

    # ---- queries -------------------------------------------------------------------------
    def inside(self, x: float, y: float) -> bool:
        return 0.0 <= x <= self.width and 0.0 <= y <= self.height

    def cell_of(self, x: float, y: float) -> tuple[int, int]:
        ny, nx = self.shape
        return (min(max(int(y // self.cell), 0), ny - 1), min(max(int(x // self.cell), 0), nx - 1))

    def centre(self, i: int, j: int) -> tuple[float, float]:
        return ((j + 0.5) * self.cell, (i + 0.5) * self.cell)

    def ground_at(self, x: float, y: float) -> int:
        return int(self.ground[self.cell_of(x, y)])

    def is_rough(self, x: float, y: float) -> bool:          # kept for step 1 callers
        return self.ground_at(x, y) == ROUGH

    def height_at(self, x: float, y: float) -> float:
        """Bilinear interpolation between cell centres."""
        ny, nx = self.shape
        fx = min(max(x / self.cell - 0.5, 0.0), nx - 1.0)
        fy = min(max(y / self.cell - 0.5, 0.0), ny - 1.0)
        j0, i0 = int(math.floor(fx)), int(math.floor(fy))
        j1, i1 = min(j0 + 1, nx - 1), min(i0 + 1, ny - 1)
        tx, ty = fx - j0, fy - i0
        e = self.elev
        top = e[i0, j0] * (1 - tx) + e[i0, j1] * tx
        bot = e[i1, j0] * (1 - tx) + e[i1, j1] * tx
        return float(top * (1 - ty) + bot * ty)

    def cells_of_many(self, xs: np.ndarray, ys: np.ndarray):
        ny, nx = self.shape
        i = np.clip((ys // self.cell).astype(int), 0, ny - 1)
        j = np.clip((xs // self.cell).astype(int), 0, nx - 1)
        return i, j

    def ground_at_many(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        i, j = self.cells_of_many(xs, ys)
        return self.ground[i, j]

    def height_at_many(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Vectorised bilinear interpolation; identical to height_at for each point."""
        ny, nx = self.shape
        fx = np.clip(xs / self.cell - 0.5, 0.0, nx - 1.0)
        fy = np.clip(ys / self.cell - 0.5, 0.0, ny - 1.0)
        j0 = np.floor(fx).astype(int)
        i0 = np.floor(fy).astype(int)
        j1 = np.minimum(j0 + 1, nx - 1)
        i1 = np.minimum(i0 + 1, ny - 1)
        tx, ty = fx - j0, fy - i0
        e = self.elev
        top = e[i0, j0] * (1 - tx) + e[i0, j1] * tx
        bot = e[i1, j0] * (1 - tx) + e[i1, j1] * tx
        return top * (1 - ty) + bot * ty

    def passable(self, x: float, y: float) -> bool:
        return self.inside(x, y) and self.ground_at(x, y) != STREAM

    def segment_passable(self, ax: float, ay: float, bx: float, by: float) -> bool:
        """True if the straight segment stays on the field and touches no stream cell."""
        if not (self.inside(ax, ay) and self.inside(bx, by)):
            return False
        return all(self.ground[i, j] != STREAM for i, j in cells_on_segment(self, ax, ay, bx, by))


def cells_on_segment(t, ax: float, ay: float, bx: float, by: float):
    """Every grid cell the segment a-b passes through, in order (exact grid traversal).

    Where the segment passes exactly through a cell corner, both cells beside the corner
    are included, so nothing can slip diagonally between two cells.
    """
    ny, nx = t.shape
    c = t.cell
    i, j = t.cell_of(ax, ay)
    gi, gj = t.cell_of(bx, by)
    out = [(i, j)]
    dx, dy = bx - ax, by - ay
    step_j = 1 if dx > 0 else -1
    step_i = 1 if dy > 0 else -1
    if dx != 0:
        next_x = (j + (1 if dx > 0 else 0)) * c
        t_max_x = (next_x - ax) / dx
        t_delta_x = c / abs(dx)
    else:
        t_max_x = t_delta_x = math.inf
    if dy != 0:
        next_y = (i + (1 if dy > 0 else 0)) * c
        t_max_y = (next_y - ay) / dy
        t_delta_y = c / abs(dy)
    else:
        t_max_y = t_delta_y = math.inf
    guard = 4 * (nx + ny) + 4
    while (i, j) != (gi, gj) and guard > 0:
        guard -= 1
        if abs(t_max_x - t_max_y) < 1e-12:
            # through a corner: include both side cells, then step diagonally
            for ci, cj in ((i, j + step_j), (i + step_i, j)):
                if 0 <= ci < ny and 0 <= cj < nx:
                    out.append((ci, cj))
            i += step_i
            j += step_j
            t_max_x += t_delta_x
            t_max_y += t_delta_y
        elif t_max_x < t_max_y:
            j += step_j
            t_max_x += t_delta_x
        else:
            i += step_i
            t_max_y += t_delta_y
        if t_max_x > 1.0 + t_delta_x and t_max_y > 1.0 + t_delta_y:
            break
        if 0 <= i < ny and 0 <= j < nx:
            out.append((i, j))
    return out


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
    """Distance from points (arrays) to segment a-b."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0.0, 1.0) if L2 > 0 else np.zeros_like(px)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def build(spec: dict) -> Terrain:
    if "cell" not in spec:
        raise ValueError("terrain: 'cell' (metres per grid cell) must be given")
    w, h, cell = float(spec["width"]), float(spec["height"]), float(spec["cell"])
    if not (w > 0 and h > 0 and cell > 0):
        raise ValueError("terrain: width, height and cell must be positive")
    nx, ny = int(math.ceil(w / cell)), int(math.ceil(h / cell))
    shape = (ny, nx)
    jj, ii = np.meshgrid(np.arange(nx), np.arange(ny))
    cx, cy = (jj + 0.5) * cell, (ii + 0.5) * cell

    elev = np.zeros(shape)
    for hx, hy, peak, radius in spec.get("hills", []):
        if radius <= 0:
            raise ValueError("terrain: hill radius must be positive")
        elev += float(peak) * np.exp(-((cx - hx) ** 2 + (cy - hy) ** 2) / (2.0 * (radius / 2.0) ** 2))

    ground = np.full(shape, OPEN, dtype=np.int8)
    for r in spec.get("rough", []):
        ground[_rect_mask(shape, cell, r)] = ROUGH
    for r in spec.get("woods", []):
        ground[_rect_mask(shape, cell, r)] = WOODS
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
        # every cell the stream's line passes through is stream too, however thin the stream,
        # so the barrier has no gaps between cells (exact traversal, see cells_on_segment)
        probe = Terrain(width=w, height=h, cell=cell, ground=np.zeros(shape, dtype=np.int8), elev=elev)
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            ax, bx = min(max(ax, 0.0), w), min(max(bx, 0.0), w)
            ay, by = min(max(ay, 0.0), h), min(max(by, 0.0), h)
            for i, j in cells_on_segment(probe, ax, ay, bx, by):
                stream[i, j] = True
        ground[stream] = STREAM
        for fx, fy, fr in spec.get("fords", []):
            ford = stream & (np.hypot(cx - fx, cy - fy) <= float(fr))
            if not ford.any():
                raise ValueError(f"terrain: ford at ({fx}, {fy}) does not touch the stream")
            ground[ford] = FORD
    elif spec.get("fords"):
        raise ValueError("terrain: fords given without a stream")
    return Terrain(width=w, height=h, cell=cell, ground=ground, elev=elev)
