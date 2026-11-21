"""World state: plain data. Systems in imperatores/systems read and write it; the engine sets the order."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import params as params_mod
from .rng import Random

SIDES = ("A", "B")
FUNCTIONS = ("heavy_infantry", "skirmishers", "light_cavalry", "heavy_cavalry")
OPEN_ORDER = ("skirmishers", "light_cavalry", "heavy_cavalry")   # turn quickly; not "formed" for order loss


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
    id: int
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
    parents: list[int] = field(default_factory=list)   # e.g. velites linked to their maniples

    def headcount_ok(self) -> bool:
        return self.fit + self.wounded + self.dead + self.fled + self.captured == self.start_strength

    @property
    def formed(self) -> bool:
        return self.function not in OPEN_ORDER


@dataclass
class Terrain:
    """Step 1: a grid with a rough-ground mask. Height, woods, streams and sight come in step 2."""
    width: float                                 # metres, x from 0
    height: float                                # metres, y from 0
    cell: float                                  # metres per cell
    rough: np.ndarray                            # bool [ny, nx]

    def is_rough(self, x: float, y: float) -> bool:
        i = int(y // self.cell)
        j = int(x // self.cell)
        if 0 <= i < self.rough.shape[0] and 0 <= j < self.rough.shape[1]:
            return bool(self.rough[i, j])
        return False

    def inside(self, x: float, y: float) -> bool:
        return 0.0 <= x <= self.width and 0.0 <= y <= self.height


@dataclass
class World:
    scenario_name: str
    seed: int
    terrain: Terrain
    entities: list[Entity]
    params: dict[str, float]
    rng: Random
    tick: int = 0
    events: list[dict] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)
    scenario_digest: str = ""

    @staticmethod
    def new(scenario_name, seed, terrain, entities, overrides=None, scenario_digest=""):
        return World(scenario_name=scenario_name, seed=seed, terrain=terrain, entities=entities,
                     params=params_mod.resolve(overrides), rng=Random(seed),
                     scenario_digest=scenario_digest)

    @property
    def time(self) -> float:
        return self.tick * self.params["tick_seconds"]

    def entity(self, eid: int) -> Entity:
        return self.entities[eid]
