"""Belief pictures (specification 5.4): what each commander and officer thinks is on the field.

A belief holds contacts: bodies of troops the owner has seen, or been told about, each with
what was perceived and when. It is never copied from the true state. It changes only
through `observe` (perception) and `merge_report` (reports carried by messengers, step 4),
so an entity nobody has seen or reported cannot appear in it, and a change in the true
state of an unseen entity cannot change it.

Decision code (step 5) receives a `BeliefView`: an immutable copy built only from the
belief store, with no reference to the world.

Assumptions (M0), recorded in docs/M0_BUILD_NOTES.md:
  * an observer can tell friend from foe for any body he sees;
  * while a body stays in sight, the observer keeps track of which body it is (no confusing
    two bodies with each other);
  * an entity's officer knows his own entity's state exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

CONTACT_FIELDS = ("id", "side", "kind", "x", "y", "pos_err", "strength", "order", "facing",
                  "seen_t", "first_seen_t", "source", "received_t")


@dataclass
class Belief:
    owner: int
    contacts: dict = field(default_factory=dict)     # entity id -> contact dict
    own: dict | None = None                          # an officer's exact knowledge of his own entity


def observe(b: Belief, contact: dict) -> None:
    """Record a direct sighting. A sighting is always newer than what was held."""
    tid = contact["id"]
    old = b.contacts.get(tid)
    c = dict(contact)
    c["source"] = "seen"
    c["received_t"] = c["seen_t"]
    c["first_seen_t"] = min(old["first_seen_t"], c["seen_t"]) if old else c["seen_t"]
    b.contacts[tid] = c


def merge_report(b: Belief, reported: list[dict], sender: int, received_t: int) -> list[int]:
    """Merge contacts from a report. A reported contact replaces what is held only if it was
    seen more recently. Returns the ids that changed."""
    changed = []
    for rc in reported:
        tid = rc["id"]
        old = b.contacts.get(tid)
        if old is not None and old["seen_t"] >= rc["seen_t"]:
            continue
        c = {k: rc.get(k) for k in CONTACT_FIELDS}
        c["source"] = {"report_from": int(sender)}
        c["received_t"] = int(received_t)
        c["first_seen_t"] = min(old["first_seen_t"], int(received_t)) if old else int(received_t)
        b.contacts[tid] = c
        changed.append(tid)
    return changed


@dataclass(frozen=True)
class Contact:
    id: int
    side: str
    kind: str              # a function name when recognised; else "horse", "foot" or "troops"
    x: float
    y: float
    pos_err: float         # spread of the position error when it was perceived (m)
    strength: int          # estimated numbers
    order: float | None    # judged order, if it was close enough to judge
    facing: float | None   # radians, if it was close enough to tell
    seen_t: int            # tick when this was last perceived (by the owner, or by the reporter)
    first_seen_t: int      # tick when the owner first knew of this body
    source: object         # "seen" or a read-only {"report_from": id}
    received_t: int        # tick when the owner got this information


@dataclass(frozen=True)
class BeliefView:
    owner: int
    tick: int
    contacts: tuple        # of Contact, sorted by id
    own: object            # read-only mapping or None

    def contact(self, tid: int):
        for c in self.contacts:
            if c.id == tid:
                return c
        return None

    def age(self, c: Contact) -> int:
        return self.tick - c.seen_t


def _freeze(v):
    if isinstance(v, dict):
        return MappingProxyType({k: _freeze(x) for k, x in v.items()})
    if isinstance(v, list):
        return tuple(_freeze(x) for x in v)
    return v


def view(w, owner: int) -> BeliefView:
    b = w.beliefs[owner]
    contacts = tuple(Contact(**{k: _freeze(c[k]) for k in CONTACT_FIELDS})
                     for _, c in sorted(b.contacts.items()))
    return BeliefView(owner=owner, tick=w.tick, contacts=contacts,
                      own=_freeze(dict(b.own)) if b.own is not None else None)


def to_json(b: Belief) -> dict:
    return {"owner": b.owner, "own": b.own,
            "contacts": [b.contacts[k] for k in sorted(b.contacts)]}
