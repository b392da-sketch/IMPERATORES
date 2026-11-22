"""Command: issuing, dispatching, understanding, relaying and executing orders; signals; plans.

Reads:  scenario inputs; commanders and entities (positions, command, liveness, own state);
        belief pictures (views only, for describing and understanding targets and for plan
        conditions; a sender's own track of a friendly unit, for where to send a rider); plans;
        params; the terrain (whether a route exists, when an order is executed).
Writes: w.orders, w.outbox, w.messengers (new ones), w.staff, w.seq, w.pending, w.audit; entity tasks and routes (when an order is executed); events. Never reads the
        true state of the enemy.
Random: keyed draws on stream "signals" (misattribution), keyed by (*signal key, entity).

See imperatores/orders.py for the model and the Codex review 005 fixes it records. Messengers'
movement and handoff are in messengers.py, which calls `deliver` here.
"""
from __future__ import annotations

import math

import numpy as np

from .. import belief as belief_mod
from .. import orders as om
from .. import pathing, record, sight
from ..rng import keyed_uniforms


# ---- helpers --------------------------------------------------------------------------------

def next_seq(w, sender: int, domain: str) -> int:
    """Readable numbering, separate for orders, reports and signals (finding 10)."""
    n = w.seq.get((sender, domain), 0) + 1
    w.seq[(sender, domain)] = n
    return n


def staff_size(w, sender: int) -> int:
    P = w.params
    if sender in w.commanders_by_id:
        return P["messengers_army"] if w.commander(sender).rank == "army" else P["messengers_wing"]
    return P["runners_entity"]


def ensure_staff(w) -> None:
    for i in [c.id for c in w.commanders] + [e.id for e in w.entities]:
        if i not in w.staff_initial:
            w.staff_initial[i] = staff_size(w, i)
            w.staff[i] = w.staff_initial[i]


def belief_mod_ensure(w) -> None:
    from . import perception
    perception.ensure_beliefs(w)
    ensure_staff(w)


def position_of(w, i: int) -> tuple:
    if i in w.by_id:
        e = w.by_id[i]
        return (e.x, e.y)
    c = w.commanders_by_id[i]
    return (c.x, c.y)


def side_of(w, i: int) -> str:
    return w.by_id[i].side if i in w.by_id else w.commanders_by_id[i].side


def alive(w, i: int) -> bool:
    return w.by_id[i].fit > 0 if i in w.by_id else bool(w.commanders_by_id[i].alive)


def subordinates(w, cid: int) -> set:
    """Everyone under a commander at any depth, with a visited guard (finding 11)."""
    out, todo = set(), list(w.commanders_by_id[cid].commands)
    while todo:
        i = todo.pop()
        if i in out:
            continue
        out.add(i)
        if i in w.commanders_by_id:
            todo.extend(w.commanders_by_id[i].commands)
    return out


def command_of(w, cid: int) -> list[int]:
    """All entities under a commander, through his wing commanders, in id order."""
    return sorted(i for i in subordinates(w, cid) if i in w.by_id)


def commanders_of(w, eid: int) -> set:
    return {c.id for c in w.commanders if eid in subordinates(w, c.id)}


def may_order(w, issuer: int, recipient: int) -> bool:
    """Finding 1: a commander orders someone in his command; an entity's officer orders himself."""
    if side_of(w, issuer) != side_of(w, recipient):
        return False
    if issuer == recipient:
        return issuer in w.by_id
    return issuer in w.commanders_by_id and recipient in subordinates(w, issuer)


def mounted(e) -> bool:
    return e.function in ("light_cavalry", "heavy_cavalry") or e.equipment.mobility == "horse"


def believed_position(w, sender: int, recipient: int) -> tuple:
    """Where the sender thinks the recipient is (finding 1): his own track of that friendly unit
    if it is more recent than the plan of battle, else its place in that plan (its home).
    Never its live position. Commanders stand still in M0 and their places are known to their
    own side (an assumption that ends when commanders move)."""
    if recipient in w.commanders_by_id:
        c = w.commanders_by_id[recipient]
        return (c.x, c.y)
    best = (-1, 0, w.plans[recipient].home)
    b = w.beliefs.get(sender)
    h = belief_mod.handle_of(b, recipient) if b is not None else None
    if h is not None and h in b.tracks:
        c = b.tracks[h]
        best = max(best, (c.seen_t, 2, (c.x, c.y)))
    return best[2]


def describe_target(w, issuer: int, spec: dict):
    """The issuer's description of a body, from his own picture: his nearest contact of the given
    side to the given point. Returns (TargetDescription, intended true id for the audit) or (None, None)."""
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
    intended = next((t for t, h in w.beliefs[issuer]._truth.items() if h == best.handle), None)
    return om.TargetDescription(side=best.side, kind=best.kind, x=best.x, y=best.y, seen_t=best.seen_t), intended


def _cause(o: om.Order) -> list:
    if o.origin == "decision":
        return [{"decision": o.parent}]
    if o.origin == "signal":
        return [{"signal": o.parent}]
    return [{"order": o.parent}] if o.parent else [{"note": f"order from {o.origin}"}]


# ---- issuing ----------------------------------------------------------------------------------

def issue(w, issuer: int, recipient: int, spec: dict, origin: str, key: tuple, oid: str,
          parent=None, intended=None) -> om.Order:
    """Create an order and put it in the issuer's outbox (or deliver it at once if self-addressed)."""
    belief_mod_ensure(w)
    if not may_order(w, issuer, recipient):
        raise ValueError(f"{issuer} has no authority to order {recipient}")
    if oid in w.orders:
        raise RuntimeError(f"order id {oid} used twice")
    target_spec = spec.get("target")
    o = om.order_from_spec(oid, key, issuer, recipient, {k: v for k, v in spec.items() if k != "target"},
                           origin, parent)
    if isinstance(target_spec, om.TargetDescription):
        o.target = target_spec
    elif o.kind in om.TARGET_KINDS:
        o.target, intended = describe_target(w, issuer, target_spec)
    w.orders[oid] = o
    if intended is not None:
        w.audit[oid] = {"intended": intended}
        om.fold(w, "audit", oid, w.audit[oid])
    detail = {"origin": origin, "kind": o.kind}
    if parent:
        detail["from"] = parent
    o.stages.append(["decided", w.tick, detail])
    om.fold(w, "order", oid, "decided", detail)
    record.log(w, "order_decided", issuer, {"order": oid, "recipient": recipient, "kind": o.kind}, _cause(o))
    if not alive(w, issuer):
        om.fail(w, o, "decided", "the issuer is dead" if issuer in w.commanders_by_id else "the unit has no men left fit")
        record.log(w, "order_failed", issuer, {"order": oid, "at": "decided"}, [{"order": oid}])
        return o
    if o.kind in om.TARGET_KINDS and o.target is None:
        om.fail(w, o, "decided", "the issuer knows of no such body")
        record.log(w, "order_failed", issuer, {"order": oid, "at": "decided"}, [{"order": oid}])
        return o
    if issuer == recipient:
        om.transition(w, o, "delivered", {"how": "own decision"})
        on_delivered(w, o)
        return o
    w.outbox.setdefault(issuer, []).append(om.Message(id=oid, key=o.key, kind="order", sender=issuer,
                                                      recipient=recipient, created_t=w.tick, order=o))
    return o


def send_report(w, sender: int, recipient: int, key: tuple, cause: dict | None = None) -> om.Message:
    belief_mod_ensure(w)
    if recipient not in w.commanders_by_id or side_of(w, sender) != side_of(w, recipient) or sender == recipient:
        raise ValueError(f"{sender} cannot report to {recipient}")
    mid = f"{sender}.r{next_seq(w, sender, 'report')}"
    contacts = belief_mod.view(w, sender).contacts          # immutable values, captured now
    m = om.Message(id=mid, key=tuple(key), kind="report", sender=sender, recipient=recipient, created_t=w.tick,
                   contacts=contacts)
    om.fold(w, "report", mid, list(key), recipient, len(contacts))
    record.log(w, "report_written", sender, {"message": mid, "recipient": recipient, "contacts": len(contacts)},
               [cause or {"note": "report input"}])
    if not alive(w, sender):
        record.log(w, "report_lost", sender, {"message": mid, "why": "the sender is dead"}, [{"message": mid}])
        return m
    w.outbox.setdefault(sender, []).append(m)
    return m


def _drop(w, m: om.Message, why: str) -> None:
    if m.order is not None:
        om.fail(w, m.order, "sent", why)
        record.log(w, "order_failed", m.sender, {"order": m.id, "at": "sent", "why": why}, [{"order": m.id}])
    else:
        om.fold(w, "report_dropped", m.id, why)
        record.log(w, "report_lost", m.sender, {"message": m.id, "why": why}, [{"message": m.id}])


def dispatch(w) -> None:
    """Hand queued messages to free messengers. A queue cannot wait for ever (finding 3): it
    fails when the sender is dead, when no messenger is left to him at all, or after
    `messenger_wait_timeout_s`."""
    from . import messengers as ms
    P = w.params
    for sender in sorted(w.outbox):
        box = w.outbox[sender]
        if not box:
            continue
        if not alive(w, sender):
            for m in box:
                _drop(w, m, "the sender is dead" if sender in w.commanders_by_id else "the unit has no men left fit")
            box.clear()
            continue
        while box and w.staff.get(sender, 0) > 0:
            m = box.pop(0)
            w.staff[sender] -= 1
            ms.launch(w, sender, m)
        if not box:
            continue
        active = any(x.sender == sender and x.status not in om.ENDED for x in w.messengers)
        keep = []
        for m in box:
            waited = (w.tick - m.created_t) * P["tick_seconds"]
            if not active:
                _drop(w, m, "no messengers left to carry it")
            elif waited >= P["messenger_wait_timeout_s"]:
                _drop(w, m, "no messenger became free in time")
            else:
                if m.order is not None and m.order.status == "decided":
                    om.transition(w, m.order, "waiting", {})
                keep.append(m)
        w.outbox[sender] = keep


# ---- delivery, understanding, relay, execution --------------------------------------------------

def deliver(w, m: om.Message) -> bool:
    """Called by the messengers system at a valid handoff. Idempotent by message id (finding 6):
    a second delivery of the same message does nothing and returns False."""
    if m.id in w.delivered:
        return False
    w.delivered.add(m.id)
    om.fold(w, "delivered", m.id)
    if m.kind == "report":
        changed = belief_mod.apply_report(w, m.recipient, list(m.contacts), m.sender, w.tick)
        w.reported_to.add(m.recipient)              # an interrupt for the commander (step 5)
        record.log(w, "report_delivered", m.recipient, {"message": m.id, "from": m.sender, "tracks_changed": len(changed)},
                   [{"message": m.id}])
        return True
    o = m.order
    om.transition(w, o, "delivered", {})
    record.log(w, "order_delivered", m.recipient, {"order": o.id}, [{"order": o.id}])
    on_delivered(w, o)
    return True


def on_delivered(w, o: om.Order) -> None:
    v = belief_mod.view(w, o.recipient)
    if not om.understand(w, o, v):
        record.log(w, "order_failed", o.recipient, {"order": o.id, "at": "understood"}, [{"order": o.id}])
        return
    record.log(w, "order_understood", o.recipient, {"order": o.id}, [{"order": o.id}])
    if o.recipient in w.commanders_by_id:
        relay(w, o)
        return
    eid = o.recipient
    if o.issuer != eid:                         # step 5: an order from someone else is a decision
        from . import decide
        if not decide.on_order(w, eid, o):
            did = f"d{eid}.{w.deciders[eid]['n']}"
            om.fail(w, o, "executed", "the recipient chose otherwise", {"decision": did})
            record.log(w, "order_declined", eid, {"order": o.id}, [{"decision": did}])
            return
    if eid in w.pending:                      # finding 2: a later order supersedes one still waiting
        old = w.orders[w.pending.pop(eid)[0]]
        om.fail(w, old, "executed", "superseded by a later order", {"superseded_by": o.id})
        record.log(w, "order_superseded", eid, {"order": old.id, "by": o.id}, [{"order": o.id}])
    w.pending[eid] = [o.id, w.tick]
    try_execute(w, eid)


def relay(w, o: om.Order) -> None:
    """A commander passes an order on to every entity and wing commander directly under him.
    Each child's key comes from the parent and the recipient (finding 10)."""
    c = w.commander(o.recipient)
    children = []
    intended = w.audit.get(o.id, {}).get("intended")
    for i in c.commands:
        spec = {"kind": o.kind, "latitude": o.latitude}
        if o.place:
            spec["place"] = o.place
        if o.target is not None:
            spec["target"] = o.target            # the description is passed on as received
        child = issue(w, c.id, i, spec, origin="relay", key=(c.id, om.KEY_RELAY, i, *o.key),
                      oid=f"{o.id}>{i}", parent=o.id, intended=intended)
        children.append(child.id)
    om.transition(w, o, "executed", {"relayed_to": children})
    record.log(w, "order_relayed", c.id, {"order": o.id, "to": children}, [{"order": o.id}])


def _failed_execution(w, eid: int, o: om.Order, why: str, detail: dict | None = None) -> None:
    del w.pending[eid]
    om.fail(w, o, "executed", why, detail)
    record.log(w, "order_failed", eid, {"order": o.id, "at": "executed", "why": why}, [{"order": o.id}])


def try_execute(w, eid: int) -> None:
    P = w.params
    oid, since = w.pending[eid]
    o = w.orders[oid]
    e = w.entity(eid)
    if e.fit <= 0:
        _failed_execution(w, eid, o, "the entity has no men left fit")
        return
    if o.kind not in ("hold", "face"):
        blocked = None
        if e.order < P["disordered_order"]:
            blocked = "disordered: must reform first"
        elif e.fatigue > P["exhausted_fatigue"]:
            blocked = "exhausted: must rest first"
        if blocked:
            waited = (w.tick - since) * P["tick_seconds"]
            if waited >= P["order_wait_timeout_s"]:
                _failed_execution(w, eid, o, f"not executable: {blocked}", {"waited_s": waited})
            elif o.status != "waiting_exec":
                om.transition(w, o, "waiting_exec", {"why": blocked})
            return
    route = None
    if o.kind in om.PLACE_KINDS:               # finding 6: a route must exist before it is "executed"
        tx, ty = float(o.place[0]), float(o.place[1])
        if not w.terrain.passable(tx, ty):
            _failed_execution(w, eid, o, "no route: the place is off the field or in the stream")
            return
        route = pathing.plan(w.terrain, P, pathing.movement_class(e), e.x, e.y, tx, ty)
        if route is None:
            _failed_execution(w, eid, o, "no route to the place")
            return
    handle = None
    if o.kind in om.TARGET_KINDS:
        b = w.beliefs[eid]
        handle = belief_mod.resolve(b, o.understood_handle)
        if handle not in b.tracks:
            _failed_execution(w, eid, o, "the body is no longer in the officer's picture")
            return
    del w.pending[eid]
    if o.origin != "decision":                  # the order he works under, from his commanders or plan
        w.standing[eid] = oid
    if o.kind == "hold":
        e.task = {"kind": "hold", "order": oid}
        e.route = e.route_for = None
    elif o.kind == "face":
        e.task = {"kind": "face", "x": float(o.toward[0]), "y": float(o.toward[1]), "order": oid}
        e.route = e.route_for = None
    elif o.kind in om.PLACE_KINDS:
        e.task = {"kind": "move_to", "x": float(o.place[0]), "y": float(o.place[1]), "order": oid}
        e.route, e.route_for = [[x, y] for x, y in route], [float(o.place[0]), float(o.place[1])]
    else:
        standoff = P["approach_standoff_m"] if o.kind == "attack" else P["support_distance_m"]
        e.task = {"kind": "approach", "handle": int(handle), "standoff": float(standoff), "order": oid}
        e.route = e.route_for = None
    e.blocked_ticks = 0
    om.transition(w, o, "executed", {"task": e.task["kind"]})
    record.log(w, "order_executed", eid, {"order": oid, "task": e.task["kind"]}, [{"order": oid}])


# ---- signals -------------------------------------------------------------------------------------

def emit_signal(w, issuer: int, meaning: str, to, key: tuple, sid: str, cause: dict | None = None) -> None:
    P = w.params
    belief_mod_ensure(w)
    if not om.valid_signal(meaning):
        raise ValueError(f"unknown signal {meaning!r}")
    c = w.commander(issuer)
    if to == "all":
        addressed = set(command_of(w, issuer))
    else:
        addressed = set()
        for i in to:
            addressed |= set(command_of(w, i)) if i in w.commanders_by_id else {i}
    om.fold(w, "signal", sid, list(key), meaning, sorted(addressed))
    record.log(w, "signal_emitted", issuer, {"signal": sid, "meaning": meaning, "to": sorted(addressed),
                                             "extension": meaning in om.SIGNAL_EXTENSIONS},
               [cause or {"note": "signal input"}])
    if not c.alive:
        record.log(w, "signal_not_given", issuer, {"signal": sid}, [{"note": "the commander is dead"}])
        return
    for i in sorted(addressed):                    # finding 9: an outcome for every addressed unit
        if w.by_id[i].fit <= 0:
            record.log(w, "signal_not_received", i, {"signal": sid}, [{"note": "the unit has no men left fit"}])
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
    parts = [np.full(len(hearers), k) for k in key] + [np.array([e.id for e in hearers])]
    u = keyed_uniforms(w.seed, "signals", parts, 1)[:, 0]
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
        comply(w, e.id, meaning, sid, key, issuer)


def comply(w, eid: int, meaning: str, sid: str, key: tuple, emitter: int) -> None:
    """What the entity does on hearing a signal (finding 9): only its own commanders' signals
    bind it, unless a plan entry names the emitter; mounted-only signals bind mounted troops."""
    e = w.entity(eid)
    plan = w.plans[eid]
    own = emitter in commanders_of(w, eid)
    spec = None
    for entry in plan.on:
        if entry["when"].get("signal") != meaning:
            continue
        frm = entry.get("from")
        if (frm is None and own) or (frm is not None and emitter in frm):
            spec = entry["do"]
            break
    if spec is None and not own:
        record.log(w, "signal_ignored", eid, {"signal": sid, "meaning": meaning},
                   [{"note": "not from one of its own commanders, and its plan does not name this emitter"}])
        return
    if meaning in om.MOUNTED_ONLY and not mounted(e):
        record.log(w, "signal_not_applicable", eid, {"signal": sid, "meaning": meaning},
                   [{"note": "a signal for mounted troops"}])
        return
    if spec is None and meaning == "recall":
        spec = {"kind": "withdraw_to", "place": list(plan.home)}
    if spec is None:
        record.log(w, "signal_without_meaning", eid, {"signal": sid, "meaning": meaning},
                   [{"note": "no prearranged meaning for this signal in the entity's plan"}])
        return
    spec, intended = _resolve_plan_target(w, eid, spec)
    issue(w, eid, eid, spec, origin="signal", key=(eid, om.KEY_SIGNAL_RESPONSE, *key), oid=f"{sid}>{eid}",
          parent=sid, intended=intended)


def _resolve_plan_target(w, eid: int, spec: dict):
    spec = dict(spec)
    intended = None
    if spec.get("kind") in om.TARGET_KINDS and isinstance(spec.get("target"), dict):
        desc, intended = describe_target(w, eid, spec["target"])
        spec["target"] = desc
    return spec, intended


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
                om.fold(w, "plan_fired", eid, k)
                record.log(w, "plan_triggered", eid, {"entry": k, "when": when}, [{"note": "conditional instruction in the plan"}])
                spec, intended = _resolve_plan_target(w, eid, entry["do"])
                issue(w, eid, eid, spec, origin="plan", key=(eid, om.KEY_PLAN, k), oid=f"{eid}.plan{k}",
                      intended=intended)


def run_inputs(w) -> None:
    """Scenario inputs, keyed by their position in the file (finding 10)."""
    while w.inputs and w.inputs[0][0] <= w.tick:
        _, kind, spec, k = w.inputs.pop(0)
        if kind == "order":
            i = spec["issuer"]
            issue(w, i, spec["recipient"], {a: v for a, v in spec.items() if a not in ("issuer", "recipient")},
                  origin="input", key=(i, om.KEY_INPUT, k), oid=f"{i}.{next_seq(w, i, 'order')}")
        elif kind == "report":
            send_report(w, spec["sender"], spec["recipient"], key=(spec["sender"], om.KEY_INPUT, k))
        elif kind == "signal":
            i = spec["issuer"]
            emit_signal(w, i, spec["meaning"], spec.get("to", "all"), key=(i, om.KEY_INPUT, k),
                        sid=f"{i}.s{next_seq(w, i, 'signal')}")


def staff_problems(w) -> list[str]:
    """Finding 3: messengers are conserved. At hand + out + permanently gone = the staff he began with."""
    out = []
    gone = {}
    for ms in w.messengers:
        if ms.status != "home":
            gone[ms.sender] = gone.get(ms.sender, 0) + 1
    for s, n in w.staff_initial.items():
        if w.staff.get(s, 0) + gone.get(s, 0) != n or w.staff.get(s, 0) < 0:
            out.append(f"sender {s}: {w.staff.get(s, 0)} at hand + {gone.get(s, 0)} out or gone != {n}")
    return out


def step(w) -> None:
    belief_mod_ensure(w)
    run_inputs(w)
    check_plans(w)
    for eid in sorted(w.pending):
        if eid in w.pending:
            try_execute(w, eid)
    dispatch(w)
