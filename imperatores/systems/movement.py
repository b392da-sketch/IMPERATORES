"""Movement, facing, fatigue and order on the march.

Reads:  entity task, position, facing, function, equipment.mobility, fatigue, order; terrain; params.
Writes: entity x, y, facing, fatigue, order, task (a "route" is added when a move is planned;
        the task becomes "hold" on arrival or when no route exists); events "arrived", "no_route".
Random: stream "movement", keyed by stable entity id (pace variation).

A move_to task is planned into a route of waypoints the first time it is seen (pathing.py),
then followed. Pace depends on movement class and ground, and slows uphill. Formed troops
lose order crossing rough ground, woods and fords. No collisions between entities yet.

Pace is capped at max_speed_any, the physical limit; the consistency check enforces the
same limit independently (Codex review 002, finding 3). Fatigue and loss of order are
charged on distance actually travelled; a blocked move costs nothing (finding 8).
"""
from __future__ import annotations

import math

from .. import pathing, record
from ..terrain import FORD, ROUGH, WOODS

_ORDER_LOSS = {ROUGH: "order_loss_rough_per_100m", WOODS: "order_loss_woods_per_100m",
               FORD: "order_loss_ford_per_100m"}


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _base_pace(e, P) -> float:
    if e.function == "heavy_infantry":
        return P["pace_infantry_formed"]
    if e.function == "skirmishers":
        return P["pace_skirmisher"]
    return P["pace_cavalry"]


def _plan(w, e) -> bool:
    tx, ty = float(e.task["x"]), float(e.task["y"])
    route = pathing.plan(w.terrain, w.params, pathing.movement_class(e), e.x, e.y, tx, ty)
    if route is None:
        e.task = {"kind": "hold"}
        record.log(w, "no_route", e.id, {"target": [tx, ty]},
                   [{"note": "no passable route to the movement target"}])
        return False
    e.task["route"] = [[x, y] for x, y in route]
    return True


def step(w) -> None:
    P = w.params
    dt = P["tick_seconds"]
    t = w.terrain
    for e in w.entities:
        if e.fit <= 0:
            continue
        if e.task.get("kind") != "move_to":
            e.order = min(1.0, e.order + P["order_recovery_per_min_halted"] * dt / 60.0)
            e.fatigue = max(0.0, e.fatigue - P["fatigue_recovery_per_min_halted"] * dt / 60.0)
            continue
        if "route" not in e.task and not _plan(w, e):
            continue

        route = e.task["route"]
        while route and math.hypot(route[0][0] - e.x, route[0][1] - e.y) <= P["arrival_tolerance"]:
            route.pop(0)
        if not route:
            target = [float(e.task["x"]), float(e.task["y"])]
            e.task = {"kind": "hold"}
            record.log(w, "arrived", e.id, {"x": e.x, "y": e.y, "target": target},
                       [{"note": "reached its movement target"}])
            continue

        wx, wy = route[0]
        dx, dy = wx - e.x, wy - e.y
        dist = math.hypot(dx, dy)
        want = math.atan2(dy, dx)
        turn = P["turn_rate_formed"] if e.formed else P["turn_rate_open"]
        diff = _wrap(want - e.facing)
        max_turn = turn * dt
        e.facing = _wrap(e.facing + max(-max_turn, min(max_turn, diff)))
        if e.formed and abs(_wrap(want - e.facing)) > math.radians(P["formed_move_alignment_deg"]):
            continue                                   # formed troops wheel before moving off

        ground = t.ground_at(e.x, e.y)
        cls = pathing.movement_class(e)
        jitter = w.rng.gen("movement", e.id).normal(0.0, P["pace_jitter"])
        speed = _base_pace(e, P) * (1.0 + jitter) * (1.0 - P["fatigue_pace_penalty"] * e.fatigue)
        speed *= pathing.pace_factor(P, cls, ground)
        ahead = min(5.0, dist)
        if ahead > 0:
            ax, ay = e.x + math.cos(e.facing) * ahead, e.y + math.sin(e.facing) * ahead
            grad = (t.height_at(ax, ay) - t.height_at(e.x, e.y)) / ahead
            if grad > 0:
                speed /= 1.0 + P["slope_pace_k"] * grad
        speed = min(max(0.0, speed), P["max_speed_any"])
        step_len = min(speed * dt, dist)
        nx = e.x + math.cos(e.facing) * step_len
        ny = e.y + math.sin(e.facing) * step_len
        if not t.segment_passable(e.x, e.y, nx, ny):
            continue                                   # blocked (field edge or stream): no movement, no cost
        e.x, e.y = nx, ny
        if step_len > 0:
            e.fatigue = min(1.0, e.fatigue + P["fatigue_per_min_moving"] * (step_len / max(speed, 1e-9)) / 60.0)
            if e.formed and ground in _ORDER_LOSS:
                e.order = max(0.0, e.order - P[_ORDER_LOSS[ground]] * step_len / 100.0)

