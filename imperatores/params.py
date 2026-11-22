"""Provisional values. Every value is a tunable starting point, not a historical measurement.

Each has an explicit plausible range and a label:
  EVIDENCED   - supported by a cited source; `grade` says how far (what was read, and how)
  ASSUMPTION  - an engineering assumption, to be tested for sensitivity

A run may override values (for sensitivity tests) with World(params=...). Overrides
outside a value's range, fractional values for integer settings, booleans and
non-finite numbers are refused.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

EVIDENCED = "evidenced"
ASSUMPTION = "assumption"

_POLYBIUS_GRADE = ("direct ancient statement; read in English translation (Paton, Loeb, via LacusCurtius); "
                   "Greek not collated; an organisational template, not a muster return")


@dataclass(frozen=True)
class Param:
    value: float
    lo: float
    hi: float
    label: str
    basis: str
    unit: str = ""
    integer: bool = False
    grade: str = ""            # required for EVIDENCED values


PARAMS: dict[str, Param] = {
    # time and recording
    "tick_seconds": Param(2.0, 1.0, 5.0, ASSUMPTION, "simulation step; small enough for contact, large enough for speed", "s"),
    "snapshot_every_ticks": Param(5, 1, 30, ASSUMPTION, "how often entity states are recorded for the viewer", "ticks", integer=True),

    # movement (step 1 placeholders; refined in step 2)
    "pace_infantry_formed": Param(1.0, 0.6, 1.4, ASSUMPTION, "walking pace of a formed infantry body keeping its ranks", "m/s"),
    "pace_skirmisher": Param(1.6, 1.0, 2.5, ASSUMPTION, "open-order light infantry moving freely", "m/s"),
    "pace_cavalry": Param(3.0, 2.0, 5.0, ASSUMPTION, "cavalry at a sustainable working pace, not a charge", "m/s"),
    "pace_jitter": Param(0.05, 0.0, 0.2, ASSUMPTION, "random variation in pace per tick, as a fraction (standard deviation)", ""),
    "turn_rate_formed": Param(0.05, 0.01, 0.2, ASSUMPTION, "how fast a formed body can change facing", "rad/s"),
    "turn_rate_open": Param(0.3, 0.05, 1.0, ASSUMPTION, "how fast open-order troops and cavalry change facing", "rad/s"),
    "formed_move_alignment_deg": Param(30.0, 5.0, 90.0, ASSUMPTION, "a formed body moves forward only once facing within this angle of its target; it does not crab sideways", "deg"),
    # ground: pace as a fraction of pace on open ground, by movement class (formed foot, open-order foot, horse)
    "pace_rough_formed": Param(0.6, 0.3, 0.9, ASSUMPTION, "formed foot on rough ground", ""),
    "pace_rough_open": Param(0.8, 0.5, 1.0, ASSUMPTION, "open-order foot on rough ground", ""),
    "pace_rough_horse": Param(0.6, 0.3, 0.9, ASSUMPTION, "horse on rough ground", ""),
    "pace_woods_formed": Param(0.35, 0.15, 0.7, ASSUMPTION, "formed foot in woods", ""),
    "pace_woods_open": Param(0.7, 0.4, 1.0, ASSUMPTION, "open-order foot in woods", ""),
    "pace_woods_horse": Param(0.35, 0.1, 0.7, ASSUMPTION, "horse in woods", ""),
    "pace_ford_formed": Param(0.4, 0.2, 0.8, ASSUMPTION, "formed foot crossing at a ford", ""),
    "pace_ford_open": Param(0.5, 0.2, 0.9, ASSUMPTION, "open-order foot crossing at a ford", ""),
    "pace_ford_horse": Param(0.5, 0.2, 0.9, ASSUMPTION, "horse crossing at a ford", ""),
    "slope_pace_k": Param(4.0, 0.0, 10.0, ASSUMPTION, "uphill slowing: pace divided by (1 + k x gradient); no effect downhill in M0", ""),
    # ground: loss of order per 100 m actually crossed, formed troops only
    "order_loss_rough_per_100m": Param(0.05, 0.0, 0.2, ASSUMPTION, "formed troops crossing rough ground", ""),
    "order_loss_woods_per_100m": Param(0.15, 0.0, 0.5, ASSUMPTION, "formed troops moving through woods", ""),
    "order_loss_ford_per_100m": Param(0.2, 0.0, 0.6, ASSUMPTION, "formed troops crossing a ford", ""),
    "order_recovery_per_min_halted": Param(0.05, 0.0, 0.2, ASSUMPTION, "order regained per minute when halted and dressing ranks", ""),
    "fatigue_per_min_moving": Param(0.004, 0.0, 0.02, ASSUMPTION, "fatigue gained per minute of actual marching in formation", ""),
    "fatigue_recovery_per_min_halted": Param(0.004, 0.0, 0.02, ASSUMPTION, "fatigue lost per minute at rest", ""),
    "fatigue_pace_penalty": Param(0.4, 0.0, 0.8, ASSUMPTION, "pace lost at full fatigue, as a fraction", ""),
    "arrival_tolerance": Param(5.0, 1.0, 20.0, ASSUMPTION, "distance at which a movement target counts as reached", "m"),
    "max_speed_any": Param(8.0, 5.0, 12.0, ASSUMPTION,
                           "physical upper limit (a galloping horse): movement is capped at it, and the consistency check enforces it independently", "m/s"),

    # sight (step 2)
    "sight_sample_spacing_cells": Param(1.0, 0.25, 1.0, ASSUMPTION,
                                        "numerical resolution: sight lines are checked every this many terrain cells (the terrain itself is no finer than one cell)", "cells"),
    "sight_range_max": Param(3000.0, 1000.0, 6000.0, ASSUMPTION, "furthest distance at which a formed body can be seen at all in clear weather", "m"),
    "sight_range_in_woods": Param(60.0, 20.0, 150.0, ASSUMPTION, "how far one sees inside a wood, or how close one must be to see into it", "m"),
    "wood_canopy_height": Param(12.0, 5.0, 25.0, ASSUMPTION, "height of a wood's canopy above the ground, for blocking sight", "m"),
    "eye_height_foot": Param(1.7, 1.5, 2.0, ASSUMPTION, "eye height of a man on foot", "m"),
    "eye_height_horse": Param(2.5, 2.2, 2.9, ASSUMPTION, "eye height of a rider", "m"),
    "target_height_foot": Param(2.0, 1.7, 3.0, ASSUMPTION, "visible height of an infantry body (men, shields, standards)", "m"),
    "target_height_horse": Param(2.6, 2.2, 3.2, ASSUMPTION, "visible height of a body of horse", "m"),

    # perception and belief (step 3)
    "perception_interval_s": Param(10.0, 4.0, 30.0, ASSUMPTION, "how often observers update what they see", "s"),
    "officer_attention_range": Param(1500.0, 600.0, 3000.0, ASSUMPTION,
                                     "an entity's officer watches his own sector: he notes bodies of troops only within this distance (army and wing commanders watch the whole field to the limit of sight)", "m"),
    "recognise_range": Param(800.0, 300.0, 1500.0, ASSUMPTION, "within this distance an observer can tell what kind of troops a body is, and its facing", "m"),
    "horse_foot_range": Param(2000.0, 800.0, 3000.0, ASSUMPTION, "within this distance horse can be told from foot", "m"),
    "order_visible_range": Param(400.0, 150.0, 800.0, ASSUMPTION, "within this distance the state of a formation (steady or ragged) can be judged", "m"),
    "pos_error_per_km": Param(30.0, 5.0, 100.0, ASSUMPTION, "spread of the error in a seen body's position, per km of distance (standard deviation)", "m"),
    "strength_error_base": Param(0.1, 0.0, 0.3, ASSUMPTION, "spread of the error in estimating a body's numbers close up, as a fraction (standard deviation)", ""),
    "strength_error_per_km": Param(0.15, 0.05, 0.4, ASSUMPTION, "added spread of the numbers error per km of distance, as a fraction", ""),
    "order_error": Param(0.1, 0.0, 0.3, ASSUMPTION, "spread of the error in judging a formation's order when close enough to see it", ""),

    # organisation (Polybius 6.20-26 as a template)
    "legion_hastati": Param(1200, 1200, 1200, EVIDENCED, "Polybius 6.21.9", "men", integer=True, grade=_POLYBIUS_GRADE),
    "legion_principes": Param(1200, 1200, 1200, EVIDENCED, "Polybius 6.21.9", "men", integer=True, grade=_POLYBIUS_GRADE),
    "legion_triarii": Param(600, 600, 600, EVIDENCED, "Polybius 6.21.9 (triarii fixed even when the legion is larger)", "men", integer=True, grade=_POLYBIUS_GRADE),
    "legion_cavalry": Param(300, 300, 300, EVIDENCED, "Polybius 6.20.9; ten turmae, 6.25.1", "men", integer=True, grade=_POLYBIUS_GRADE),
    "pila_per_hastatus": Param(2, 2, 2, EVIDENCED, "Polybius 6.23.8", "", integer=True, grade=_POLYBIUS_GRADE),
}


def check_override(name: str, value) -> float:
    p = PARAMS[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name}: value must be a number, not {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"{name}={value} is not finite")
    if p.integer and value != int(value):
        raise ValueError(f"{name}={value} must be a whole number")
    if not (p.lo <= value <= p.hi):
        raise ValueError(f"{name}={value} is outside its range [{p.lo}, {p.hi}]")
    return int(value) if p.integer else float(value)


def resolve(overrides: dict | None = None) -> dict[str, float]:
    """The values in force for one run."""
    vals = {k: (int(p.value) if p.integer else float(p.value)) for k, p in PARAMS.items()}
    for k, v in (overrides or {}).items():
        if k not in PARAMS:
            raise KeyError(f"unknown parameter {k}")
        vals[k] = check_override(k, v)
    return vals
