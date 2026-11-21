"""World state: plain data. Systems in imperatores/systems read and write it; the engine sets the order.

Entities have stable ids taken from the scenario file. Ids are used for every reference
(parents, random keys, records) and never depend on list position, so removing or adding
an entity in a paired intervention run leaves every other entity's identity, links and
random draws unchanged (Codex review 002, finding 1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import params as params_mod
from .rng import Random
from .terrain import Terrain  # noqa: F401  (re-exported for callers)

SIDES = ("A", "B")
FUNCTIONS = ("heavy_infantry", "skirmishers", "light_cavalry", "heavy_cavalry")
OPEN_ORDER = ("skirmishers", "light_cavalry", "heavy_cavalry")   # turn quickly; not "formed" for order loss
HEADCOUNT_FIELDS = ("fit", "wounded", "dead", "fled", "captured")
UNIT_RANGE_FIELDS = ("fatigue", "order", "resolve")


@dataclass
class Officer:
    rank: str            # e.g. "centurion (prior)", "decurion"
    alive: bool = True
    present: bool = True


@dataclass
class Equipment:
    reach: str                                   # "missile", "spear", "sword"
    missiles: dict[str, int] = field(default_factory=dict)   # e.g. {"pilum": 240}; per entity, not per man
    protection: str = "medium"                   # "light", "medium", "heavy"
    mobility: str = "foot"                       # "foot", "horse"


@dataclass
class Entity:
    id: int                                      # stable, from the scenario file
    side: str
    name: str
    function: str
    represents: list[str]                        # historical units this tactical entity stands for
    x: float
    y: float
    facing: float                                # radians; 0 = +x (east), pi/2 = +y (north)
    frontage: float                              # metres
    depth: float                                 # metres
    start_strength: int
    fit: int
    wounded: int = 0
    dead: int = 0
    fled: int = 0
    captured: int = 0
    fatigue: float = 0.0                         # 0 fresh .. 1 exhausted
    order: float = 1.0                           # cohesion: 0 dissolved .. 1 perfect order
    resolve: float = 1.0                         # willingness to stay: 0 .. 1
    task: dict = field(default_factory=lambda: {"kind": "hold"})
    succession: list[Officer] = field(default_factory=list)
    equipment: Equipment = field(default_factory=lambda: Equipment(reach="sword"))
    parents: list[int] = field(default_factory=list)   # stable ids, e.g. velites linked to their maniples

    @property
    def formed(self) -> bool:
        return self.function not in OPEN_ORDER


def invariant_problems(e: Entity, terrain) -> list[str]:
    """Everything wrong with one entity's state; empty if it is consistent."""
    out = []
    counts = [getattr(e, f) for f in HEADCOUNT_FIELDS]
    for f, v in zip(HEADCOUNT_FIELDS, counts):
        if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
            out.append(f"{f}={v!r} is not a whole number")
        elif v < 0:
            out.append(f"{f}={v} is negative")
    if not out and sum(counts) != e.start_strength:
        out.append(f"headcount sums to {sum(counts)}, not {e.start_strength}")
    for f in UNIT_RANGE_FIELDS:
        v = getattr(e, f)
        if not (isinstance(v, float) and math.isfinite(v) and 0.0 <= v <= 1.0):
            out.append(f"{f}={v!r} outside 0..1")
    if not (math.isfinite(e.x) and math.isfinite(e.y) and terrain.inside(e.x, e.y)):
        out.append(f"position ({e.x}, {e.y}) is off the field")
    elif not terrain.passable(e.x, e.y):
        out.append(f"position ({e.x:.1f}, {e.y:.1f}) is in the stream away from a ford")
    if not math.isfinite(e.facing):
        out.append(f"facing={e.facing!r} is not finite")
    return out


@dataclass
class World:
    scenario_name: str
    seed: int
    terrain: Terrain
    entities: list[Entity]                       # iteration order: scenario file order
    params: dict[str, float]
    rng: Random
    tick: int = 0
    events: list[dict] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)
    scenario_digest: str = ""
    trace: str = ""                              # rolling hash of the full-precision state after every tick
    by_id: dict[int, Entity] = field(default_factory=dict)
    roster: tuple = ()                           # ids at the start; roster changes must be explicit

    @staticmethod
    def new(scenario_name, seed, terrain, entities, overrides=None, scenario_digest=""):
        w = World(scenario_name=scenario_name, seed=seed, terrain=terrain, entities=entities,
                  params=params_mod.resolve(overrides), rng=Random(seed),
                  scenario_digest=scenario_digest)
        w.by_id = {e.id: e for e in entities}
        w.roster = tuple(e.id for e in entities)
        return w

    @property
    def time(self) -> float:
        return self.tick * self.params["tick_seconds"]

    def entity(self, eid: int) -> Entity:
        return self.by_id[eid]
