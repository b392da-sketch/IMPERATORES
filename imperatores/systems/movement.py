"""Movement, facing, fatigue and order on the march.

Reads:  entity task, position, facing, function, fatigue, order; terrain; params.
Writes: entity x, y, facing, fatigue, order, task (to "hold" on arrival); events "arrived".
Random: stream "movement", keyed by entity id (pace variation).

Step 1 placeholder: entities move straight towards a target. No collisions, no paths
around obstacles, no sight. Those come in step 2 onwards.
"""
from __future__ import annotations

import math

from .. import record


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _pace(e, P) -> float:
    if e.function == "heavy_infantry":
        return P["pace_infantry_formed"]
    if e.function == "skirmishers":
        return P["pace_skirmisher"]
    return P["pace_cavalry"]


def step(w) -> None:
    P = w.params
    dt = P["tick_seconds"]
    for e in w.entities:
        if e.fit <= 0:
            continue
        if e.task.get("kind") != "move_to":
            # halted: recover order and fatigue
            e.order = min(1.0, e.order + P["order_recovery_per_min_halted"] * dt / 60.0)
            e.fatigue = max(0.0, e.fatigue - P["fatigue_recovery_per_min_halted"] * dt / 60.0)
            continue

        tx, ty = float(e.task["x"]), float(e.task["y"])
        dx, dy = tx - e.x, ty - e.y
        dist = math.hypot(dx, dy)
        if dist <= P["arrival_tolerance"]:
            e.task = {"kind": "hold"}
            record.log(w, "arrived", e.id, {"x": round(e.x, 2), "y": round(e.y, 2)},
                       [{"note": "reached its movement target"}])
            continue

        # turn towards the target, limited by turn rate; formed bodies wheel slowly
        want = math.atan2(dy, dx)
        turn = P["turn_rate_formed"] if e.formed else P["turn_rate_open"]
        diff = _wrap(want - e.facing)
        max_turn = turn * dt
        e.facing = _wrap(e.facing + max(-max_turn, min(max_turn, diff)))

        # move forward along facing only once roughly aligned (formed troops do not crab sideways)
        if abs(_wrap(want - e.facing)) > math.radians(30) and e.formed:
            continue
        rough = w.terrain.is_rough(e.x, e.y)
        jitter = w.rng.gen("movement", e.id).normal(0.0, P["pace_jitter"])
        speed = _pace(e, P) * (1.0 + jitter) * (1.0 - P["fatigue_pace_penalty"] * e.fatigue)
        if rough:
            speed *= P["rough_pace_factor"]
        speed = max(0.0, speed)
        step_len = min(speed * dt, dist)
        nx = e.x + math.cos(e.facing) * step_len
        ny = e.y + math.sin(e.facing) * step_len
        if w.terrain.inside(nx, ny):
            e.x, e.y = nx, ny
        e.fatigue = min(1.0, e.fatigue + P["fatigue_per_min_moving"] * dt / 60.0)
        if rough and e.formed:
            e.order = max(0.0, e.order - P["rough_order_loss_per_100m"] * step_len / 100.0)
