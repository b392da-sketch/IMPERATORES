"""One tick in a fixed order of phases. New phases are added here, in order, as systems are built."""
from __future__ import annotations

from . import record
from .systems import movement, observe

PHASES = [
    ("movement", movement.step),
]


def step(w, ticks: int = 1) -> None:
    for _ in range(ticks):
        observe.begin_tick(w)
        for _name, fn in PHASES:
            fn(w)
        observe.end_tick(w)
        w.tick += 1
        if w.tick % int(w.params["snapshot_every_ticks"]) == 0:
            record.snapshot(w)


def run(w, seconds: float) -> None:
    record.snapshot(w)                 # initial state
    step(w, int(round(seconds / w.params["tick_seconds"])))
