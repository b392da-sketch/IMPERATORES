"""Decide: when officers and commanders reconsider, what they are given, and what follows.

Reads:  belief views (the decision-maker's own picture and own state); his standing and
        received orders, as `OrderView`s (never the audit); plans (homes); a commander's own
        tracks of the units under him; what his messengers tell him when they come back;
        profiles; params.
Writes: w.decisions (full decision records), w.deciders (schedules, interrupt memory,
        commitments), orders, reports and signals through command, events. Never reads the
        true state of anyone else.
Random: stream "decisions": the routine interval and the choice, keyed by (owner, decision
        number), so one decision-maker's choices never shift another's.

When (specification 5.6):
  * routine reassessment at random intervals: officers `decide_officer_*_s`, wing commanders
    `decide_wing_*_s`, army commanders `decide_army_*_s`;
  * interrupts, checked after each perception cycle and each delivered report: an enemy track
    newly within the threat radius ("contact"), or newly on a flank or the rear ("flank"); for a
    commander, a unit under him newly threatened ("threat to a unit"), or a report received;
  * an order arriving from someone else is decided on at once, obey or decline (command.py calls
    `on_order`).
Timing policy (Codex review 006, finding 11): every decision, whatever its trigger, restarts the
routine timer, so a routine reassessment never immediately follows another decision. Several
decisions by one person in a tick (a routine or interrupt in the decide phase, then receipts of
orders in the command phase) are numbered in the order they happened (`seq_in_tick`).

**Commitments** (finding 2): a commander remembers the reserves he has sent and the actions he
has taken, so as not to repeat them. That memory lapses after `commitment_review_s`, or at once
when a messenger comes back and tells him the order did not get through. He learns nothing
from a messenger who never returns.

**The record** (finding 7) holds everything the choice depended on: the context fields, every
contact the scoring read (in full), the draw, every option with its actions and components, the
side actions, and what followed. `context_from_record` rebuilds the context from it, and the
tests check that the rebuilt decision gives the same menu, scores, probabilities and choice.

The decision itself is in imperatores/decisions.py, which is pure.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from types import MappingProxyType

import numpy as np

from .. import belief as belief_mod
from .. import decisions as dm
from .. import orders as om
from .. import record
from ..belief import Contact
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
        st = {"n": 0, "next": None, "near": [], "flank": [], "hot": [], "reported_t": -10 ** 9,
              "committed": [], "done": [], "doing": None, "doing_order": None, "last_t": -1, "seq": 0}
        w.deciders[owner] = st
    return st


def _uniforms(w, owner: int, n: int) -> np.ndarray:
    return keyed_uniforms(w.seed, "decisions", [np.array([owner]), np.array([n])], 2)[0]


def _interval(w, owner: int, u: float) -> int:
    P = w.params
    name = _rank(w, owner)
    lo, hi = P[f"decide_{name}_min_s"], P[f"decide_{name}_max_s"]
    return max(1, int(round((lo + (hi - lo) * u) / P["tick_seconds"])))


def _order_view(w, oid: str | None, owner: int):
    """The order as its recipient knows it. Only for orders addressed to `owner`."""
    if oid is None or oid not in w.orders:
        return None
    o = w.orders[oid]
    if o.recipient != owner:
        raise RuntimeError(f"order {oid} is not addressed to {owner}")
    return dm.OrderView(id=o.id, kind=o.kind, latitude=o.latitude, issuer=o.issuer,
                        place=tuple(o.place) if o.place else None,
                        target_at=(o.target.x, o.target.y) if o.target is not None else None,
                        target_handle=o.understood_handle, toward=tuple(o.toward) if o.toward else None)


def _live(w, entries: list) -> list:
    """Commitments still in force: not yet past `commitment_review_s`."""
    limit = w.params["commitment_review_s"] / w.params["tick_seconds"]
    return [e for e in entries if w.tick - e[1] < limit]


def _context(w, owner: int, trigger: str, received=None) -> dm.Context:
    P = w.params
    v = belief_mod.view(w, owner)
    st = _state(w, owner)
    prof = _profile(w, owner)
    own = dict(v.own)
    own["reported_t"] = st["reported_t"]
    if "commands" in own:
        own["commands"] = tuple(own["commands"])
    params = MappingProxyType({k: P[k] for k in _PARAM_KEYS})
    common = dict(owner=owner, side=own["side"], tick=w.tick, tick_s=P["tick_seconds"], tendencies=dm.PROFILES[prof],
                  profile=prof, own=MappingProxyType(own), contacts=v.contacts, trigger=trigger, params=params)
    if owner in w.by_id:
        task = w.by_id[owner].task
        current = st["doing"] if st["doing_order"] is not None and task.get("order") == st["doing_order"] else None
        return dm.Context(rank="officer", home=tuple(w.plans[owner].home),
                          standing=_order_view(w, w.standing.get(owner), owner),
                          received=_order_view(w, received, owner),
                          has_commander=bool(command.commanders_of(w, owner)), current=current, **common)
    subs = []
    b = w.beliefs[owner]
    for i in command.command_of(w, owner):
        home = tuple(w.plans[i].home)
        h = belief_mod.handle_of(b, i)          # his own units, recognised by their standards (documented)
        c = b.tracks.get(h) if h is not None else None
        if c is not None:
            subs.append(dm.SubView(id=i, x=c.x, y=c.y, strength=c.strength, known_t=c.seen_t, home=home))
        else:
            subs.append(dm.SubView(id=i, x=home[0], y=home[1], strength=w.by_id[i].start_strength, known_t=0, home=home))
    return dm.Context(rank=_rank(w, owner), home=(own["x"], own["y"]), subs=tuple(subs),
                      committed=tuple(e[0] for e in _live(w, st["committed"])),
                      done=tuple(e[0] for e in _live(w, st["done"])), **common)


# ---- the record --------------------------------------------------------------------------------

def _ctx_record(ctx: dm.Context, read: list) -> dict:
    by_handle = {c.handle: c for c in ctx.contacts}
    return {
        "rank": ctx.rank, "side": ctx.side, "tick": ctx.tick, "tick_s": ctx.tick_s, "profile": ctx.profile,
        "own": {k: (list(v) if isinstance(v, tuple) else v) for k, v in sorted(ctx.own.items())},
        "home": list(ctx.home), "trigger": ctx.trigger, "has_commander": ctx.has_commander,
        "standing": None if ctx.standing is None else asdict(ctx.standing),
        "received": None if ctx.received is None else asdict(ctx.received),
        "contacts": [asdict(by_handle[h]) for h in sorted(read)],
        "subs": [asdict(s) for s in ctx.subs],
        "committed": list(ctx.committed), "done": list(ctx.done), "current": ctx.current,
        "params": dict(ctx.params),
    }


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def context_from_record(rec: dict) -> dm.Context:
    """Rebuild the context a decision was made in, from its record alone."""
    i = rec["inputs"]

    def ov(d):
        return None if d is None else dm.OrderView(**{k: _tup(v) for k, v in d.items()})
    return dm.Context(
        owner=rec["owner"], rank=i["rank"], side=i["side"], tick=i["tick"], tick_s=i["tick_s"],
        tendencies=dm.PROFILES[i["profile"]], profile=i["profile"],
        own=MappingProxyType({k: _tup(v) for k, v in i["own"].items()}),
        contacts=tuple(Contact(**c) for c in i["contacts"]), home=tuple(i["home"]), trigger=i["trigger"],
        standing=ov(i["standing"]), received=ov(i["received"]), has_commander=i["has_commander"],
        subs=tuple(dm.SubView(**{k: _tup(v) for k, v in s.items()}) for s in i["subs"]),
        committed=tuple(i["committed"]), done=tuple(i["done"]), current=i["current"],
        params=MappingProxyType(dict(i["params"])))


def make(w, owner: int, trigger: str, received: str | None = None) -> dict:
    """Run one decision and record it. Returns the record."""
    st = _state(w, owner)
    st["n"] += 1
    n = st["n"]
    st["seq"] = st["seq"] + 1 if st["last_t"] == w.tick else 1
    st["last_t"] = w.tick
    u = _uniforms(w, owner, n)
    ctx = _context(w, owner, trigger, received)
    opts, i, probs, read, side = dm.decide(ctx, float(u[0]))
    did = f"d{owner}.{n}"
    chosen = opts[i]
    rec = {
        "id": did, "owner": owner, "rank": ctx.rank, "profile": ctx.profile, "t": w.tick, "seq_in_tick": st["seq"],
        "trigger": trigger, "draw": float(u[0]), "inputs": _ctx_record(ctx, read),
        "options": [{"name": o.name, "actions": record._owned(o.actions), "components": dict(o.components),
                     "total": o.total, "p": p, "beyond_orders": o.beyond_orders} for o, p in zip(opts, probs)],
        "side_actions": record._owned(side),
        "chosen": chosen.name, "beyond_orders": chosen.beyond_orders, "links": [],
    }
    w.decisions[did] = rec
    _apply(w, owner, n, rec, ctx, chosen.actions + side)
    if ctx.rank == "officer" and ctx.received is None:
        own_orders = [l["order"] for l in rec["links"] if "order" in l]
        if own_orders:
            st["doing"], st["doing_order"] = chosen.name, own_orders[0]
    elif ctx.rank != "officer" and chosen.actions:
        oid = next((l.get("order") or l.get("signal") for l in rec["links"]), None)
        st["done"].append([chosen.name, w.tick, oid])
        for e in st["committed"]:
            if e[2] is None:
                e[2] = oid
    st["next"] = w.tick + _interval(w, owner, float(u[1]))          # any decision restarts the routine timer
    rec = record._owned(rec)
    w.decisions[did] = rec
    om.fold(w, "decision", rec)
    if rec["links"] or chosen.beyond_orders:
        record.log(w, "decided", owner, {"decision": did, "chosen": chosen.name, "trigger": trigger},
                   [{"decision": did}])
    return rec


def _apply(w, owner: int, n: int, rec: dict, ctx: dm.Context, actions: list) -> None:
    st = _state(w, owner)
    for j, a in enumerate(actions):
        key = (owner, om.KEY_DECISION, n, j)
        if a["do"] == "order":
            recipient = a.get("recipient", owner)
            spec = dict(a["spec"])
            if "place" in spec:
                x = min(max(float(spec["place"][0]), 0.0), w.terrain.width)
                y = min(max(float(spec["place"][1]), 0.0), w.terrain.height)
                spec["place"] = [x, y]
            own_handle = None
            if "target_handle" in spec:
                h = spec.pop("target_handle")
                c = next(c for c in ctx.contacts if c.handle == h)
                spec["target"] = om.TargetDescription(side=c.side, kind=c.kind, x=c.x, y=c.y, seen_t=c.seen_t)
                if recipient == owner:
                    own_handle = h                  # his own choice of track, carried through (review 006/1)
            o = command.issue(w, owner, recipient, spec, origin="decision", key=key, oid=f"{rec['id']}/{j}",
                              parent=rec["id"], own_handle=own_handle)
            rec["links"].append({"order": o.id})
        elif a["do"] == "signal":
            sid = f"{rec['id']}/{j}"
            command.emit_signal(w, owner, a["meaning"], "all", key=key, sid=sid, cause={"decision": rec["id"]})
            rec["links"].append({"signal": sid})
        elif a["do"] == "report":
            for cid in sorted(command.commanders_of(w, owner)):
                if owner in w.commander(cid).commands:
                    m = command.send_report(w, owner, cid, key=key, cause={"decision": rec["id"]})
                    rec["links"].append({"message": m.id})
            st["reported_t"] = w.tick
        elif a["do"] == "commit":
            st["committed"].append([a["id"], w.tick, None])
        elif a["do"] in ("obey", "decline"):
            rec["links"].append({"order": ctx.received.id, "response": a["do"]})


def on_order(w, eid: int, o: om.Order) -> bool:
    """An order from someone else has been understood: the officer decides whether to obey.
    Returns True to obey. Orders he gave himself (his own decisions, plan, signals he heard)
    are carried out without a second decision."""
    rec = make(w, eid, "order arrived", received=o.id)
    return rec["chosen"] == "obey"


def on_news(w, sender: int, o: om.Order) -> None:
    """A messenger is back and tells his commander the order did not get through (finding 2):
    what that order committed is free to be reconsidered."""
    st = w.deciders.get(sender)
    if st is None:
        return
    before = (len(st["done"]), len(st["committed"]))
    st["done"] = [e for e in st["done"] if e[2] != o.id]
    st["committed"] = [e for e in st["committed"] if e[2] != o.id]
    if (len(st["done"]), len(st["committed"])) != before:
        om.fold(w, "news", sender, o.id)
        record.log(w, "news_of_failure", sender, {"order": o.id}, [{"order": o.id}])


def _near(w, ctx: dm.Context):
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
    """Units under a commander that he believes threatened, from the unfiltered picture (finding 6)."""
    return [] if ctx.rank == "officer" else dm.threatened(ctx)


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
            near, flank = _near(w, ctx)
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
    w.reported_to.clear()
