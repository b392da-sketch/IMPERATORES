"""Belief pictures (specification 5.4): what each commander and officer thinks is on the field.

A belief holds **tracks**: bodies of troops the owner has seen, or been told about. Each track
has an observer-local handle (1, 2, 3... per owner), never the true identity of the body
(Codex review 004, finding 3), and a `Contact`: what was perceived and when. It is never
copied from the true state.

The boundary (findings 1 and 2):
  * a belief changes only through `apply_sighting` (perception) and `apply_report` (a report
    delivered by a messenger, step 4);
  * every value entering is validated (types, finite numbers, ranges) and stored as an
    immutable `Contact` made only of plain numbers and strings;
  * every change is folded into the world's belief hash, so replay covers it;
  * `view` gives decision code an immutable `BeliefView`, and `to_record` gives a detached
    copy for the record. Neither holds a reference into the world.

Tracking rules (all recorded in docs/M0_BUILD_NOTES.md as assumptions):
  * while a body stays in sight (seen again within `track_gap_s`), the observer keeps track of
    which body it is;
  * links to bodies not seen within `track_gap_s` are dropped before any new sighting is
    associated, so association never depends on which true body is seen (review 005/7);
  * after a longer gap, a body is re-identified as the same body only if it is recognised
    (seen within recognition range, where standards and equipment identify a particular
    body); otherwise it is matched by what is seen (side, kind, position) to a track not
    currently linked, or becomes a new track, and an old one may remain as a duplicate until
    the body is recognised; merging leaves a redirect from the old handle to the new;
  * a reported body is matched to a track by what is known about it (side, kind, position),
    never by its true identity;
  * an observer can tell friend from foe for any body he sees;
  * an entity's officer knows his own entity's present state exactly; a commander knows his
    own position, rank and command.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from types import MappingProxyType

from .state import FUNCTIONS, SIDES

MOBILITY_OF = {"heavy_infantry": "foot", "skirmishers": "foot", "light_cavalry": "horse", "heavy_cavalry": "horse"}
KINDS = FUNCTIONS + ("horse", "foot", "troops")
_SPECIFICITY = {"troops": 0, "horse": 1, "foot": 1, **{f: 2 for f in FUNCTIONS}}


@dataclass(frozen=True)
class Contact:
    handle: int            # the owner's own label for this track
    side: str
    kind: str              # a function when recognised; else "horse", "foot" or "troops"
    x: float
    y: float
    pos_err: float         # the owner's idea of how far off the position may be (m)
    strength: int          # estimated numbers
    order: float | None    # judged order, if it was close enough to judge
    facing: float | None   # radians, to the visual resolution, if close enough to tell
    seen_t: int            # tick when this was last perceived (by the owner, or by the reporter)
    first_seen_t: int      # tick when the owner first knew of this track
    source: str            # "seen" or "report"
    report_from: int | None
    received_t: int        # tick when the owner got this information


def _num(v, name, lo=-math.inf, hi=math.inf) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not (lo <= v <= hi):
        raise ValueError(f"contact field {name}={v!r} is not a finite number in [{lo}, {hi}]")
    return float(v)


def _whole(v, name, lo=0) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < lo:
        raise ValueError(f"contact field {name}={v!r} is not a whole number >= {lo}")
    return int(v)


def _validated(c: Contact) -> Contact:
    if c.side not in SIDES:
        raise ValueError(f"contact side {c.side!r}")
    if c.kind not in KINDS:
        raise ValueError(f"contact kind {c.kind!r}")
    if c.source not in ("seen", "report"):
        raise ValueError(f"contact source {c.source!r}")
    return Contact(
        handle=_whole(c.handle, "handle", 1), side=c.side, kind=c.kind,
        x=_num(c.x, "x"), y=_num(c.y, "y"), pos_err=_num(c.pos_err, "pos_err", 0.0),
        strength=_whole(c.strength, "strength"),
        order=None if c.order is None else _num(c.order, "order", 0.0, 1.0),
        facing=None if c.facing is None else _num(c.facing, "facing", -4.0, 4.0),
        seen_t=_whole(c.seen_t, "seen_t"), first_seen_t=_whole(c.first_seen_t, "first_seen_t"),
        source=c.source, report_from=None if c.report_from is None else _whole(c.report_from, "report_from"),
        received_t=_whole(c.received_t, "received_t"))


@dataclass
class Belief:
    owner: int
    tracks: dict = field(default_factory=dict)       # handle -> Contact
    _truth: dict = field(default_factory=dict)       # true entity id -> handle (sightings only; never exposed)
    _former: dict = field(default_factory=dict)      # handle -> true id, for tracks whose link was lost (never exposed)
    redirects: dict = field(default_factory=dict)    # handle -> handle: tracks the owner merged into another (his own knowledge)
    _next: int = 1

    def _new_handle(self) -> int:
        h = self._next
        self._next += 1
        return h


def compatible(a: str, b: str) -> bool:
    """Could a body described as kind a be the same as one described as kind b?"""
    if a == "troops" or b == "troops" or a == b:
        return True
    ma = MOBILITY_OF.get(a, a)
    mb = MOBILITY_OF.get(b, b)
    return ma == mb and (a not in FUNCTIONS or b not in FUNCTIONS)


def _fold(w, owner: int, c: Contact | None, handle: int, tag: str) -> None:
    w.belief_hasher.update(repr((tag, owner, handle, None if c is None else astuple_c(c))).encode())


def astuple_c(c: Contact) -> tuple:
    return (c.handle, c.side, c.kind, c.x, c.y, c.pos_err, c.strength, c.order, c.facing,
            c.seen_t, c.first_seen_t, c.source, c.report_from, c.received_t)


def _link(w, b: Belief, tag: str, true_id: int, h: int) -> None:
    """Fold a change to the private tracking links into the replay hash (finding 8)."""
    w.belief_hasher.update(repr((tag, b.owner, int(true_id), int(h), w.tick)).encode())


def age_links(w, b: Belief) -> None:
    """Drop every link to a body not seen within track_gap_s, before any sighting is associated
    (Codex review 005, finding 7). Association then sees the same tracks whichever true body
    the new sighting happens to be, so identical observations give identical handles."""
    P = w.params
    gap_ticks = P["track_gap_s"] / P["tick_seconds"]
    for tid in sorted(b._truth):
        h = b._truth[tid]
        c = b.tracks.get(h)
        if c is None or w.tick - c.seen_t > gap_ticks:
            del b._truth[tid]
            if c is not None:
                b._former[h] = tid       # remembered internally, so recognition can merge them later
            _link(w, b, "unlinked", tid, h)


def resolve(b: Belief, h):
    """The handle a track goes by now, following the owner's own merges."""
    seen = set()
    while h in b.redirects and h not in seen:
        seen.add(h)
        h = b.redirects[h]
    return h


def _associate(b: Belief, side: str, kind: str, x: float, y: float, radius: float, only_unlinked: bool):
    linked = set(b._truth.values())
    best, best_d = None, math.inf
    for h in sorted(b.tracks):
        if only_unlinked and h in linked:
            continue
        c = b.tracks[h]
        if c.side != side or not compatible(c.kind, kind):
            continue
        d = math.hypot(c.x - x, c.y - y)
        if d <= radius and d < best_d:
            best, best_d = h, d
    return best


def apply_sighting(w, owner: int, true_id: int, side: str, kind: str, x: float, y: float, pos_err: float,
                   strength: int, order, facing, recognised: bool) -> int:
    """Record one direct sighting of the body with true identity `true_id` (validated). Returns the handle."""
    age_links(w, w.beliefs[owner])
    c = _sighting(w, owner, true_id, side, kind, x, y, pos_err, strength, order, facing, recognised, check=True)
    _fold(w, owner, c, c.handle, "seen")
    return c.handle


def apply_sightings(w, owners, true_ids, sides, kinds, xs, ys, pos_errs, strengths, orders, facings, recognised):
    """Record a batch of sightings (perception). Numeric arrays are validated as a whole, each
    contact is built once, and the batch is folded into the belief hash in one go."""
    import numpy as np
    xs, ys, pos_errs = (np.asarray(a, dtype=float) for a in (xs, ys, pos_errs))
    orders, facings = np.asarray(orders, dtype=float), np.asarray(facings, dtype=float)   # NaN means "not judged"
    strengths = np.asarray(strengths)
    if not (np.isfinite(xs).all() and np.isfinite(ys).all() and np.isfinite(pos_errs).all() and (pos_errs >= 0).all()):
        raise ValueError("sighting positions and errors must be finite")
    if strengths.dtype.kind not in "iu" or (strengths.size and strengths.min() < 0):
        raise ValueError("sighting strengths must be whole numbers >= 0")
    o = orders[~np.isnan(orders)]
    if o.size and not ((o >= 0) & (o <= 1)).all():
        raise ValueError("judged order must be in [0, 1]")
    f = facings[~np.isnan(facings)]
    if f.size and not (np.isfinite(f) & (np.abs(f) <= 4.0)).all():
        raise ValueError("judged facing must be finite")
    if not set(sides) <= set(SIDES) or not set(kinds) <= set(KINDS):
        raise ValueError("sighting side or kind not recognised")
    for o_ in sorted({int(o) for o in owners}):
        age_links(w, w.beliefs[o_])
    handles = np.empty(len(owners), dtype=np.int64)
    firsts = np.empty(len(owners), dtype=np.int64)
    for k in range(len(owners)):
        c = _sighting(w, int(owners[k]), int(true_ids[k]), sides[k], kinds[k], float(xs[k]), float(ys[k]),
                      float(pos_errs[k]), int(strengths[k]),
                      None if np.isnan(orders[k]) else float(orders[k]),
                      None if np.isnan(facings[k]) else float(facings[k]), bool(recognised[k]), check=False)
        handles[k] = c.handle
        firsts[k] = c.first_seen_t
    hsh = w.belief_hasher
    hsh.update(repr(("seen-batch", w.tick, list(sides), list(kinds))).encode())
    for a in (np.asarray(owners, dtype=np.int64), handles, firsts, xs, ys, pos_errs,
              strengths.astype(np.int64), orders, facings, np.asarray(recognised, dtype=bool)):
        hsh.update(np.ascontiguousarray(a).tobytes())
    return handles


def _sighting(w, owner, true_id, side, kind, x, y, pos_err, strength, order, facing, recognised, check):
    b = w.beliefs[owner]
    P = w.params
    h = b._truth.get(true_id)                # links were aged out before this batch (age_links)
    old = b.tracks.get(h) if h is not None else None
    if h is None:
        mine = sorted(k for k, tid in b._former.items() if tid == true_id and k in b.tracks)
        if recognised and mine:
            # recognised: identified individually (standards, equipment), so it is his old track
            h = max(mine, key=lambda k: (b.tracks[k].seen_t, k))
        else:
            h = _associate(b, side, kind, x, y, P["report_assoc_radius_m"], only_unlinked=True)
        old = b.tracks.get(h) if h is not None else None
        if h is None:
            h = b._new_handle()
        b._truth[true_id] = h
        _link(w, b, "linked", true_id, h)
    b._former.pop(h, None)
    first_seen = old.first_seen_t if old is not None else w.tick
    if recognised:
        # a recognised body is identified individually: fold its older duplicate tracks into this
        # one, and leave a redirect so orders and tasks that name the old track follow it
        for hh in sorted(k for k, tid in b._former.items() if tid == true_id and k != h):
            if hh in b.tracks:
                first_seen = min(first_seen, b.tracks[hh].first_seen_t)
                del b.tracks[hh]
                b.redirects[hh] = h
                for k2 in sorted(b.redirects):
                    if b.redirects[k2] == hh:
                        b.redirects[k2] = h
                _fold(w, owner, None, hh, "merged")
                _link(w, b, "redirect", hh, h)
            del b._former[hh]
    if old is not None and _SPECIFICITY[old.kind] > _SPECIFICITY[kind] and compatible(old.kind, kind):
        kind = old.kind                  # still the same tracked body: what was recognised stays known
    c = Contact(handle=h, side=side, kind=kind, x=x, y=y, pos_err=pos_err, strength=strength,
                order=order, facing=facing, seen_t=w.tick, first_seen_t=first_seen,
                source="seen", report_from=None, received_t=w.tick)
    if check:
        c = _validated(c)
    b.tracks[h] = c
    return c


def apply_report(w, owner: int, reported: list, sender: int, received_t: int) -> list[int]:
    """Merge contacts from a report (the sender's Contacts, captured when the report was sent).
    A reported contact updates a matching track only if it was seen more recently; otherwise
    an unmatched one becomes a new track. Matching uses only what is known (side, kind,
    position). Returns the handles that changed."""
    b = w.beliefs[owner]
    P = w.params
    changed = []
    for rc in reported:
        if not isinstance(rc, Contact):
            raise TypeError("a report carries Contact values")
        rc = _validated(rc)
        h = _associate(b, rc.side, rc.kind, rc.x, rc.y, P["report_assoc_radius_m"], only_unlinked=False)
        old = b.tracks.get(h) if h is not None else None
        if old is not None and old.seen_t >= rc.seen_t:
            continue
        if h is None:
            h = b._new_handle()
        kind = rc.kind
        if old is not None and _SPECIFICITY[old.kind] > _SPECIFICITY[kind]:
            kind = old.kind
        c = _validated(replace(rc, handle=h, kind=kind, source="report", report_from=int(sender),
                               received_t=int(received_t),
                               first_seen_t=old.first_seen_t if old is not None else int(received_t)))
        b.tracks[h] = c
        _fold(w, owner, c, h, "report")
        changed.append(h)
    return changed


@dataclass(frozen=True)
class BeliefView:
    owner: int
    tick: int
    contacts: tuple        # of Contact, sorted by handle
    own: object            # read-only mapping: own entity's state, or a commander's own position and command

    def contact(self, handle: int):
        for c in self.contacts:
            if c.handle == handle:
                return c
        return None

    def age(self, c: Contact) -> int:
        return self.tick - c.seen_t


def _own(w, owner: int):
    if owner in w.by_id:
        e = w.by_id[owner]
        own = {"kind": "entity", "id": e.id, "side": e.side, "function": e.function, "x": e.x, "y": e.y,
               "facing": e.facing, "start_strength": e.start_strength, "fit": e.fit, "wounded": e.wounded, "dead": e.dead, "fled": e.fled,
               "captured": e.captured, "fatigue": e.fatigue, "order": e.order, "resolve": e.resolve,
               "task": e.task.get("kind", ""), "known_t": w.tick}
    else:
        c = w.commanders_by_id[owner]
        own = {"kind": "commander", "id": c.id, "side": c.side, "rank": c.rank, "x": c.x, "y": c.y,
               "commands": tuple(c.commands), "known_t": w.tick}
    return MappingProxyType(own)


def view(w, owner: int) -> BeliefView:
    b = w.beliefs[owner]
    return BeliefView(owner=owner, tick=w.tick, contacts=tuple(b.tracks[h] for h in sorted(b.tracks)),
                      own=_own(w, owner))


def to_record(b: Belief) -> dict:
    """A detached copy for the record and tests: plain dicts, nothing shared with the belief."""
    return {"owner": b.owner, "tracks": [asdict(b.tracks[h]) for h in sorted(b.tracks)],
            "truth": {str(k): v for k, v in sorted(b._truth.items())},
            "former": {str(k): v for k, v in sorted(b._former.items())},
            "redirects": {str(k): v for k, v in sorted(b.redirects.items())}}


def handle_of(b: Belief, true_id: int):
    """For tests, the record, and a sender finding his own friendly units: the owner's track for
    a true body, if linked, else the most recent track whose link to it lapsed."""
    h = b._truth.get(true_id)
    if h is not None:
        return h
    old = [k for k, t in b._former.items() if t == true_id and k in b.tracks]
    return max(old, key=lambda k: (b.tracks[k].seen_t, k)) if old else None
