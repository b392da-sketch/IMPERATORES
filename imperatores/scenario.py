"""Load a scenario file (JSON) into a World. Orders of battle live in scenarios/, not in code.

Every entity needs a stable integer "id", unique in the file; "parents" refer to ids.
The terrain format is described in terrain.py. Movement targets must be on passable ground. The loaded world is checked for consistency before it is returned.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from . import terrain as terrain_mod
from .state import FUNCTIONS, RANKS, SIDES, Commander, Entity, Equipment, Officer, World
from .systems import observe


def _int(d: dict, key: str, what: str) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"{what}: '{key}' must be a whole number, got {v!r}")
    return v


def _entity(d: dict) -> Entity:
    name = d.get("name", "?")
    eid = _int(d, "id", f"entity {name}")
    if eid < 0:
        raise ValueError(f"entity {name}: id must not be negative")
    if d["side"] not in SIDES:
        raise ValueError(f"entity {name}: unknown side {d['side']}")
    if d["function"] not in FUNCTIONS:
        raise ValueError(f"entity {name}: unknown function {d['function']}")
    strength = _int(d, "strength", f"entity {name}")
    if strength <= 0:
        raise ValueError(f"entity {name}: strength must be positive")
    task = dict(d.get("task", {"kind": "hold"}))
    allowed = {"hold": {"kind"}, "move_to": {"kind", "x", "y"}}
    if task.get("kind") not in allowed:
        raise ValueError(f"entity {name}: unknown task kind {task.get('kind')!r}")
    extra = set(task) - allowed[task["kind"]]
    if extra:
        raise ValueError(f"entity {name}: task has keys a scenario may not set: {sorted(extra)}")
    if task["kind"] == "move_to":
        task["x"], task["y"] = float(task["x"]), float(task["y"])
    eq = d.get("equipment", {})
    return Entity(
        id=eid, side=d["side"], name=name, function=d["function"],
        represents=list(d.get("represents", [])),
        x=float(d["x"]), y=float(d["y"]), facing=math.radians(float(d.get("facing_deg", 0.0))),
        frontage=float(d["frontage"]), depth=float(d["depth"]),
        start_strength=strength, fit=strength,
        task=task,
        succession=[Officer(rank=r) for r in d.get("succession", [])],
        equipment=Equipment(reach=eq.get("reach", "sword"), missiles=dict(eq.get("missiles", {})),
                            protection=eq.get("protection", "medium"), mobility=eq.get("mobility", "foot")),
        parents=[int(p) for p in d.get("parents", [])],
    )


def _commander(d: dict) -> Commander:
    name = d.get("name", "?")
    cid = _int(d, "id", f"commander {name}")
    if cid < 0:
        raise ValueError(f"commander {name}: id must not be negative")
    if d["side"] not in SIDES:
        raise ValueError(f"commander {name}: unknown side {d['side']}")
    if d["rank"] not in RANKS:
        raise ValueError(f"commander {name}: unknown rank {d['rank']}")
    return Commander(id=cid, side=d["side"], name=name, rank=d["rank"], x=float(d["x"]), y=float(d["y"]),
                     mobility=d.get("mobility", "horse"), commands=[int(i) for i in d.get("commands", [])])


def load(path: str | Path, seed: int, overrides: dict | None = None) -> World:
    raw = Path(path).read_bytes()
    spec = json.loads(raw)
    terrain = terrain_mod.build(spec["terrain"])
    entities = [_entity(d) for d in spec["entities"]]
    commanders = [_commander(d) for d in spec.get("commanders", [])]
    ids = [e.id for e in entities] + [c.id for c in commanders]
    if len(set(ids)) != len(ids):
        raise ValueError("ids must be unique across entities and commanders")
    known = {e.id for e in entities}
    everyone = set(ids)
    sides = {e.id: e.side for e in entities} | {c.id: c.side for c in commanders}
    for c in commanders:
        for i in c.commands:
            if i not in everyone or i == c.id:
                raise ValueError(f"commander {c.name}: commands unknown id {i}")
            if sides[i] != c.side:
                raise ValueError(f"commander {c.name}: commands id {i} on the other side")
    for e in entities:
        for p in e.parents:
            if p not in known:
                raise ValueError(f"entity {e.name}: parent id {p} does not exist")
            if p == e.id:
                raise ValueError(f"entity {e.name}: cannot be its own parent")
        if e.task.get("kind") == "move_to" and not terrain.passable(float(e.task["x"]), float(e.task["y"])):
            raise ValueError(f"entity {e.name}: movement target is off the field or in the stream")
    w = World.new(spec.get("name", Path(path).stem), seed, terrain, entities,
                  overrides=overrides, scenario_digest=hashlib.sha256(raw).hexdigest(),
                  commanders=commanders)
    try:
        observe.check_all(w, "at load")
    except observe.ConsistencyError as err:       # an inconsistent file is a bad input, not a simulation fault
        raise ValueError(f"scenario {path}: {err}") from err
    return w
