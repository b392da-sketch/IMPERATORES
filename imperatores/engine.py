"""One tick in a fixed order of phases. New phases are added here, in order, as systems are built."""
from __future__ import annotations

from . import record
from .systems import command, messengers, movement, observe, perception

PHASES = [
    ("perception", perception.step),     # observers look at the field as it stands at the start of the tick
    ("command", command.step),           # inputs, plans, executing orders, dispatching messengers
    ("messengers", messengers.step),     # riders move, deliver, search, return, are caught or lost
    ("movement", movement.step),
]


def step(w, ticks: int = 1) -> None:
    for _ in range(ticks):
        observe.begin_tick(w)
        for name, fn in PHASES:
            fn(w)
            observe.after_phase(w, name)
        observe.end_tick(w)
        w.tick += 1
        record.advance_trace(w)
        if w.tick % int(w.params["snapshot_every_ticks"]) == 0:
            record.snapshot(w)


def run(w, seconds: float) -> None:
    """Run for a duration. The record always holds the initial and the final state."""
    record.snapshot(w)
    step(w, int(round(seconds / w.params["tick_seconds"])))
    if w.snapshots[-1]["t"] != w.tick:
        record.snapshot(w)
