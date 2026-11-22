"""Decisions (specification 5.6): what an officer or commander chooses, from his own picture only.

This module is pure. It is given a `Context` built from the decision-maker's belief view, his
own state, his standing and received orders and his tendencies, and returns the options he
considered, each with named score components, and which he chose. It never sees the world,
true identities or the order audit; a test scans this file to keep it so (acceptance check 3,
structural).

Choice is a softmax over option totals at `decision_temperature`, drawn with one uniform the
caller supplies (keyed per decision-maker and decision number), so a decision is reproducible
and independent of every other.

**Every formula and weight here is an engineering assumption**, chosen so that the components
pull in the directions the specification names (danger, opportunity, duty to orders, keeping a
reserve, the unit's condition) and so that tendencies change choices. None is calibrated. They
are listed in docs/M0_BUILD_NOTES.md (step 5) and are to be tested for sensitivity, not tuned
to outcomes.

Tendencies (section 5.6), each in [0, 1]:
  risk        how much risk he accepts
  reserve     how strongly he prefers keeping a reserve
  initiative  how far he will act beyond his orders
  commitment  how quickly he commits to an opening
  trust       how much he trusts reports against his own eyes

M0 profiles are generic test profiles, not historical people.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class Tendencies:
    risk: float
    reserve: float
    initiative: float
    commitment: float
    trust: float


PROFILES = MappingProxyType({
    "by_the_book": Tendencies(risk=0.4, reserve=0.6, initiative=0.15, commitment=0.4, trust=0.5),
    "cautious": Tendencies(risk=0.15, reserve=0.85, initiative=0.3, commitment=0.2, trust=0.4),
    "bold": Tendencies(risk=0.8, reserve=0.25, initiative=0.6, commitment=0.85, trust=0.6),
})

MOVING = ("move_to", "approach")
# what each kind of standing order allows without acting beyond it
_WITHIN = {
    "hold": {"continue", "hold", "face"},
    "face": {"continue", "hold", "face"},
    "advance_to": {"continue"},
    "withdraw_to": {"continue", "withdraw"},
    "attack": {"continue"},              # attacking the ordered body is checked by handle (review 006/3)
    "support": {"continue"},
}


@dataclass(frozen=True)
class OrderView:
    """What the decision-maker knows of an order: never who was meant, never the audit."""
    id: str
    kind: str
    latitude: str
    issuer: int
    place: tuple | None = None
    target_at: tuple | None = None       # where the issuer described the target
    target_handle: int | None = None     # the track the officer took it to mean, once understood
    toward: tuple | None = None          # for a face order


@dataclass(frozen=True)
class SubView:
    """A commander's picture of one unit under him: where he believes it is, how strong."""
    id: int
    x: float
    y: float
    strength: int
    known_t: int                         # when he last saw or heard where it is (0: plan of battle)
    home: tuple = (0.0, 0.0)             # its place in the plan of battle


@dataclass(frozen=True)
class Context:
    owner: int
    rank: str                            # "officer", "wing" or "army"
    side: str
    tick: int
    tick_s: float
    tendencies: Tendencies
    profile: str
    own: object                          # read-only mapping from the belief view
    contacts: tuple                      # belief.Contact values
    home: tuple
    trigger: str
    standing: OrderView | None = None    # the order he is working under
    received: OrderView | None = None    # an order just understood, to obey or decline
    has_commander: bool = False
    subs: tuple = ()                     # SubView, for commanders
    committed: tuple = ()                # ids a commander has already sent forward
    current: str | None = None           # the option he chose earlier that his unit is still carrying out
    done: tuple = ()                     # options a commander has already carried out (not repeated)
    params: object = field(default_factory=dict)


@dataclass
class Option:
    name: str
    actions: list
    components: dict
    beyond_orders: bool = False

    @property
    def total(self) -> float:
        return sum(self.components.values())


# ---- the picture, as the decision-maker reads it -----------------------------------------------

def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _weight(ctx: Context, c, x: float, y: float, radius: float, against: float) -> float:
    """How much a contact threatens a body of `against` men at (x, y): its believed strength
    relative to them, nearness, trust in the source, and freshness."""
    d = math.hypot(c.x - x, c.y - y)
    if d >= radius:
        return 0.0
    trust = 1.0 if c.source == "seen" else ctx.tendencies.trust
    fresh = 1.0 / (1.0 + (ctx.tick - c.seen_t) * ctx.tick_s / 120.0)
    return (c.strength / max(against, 1.0)) * (1.0 - d / radius) * trust * fresh


def _enemies(ctx: Context) -> list:
    return [c for c in ctx.contacts if c.side != ctx.side]


def officer_picture(ctx: Context) -> dict:
    """Danger to the officer's unit from what he believes, split by front, flank and rear."""
    P = ctx.params
    own = ctx.own
    R = P["threat_radius_m"]
    flank_a, rear_a = math.radians(P["flank_angle_deg"]), math.radians(P["rear_angle_deg"])
    pic = {"danger": 0.0, "flank": 0.0, "flank_front": 0.0, "threats": [], "read": []}
    for c in _enemies(ctx):
        wgt = _weight(ctx, c, own["x"], own["y"], R, own["fit"])
        if wgt <= 0:
            continue
        off = abs(_wrap(math.atan2(c.y - own["y"], c.x - own["x"]) - own["facing"]))
        mult = 1.0 if off <= flank_a else (P["flank_factor"] if off <= rear_a else P["rear_factor"])
        pic["danger"] += wgt * mult
        if mult > 1.0:
            pic["flank"] += wgt * mult
            pic["flank_front"] += wgt
        pic["threats"].append((wgt * mult, c))
        pic["read"].append(c.handle)
    pic["threats"].sort(key=lambda t: (-t[0], t[1].handle))
    return pic


def exposure_at(ctx: Context, heading: float) -> float:
    """Danger to the officer's unit if it faced `heading` (review 006/5)."""
    P = ctx.params
    own = ctx.own
    flank_a, rear_a = math.radians(P["flank_angle_deg"]), math.radians(P["rear_angle_deg"])
    total = 0.0
    for c in _enemies(ctx):
        wgt = _weight(ctx, c, own["x"], own["y"], P["threat_radius_m"], own["fit"])
        if wgt <= 0:
            continue
        off = abs(_wrap(math.atan2(c.y - own["y"], c.x - own["x"]) - heading))
        total += wgt * (1.0 if off <= flank_a else (P["flank_factor"] if off <= rear_a else P["rear_factor"]))
    return total


def _danger_at(ctx: Context, x: float, y: float, read: list) -> float:
    R = ctx.params["threat_radius_m"]
    total = 0.0
    for c in _enemies(ctx):
        wgt = _weight(ctx, c, x, y, R, ctx.own["fit"])
        if wgt > 0:
            total += wgt
            if c.handle not in read:
                read.append(c.handle)
    return total


def _lat_cost(ctx: Context, order: OrderView | None) -> float:
    if order is None:
        return 0.0
    return ctx.params[f"latitude_cost_{order.latitude}"] * (1.0 - ctx.tendencies.initiative)


# ---- option menus ------------------------------------------------------------------------------

def officer_options(ctx: Context):
    """An entity's officer, at a routine reassessment or an interrupt."""
    t = ctx.tendencies
    own = ctx.own
    pic = officer_picture(ctx)
    danger, read = pic["danger"], pic["read"]
    cost = _lat_cost(ctx, ctx.standing)
    within = _WITHIN.get(ctx.standing.kind, set()) if ctx.standing else None
    moving = own["task"] in MOVING
    condition = own["fatigue"] * 0.5 + (1.0 - own["order"]) * 0.5
    losses = 1.0 - own["fit"] / max(own["start_strength"], 1)

    def option(name: str, actions: list, comps: dict, ok: bool = False) -> Option:
        """Whether an option goes beyond the standing order is recorded on its own (review
        006/3); its cost is the latitude cost, which may be zero."""
        beyond = within is not None and name.split(":")[0] not in within and not ok
        comps["deviation"] = -cost if beyond else 0.0
        return Option(name, actions, comps, beyond_orders=beyond)

    opts = [Option("continue", [], {"inertia": 0.25, "exposure": -danger * (1 - t.risk)})]
    if moving and danger > 0:                      # no reason to stop when he sees no danger
        opts.append(option("hold", [{"do": "order", "spec": {"kind": "hold"}}],
                           {"exposure": -0.7 * danger * (1 - t.risk)}))
    if pic["flank"] > 0:
        # turn towards a threat that is actually on the flank or rear, rescoring every sector at
        # the new heading (review 006/5); of the two heaviest such threats, the better heading
        flank_a = math.radians(ctx.params["flank_angle_deg"])
        side_threats = [c for _, c in pic["threats"]
                        if abs(_wrap(math.atan2(c.y - own["y"], c.x - own["x"]) - own["facing"])) > flank_a][:2]
        best = min(side_threats, key=lambda c: (exposure_at(ctx, math.atan2(c.y - own["y"], c.x - own["x"])), c.handle))
        heading = math.atan2(best.y - own["y"], best.x - own["x"])
        opts.append(option("face", [{"do": "order", "spec": {"kind": "face", "toward": [best.x, best.y]}}],
                           {"turning": -0.05, "exposure": -exposure_at(ctx, heading) * (1 - t.risk)}))
    if danger > 0:
        opts.append(option("withdraw", [{"do": "order", "spec": {"kind": "withdraw_to", "place": list(ctx.home)}}],
                           {"giving_ground": -1.0, "exposure": -0.3 * danger * (1 - t.risk),
                            "condition": condition + losses}))
    seen_targets = 0
    for _, c in pic["threats"]:
        if seen_targets >= 3:
            break
        seen_targets += 1
        odds = own["fit"] / max(c.strength, 1)
        ordered = bool(ctx.standing and ctx.standing.kind == "attack" and ctx.standing.target_handle == c.handle)
        opts.append(option(f"attack:{c.handle}",
                           [{"do": "order", "spec": {"kind": "attack", "target_handle": c.handle}}],
                           {"opportunity": t.commitment * (min(odds, 3.0) - 1.0),
                            "exposure": -danger * (1 - t.risk), "condition": -condition}, ok=ordered))
    opts = _settle(ctx, opts)
    side = []
    if (ctx.has_commander and ctx.trigger in ("contact", "flank") and danger > 0
            and ctx.tick - own.get("reported_t", -10 ** 9) >= ctx.params["report_min_interval_s"] / ctx.tick_s):
        side.append({"do": "report"})         # a new threat is reported up, whatever he chooses
    return opts, read, side


def receipt_options(ctx: Context):
    """An officer with an order just understood: obey it or not."""
    t = ctx.tendencies
    o = ctx.received
    own = ctx.own
    read: list = []
    risk = 0.0
    if o.kind == "advance_to" and o.place:
        risk = -_danger_at(ctx, o.place[0], o.place[1], read) * (1 - t.risk)
    elif o.kind in ("attack", "support"):
        # score where he would actually go: the track he took the order to mean (review 006/4)
        mine = next((c for c in ctx.contacts if c.handle == o.target_handle), None)
        at = (mine.x, mine.y) if mine is not None else o.target_at
        if mine is not None and mine.handle not in read:
            read.append(mine.handle)
        if at:
            risk = -_danger_at(ctx, at[0], at[1], read) * (1 - t.risk)
    here = _danger_at(ctx, own["x"], own["y"], read)
    condition = own["fatigue"] * 0.5 + (1.0 - own["order"]) * 0.5
    duty = 1.0 + ctx.params[f"latitude_cost_{o.latitude}"] * (1.0 - t.initiative)
    obey = Option("obey", [{"do": "obey"}], {"duty": duty, "risk": risk,
                                             "relief": 0.3 * here * (1 - t.risk) if o.kind == "withdraw_to" else 0.0})
    decline = Option("decline", [{"do": "decline"}], {"duty": -1.0, "condition": condition * (0.5 + t.initiative),
                                                      "avoided_risk": -risk * t.initiative}, beyond_orders=True)
    return [obey, decline], read, []


def commander_threats(ctx: Context):
    """The threat a commander believes each unit under him faces, and the contacts read. This
    is the unfiltered picture; what he has already done does not change it (review 006/6)."""
    R = ctx.params["commander_threat_radius_m"]
    read: list = []
    threat = {}
    for s in ctx.subs:
        tot = 0.0
        for c in _enemies(ctx):
            wgt = _weight(ctx, c, s.x, s.y, R, s.strength)
            if wgt > 0:
                tot += wgt
                if c.handle not in read:
                    read.append(c.handle)
        threat[s.id] = tot
    return threat, read


def threatened(ctx: Context) -> list:
    threat, _ = commander_threats(ctx)
    return sorted(i for i, v in threat.items() if v > 0)


def commander_options(ctx: Context):
    """A wing or army commander: wait, send a reserve forward, pull a threatened unit back, or
    (army) sound the recall."""
    t = ctx.tendencies
    P = ctx.params
    threat, read = commander_threats(ctx)
    sub_of = {s.id: s for s in ctx.subs}
    hot = sorted((sid for sid in threat if threat[sid] > 0), key=lambda i: (-threat[i], i))
    peak = threat[hot[0]] if hot else 0.0
    reserves = [s for s in ctx.subs if threat[s.id] == 0 and s.id not in ctx.committed]
    opts = [Option("wait", [], {"inertia": 0.5, "exposure": -peak * (1 - t.risk)})]
    if hot and reserves:
        s = sub_of[hot[0]]
        r = min(reserves, key=lambda q: (math.hypot(q.x - s.x, q.y - s.y), q.id))
        # come up beside the threatened unit, on the side the threat is coming from
        foe = min((c for c in _enemies(ctx) if c.handle in read),
                  key=lambda c: (math.hypot(c.x - s.x, c.y - s.y), c.handle))
        d = max(math.hypot(foe.x - s.x, foe.y - s.y), 1e-9)
        k = min(P["support_distance_m"], d / 2) / d
        place = [s.x + (foe.x - s.x) * k, s.y + (foe.y - s.y) * k]
        opts.append(Option(f"reinforce:{r.id}>{s.id}",
                           [{"do": "order", "recipient": r.id, "spec": {"kind": "advance_to", "place": place}},
                            {"do": "commit", "id": r.id}],
                           {"support": threat[s.id] * (0.5 + t.commitment),
                            "keeping_a_reserve": -t.reserve * (1.0 if len(reserves) == 1 else 0.5),
                            "exposure": -0.5 * peak * (1 - t.risk)}))
    if hot:
        s = sub_of[hot[0]]
        opts.append(Option(f"withdraw:{s.id}",
                           [{"do": "order", "recipient": s.id, "spec": {"kind": "withdraw_to", "place": list(s.home)}}],
                           {"relief": threat[s.id] * (1 - t.risk), "giving_ground": -1.0,
                            "exposure": -(peak - threat[s.id]) * (1 - t.risk)}))
    if ctx.rank == "army" and len(hot) >= 2:
        total = sum(threat[i] for i in hot)
        opts.append(Option("recall", [{"do": "signal", "meaning": "recall"}],
                           {"relief": 0.8 * total * (1 - t.risk), "giving_ground": -2.0}))
    opts = [o for o in opts if o.name not in ctx.done]
    for o in opts[1:]:
        o.components["change_of_plan"] = -P["change_cost"]
    return opts, read, []


def _settle(ctx: Context, opts: list) -> list:
    """Commitment to a course: what he is already doing is "continue", not a new option, and
    any change of course costs `change_cost`, so he changes only for a reason."""
    out = []
    for o in opts:
        if o.name == ctx.current:
            continue
        if o.name != "continue":
            o.components["change_of_plan"] = -ctx.params["change_cost"]
        out.append(o)
    return out


# ---- choosing ----------------------------------------------------------------------------------

def choose(opts: list, temperature: float, u: float):
    """Softmax over totals; `u` in (0, 1) picks. Returns (index, probabilities)."""
    totals = [o.total for o in opts]
    top = max(totals)
    ex = [math.exp((x - top) / temperature) for x in totals]
    s = sum(ex)
    probs = [e / s for e in ex]
    acc = 0.0
    for i, p in enumerate(probs):
        acc += p
        if u < acc:
            return i, probs
    return len(opts) - 1, probs


def decide(ctx: Context, u: float):
    """Returns (options, chosen index, probabilities, handles read, side actions)."""
    if ctx.received is not None:
        opts, read, side = receipt_options(ctx)
    elif ctx.rank == "officer":
        opts, read, side = officer_options(ctx)
    else:
        opts, read, side = commander_options(ctx)
    i, probs = choose(opts, ctx.params["decision_temperature"], u)
    return opts, i, probs, read, side
