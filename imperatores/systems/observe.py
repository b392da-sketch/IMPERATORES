"""Consistency checks run every tick (specification 7.1, check 2).

Reads:  entity headcounts and positions; previous positions kept here; params.
Writes: nothing in the world. Raises ConsistencyError on a violation.
"""
from __future__ import annotations

import math


class ConsistencyError(AssertionError):
    pass


def begin_tick(w) -> None:
    w._prev_pos = [(e.x, e.y) for e in w.entities]


def end_tick(w) -> None:
    P = w.params
    limit = P["max_speed_any"] * P["tick_seconds"] + 1e-9
    for e, (px, py) in zip(w.entities, w._prev_pos):
        if not e.headcount_ok():
            raise ConsistencyError(f"tick {w.tick}: {e.name} headcount does not sum to {e.start_strength}")
        if min(e.fit, e.wounded, e.dead, e.fled, e.captured) < 0:
            raise ConsistencyError(f"tick {w.tick}: {e.name} has a negative headcount")
        moved = math.hypot(e.x - px, e.y - py)
        if moved > limit:
            raise ConsistencyError(f"tick {w.tick}: {e.name} moved {moved:.1f} m in one tick")
        if not w.terrain.inside(e.x, e.y):
            raise ConsistencyError(f"tick {w.tick}: {e.name} left the field")
        for v, n in ((e.fatigue, "fatigue"), (e.order, "order"), (e.resolve, "resolve")):
            if not (0.0 <= v <= 1.0):
                raise ConsistencyError(f"tick {w.tick}: {e.name} {n}={v} outside 0..1")
