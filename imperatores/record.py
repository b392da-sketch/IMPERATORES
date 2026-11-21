"""The run record: events with their causes, viewer snapshots, an exact state trace and the replay digest.

An event is a dict: {"id", "t" (tick), "kind", "entity", "data", "causes": [refs]}.
A ref is a small dict such as {"event": id} or {"note": "..."}; step 5 adds {"decision": id}.

Events own their data: `log` stores a strict-JSON copy, so changing a belief, order or list
after logging can never rewrite what was recorded (Codex review 002, finding 6).

Two levels of state recording (Codex review 002, finding 5):
  * snapshots: rounded, every few ticks, for the viewer;
  * trace: a rolling SHA-256 of the full-precision state of every entity after every tick,
    which is what exact replay is judged by. The digest covers the trace, the final tick,
    the scenario, seed, parameters, events and snapshots.
"""
from __future__ import annotations

import hashlib
import json

from .state import HEADCOUNT_FIELDS

SNAPSHOT_FIELDS = ("x", "y", "facing", *HEADCOUNT_FIELDS, "fatigue", "order", "resolve")


def _owned(obj):
    """A strict-JSON deep copy: no shared references, no NaN or infinity, only JSON types."""
    return json.loads(json.dumps(obj, allow_nan=False))


def log(w, kind: str, entity: int | None, data: dict | None = None, causes: list | None = None) -> int:
    eid = len(w.events)
    w.events.append({"id": eid, "t": w.tick, "kind": kind, "entity": entity,
                     "data": _owned(data or {}), "causes": _owned(causes or [])})
    return eid


def state_bytes(w) -> bytes:
    """Full-precision state of every entity (floats as shortest round-trip repr)."""
    rows = [[e.id, e.x, e.y, e.facing, e.fit, e.wounded, e.dead, e.fled, e.captured,
             e.fatigue, e.order, e.resolve, e.task] for e in w.entities]
    return json.dumps([w.tick, rows], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def advance_trace(w) -> None:
    w.trace = hashlib.sha256(w.trace.encode() + state_bytes(w)).hexdigest()


def snapshot(w) -> None:
    w.snapshots.append({"t": w.tick, "entities": [
        [e.id] + [round(v, 4) if isinstance(v, float) else v for v in (getattr(e, f) for f in SNAPSHOT_FIELDS)]
        + [e.task.get("kind", "")]
        for e in w.entities]})


def digest(w) -> str:
    body = json.dumps({"scenario": w.scenario_digest, "seed": w.seed, "params": w.params,
                       "final_tick": w.tick, "trace": w.trace,
                       "events": w.events, "snapshots": w.snapshots},
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode()).hexdigest()


def to_json(w) -> dict:
    out = {"scenario": w.scenario_name, "scenario_digest": w.scenario_digest, "seed": w.seed,
           "params": w.params, "final_tick": w.tick, "trace": w.trace,
           "snapshot_fields": ["id", *SNAPSHOT_FIELDS, "task"],
           "terrain": {"width": w.terrain.width, "height": w.terrain.height, "cell": w.terrain.cell,
                       "ground": w.terrain.ground.astype(int).tolist(),
                       "elev": [[round(float(v), 2) for v in row] for row in w.terrain.elev]},
           "entities": [{"id": e.id, "side": e.side, "name": e.name, "function": e.function,
                         "represents": e.represents, "parents": e.parents, "frontage": e.frontage,
                         "depth": e.depth, "start_strength": e.start_strength} for e in w.entities],
           "events": w.events, "snapshots": w.snapshots, "digest": digest(w)}
    return _owned(out)
