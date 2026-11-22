"""Messengers: riders (or runners) carrying orders and reports across the field (specification 5.5).

Reads:  messengers; the recipient's and sender's true positions and liveness (a messenger
        physically finds the man he is looking for when he can see him, and physically hands
        the message over); enemy entities near a messenger and whether they can see him
        (physical interception); terrain; params.
Writes: messenger positions, routes and status; w.staff (when a messenger returns); events; and,
        through command.deliver, orders and beliefs.
Random: counter-based keyed draws on stream "messengers", keyed by (*message key, tick), so one
        messenger's fate never shifts another's.

Each tick, a messenger riding out (Codex review 005, findings 3 and 4):
  1. looks for the recipient: once he can see him (within `messenger_sight_m`, line of sight)
     he rides to him;
  2. moves along his route (replanned when it is used up short of the goal, or the goal moves
     more than `messenger_retarget_m`);
  3. runs the risks of the ride: caught by enemy troops within `intercept_radius_m` who can see
     him, or lost by accident (`messenger_loss_per_km`). Interception comes before handoff;
  4. hands the message over only when he is within `deliver_radius_m` of the recipient with
     open ground between them, and the recipient is alive (if not, the message fails);
  5. gives up after `search_time_s` searching where he expected the recipient, or after
     `search_time_s` without progress (no route, or a barrier).
Riding back, the same access rule applies at his sender's side, and after `search_time_s`
without progress he is stranded (lost to his sender). If his sender is dead he is dismissed.
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
    mob = w.commander(sender).mobility if sender in w.commanders_by_id else w.entity(sender).equipment.mobility
    dest = command.believed_position(w, sender, m.recipient)
    ms = om.Messenger(key=tuple(m.key), sender=sender, message=m, mobility=mob, x=sx, y=sy, dest=tuple(dest))
    w.messengers.append(ms)
    if m.order is not None:
        om.transition(w, m.order, "sent", {"messenger": ms.id, "riding_to": list(dest)})
    om.fold(w, "launched", ms.id, list(dest))
    record.log(w, "messenger_sent", sender, {"messenger": ms.id, "message": m.id, "to": m.recipient,
                                             "riding_to": list(dest)},
               [{"order": m.id} if m.order is not None else {"message": m.id}])


def _speed(w, ms) -> float:
    P = w.params
    return P["messenger_speed_horse"] if ms.mobility == "horse" else P["messenger_speed_foot"]


def _move(w, ms, tx: float, ty: float):
    """Move along a planned route towards (tx, ty). Returns the distance travelled, or None if
    there is no route there."""
    t = w.terrain
    P = w.params
    cls = "horse" if ms.mobility == "horse" else "open"
    goal = [float(tx), float(ty)]
    if not t.passable(*goal):
        return None
    far = math.hypot(goal[0] - ms.x, goal[1] - ms.y) > 1e-6
    if (ms.route is None or ms.route_for is None or (not ms.route and far)
            or math.hypot(ms.route_for[0] - goal[0], ms.route_for[1] - goal[1]) > P["messenger_retarget_m"]):
        r = pathing.plan(t, P, cls, ms.x, ms.y, goal[0], goal[1])
        if r is None:
            ms.route = None
            return None
        ms.route, ms.route_for = [list(p) for p in r], goal
    budget = min(_speed(w, ms), P["max_speed_any"]) * P["tick_seconds"]
    moved = 0.0
    while ms.route and budget > 1e-9:
        wx, wy = ms.route[0]
        d = math.hypot(wx - ms.x, wy - ms.y)
        if d <= 1e-9:
            ms.route.pop(0)
            continue
        f = pathing.pace_factor(P, cls, t.ground_at(ms.x, ms.y))
        step = min(d, budget * f)
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


def _reach(w, ms, x: float, y: float) -> bool:
    """A physical handoff: close enough, with open ground between them."""
    return (math.hypot(x - ms.x, y - ms.y) <= w.params["deliver_radius_m"]
            and w.terrain.segment_passable(ms.x, ms.y, x, y))


def _risk(w, ms, moved: float) -> str | None:
    """Interception by enemy troops who can see him, or loss by accident. Returns the outcome or None."""
    P = w.params
    side = command.side_of(w, ms.sender)
    near = [e for e in w.entities if e.side != side and e.fit > 0
            and math.hypot(e.x - ms.x, e.y - ms.y) <= P["intercept_radius_m"]]
    u = keyed_uniforms(w.seed, "messengers", [np.array([k]) for k in ms.key] + [np.array([w.tick])], 2)[0]
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
    if o is not None:
        if o.status not in om.TERMINAL:
            om.fail(w, o, "delivered", why, {"messenger": ms.id})
            record.log(w, "order_failed", ms.sender, {"order": o.id, "at": "delivered", "why": why}, [{"order": o.id}])
    else:
        om.fold(w, "report_lost", ms.id, why)
        record.log(w, "report_lost", ms.sender, {"message": ms.message.id, "why": why}, [{"message": ms.message.id}])


def _set(w, ms, status: str) -> None:
    ms.status = status
    ms.route = ms.route_for = None
    ms.stuck_ticks = 0
    om.fold(w, "messenger", ms.id, status)


def _ref(ms) -> dict:
    return {"order": ms.message.id} if ms.message.order is not None else {"message": ms.message.id}


def _outward(w, ms) -> None:
    P = w.params
    m = ms.message
    rx, ry = command.position_of(w, m.recipient)
    seen = _can_see(w, ms, rx, ry, _mobility(w, m.recipient))
    if seen:
        ms.dest = (rx, ry)
        if ms.status == "searching":
            ms.status = "riding"
            ms.search_ticks = 0
    moved = 0.0
    if ms.status == "riding":
        got = _move(w, ms, *ms.dest)
        moved = got or 0.0
        arrived = math.hypot(ms.dest[0] - ms.x, ms.dest[1] - ms.y) <= P["deliver_radius_m"]
        if (arrived or got is None) and not seen:
            ms.status = "searching"
            om.fold(w, "messenger", ms.id, "searching")
            record.log(w, "messenger_searching", ms.sender, {"messenger": ms.id, "at": [ms.x, ms.y]},
                       [{"note": "the recipient is not where he was expected"}])
        ms.stuck_ticks = 0 if moved > 1e-6 else ms.stuck_ticks + 1
    outcome = _risk(w, ms, moved)
    ms.ridden_m += moved
    if outcome:
        _fail_message(w, ms, f"messenger {outcome}")
        _set(w, ms, outcome)
        record.log(w, f"messenger_{outcome}", ms.sender, {"messenger": ms.id, "at": [ms.x, ms.y]},
                   [{"note": "caught by enemy troops" if outcome == "captured" else "lost by accident"}])
        return
    if _reach(w, ms, rx, ry):
        if not command.alive(w, m.recipient):
            why = "the recipient is dead" if m.recipient in w.commanders_by_id else "the recipient's unit has no men left fit"
            _fail_message(w, ms, why)
        else:
            command.deliver(w, m)
            record.log(w, "messenger_delivered", ms.sender, {"messenger": ms.id, "to": m.recipient}, [_ref(ms)])
        _set(w, ms, "returning")
        return
    if ms.status == "searching":
        ms.search_ticks += 1
        if ms.search_ticks * P["tick_seconds"] >= P["search_time_s"]:
            _fail_message(w, ms, "the messenger could not find the recipient")
            _set(w, ms, "returning")
    elif ms.stuck_ticks * P["tick_seconds"] >= P["search_time_s"]:
        _fail_message(w, ms, "the messenger could not reach the recipient")
        _set(w, ms, "returning")


def _back(w, ms) -> None:
    P = w.params
    sx, sy = command.position_of(w, ms.sender)
    if _reach(w, ms, sx, sy):
        if command.alive(w, ms.sender):
            _set(w, ms, "home")
            w.staff[ms.sender] = w.staff.get(ms.sender, 0) + 1
            record.log(w, "messenger_returned", ms.sender, {"messenger": ms.id}, [{"note": "back with his sender"}])
        else:
            _set(w, ms, "dismissed")
            record.log(w, "messenger_dismissed", ms.sender, {"messenger": ms.id}, [{"note": "his sender is dead"}])
        return
    moved = _move(w, ms, sx, sy) or 0.0
    ms.stuck_ticks = 0 if moved > 1e-6 else ms.stuck_ticks + 1
    outcome = _risk(w, ms, moved)
    ms.ridden_m += moved
    if outcome:
        _set(w, ms, outcome)
        record.log(w, f"messenger_{outcome}", ms.sender, {"messenger": ms.id, "at": [ms.x, ms.y]},
                   [{"note": "on the way back"}])
    elif ms.stuck_ticks * P["tick_seconds"] >= P["search_time_s"]:
        _set(w, ms, "stranded")
        record.log(w, "messenger_stranded", ms.sender, {"messenger": ms.id, "at": [ms.x, ms.y]},
                   [{"note": "no way back to his sender"}])


def step(w) -> None:
    for ms in w.messengers:
        if ms.status in ("riding", "searching"):
            _outward(w, ms)
        elif ms.status == "returning":
            _back(w, ms)
