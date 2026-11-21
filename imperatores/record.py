"""The run record: events with their causes, periodic entity snapshots, and the replay digest.

An event is a dict: {"id", "t" (tick), "kind", "entity", "data", "causes": [refs]}.
A ref is a small dict such as {"event": id} or {"note": "..."}; step 5 adds {"decision": id}.
"""
from __future__ import annotations

import hashlib
import json

SNAPSHOT_FIELDS = ("x", "y", "facing", "fit", "wounded", "dead", "fled", "captured",
                   "fatigue", "order", "resolve")


def log(w, kind: str, entity: int | None, data: dict | None = None, causes: list | None = None) -> int:
    eid = len(w.events)
    w.events.append({"id": eid, "t": w.tick, "kind": kind, "entity": entity,
                     "data": data or {}, "causes": causes or []})
    return eid


def snapshot(w) -> None:
    w.snapshots.append({"t": w.tick, "entities": [
        [e.id] + [round(getattr(e, f), 4) if isinstance(getattr(e, f), float) else getattr(e, f)
                  for f in SNAPSHOT_FIELDS]
        + [e.task.get("kind", "")]
        for e in w.entities]})


def digest(w) -> str:
    body = json.dumps({"scenario": w.scenario_digest, "seed": w.seed, "params": w.params,
                       "events": w.events, "snapshots": w.snapshots},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def to_json(w) -> dict:
    return {"scenario": w.scenario_name, "scenario_digest": w.scenario_digest, "seed": w.seed,
            "params": w.params, "snapshot_fields": ["id", *SNAPSHOT_FIELDS, "task"],
            "terrain": {"width": w.terrain.width, "height": w.terrain.height, "cell": w.terrain.cell,
                        "rough": w.terrain.rough.astype(int).tolist()},
            "entities": [{"id": e.id, "side": e.side, "name": e.name, "function": e.function,
                          "represents": e.represents, "frontage": e.frontage, "depth": e.depth,
                          "start_strength": e.start_strength} for e in w.entities],
            "events": w.events, "snapshots": w.snapshots, "digest": digest(w)}
