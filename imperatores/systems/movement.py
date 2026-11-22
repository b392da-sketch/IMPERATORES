"""Movement, facing, fatigue and order on the march.

Reads:  entity task, route, position, facing, function, equipment.mobility, fatigue, order;
        terrain; params.
Writes: entity x, y, facing, fatigue, order, route, route_for, blocked_ticks, task (to "hold"
        on arrival, or when no route exists); events "arrived", "no_route", "replanned",
        "stalled".
Random: stream "movement", keyed by stable entity id (pace variation).

Routes are engine-owned (Codex review 003, finding 9): planned here for the task's target,
stored on the entity with the target they were planned for, and replanned whenever the
target changes. Scenarios cannot supply them.

Following a route (finding 2): an entity moves straight towards its current waypoint, so it
stays on the leg the planner checked. A formed body must first wheel until its facing is
within `formed_move_alignment_deg` of the leg; its facing is then its orientation, and its
movement stays on the leg. Intermediate waypoints are reached exactly; the arrival
tolerance applies only to the final target. A blocked step costs nothing; after
`stall_replan_ticks` blocked steps the entity replans from where it stands, and if no route
exists it halts and the stall is recorded.

Pace depends on movement class and ground, and slows uphill. Formed troops lose order
crossing rough ground, woods and fords. No collisions between entities yet. Pace is capped
at max_speed_any; fatigue and loss of order are charged on distance actually travelled.
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


def _halt(e) -> None:
    e.task = {"kind": "hold"}
    e.route = e.route_for = None
    e.blocked_ticks = 0


def _plan(w, e, why: str) -> bool:
    tx, ty = float(e.task["x"]), float(e.task["y"])
    if not w.terrain.inside(tx, ty):
        _halt(e)
        record.log(w, "no_route", e.id, {"target": [tx, ty], "at": [e.x, e.y]},
                   [{"note": "the movement target is off the field"}])
        return False
    route = pathing.plan(w.terrain, w.params, pathing.movement_class(e), e.x, e.y, tx, ty)
    if route is None:
        kind = "no_route" if why == "new target" else "stalled"
        _halt(e)
        record.log(w, kind, e.id, {"target": [tx, ty], "at": [e.x, e.y]},
                   [{"note": f"no passable route to the movement target ({why})"}])
        return False
    e.route = [[x, y] for x, y in route]
    e.route_for = [tx, ty]
    e.blocked_ticks = 0
    if why != "new target":
        record.log(w, "replanned", e.id, {"target": [tx, ty], "at": [e.x, e.y]}, [{"note": why}])
    return True


def step(w) -> None:
    P = w.params
    dt = P["tick_seconds"]
    t = w.terrain
    for e in w.entities:
        if e.fit <= 0:
            continue
        if e.task.get("kind") != "move_to":
            if e.route is not None:
                e.route = e.route_for = None
            e.order = min(1.0, e.order + P["order_recovery_per_min_halted"] * dt / 60.0)
            e.fatigue = max(0.0, e.fatigue - P["fatigue_recovery_per_min_halted"] * dt / 60.0)
            continue
        target = [float(e.task["x"]), float(e.task["y"])]
        if e.route is None or e.route_for != target:
            if not _plan(w, e, "new target"):
                continue

        final = len(e.route) == 1
        wx, wy = e.route[0]
        dist = math.hypot(wx - e.x, wy - e.y)
        if final and dist <= P["arrival_tolerance"]:
            _halt(e)
            record.log(w, "arrived", e.id, {"x": e.x, "y": e.y, "target": target},
                       [{"note": "reached its movement target"}])
            continue
        if dist <= 1e-9:                               # exactly on an intermediate waypoint
            e.route.pop(0)
            continue

        want = math.atan2(wy - e.y, wx - e.x)
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
        ahead = min(P["slope_lookahead_m"], dist)
        ux, uy = (wx - e.x) / dist, (wy - e.y) / dist
        grad = (t.height_at(e.x + ux * ahead, e.y + uy * ahead) - t.height_at(e.x, e.y)) / ahead
        if grad > 0:
            speed /= 1.0 + P["slope_pace_k"] * grad
        speed = min(max(0.0, speed), P["max_speed_any"])
        step_len = min(speed * dt, dist)
        if step_len >= dist:
            nx, ny = wx, wy                            # land exactly on the waypoint
        else:
            nx, ny = e.x + ux * step_len, e.y + uy * step_len
        if not t.segment_passable(e.x, e.y, nx, ny):
            e.blocked_ticks += 1                       # blocked: no movement, no cost
            if e.blocked_ticks >= P["stall_replan_ticks"]:
                _plan(w, e, f"blocked for {e.blocked_ticks} ticks; replanning from where it stands")
            continue
        e.blocked_ticks = 0
        e.x, e.y = nx, ny
        if step_len >= dist and not final:
            e.route.pop(0)
        if step_len > 0:
            e.fatigue = min(1.0, e.fatigue + P["fatigue_per_min_moving"] * (step_len / max(speed, 1e-9)) / 60.0)
            if e.formed and ground in _ORDER_LOSS:
                e.order = max(0.0, e.order - P[_ORDER_LOSS[ground]] * step_len / 100.0)
