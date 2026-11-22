"""Command: issuing, dispatching, understanding, relaying and executing orders; signals; plans.

Reads:  scenario inputs; commanders and entities (positions, command, state); belief pictures
        (views only, for describing and understanding targets and for plan conditions); plans;
        params.
Writes: w.orders, w.outbox, w.messengers (new ones), w.staff, w.seq, w.pending; entity tasks
        (when an order is executed); events. Never reads the true state of the enemy.
Random: keyed draws on stream "signals" (misattribution), keyed by (issuer, signal number, entity).

See imperatores/orders.py for the model. Messengers' movement and delivery are in messengers.py,
which calls `deliver` here.
"""
from __future__ import annotations

import math

import numpy as np

from .. import belief as belief_mod
from .. import orders as om
from .. import record, sight
from ..rng import keyed_uniforms


# ---- helpers --------------------------------------------------------------------------------

def next_seq(w, sender: int) -> int:
    n = w.seq.get(sender, 0) + 1
    w.seq[sender] = n
    return n


def staff_size(w, sender: int) -> int:
    P = w.params
    if sender in w.commanders_by_id:
        return P["messengers_army"] if w.commander(sender).rank == "army" else P["messengers_wing"]
    return P["runners_entity"]


def ensure_staff(w) -> None:
    for c in w.commanders:
        w.staff.setdefault(c.id, staff_size(w, c.id))
    for e in w.entities:
        w.staff.setdefault(e.id, staff_size(w, e.id))


def position_of(w, i: int) -> tuple:
    if i in w.by_id:
        e = w.by_id[i]
        return (e.x, e.y)
    c = w.commanders_by_id[i]
    return (c.x, c.y)


def side_of(w, i: int) -> str:
    return w.by_id[i].side if i in w.by_id else w.commanders_by_id[i].side


def believed_position(w, sender: int, recipient: int) -> tuple:
    """Where the sender thinks the recipient is: his own track of a friendly entity, else its
    place in the deployment plan. Commanders stand still in M0, so their positions are known
    to their own side (an assumption that ends when commanders move, step 5)."""
    if recipient in w.commanders_by_id:
        c = w.commanders_by_id[recipient]
        return (c.x, c.y)
    b = w.beliefs.get(sender)
    h = belief_mod.handle_of(b, recipient) if b is not None else None
    if h is not None:
        c = b.tracks[h]
        return (c.x, c.y)
    if recipient in w.plans:
        return w.plans[recipient].home
    return position_of(w, recipient)          # own deployment, known from the plan of battle


def command_of(w, cid: int) -> list[int]:
    """All entities under a commander, through his wing commanders."""
    out = []
    for i in w.commanders_by_id[cid].commands:
        if i in w.commanders_by_id:
            out.extend(command_of(w, i))
        else:
            out.append(i)
    return out


def describe_target(w, issuer: int, spec: dict):
    """The issuer's description of a body, from his own picture: his nearest contact of the given
    side to the given point. Returns (TargetDescription, intended true id or None) or (None, None)."""
    v = belief_mod.view(w, issuer)
    nx, ny = spec["near"]
    best, best_d = None, math.inf
    for c in v.contacts:
        if c.side != spec["side"]:
            continue
        d = math.hypot(c.x - nx, c.y - ny)
        if d < best_d:
            best, best_d = c, d
    if best is None:
        return None, None
    true_of = {h: t for t, h in w.beliefs[issuer]._truth.items()}
    return om.TargetDescription(side=best.side, kind=best.kind, x=best.x, y=best.y, seen_t=best.seen_t), \
        true_of.get(best.handle)


# ---- issuing ----------------------------------------------------------------------------------

def issue(w, issuer: int, recipient: int, spec: dict, origin: str, parent=None, oid=None):
    """Create an order and put it in the issuer's outbox (or act on it at once if self-addressed)."""
    belief_mod_ensure(w)
    oid = oid or f"{issuer}.{next_seq(w, issuer)}"
    target_spec = spec.get("target")
    o = om.order_from_spec(oid, issuer, recipient, {k: v for k, v in spec.items() if k != "target"}, origin, parent)
    if isinstance(target_spec, om.TargetDescription):
        o.target = target_spec
        o.intended = spec.get("_intended")
    elif o.kind in om.TARGET_KINDS:
        o.target, o.intended = describe_target(w, issuer, target_spec)
    w.orders[oid] = o
    detail = {"origin": origin, "kind": o.kind}
    if parent:
        detail["relays"] = parent
    o.stage(w, "decided", detail)
    record.log(w, "order_decided", issuer, {"order": oid, "recipient": recipient, "kind": o.kind},
               [{"order": parent} if parent else {"note": f"order from {origin}"}])
    if o.kind in om.TARGET_KINDS and o.target is None:
        o.fail(w, "decided", "the issuer knows of no such body")
        record.log(w, "order_failed", issuer, {"order": oid}, [{"order": oid}])
        return o
    if issuer == recipient:
        o.status = "delivered"
        o.stage(w, "delivered", {"how": "own decision"})
        on_delivered(w, o)
        return o
    w.outbox.setdefault(issuer, []).append(om.Message(id=oid, kind="order", sender=issuer, recipient=recipient,
                                                      created_t=w.tick, order=o))
    return o


def belief_mod_ensure(w) -> None:
    from . import perception
    perception.ensure_beliefs(w)
    ensure_staff(w)


def send_report(w, sender: int, recipient: int) -> om.Message:
    belief_mod_ensure(w)
    mid = f"{sender}.{next_seq(w, sender)}"
    contacts = belief_mod.view(w, sender).contacts          # immutable values, captured now
    m = om.Message(id=mid, kind="report", sender=sender, recipient=recipient, created_t=w.tick, contacts=contacts)
    w.outbox.setdefault(sender, []).append(m)
    record.log(w, "report_written", sender, {"message": mid, "recipient": recipient, "contacts": len(contacts)},
               [{"note": "report input"}])
    return m


def dispatch(w) -> None:
    from . import messengers as ms
    for sender in sorted(w.outbox):
        box = w.outbox[sender]
        while box and w.staff.get(sender, 0) > 0:
            m = box.pop(0)
            w.staff[sender] -= 1
            ms.launch(w, sender, m)
        for m in box:
            if m.order is not None and not any(s[0] == "waiting for a messenger" for s in m.order.stages):
                m.order.stage(w, "waiting for a messenger", {})


# ---- delivery, understanding, relay, execution --------------------------------------------------

def deliver(w, m: om.Message) -> None:
    """Called by the messengers system when a messenger reaches his recipient."""
    if m.kind == "report":
        changed = belief_mod.apply_report(w, m.recipient, list(m.contacts), m.sender, w.tick)
        record.log(w, "report_delivered", m.recipient, {"message": m.id, "from": m.sender, "tracks_changed": len(changed)},
                   [{"message": m.id}])
        return
    o = m.order
    o.status = "delivered"
    o.stage(w, "delivered", {})
    record.log(w, "order_delivered", m.recipient, {"order": o.id}, [{"order": o.id}])
    on_delivered(w, o)


def on_delivered(w, o: om.Order) -> None:
    v = belief_mod.view(w, o.recipient)
    if not om.understand(w, o, v):
        record.log(w, "order_failed", o.recipient, {"order": o.id, "at": "understood"}, [{"order": o.id}])
        return
    record.log(w, "order_understood", o.recipient, {"order": o.id}, [{"order": o.id}])
    if o.recipient in w.commanders_by_id:
        relay(w, o)
        return
    w.pending[o.recipient] = [o.id, w.tick]
    try_execute(w, o.recipient)


def relay(w, o: om.Order) -> None:
    """A commander passes an order on to every entity and wing commander directly under him."""
    c = w.commander(o.recipient)
    children = []
    for i in c.commands:
        spec = {"kind": o.kind, "latitude": o.latitude}
        if o.place:
            spec["place"] = o.place
        if o.target is not None:
            spec["target"] = o.target            # the description is passed on as received
            spec["_intended"] = o.intended
        child = issue(w, c.id, i, spec, origin="relay", parent=o.id)
        children.append(child.id)
    o.status = "executed"
    o.stage(w, "executed", {"relayed_to": children})
    record.log(w, "order_relayed", c.id, {"order": o.id, "to": children}, [{"order": o.id}])


def try_execute(w, eid: int) -> None:
    P = w.params
    oid, since = w.pending[eid]
    o = w.orders[oid]
    e = w.entity(eid)
    if e.fit <= 0:
        del w.pending[eid]
        o.fail(w, "executed", "the entity has no men left fit")
        record.log(w, "order_failed", eid, {"order": oid, "at": "executed"}, [{"order": oid}])
        return
    if o.kind != "hold":
        blocked = None
        if e.order < P["disordered_order"]:
            blocked = "disordered: must reform first"
        elif e.fatigue > P["exhausted_fatigue"]:
            blocked = "exhausted: must rest first"
        if blocked:
            waited = (w.tick - since) * P["tick_seconds"]
            if waited >= P["order_wait_timeout_s"]:
                del w.pending[eid]
                o.fail(w, "executed", f"not executable: {blocked}", {"waited_s": waited})
                record.log(w, "order_failed", eid, {"order": oid, "at": "executed", "why": blocked}, [{"order": oid}])
            elif not any(s[0] == "waiting to execute" for s in o.stages):
                o.stage(w, "waiting to execute", {"why": blocked})
            return
    del w.pending[eid]
    if o.kind == "hold":
        e.task = {"kind": "hold", "order": oid}
    elif o.kind in om.PLACE_KINDS:
        e.task = {"kind": "move_to", "x": float(o.place[0]), "y": float(o.place[1]), "order": oid}
    else:
        standoff = P["approach_standoff_m"] if o.kind == "attack" else P["support_distance_m"]
        e.task = {"kind": "approach", "handle": int(o.understood_handle), "standoff": float(standoff), "order": oid}
    e.route = e.route_for = None
    o.status = "executed"
    o.stage(w, "executed", {"task": e.task["kind"], "note": "carried out (no decision layer until step 5)"})
    record.log(w, "order_executed", eid, {"order": oid, "task": e.task["kind"]}, [{"order": oid}])


# ---- signals -------------------------------------------------------------------------------------

def emit_signal(w, issuer: int, meaning: str, to) -> None:
    P = w.params
    belief_mod_ensure(w)
    if not om.valid_signal(meaning):
        raise ValueError(f"unknown signal {meaning!r}")
    n = next_seq(w, issuer)
    sid = f"{issuer}.{n}"
    c = w.commander(issuer)
    addressed = set(command_of(w, issuer) if to == "all" else to)
    record.log(w, "signal_emitted", issuer, {"signal": sid, "meaning": meaning, "to": sorted(addressed),
                                             "extension": meaning in om.SIGNAL_EXTENSIONS},
               [{"note": "signal input"}])
    hearers = [e for e in w.entities if e.side == c.side and e.fit > 0]
    if not hearers:
        return
    ex = np.array([e.x for e in hearers])
    ey = np.array([e.y for e in hearers])
    los = sight.visible_pairs(w.terrain, P, np.full(len(hearers), c.x), np.full(len(hearers), c.y),
                              np.full(len(hearers), sight.eye_height(c.mobility, P)), ex, ey,
                              np.array([sight.target_height(e.equipment.mobility, P) for e in hearers]))
    rng = np.where(los, P["signal_range_m"], P["signal_range_m"] * P["signal_blocked_factor"])
    d = np.hypot(ex - c.x, ey - c.y)
    u = keyed_uniforms(w.seed, "signals", [np.full(len(hearers), issuer), np.full(len(hearers), n),
                                           np.array([e.id for e in hearers])], 1)[:, 0]
    for k, e in enumerate(hearers):
        if d[k] > rng[k]:
            if e.id in addressed:
                record.log(w, "signal_not_heard", e.id, {"signal": sid, "distance_m": float(d[k]),
                                                          "ground_in_the_way": bool(not los[k])}, [{"signal": sid}])
            continue
        if e.id not in addressed:
            if u[k] >= P["signal_misattribution_prob"]:
                continue
            record.log(w, "signal_misattributed", e.id, {"signal": sid}, [{"signal": sid}])
        record.log(w, "signal_heard", e.id, {"signal": sid, "meaning": meaning}, [{"signal": sid}])
        comply(w, e.id, meaning, sid)


def comply(w, eid: int, meaning: str, sid: str) -> None:
    plan = w.plans.get(eid)
    spec = None
    if plan is not None:
        for entry in plan.on:
            if entry["when"].get("signal") == meaning:
                spec = entry["do"]
                break
    if spec is None and meaning == "recall":
        spec = {"kind": "withdraw_to", "place": list(plan.home if plan else position_of(w, eid))}
    if spec is None:
        record.log(w, "signal_without_meaning", eid, {"signal": sid, "meaning": meaning},
                   [{"note": "no prearranged meaning for this signal in the entity's plan"}])
        return
    issue(w, eid, eid, _resolve_plan_target(w, eid, spec), origin="signal", parent=sid,
          oid=f"{sid}.{eid}")


def _resolve_plan_target(w, eid: int, spec: dict) -> dict:
    spec = dict(spec)
    if spec.get("kind") in om.TARGET_KINDS and isinstance(spec.get("target"), dict):
        desc, intended = describe_target(w, eid, spec["target"])
        if desc is not None:
            spec["target"] = desc
            spec["_intended"] = intended
    return spec


# ---- plans and inputs ------------------------------------------------------------------------------

def check_plans(w) -> None:
    P = w.params
    gap = P["track_gap_s"] / P["tick_seconds"]
    for eid in sorted(w.plans):
        plan = w.plans[eid]
        e = w.entity(eid)
        if e.fit <= 0:
            continue
        for k, entry in enumerate(plan.on):
            if entry.get("fired"):
                continue
            when = entry["when"]
            hit = False
            if "after_s" in when:
                hit = w.time >= float(when["after_s"])
            elif "enemy_within" in when:
                x, y, r = when["enemy_within"]
                b = w.beliefs.get(eid)
                if b is not None:
                    hit = any(c.side != e.side and w.tick - c.seen_t <= gap and math.hypot(c.x - x, c.y - y) <= r
                              for c in b.tracks.values())
            if hit:
                entry["fired"] = True
                record.log(w, "plan_triggered", eid, {"entry": k, "when": when}, [{"note": "conditional instruction in the plan"}])
                issue(w, eid, eid, _resolve_plan_target(w, eid, entry["do"]), origin="plan",
                      oid=f"{eid}.plan{k}")


def run_inputs(w) -> None:
    while w.inputs and w.inputs[0][0] <= w.tick:
        _, kind, spec = w.inputs.pop(0)
        if kind == "order":
            issue(w, spec["issuer"], spec["recipient"], {k: v for k, v in spec.items() if k not in ("issuer", "recipient")},
                  origin="input")
        elif kind == "report":
            send_report(w, spec["sender"], spec["recipient"])
        elif kind == "signal":
            emit_signal(w, spec["issuer"], spec["meaning"], spec.get("to", "all"))


def step(w) -> None:
    belief_mod_ensure(w)
    run_inputs(w)
    check_plans(w)
    for eid in sorted(w.pending):
        if eid in w.pending:
            try_execute(w, eid)
    dispatch(w)
