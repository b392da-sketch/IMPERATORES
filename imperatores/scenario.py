"""Load a scenario file (JSON) into a World. Orders of battle live in scenarios/, not in code.

Every entity needs a stable integer "id", unique in the file; "parents" refer to ids.
The terrain "cell" size is a scenario setting and must be given. Movement targets must be
on the field. The loaded world is checked for consistency before it is returned.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .state import FUNCTIONS, SIDES, Entity, Equipment, Officer, Terrain, World
from .systems import observe


def _terrain(spec: dict) -> Terrain:
    if "cell" not in spec:
        raise ValueError("terrain: 'cell' (metres per grid cell) must be given")
    w, h, cell = float(spec["width"]), float(spec["height"]), float(spec["cell"])
    if not (w > 0 and h > 0 and cell > 0):
        raise ValueError("terrain: width, height and cell must be positive")
    nx, ny = int(math.ceil(w / cell)), int(math.ceil(h / cell))
    rough = np.zeros((ny, nx), dtype=bool)
    for r in spec.get("rough", []):              # rectangles [x0, y0, x1, y1] in metres
        x0, y0, x1, y1 = r
        rough[int(y0 // cell):int(math.ceil(y1 / cell)), int(x0 // cell):int(math.ceil(x1 / cell))] = True
    return Terrain(width=w, height=h, cell=cell, rough=rough)


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
    eq = d.get("equipment", {})
    return Entity(
        id=eid, side=d["side"], name=name, function=d["function"],
        represents=list(d.get("represents", [])),
        x=float(d["x"]), y=float(d["y"]), facing=math.radians(float(d.get("facing_deg", 0.0))),
        frontage=float(d["frontage"]), depth=float(d["depth"]),
        start_strength=strength, fit=strength,
        task=dict(d.get("task", {"kind": "hold"})),
        succession=[Officer(rank=r) for r in d.get("succession", [])],
        equipment=Equipment(reach=eq.get("reach", "sword"), missiles=dict(eq.get("missiles", {})),
                            protection=eq.get("protection", "medium"), mobility=eq.get("mobility", "foot")),
        parents=[int(p) for p in d.get("parents", [])],
    )


def load(path: str | Path, seed: int, overrides: dict | None = None) -> World:
    raw = Path(path).read_bytes()
    spec = json.loads(raw)
    terrain = _terrain(spec["terrain"])
    entities = [_entity(d) for d in spec["entities"]]
    ids = [e.id for e in entities]
    if len(set(ids)) != len(ids):
        raise ValueError("entity ids must be unique")
    known = set(ids)
    for e in entities:
        for p in e.parents:
            if p not in known:
                raise ValueError(f"entity {e.name}: parent id {p} does not exist")
            if p == e.id:
                raise ValueError(f"entity {e.name}: cannot be its own parent")
        if e.task.get("kind") == "move_to" and not terrain.inside(float(e.task["x"]), float(e.task["y"])):
            raise ValueError(f"entity {e.name}: movement target is off the field")
    w = World.new(spec.get("name", Path(path).stem), seed, terrain, entities,
                  overrides=overrides, scenario_digest=hashlib.sha256(raw).hexdigest())
    try:
        observe.check_all(w, "at load")
    except observe.ConsistencyError as err:       # an inconsistent file is a bad input, not a simulation fault
        raise ValueError(f"scenario {path}: {err}") from err
    return w
