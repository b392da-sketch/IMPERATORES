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
    "slope_lookahead_m": Param(5.0, 2.0, 20.0, ASSUMPTION, "distance ahead over which the gradient is measured for the uphill slowing", "m"),
    "stall_replan_ticks": Param(5, 1, 60, ASSUMPTION, "after this many consecutive blocked steps an entity replans its route; if no route exists it halts and the stall is recorded", "ticks", integer=True),
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
    "track_gap_s": Param(25.0, 10.0, 120.0, ASSUMPTION,
                         "an observer keeps track of a body that drops out of sight for no longer than this; after a longer gap it is the same body only if recognised", "s"),
    "report_assoc_radius_m": Param(150.0, 30.0, 500.0, ASSUMPTION,
                                   "a reported body (or a newly seen unidentified one) is taken to be an already-known track of the same side and compatible kind within this distance", "m"),
    "facing_resolution_deg": Param(45.0, 10.0, 90.0, ASSUMPTION, "an observer judges a body's facing only to the nearest this many degrees", "deg"),
    "recognise_range": Param(800.0, 300.0, 1500.0, ASSUMPTION, "within this distance an observer can tell what kind of troops a body is, and its facing", "m"),
    "horse_foot_range": Param(2000.0, 800.0, 3000.0, ASSUMPTION, "within this distance horse can be told from foot", "m"),
    "order_visible_range": Param(400.0, 150.0, 800.0, ASSUMPTION, "within this distance the state of a formation (steady or ragged) can be judged", "m"),
    "pos_error_per_km": Param(30.0, 5.0, 100.0, ASSUMPTION, "spread of the error in a seen body's position, per km of distance (standard deviation)", "m"),
    "strength_error_base": Param(0.1, 0.0, 0.3, ASSUMPTION, "spread of the error in estimating a body's numbers close up, as a fraction (standard deviation)", ""),
    "strength_error_per_km": Param(0.15, 0.05, 0.4, ASSUMPTION, "added spread of the numbers error per km of distance, as a fraction", ""),
    "order_error": Param(0.1, 0.0, 0.3, ASSUMPTION, "spread of the error in judging a formation's order when close enough to see it", ""),

    # orders, messengers and signals (step 4)
    "messengers_army": Param(6, 2, 12, ASSUMPTION, "riders on an army commander's staff available to carry orders and reports", "", integer=True),
    "messengers_wing": Param(3, 1, 8, ASSUMPTION, "riders with a wing commander", "", integer=True),
    "runners_entity": Param(1, 0, 3, ASSUMPTION, "men an entity's officer can send with a report (mounted for cavalry, on foot otherwise)", "", integer=True),
    "messenger_speed_horse": Param(5.0, 3.0, 8.0, ASSUMPTION, "a mounted messenger's speed across the field", "m/s"),
    "messenger_speed_foot": Param(2.5, 1.5, 4.0, ASSUMPTION, "a runner's speed across the field", "m/s"),
    "messenger_sight_m": Param(400.0, 100.0, 1000.0, ASSUMPTION, "how far a messenger can pick out the body he is looking for", "m"),
    "deliver_radius_m": Param(30.0, 10.0, 80.0, ASSUMPTION, "how close a messenger must come to deliver", "m"),
    # decisions (step 5): all engineering assumptions, not historical reaction times (spec 5.6)
    "decide_officer_min_s": Param(10.0, 4.0, 60.0, ASSUMPTION, "shortest interval between an officer's routine reassessments", "s"),
    "decide_officer_max_s": Param(30.0, 10.0, 120.0, ASSUMPTION, "longest interval between an officer's routine reassessments", "s"),
    "decide_wing_min_s": Param(30.0, 10.0, 120.0, ASSUMPTION, "shortest interval between a wing commander's routine reassessments", "s"),
    "decide_wing_max_s": Param(60.0, 20.0, 240.0, ASSUMPTION, "longest interval between a wing commander's routine reassessments", "s"),
    "decide_army_min_s": Param(60.0, 20.0, 240.0, ASSUMPTION, "shortest interval between an army commander's routine reassessments", "s"),
    "decide_army_max_s": Param(120.0, 40.0, 480.0, ASSUMPTION, "longest interval between an army commander's routine reassessments", "s"),
    "threat_radius_m": Param(500.0, 150.0, 1500.0, ASSUMPTION, "an officer weighs enemy bodies he believes within this distance", "m"),
    "commander_threat_radius_m": Param(600.0, 150.0, 1500.0, ASSUMPTION, "a commander weighs enemy bodies he believes within this distance of a unit under him", "m"),
    "flank_angle_deg": Param(60.0, 30.0, 90.0, ASSUMPTION, "beyond this angle off an entity's facing a threat is on its flank", "deg"),
    "rear_angle_deg": Param(120.0, 90.0, 160.0, ASSUMPTION, "beyond this angle off an entity's facing a threat is in its rear", "deg"),
    "flank_factor": Param(2.0, 1.0, 4.0, ASSUMPTION, "how much more an officer weighs a threat on his flank", ""),
    "rear_factor": Param(3.0, 1.0, 5.0, ASSUMPTION, "how much more an officer weighs a threat in his rear", ""),
    "decision_temperature": Param(0.5, 0.05, 2.0, ASSUMPTION, "randomness of choice: softmax temperature over option scores", ""),
    "latitude_cost_strict": Param(3.0, 0.5, 6.0, ASSUMPTION, "score cost of acting beyond a strict order, before initiative", ""),
    "latitude_cost_normal": Param(1.0, 0.2, 3.0, ASSUMPTION, "score cost of acting beyond an order with normal latitude, before initiative", ""),
    "latitude_cost_free": Param(0.3, 0.0, 1.0, ASSUMPTION, "score cost of acting beyond an order with free latitude, before initiative", ""),
    "change_cost": Param(0.5, 0.0, 2.0, ASSUMPTION, "score cost of changing course at a reassessment: he changes only for a reason", ""),
    "commitment_review_s": Param(600.0, 120.0, 1800.0, ASSUMPTION, "a commander reconsiders a reserve he sent, or an action he took, after this long without news", "s"),
    "report_min_interval_s": Param(60.0, 10.0, 300.0, ASSUMPTION, "an officer reports a new threat no more often than this", "s"),
    "face_tolerance_deg": Param(10.0, 2.0, 30.0, ASSUMPTION, "an entity facing a threat has turned enough within this angle", "deg"),
    "messenger_retarget_m": Param(20.0, 5.0, 100.0, ASSUMPTION, "a messenger replans his route when where he is riding to moves by more than this", "m"),
    "messenger_wait_timeout_s": Param(1800.0, 300.0, 3600.0, ASSUMPTION, "a message waiting this long for a free messenger is given up", "s"),
    "search_time_s": Param(300.0, 60.0, 900.0, ASSUMPTION, "how long a messenger searches where he expected the recipient before giving up", "s"),
    "intercept_radius_m": Param(150.0, 50.0, 400.0, ASSUMPTION, "enemy troops within this distance, who can see him, may catch a messenger", "m"),
    "intercept_per_min": Param(0.5, 0.0, 3.0, ASSUMPTION, "chance per minute (as a rate) of being caught while within reach and sight of enemy troops", "/min"),
    "intercept_mounted_factor": Param(2.0, 1.0, 4.0, ASSUMPTION, "how much likelier enemy horse or skirmishers are to catch a messenger than formed foot", ""),
    "messenger_loss_per_km": Param(0.002, 0.0, 0.02, ASSUMPTION, "chance per km ridden of a messenger being lost by accident (fall, lamed horse); no documented frequency (Q002)", ""),
    "order_target_radius_m": Param(300.0, 100.0, 800.0, ASSUMPTION, "a recipient takes a described body to be the nearest he knows of that side and kind within this distance of the description", "m"),
    "order_stale_m": Param(100.0, 30.0, 300.0, ASSUMPTION, "an order is recorded as stale on delivery if the body it describes is believed this far from where the issuer described it", "m"),
    "signal_range_m": Param(800.0, 300.0, 2000.0, ASSUMPTION, "hearing range of a trumpet signal over open ground; no documented range (Q002)", "m"),
    "signal_blocked_factor": Param(0.5, 0.1, 1.0, ASSUMPTION, "hearing range is multiplied by this where ground blocks the line between trumpeter and hearer (compare Gergovia, Caesar BG 7.47, a later case)", ""),
    "signal_misattribution_prob": Param(0.0, 0.0, 0.5, ASSUMPTION, "chance that a unit not addressed but hearing a signal acts on it; no verified case in 220-100 BCE (Q002), so off by default", ""),
    "exhausted_fatigue": Param(0.9, 0.6, 1.0, ASSUMPTION, "above this fatigue an entity cannot carry out a movement order until it has rested", ""),
    "disordered_order": Param(0.3, 0.1, 0.6, ASSUMPTION, "below this order an entity cannot carry out a movement order until it has reformed", ""),
    "order_wait_timeout_s": Param(600.0, 60.0, 1800.0, ASSUMPTION, "an order that cannot be carried out within this time lapses", "s"),
    "approach_standoff_m": Param(30.0, 5.0, 100.0, ASSUMPTION, "an attacking entity closes to this distance from where it believes the target is (combat begins in step 6)", "m"),
    "support_distance_m": Param(60.0, 20.0, 200.0, ASSUMPTION, "a supporting entity moves to this distance from the body it supports", "m"),
    "approach_replan_m": Param(50.0, 10.0, 200.0, ASSUMPTION, "an approaching entity replans when its believed target has moved this far", "m"),

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
    for lo, hi in ORDERED:                       # pairs that must not be inverted (review 006, notes)
        if vals[lo] > vals[hi]:
            raise ValueError(f"{lo}={vals[lo]} is greater than {hi}={vals[hi]}")
    return vals


ORDERED = (("decide_officer_min_s", "decide_officer_max_s"), ("decide_wing_min_s", "decide_wing_max_s"),
           ("decide_army_min_s", "decide_army_max_s"), ("flank_angle_deg", "rear_angle_deg"))
