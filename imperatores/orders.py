"""Orders, messages, signals and deployment plans (specification 5.5; research Q002).

An **order** is an intent, not a path: hold; advance to a place; withdraw to a place; attack a
body; support a body. It carries a **latitude** (how much discretion the recipient has) and a
record of its life in **stages**, each with a time and, if it failed there, why:

  decided     the issuer settles on it (from step 5, with the decision record that led to it)
  sent        handed to a messenger (or waiting for one)
  delivered   the messenger finds the recipient (or is lost, captured, or cannot find him)
  understood  the recipient makes sense of it against his own picture of the battle
  executed    the recipient acts on it (or cannot: disordered, exhausted, no route; or, from
              step 5, chooses not to, within or beyond his latitude)

**Targets are described from the issuer's picture**, never by true identity: side, kind, and
where the issuer believes the body is ("the enemy horse near (x, y)"). The recipient matches
the description against his own picture: the nearest contact of that side and a compatible
kind within `order_target_radius_m`. He may find nothing ("not identified"), or a different
body from the one the issuer meant ("misread"), because their pictures differ. Which body the
issuer meant is kept in the order's record for the "Why?" chain only; no decision sees it.

**Signals** (Q002): `recall` (attested), `cavalry_engage` (attested, for mounted troops), and
`action:<name>` (a cue whose meaning is fixed in the deployment plan, attested as a practice).
`advance` exists only as a labelled engineering extension. A signal is emitted, received (within
hearing range, shorter where ground blocks the line between them), and complied with, each a
separate stage. What an entity does on hearing it comes from its plan.

**Deployment plans** (Q002, Scipio briefing Laelius and Masinissa, Polybius 14.4): each entity
may have a home position (its place in the line, where `recall` sends it) and conditional
instructions, "on <condition>, do <order>". Conditions are evaluated only on the entity
officer's own picture: a signal heard, an enemy body believed within a distance of a place, or
a time.

**Reports** are messages carrying the sender's contacts, captured as immutable values when the
report is sent, merged into the recipient's picture on delivery.

Scenario "inputs" (orders, reports and signals at given times) stand in for decisions until
step 5, and for the player in commander mode (M1). They are labelled as inputs in the record.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

ORDER_KINDS = ("hold", "advance_to", "withdraw_to", "attack", "support")
PLACE_KINDS = ("advance_to", "withdraw_to")
TARGET_KINDS = ("attack", "support")
LATITUDES = ("strict", "normal", "free")
SIGNALS = ("recall", "cavalry_engage", "advance")      # plus "action:<name>"
SIGNAL_EXTENSIONS = ("advance",)                         # not attested for 220-100 BCE (Q002)


def valid_signal(meaning: str) -> bool:
    return meaning in SIGNALS or (meaning.startswith("action:") and len(meaning) > 7)


@dataclass(frozen=True)
class TargetDescription:
    side: str
    kind: str
    x: float
    y: float
    seen_t: int


@dataclass
class Order:
    id: str                       # "<issuer>.<sequence>": stable, independent of other issuers
    issuer: int
    recipient: int
    kind: str
    latitude: str = "normal"
    place: tuple | None = None    # for advance_to / withdraw_to
    target: TargetDescription | None = None   # for attack / support
    origin: str = "input"         # "input", "relay", "plan", "signal"; "decision" from step 5
    parent: str | None = None     # the order this one relays, if any
    intended: int | None = None   # record only: the true body the issuer meant (never shown to decisions)
    stages: list = field(default_factory=list)   # [stage, tick, detail]
    status: str = "decided"       # decided, sent, delivered, understood, executed, failed
    understood_handle: int | None = None

    def stage(self, w, name: str, detail: dict | None = None) -> None:
        self.stages.append([name, w.tick, detail or {}])

    def fail(self, w, at: str, why: str, detail: dict | None = None) -> None:
        self.status = "failed"
        self.stages.append(["failed", w.tick, {"at": at, "why": why, **(detail or {})}])

    def to_record(self) -> dict:
        return {"id": self.id, "issuer": self.issuer, "recipient": self.recipient, "kind": self.kind,
                "latitude": self.latitude, "place": list(self.place) if self.place else None,
                "target": None if self.target is None else vars(self.target).copy(),
                "origin": self.origin, "parent": self.parent, "intended": self.intended,
                "status": self.status, "understood_handle": self.understood_handle,
                "stages": [[s, t, dict(d)] for s, t, d in self.stages]}


@dataclass
class Message:
    id: str                       # same as the order's id, or "<sender>.<sequence>" for a report
    kind: str                     # "order" or "report"
    sender: int
    recipient: int
    created_t: int
    order: Order | None = None
    contacts: tuple = ()          # for a report: the sender's Contact values when it was sent


@dataclass
class Messenger:
    key: tuple                    # (sender, sequence): stable random key
    sender: int
    message: Message
    mobility: str                 # "horse" or "foot"
    x: float
    y: float
    status: str = "riding"        # riding, searching, returning, home, lost, captured
    dest: tuple = (0.0, 0.0)
    route: list | None = None
    route_for: list | None = None
    search_ticks: int = 0
    ridden_m: float = 0.0

    @property
    def id(self) -> str:
        return f"{self.key[0]}.{self.key[1]}"


@dataclass
class Plan:
    home: tuple                   # the entity's place in the line (where recall sends it)
    on: list = field(default_factory=list)    # [{"when": {...}, "do": {...}, "fired": bool}]


def order_from_spec(oid: str, issuer: int, recipient: int, spec: dict, origin: str, parent=None) -> Order:
    kind = spec["kind"]
    if kind not in ORDER_KINDS:
        raise ValueError(f"order kind {kind!r}")
    lat = spec.get("latitude", "normal")
    if lat not in LATITUDES:
        raise ValueError(f"order latitude {lat!r}")
    place = None
    target = spec.get("target")
    if kind in PLACE_KINDS:
        if "place" not in spec:
            raise ValueError(f"order {kind} needs a place")
        place = (float(spec["place"][0]), float(spec["place"][1]))
    return Order(id=oid, issuer=issuer, recipient=recipient, kind=kind, latitude=lat, place=place,
                 target=target if isinstance(target, TargetDescription) else None, origin=origin, parent=parent)


def understand(w, o: Order, recipient_view) -> bool:
    """The recipient makes sense of an order against his own picture (a BeliefView). Records
    'understood', or fails it. For target orders, records misreading and staleness."""
    P = w.params
    if o.kind not in TARGET_KINDS:
        o.status = "understood"
        o.stage(w, "understood", {})
        return True
    d = o.target
    best, best_d = None, math.inf
    from .belief import compatible
    for c in recipient_view.contacts:
        if c.side != d.side or not compatible(c.kind, d.kind):
            continue
        dist = math.hypot(c.x - d.x, c.y - d.y)
        if dist <= P["order_target_radius_m"] and dist < best_d:
            best, best_d = c, dist
    if best is None:
        o.fail(w, "understood", "target not identified: nothing in the recipient's picture matches the description",
               {"described": [d.x, d.y], "kind": d.kind, "side": d.side})
        return False
    o.understood_handle = best.handle
    detail = {"handle": best.handle, "believed_at": [best.x, best.y], "described_at": [d.x, d.y],
              "offset_m": best_d}
    # record only: did he take it to mean the body the issuer meant?
    b = w.beliefs[recipient_view.owner]
    true_of = {h: t for t, h in b._truth.items()}
    meant = o.intended
    took = true_of.get(best.handle)
    if meant is not None and took is not None and took != meant:
        detail["misread"] = {"meant": meant, "took": took}
    if best_d > P["order_stale_m"]:
        detail["stale"] = ("the body the recipient matched is not where the issuer described it "
                           "(it has moved, or it is a different body: the recipient cannot tell which)")
    o.status = "understood"
    o.stage(w, "understood", detail)
    return True
