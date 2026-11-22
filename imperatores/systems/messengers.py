"""Messengers: riders (or runners) carrying orders and reports across the field (specification 5.5).

Reads:  messengers; the recipient's and sender's true positions (a messenger physically finds
        the man he is looking for when he can see him); enemy entities near a messenger and
        whether they can see him (physical interception); terrain; params.
Writes: messenger positions, routes and status; w.staff (when a messenger returns); events; and,
        through command.deliver, orders and beliefs.
Random: counter-based keyed draws on stream "messengers", keyed by (sender, message number,
        tick), so one messenger's fate never shifts another's.

A messenger rides towards where his sender believed the recipient to be. Each tick he looks for
the recipient: once he can see him (within `messenger_sight_m`, line of sight) he rides to him;
within `deliver_radius_m` he delivers. If he reaches the expected place without finding him he
searches there for up to `search_time_s`, then gives up. After delivering, or giving up, he rides
back to his sender and is available again. On the way he may be caught by enemy troops within
`intercept_radius_m` who can see him, or lost by accident (`messenger_loss_per_km`).
"""
from __future__ import annotations

import math

import numpy as np

from .. import orders as om
from .. import pathing, record, sight
from ..rng import keyed_uniforms
from . import command


def launch(w, sender: int, m: om.Message) -> None:
    sx, sy = command.position_of(w, sender)
    if sender in w.commanders_by_id:
        mob = w.commander(sender).mobility
    else:
        mob = w.entity(sender).equipment.mobility
    seq = int(m.id.split(".")[1])
    dest = command.believed_position(w, sender, m.recipient)
    ms = om.Messenger(key=(sender, seq), sender=sender, message=m, mobility=mob, x=sx, y=sy, dest=tuple(dest))
    w.messengers.append(ms)
    if m.order is not None:
        m.order.status = "sent"
        m.order.stage(w, "sent", {"messenger": ms.id, "riding_to": list(dest)})
    record.log(w, "messenger_sent", sender, {"messenger": ms.id, "message": m.id, "to": m.recipient,
                                             "riding_to": list(dest)},
               [{"order": m.id} if m.order is not None else {"message": m.id}])


def _speed(w, ms) -> float:
    P = w.params
    return P["messenger_speed_horse"] if ms.mobility == "horse" else P["messenger_speed_foot"]


def _move(w, ms, tx: float, ty: float) -> float:
    """Move along a planned route towards (tx, ty). Returns the distance travelled, or None if
    there is no route there."""
    t = w.terrain
    P = w.params
    cls = "horse" if ms.mobility == "horse" else "open"
    goal = [float(tx), float(ty)]
    if not t.passable(*goal):
        return None
    if ms.route is None or ms.route_for is None or math.hypot(ms.route_for[0] - goal[0], ms.route_for[1] - goal[1]) > 20.0:
        r = pathing.plan(t, P, cls, ms.x, ms.y, goal[0], goal[1])
        if r is None:
            return None
        ms.route, ms.route_for = [list(p) for p in r], goal
    budget = min(_speed(w, ms), P["max_speed_any"]) * P["tick_seconds"]
    moved = 0.0
    while ms.route and budget > 1e-9:
        wx, wy = ms.route[0]
        d = math.hypot(wx - ms.x, wy - ms.y)
        f = pathing.pace_factor(P, cls, t.ground_at(ms.x, ms.y))
        step = min(d, budget * f)
        if d <= 1e-9:
            ms.route.pop(0)
            continue
        nx, ny = (wx, wy) if step >= d else (ms.x + (wx - ms.x) / d * step, ms.y + (wy - ms.y) / d * step)
        if not t.segment_passable(ms.x, ms.y, nx, ny):
            ms.route = None
            break
        ms.x, ms.y = nx, ny
        moved += step
        budget -= step / max(f, 1e-9)
        if step >= d:
            ms.route.pop(0)
    return moved


def _can_see(w, ms, x: float, y: float, target_mobility: str) -> bool:
    P = w.params
    if math.hypot(x - ms.x, y - ms.y) > P["messenger_sight_m"]:
        return False
    return sight.line_of_sight(w.terrain, P, ms.x, ms.y, sight.eye_height(ms.mobility, P), x, y,
                               sight.target_height(target_mobility, P))


def _mobility(w, i: int) -> str:
    return w.by_id[i].equipment.mobility if i in w.by_id else w.commanders_by_id[i].mobility


def _risk(w, ms, moved: float) -> str | None:
    """Interception by enemy troops who can see him, or loss by accident. Returns the outcome or None."""
    P = w.params
    side = command.side_of(w, ms.sender)
    near = [e for e in w.entities if e.side != side and e.fit > 0
            and math.hypot(e.x - ms.x, e.y - ms.y) <= P["intercept_radius_m"]]
    u = keyed_uniforms(w.seed, "messengers", [np.array([ms.key[0]]), np.array([ms.key[1]]), np.array([w.tick])], 2)[0]
    if near:
        seen_by = sight.visible_pairs(w.terrain, P, np.array([e.x for e in near]), np.array([e.y for e in near]),
                                      np.array([sight.eye_height(e.equipment.mobility, P) for e in near]),
                                      np.full(len(near), ms.x), np.full(len(near), ms.y),
                                      np.full(len(near), sight.target_height(ms.mobility, P)))
        rate = 0.0
        for e, s in zip(near, seen_by):
            if s:
                factor = P["intercept_mounted_factor"] if e.function in ("skirmishers", "light_cavalry", "heavy_cavalry") else 1.0
                rate += P["intercept_per_min"] * factor
        p = 1.0 - math.exp(-rate * P["tick_seconds"] / 60.0)
        if u[0] < p:
            return "captured"
    if u[1] < P["messenger_loss_per_km"] * moved / 1000.0:
        return "lost"
    return None


def _fail_message(w, ms, why: str) -> None:
    o = ms.message.order
    if o is not None and o.status not in ("failed", "executed"):
        o.fail(w, "delivered", why, {"messenger": ms.id})
        record.log(w, "order_failed", ms.sender, {"order": o.id, "at": "delivered", "why": why}, [{"order": o.id}])
    elif ms.message.kind == "report":
        record.log(w, "report_lost", ms.sender, {"message": ms.message.id, "why": why}, [{"message": ms.message.id}])


def step(w) -> None:
    P = w.params
    for ms in w.messengers:
        if ms.status in ("home", "lost", "captured"):
            continue
        m = ms.message
        if ms.status in ("riding", "searching"):
            rx, ry = command.position_of(w, m.recipient)
            if math.hypot(rx - ms.x, ry - ms.y) <= P["deliver_radius_m"]:
                command.deliver(w, m)
                ms.status, ms.route = "returning", None
                record.log(w, "messenger_delivered", ms.sender, {"messenger": ms.id, "to": m.recipient},
                           [{"order": m.id} if m.order is not None else {"message": m.id}])
                continue
            if _can_see(w, ms, rx, ry, _mobility(w, m.recipient)):
                ms.dest = (rx, ry)
                if ms.status == "searching":
                    ms.status = "riding"
            moved = 0.0
            if ms.status == "riding":
                got = _move(w, ms, *ms.dest)
                moved = got or 0.0
                arrived = math.hypot(ms.dest[0] - ms.x, ms.dest[1] - ms.y) <= P["deliver_radius_m"]
                if (arrived or got is None) and not _can_see(w, ms, rx, ry, _mobility(w, m.recipient)):
                    ms.status = "searching"
                    record.log(w, "messenger_searching", ms.sender, {"messenger": ms.id, "at": [ms.x, ms.y]},
                               [{"note": "the recipient is not where he was expected"}])
            else:
                ms.search_ticks += 1
                if ms.search_ticks * P["tick_seconds"] >= P["search_time_s"]:
                    _fail_message(w, ms, "the messenger could not find the recipient")
                    ms.status, ms.route = "returning", None
                    continue
            outcome = _risk(w, ms, moved)
            ms.ridden_m += moved
            if outcome:
                ms.status = outcome
                _fail_message(w, ms, f"messenger {outcome}")
                record.log(w, f"messenger_{outcome}", ms.sender, {"messenger": ms.id, "at": [ms.x, ms.y]},
                           [{"note": "caught by enemy troops" if outcome == "captured" else "lost by accident"}])
        elif ms.status == "returning":
            sx, sy = command.position_of(w, ms.sender)
            if math.hypot(sx - ms.x, sy - ms.y) <= P["deliver_radius_m"]:
                ms.status = "home"
                w.staff[ms.sender] = w.staff.get(ms.sender, 0) + 1
                record.log(w, "messenger_returned", ms.sender, {"messenger": ms.id}, [{"note": "back with his sender"}])
                continue
            moved = _move(w, ms, sx, sy) or 0.0
            outcome = _risk(w, ms, moved)
            ms.ridden_m += moved
            if outcome:
                ms.status = outcome
                record.log(w, f"messenger_{outcome}", ms.sender, {"messenger": ms.id, "at": [ms.x, ms.y]},
                           [{"note": "on the way back"}])
