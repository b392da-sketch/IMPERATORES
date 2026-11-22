"""Decide: when officers and commanders reconsider, what they are given, and what follows.

Reads:  belief views (the decision-maker's own picture and own state); his standing and
        received orders, as `OrderView`s (never the audit); plans (homes); a commander's own
        tracks of the units under him (command.believed_position); profiles; params.
Writes: w.decisions (full decision records), w.deciders (schedules, interrupt memory), orders,
        reports and signals through command, events. Never reads the true state of anyone else.
Random: stream "decisions": the routine interval and the choice, keyed by (owner, decision
        number), so one decision-maker's choices never shift another's.

When (specification 5.6):
  * routine reassessment at random intervals: officers `decide_officer_s`, wing commanders
    `decide_wing_s`, army commanders `decide_army_s` (each a [min, max] pair of parameters);
  * interrupts, checked after each perception cycle and each delivered report: an enemy track
    newly within the threat radius ("contact"), or newly on a flank or the rear ("flank"); for a
    commander, a unit under him newly threatened ("threat to a unit");
  * an order arriving (from someone else) is decided on at once: obey or decline (command.py
    calls `on_order`).

The decision itself is in imperatores/decisions.py, which is pure.
"""
from __future__ import annotations

import math
from types import MappingProxyType

import numpy as np

from .. import belief as belief_mod
from .. import decisions as dm
from .. import orders as om
from .. import record
from ..rng import keyed_uniforms
from . import command, perception

_PARAM_KEYS = ("threat_radius_m", "commander_threat_radius_m", "flank_angle_deg", "rear_angle_deg",
               "flank_factor", "rear_factor", "decision_temperature", "latitude_cost_strict",
               "latitude_cost_normal", "latitude_cost_free", "report_min_interval_s", "support_distance_m",
               "change_cost")


def _rank(w, owner: int) -> str:
    return "officer" if owner in w.by_id else w.commander(owner).rank


def _profile(w, owner: int) -> str:
    return (w.by_id[owner] if owner in w.by_id else w.commander(owner)).profile


def _state(w, owner: int) -> dict:
    st = w.deciders.get(owner)
    if st is None:
        st = {"n": 0, "next": None, "near": [], "flank": [], "hot": [], "reported_t": -10 ** 9, "committed": [],
              "doing": None, "doing_order": None, "done": []}
        w.deciders[owner] = st
    return st


def _uniforms(w, owner: int, n: int) -> np.ndarray:
    return keyed_uniforms(w.seed, "decisions", [np.array([owner]), np.array([n])], 2)[0]


def _interval(w, owner: int, u: float) -> int:
    P = w.params
    name = {"officer": "officer", "wing": "wing", "army": "army"}[_rank(w, owner)]
    lo, hi = P[f"decide_{name}_min_s"], P[f"decide_{name}_max_s"]
    return max(1, int(round((lo + (hi - lo) * u) / P["tick_seconds"])))


def _order_view(w, oid: str | None, owner: int):
    if oid is None or oid not in w.orders:
        return None
    o = w.orders[oid]
    return dm.OrderView(id=o.id, kind=o.kind, latitude=o.latitude, issuer=o.issuer,
                        place=tuple(o.place) if o.place else None,
                        target_at=(o.target.x, o.target.y) if o.target is not None else None,
                        target_handle=o.understood_handle)


def _context(w, owner: int, trigger: str, received=None) -> dm.Context:
    P = w.params
    v = belief_mod.view(w, owner)
    st = _state(w, owner)
    prof = _profile(w, owner)
    own = dict(v.own)
    own["reported_t"] = st["reported_t"]
    params = MappingProxyType({k: P[k] for k in _PARAM_KEYS})
    if owner in w.by_id:
        task = w.by_id[owner].task
        current = st["doing"] if st["doing_order"] is not None and task.get("order") == st["doing_order"] else None
        return dm.Context(owner=owner, rank="officer", side=own["side"], tick=w.tick, tick_s=P["tick_seconds"],
                          tendencies=dm.PROFILES[prof], profile=prof, own=MappingProxyType(own),
                          contacts=v.contacts, home=tuple(w.plans[owner].home), trigger=trigger,
                          standing=_order_view(w, w.standing.get(owner), owner),
                          received=_order_view(w, received, owner),
                          has_commander=bool(command.commanders_of(w, owner)), current=current, params=params)
    subs = []
    for i in command.command_of(w, owner):
        b = w.beliefs[owner]
        h = belief_mod.handle_of(b, i)
        c = b.tracks.get(h) if h is not None else None
        if c is not None:
            subs.append(dm.SubView(id=i, x=c.x, y=c.y, strength=c.strength, known_t=c.seen_t))
        else:
            hx, hy = w.plans[i].home
            subs.append(dm.SubView(id=i, x=hx, y=hy, strength=w.by_id[i].start_strength, known_t=0))
    return dm.Context(owner=owner, rank=_rank(w, owner), side=own["side"], tick=w.tick, tick_s=P["tick_seconds"],
                      tendencies=dm.PROFILES[prof], profile=prof, own=MappingProxyType(own), contacts=v.contacts,
                      home=(own["x"], own["y"]), trigger=trigger, subs=tuple(subs),
                      committed=tuple(st["committed"]), done=tuple(st["done"]), params=params)


def _contact_record(c) -> dict:
    return {"handle": c.handle, "side": c.side, "kind": c.kind, "x": c.x, "y": c.y, "strength": c.strength,
            "seen_t": c.seen_t, "source": c.source}


def make(w, owner: int, trigger: str, received: str | None = None) -> dict:
    """Run one decision and record it. Returns the record."""
    st = _state(w, owner)
    st["n"] += 1
    n = st["n"]
    u = _uniforms(w, owner, n)
    ctx = _context(w, owner, trigger, received)
    opts, i, probs, read, side = dm.decide(ctx, float(u[0]))
    did = f"d{owner}.{n}"
    chosen = opts[i]
    by_handle = {c.handle: c for c in ctx.contacts}
    rec = {
        "id": did, "owner": owner, "rank": ctx.rank, "profile": ctx.profile, "t": w.tick, "trigger": trigger,
        "inputs": {
            "own": {k: ctx.own[k] for k in sorted(ctx.own) if k != "commands"},
            "standing": None if ctx.standing is None else dict(vars(ctx.standing)),
            "received": None if ctx.received is None else dict(vars(ctx.received)),
            "contacts": [_contact_record(by_handle[h]) for h in sorted(read)],
            "subs": [dict(vars(s)) for s in ctx.subs],
        },
        "options": [{"name": o.name, "components": dict(o.components), "total": o.total, "p": p,
                     "beyond_orders": o.beyond_orders} for o, p in zip(opts, probs)],
        "chosen": chosen.name, "beyond_orders": chosen.beyond_orders, "links": [],
    }
    w.decisions[did] = rec
    _apply(w, owner, n, rec, ctx, chosen.actions + side)
    if ctx.rank == "officer" and ctx.received is None:
        own_orders = [l["order"] for l in rec["links"] if "order" in l]
        if own_orders:
            st["doing"], st["doing_order"] = chosen.name, own_orders[0]
    elif ctx.rank != "officer" and chosen.actions:
        st["done"].append(chosen.name)
    rec = record._owned(rec)
    w.decisions[did] = rec
    om.fold(w, "decision", rec)
    if rec["links"] or chosen.beyond_orders:
        record.log(w, "decided", owner, {"decision": did, "chosen": chosen.name, "trigger": trigger},
                   [{"decision": did}])
    return rec


def _apply(w, owner: int, n: int, rec: dict, ctx: dm.Context, actions: list) -> None:
    P = w.params
    st = _state(w, owner)
    for j, a in enumerate(actions):
        key = (owner, om.KEY_DECISION, n, j)
        if a["do"] == "order":
            recipient = a.get("recipient", owner)
            spec = dict(a["spec"])
            if spec.get("place") == "home":
                spec["place"] = list(w.plans[recipient].home)
            if "place" in spec:
                x = min(max(float(spec["place"][0]), 0.0), w.terrain.width)
                y = min(max(float(spec["place"][1]), 0.0), w.terrain.height)
                spec["place"] = [x, y]
            if "target_handle" in spec:
                h = spec.pop("target_handle")
                c = next(c for c in ctx.contacts if c.handle == h)
                spec["target"] = om.TargetDescription(side=c.side, kind=c.kind, x=c.x, y=c.y, seen_t=c.seen_t)
            o = command.issue(w, owner, recipient, spec, origin="decision", key=key,
                              oid=f"{rec['id']}/{j}", parent=rec["id"])
            rec["links"].append({"order": o.id})
        elif a["do"] == "signal":
            sid = f"{rec['id']}/{j}"
            command.emit_signal(w, owner, a["meaning"], "all", key=key, sid=sid, cause={"decision": rec["id"]})
            rec["links"].append({"signal": sid})
        elif a["do"] == "report":
            for cid in sorted(command.commanders_of(w, owner)):
                if cid in w.commanders_by_id and owner in w.commander(cid).commands:
                    m = command.send_report(w, owner, cid, key=key, cause={"decision": rec["id"]})
                    rec["links"].append({"message": m.id})
            st["reported_t"] = w.tick
        elif a["do"] == "commit":
            st["committed"].append(a["id"])
        elif a["do"] in ("obey", "decline"):
            rec["links"].append({"order": ctx.received.id, "response": a["do"]})


def on_order(w, eid: int, o: om.Order) -> bool:
    """An order from someone else has been understood: the officer decides whether to obey.
    Returns True to obey. Orders he gave himself (his own decisions, plan, signals he heard)
    are carried out without a second decision."""
    rec = make(w, eid, "order arrived", received=o.id)
    return rec["chosen"] == "obey"


def _near(w, owner: int, ctx: dm.Context):
    """Enemy handles within threat radius, and those on a flank or rear, as the owner believes."""
    if ctx.rank != "officer":
        return [], []
    pic = dm.officer_picture(ctx)
    flank_a = math.radians(w.params["flank_angle_deg"])
    near, flank = [], []
    own = ctx.own
    for _, c in pic["threats"]:
        near.append(c.handle)
        off = abs(dm._wrap(math.atan2(c.y - own["y"], c.x - own["x"]) - own["facing"]))
        if off > flank_a:
            flank.append(c.handle)
    return sorted(near), sorted(flank)


def _hot(ctx: dm.Context):
    if ctx.rank == "officer":
        return []
    opts, _, _ = dm.commander_options(ctx)
    return sorted({int(o.name.split(":")[1].split(">")[-1]) for o in opts if o.name.startswith(("withdraw:", "reinforce:"))})


def step(w) -> None:
    command.belief_mod_ensure(w)
    every = perception._interval_ticks(w.params)
    look = w.tick % every == 0
    owners = [e.id for e in w.entities if e.fit > 0] + [c.id for c in w.commanders if c.alive]
    for owner in owners:
        st = _state(w, owner)
        if st["next"] is None:                    # first reassessment: a random offset into the interval
            st["next"] = w.tick + _interval(w, owner, float(_uniforms(w, owner, 0)[1]))
        trigger = None
        if look or owner in w.reported_to:
            ctx = _context(w, owner, "scan")
            near, flank = _near(w, owner, ctx)
            hot = _hot(ctx)
            if set(flank) - set(st["flank"]):
                trigger = "flank"
            elif set(near) - set(st["near"]):
                trigger = "contact"
            elif set(hot) - set(st["hot"]):
                trigger = "threat to a unit"
            elif owner in w.reported_to:
                trigger = "report received"
            st["near"], st["flank"], st["hot"] = near, flank, hot
        if trigger is None and w.tick >= st["next"]:
            trigger = "routine"
        if trigger is None:
            continue
        make(w, owner, trigger)
        st["next"] = w.tick + _interval(w, owner, float(_uniforms(w, owner, st["n"])[1]))
    w.reported_to.clear()
