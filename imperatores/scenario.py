"""Load a scenario file (JSON) into a World. Orders of battle live in scenarios/, not in code."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .state import FUNCTIONS, SIDES, Entity, Equipment, Officer, Terrain, World


def _terrain(spec: dict) -> Terrain:
    w, h, cell = float(spec["width"]), float(spec["height"]), float(spec.get("cell", 20.0))
    nx, ny = int(math.ceil(w / cell)), int(math.ceil(h / cell))
    rough = np.zeros((ny, nx), dtype=bool)
    for r in spec.get("rough", []):              # rectangles [x0, y0, x1, y1] in metres
        x0, y0, x1, y1 = r
        rough[int(y0 // cell):int(math.ceil(y1 / cell)), int(x0 // cell):int(math.ceil(x1 / cell))] = True
    return Terrain(width=w, height=h, cell=cell, rough=rough)


def _entity(i: int, d: dict) -> Entity:
    if d["side"] not in SIDES:
        raise ValueError(f"entity {d.get('name')}: unknown side {d['side']}")
    if d["function"] not in FUNCTIONS:
        raise ValueError(f"entity {d.get('name')}: unknown function {d['function']}")
    eq = d.get("equipment", {})
    return Entity(
        id=i, side=d["side"], name=d["name"], function=d["function"],
        represents=list(d.get("represents", [])),
        x=float(d["x"]), y=float(d["y"]), facing=math.radians(float(d.get("facing_deg", 0.0))),
        frontage=float(d["frontage"]), depth=float(d["depth"]),
        start_strength=int(d["strength"]), fit=int(d["strength"]),
        task=dict(d.get("task", {"kind": "hold"})),
        succession=[Officer(rank=r) for r in d.get("succession", [])],
        equipment=Equipment(reach=eq.get("reach", "sword"), missiles=dict(eq.get("missiles", {})),
                            protection=eq.get("protection", "medium"), mobility=eq.get("mobility", "foot")),
        parents=list(d.get("parents", [])),
    )


def load(path: str | Path, seed: int, overrides: dict | None = None) -> World:
    raw = Path(path).read_bytes()
    spec = json.loads(raw)
    entities = [_entity(i, d) for i, d in enumerate(spec["entities"])]
    for e in entities:
        for p in e.parents:
            if not (0 <= p < len(entities)):
                raise ValueError(f"entity {e.name}: parent {p} does not exist")
    return World.new(spec.get("name", Path(path).stem), seed, _terrain(spec["terrain"]), entities,
                     overrides=overrides, scenario_digest=hashlib.sha256(raw).hexdigest())
