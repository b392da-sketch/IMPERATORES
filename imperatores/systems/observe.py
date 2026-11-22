"""Consistency checks (specification 7.1, check 2).

Reads:  all entity state; the roster; positions at the start of the tick, by stable id; params.
Writes: nothing in the world. Raises ConsistencyError on a violation.

When the checks run (Codex review 002, finding 4):
  * at load (scenario.load calls check_all) and at the start of every tick, so an invalid
    state is caught before any system can mask it;
  * after every phase, so a violation cannot be hidden by a later phase;
  * at the end of every tick, adding the roster and speed checks.
Headcount changes inside a single phase will go through one transfer function (combat,
step 6) that checks conservation at each transfer.

The speed check measures net displacement over the tick. While movement is the only phase
that moves entities this equals actual travel; if several phases ever move an entity in
one tick, movement must be accounted for explicitly instead.
"""
from __future__ import annotations

import math

from ..state import commander_problems, invariant_problems


class ConsistencyError(AssertionError):
    pass


def check_all(w, when: str) -> None:
    if tuple(e.id for e in w.entities) != w.roster:
        raise ConsistencyError(f"tick {w.tick} ({when}): the roster changed without an explicit roster event")
    for e in w.entities:
        problems = invariant_problems(e, w.terrain)
        if problems:
            raise ConsistencyError(f"tick {w.tick} ({when}): {e.name} (id {e.id}): " + "; ".join(problems))
    for c in w.commanders:
        problems = commander_problems(c, w.terrain)
        if problems:
            raise ConsistencyError(f"tick {w.tick} ({when}): commander {c.name} (id {c.id}): " + "; ".join(problems))
    from .command import staff_problems         # messengers are conserved too (review 005/3)
    problems = staff_problems(w)
    if problems:
        raise ConsistencyError(f"tick {w.tick} ({when}): " + "; ".join(problems))


def begin_tick(w) -> None:
    check_all(w, "start of tick")
    w._prev_pos = {e.id: (e.x, e.y) for e in w.entities}


def after_phase(w, phase: str) -> None:
    check_all(w, f"after {phase}")


def end_tick(w) -> None:
    check_all(w, "end of tick")
    P = w.params
    limit = P["max_speed_any"] * P["tick_seconds"] + 1e-9
    for e in w.entities:
        px, py = w._prev_pos[e.id]
        moved = math.hypot(e.x - px, e.y - py)
        if moved > limit:
            raise ConsistencyError(f"tick {w.tick}: {e.name} (id {e.id}) moved {moved:.1f} m in one tick")
