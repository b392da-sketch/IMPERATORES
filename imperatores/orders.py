"""Orders, messages, signals and deployment plans (specification 5.5; research Q002).

An **order** is an intent, not a path: hold; advance to a place; withdraw to a place; attack a
body; support a body. It carries a **latitude** (how much discretion the recipient has) and a
record of its life. Its status moves only along legal transitions, and every order ends in
exactly one terminal status, executed or failed (Codex review 005, findings 2 and 6):

  decided -> [waiting for a messenger] -> sent -> delivered -> understood
          -> [waiting to execute] -> executed
  any status before executed -> failed (recording the stage where it failed, and why)

  decided     the issuer settles on it (from step 5, with the decision record that led to it)
  sent        handed to a messenger (after waiting for one, if none was at hand)
  delivered   the messenger hands it over (or is caught, lost, cannot reach or find the recipient)
  understood  the recipient makes sense of it against his own picture of the battle
  executed    the recipient begins to carry it out: his task is set, once a route to the place
              exists (or it fails: disordered or exhausted too long, no route, superseded by a
              later order, the unit destroyed; from step 5, he chooses otherwise). What happens
              afterwards on the march is recorded as events linked to the order.

**Authority** (finding 1): an order goes only from a commander to someone in his command (any
depth), or from an entity's officer to himself (plans, signals, decisions). Reports go to a
commander on the same side.

**Targets are described from the issuer's picture**, never by true identity: side, kind, and
where the issuer believes the body is. The recipient matches the description against his own
picture: the nearest contact of that side and a compatible kind within `order_target_radius_m`.
Which body the issuer meant, and which the recipient took, are kept in the world's audit record
(`w.audit`), never on the order, so no decision can read them.

**Keys** (finding 10). Every order, message and signal has a stable random key of whole numbers,
chosen so that unrelated actions never shift each other's draws:
  (issuer, 1, n)                     a decision (step 5), counted per issuer
  (issuer, 4, k)                     scenario input number k (its position in the file)
  (relayer, 5, recipient, *parent)   an order relayed by a commander
  (entity, 6, k)                     the entity's plan entry k
  (entity, 7, *signal)               an entity's response to a signal
Its id, for people and the record, is readable: "<issuer>.<n>" for orders an issuer decides or is
given as input (numbered per issuer, orders only), "<parent>><recipient>" for relays,
"<entity>.plan<k>" for plans, "<signal>><entity>" for responses, "<sender>.r<n>" for reports and
"<issuer>.s<n>" for signals.

**Signals** (Q002): `recall` (attested), `cavalry_engage` (attested, mounted troops only), and
`action:<name>` (a cue whose meaning is fixed in the deployment plan). `advance` exists only as a
labelled engineering extension. A signal binds an entity only if it comes from one of its own
commanders, or from an emitter its plan names (finding 9).

**Deployment plans** (Q002, Polybius 14.4): every entity has a home, its place in the line,
by default its deployment position (where `recall` sends it), and may have conditional
instructions, "on <condition>, do <order>". Conditions use only the officer's own picture.

**Reports** carry the sender's contacts, captured as immutable values when the report is sent.

Scenario "inputs" (orders, reports and signals at given times) stand in for decisions until
step 5, and for the player in commander mode (M1).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

ORDER_KINDS = ("hold", "advance_to", "withdraw_to", "attack", "support")
PLACE_KINDS = ("advance_to", "withdraw_to")
TARGET_KINDS = ("attack", "support")
LATITUDES = ("strict", "normal", "free")
SIGNALS = ("recall", "cavalry_engage", "advance")      # plus "action:<name>"
SIGNAL_EXTENSIONS = ("advance",)                         # not attested for 220-100 BCE (Q002)
MOUNTED_ONLY = ("cavalry_engage",)
TERMINAL = ("executed", "failed")

_NEXT = {
    "decided": {"waiting", "sent", "delivered", "failed"},
    "waiting": {"sent", "failed"},
    "sent": {"delivered", "failed"},
    "delivered": {"understood", "failed"},
    "understood": {"waiting_exec", "executed", "failed"},
    "waiting_exec": {"executed", "failed"},
    "executed": set(),
    "failed": set(),
}
_STAGE = {"waiting": "waiting for a messenger", "waiting_exec": "waiting to execute"}

KEY_DECISION, KEY_INPUT, KEY_RELAY, KEY_PLAN, KEY_SIGNAL_RESPONSE = 1, 4, 5, 6, 7


def valid_signal(meaning: str) -> bool:
    return meaning in SIGNALS or (meaning.startswith("action:") and len(meaning) > 7)


def fold(w, *parts) -> None:
    """Fold a change to command state into the replay hash (finding 8)."""
    w.command_hasher.update(json.dumps([w.tick, *parts], sort_keys=True, separators=(",", ":"),
                                       default=list, allow_nan=False).encode())


@dataclass(frozen=True)
class TargetDescription:
    side: str
    kind: str
    x: float
    y: float
    seen_t: int


@dataclass
class Order:
    id: str                       # readable, stable (see module notes)
    key: tuple                    # stable random key of whole numbers
    issuer: int
    recipient: int
    kind: str
    latitude: str = "normal"
    place: tuple | None = None    # for advance_to / withdraw_to
    target: TargetDescription | None = None   # for attack / support
    origin: str = "input"         # "input", "relay", "plan", "signal"; "decision" from step 5
    parent: str | None = None     # the order or signal this one comes from
    stages: list = field(default_factory=list)   # [stage, tick, detail]
    status: str = "decided"
    understood_handle: int | None = None

    def to_record(self) -> dict:
        return {"id": self.id, "key": list(self.key), "issuer": self.issuer, "recipient": self.recipient,
                "kind": self.kind, "latitude": self.latitude, "place": list(self.place) if self.place else None,
                "target": None if self.target is None else dict(vars(self.target)),
                "origin": self.origin, "parent": self.parent, "status": self.status,
                "understood_handle": self.understood_handle,
                "stages": [[s, t, dict(d)] for s, t, d in self.stages]}


def transition(w, o: Order, to: str, detail: dict | None = None) -> None:
    """Move an order to its next status, recording the stage. An illegal transition is a
    simulation fault and raises."""
    if to not in _NEXT[o.status]:
        raise RuntimeError(f"order {o.id}: illegal transition {o.status} -> {to}")
    d = dict(detail or {})
    o.status = to
    o.stages.append([_STAGE.get(to, to), w.tick, d])
    fold(w, "order", o.id, to, d)


def fail(w, o: Order, at: str, why: str, detail: dict | None = None) -> None:
    transition(w, o, "failed", {"at": at, "why": why, **(detail or {})})


@dataclass
class Message:
    id: str
    key: tuple
    kind: str                     # "order" or "report"
    sender: int
    recipient: int
    created_t: int
    order: Order | None = None
    contacts: tuple = ()          # for a report: the sender's Contact values when it was sent


@dataclass
class Messenger:
    key: tuple                    # the message's key: his stable random key
    sender: int
    message: Message
    mobility: str                 # "horse" or "foot"
    x: float
    y: float
    status: str = "riding"        # riding, searching, returning; ended: home, lost, captured, stranded, dismissed
    dest: tuple = (0.0, 0.0)
    route: list | None = None
    route_for: list | None = None
    search_ticks: int = 0
    stuck_ticks: int = 0          # ticks in a row without progress (outward or back)
    ridden_m: float = 0.0

    @property
    def id(self) -> str:
        return self.message.id


ENDED = ("home", "lost", "captured", "stranded", "dismissed")


@dataclass
class Plan:
    home: tuple                   # the entity's place in the line (where recall sends it)
    on: list = field(default_factory=list)    # [{"when": {...}, "do": {...}, "from": [ids] or None, "fired": bool}]


def order_from_spec(oid: str, key: tuple, issuer: int, recipient: int, spec: dict, origin: str, parent=None) -> Order:
    kind = spec["kind"]
    if kind not in ORDER_KINDS:
        raise ValueError(f"order kind {kind!r}")
    lat = spec.get("latitude", "normal")
    if lat not in LATITUDES:
        raise ValueError(f"order latitude {lat!r}")
    place = None
    if kind in PLACE_KINDS:
        if "place" not in spec:
            raise ValueError(f"order {kind} needs a place")
        place = (float(spec["place"][0]), float(spec["place"][1]))
    target = spec.get("target")
    return Order(id=oid, key=tuple(int(k) for k in key), issuer=issuer, recipient=recipient, kind=kind,
                 latitude=lat, place=place, target=target if isinstance(target, TargetDescription) else None,
                 origin=origin, parent=parent)


def understand(w, o: Order, recipient_view) -> bool:
    """The recipient makes sense of an order against his own picture (a BeliefView)."""
    P = w.params
    if o.kind not in TARGET_KINDS:
        transition(w, o, "understood", {})
        return True
    from .belief import compatible
    d = o.target
    best, best_d = None, math.inf
    for c in recipient_view.contacts:
        if c.side != d.side or not compatible(c.kind, d.kind):
            continue
        dist = math.hypot(c.x - d.x, c.y - d.y)
        if dist <= P["order_target_radius_m"] and dist < best_d:
            best, best_d = c, dist
    if best is None:
        fail(w, o, "understood", "target not identified: nothing in the recipient's picture matches the description",
             {"described": [d.x, d.y], "kind": d.kind, "side": d.side})
        return False
    o.understood_handle = best.handle
    detail = {"handle": best.handle, "believed_at": [best.x, best.y], "described_at": [d.x, d.y], "offset_m": best_d}
    if best_d > P["order_stale_m"]:
        detail["stale"] = ("the body the recipient matched is not where the issuer described it "
                           "(it has moved, or it is a different body: the recipient cannot tell which)")
    transition(w, o, "understood", detail)
    # audit only (the "Why?" chain and tests): which true body did he take it to mean?
    b = w.beliefs[recipient_view.owner]
    took = next((t for t, h in b._truth.items() if h == best.handle), None)
    a = w.audit.setdefault(o.id, {})
    a["took"] = took
    if a.get("intended") is not None and took is not None and took != a["intended"]:
        a["misread"] = {"meant": a["intended"], "took": took}
    fold(w, "audit", o.id, a)
    return True
