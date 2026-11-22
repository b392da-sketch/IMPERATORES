"""Load a scenario file (JSON) into a World. Orders of battle live in scenarios/, not in code.

Every entity needs a stable integer "id", unique in the file; "parents" refer to ids.
The terrain format is described in terrain.py. Movement targets must be on passable ground. The loaded world is checked for consistency before it is returned.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from . import orders as om
from . import terrain as terrain_mod
from .state import FUNCTIONS, RANKS, SIDES, Commander, Entity, Equipment, Officer, World
from .systems import observe


MAX_ID = 2 ** 32 - 1              # ids are random-stream keys, which are unsigned 32-bit (finding 004/9)


def _int(d: dict, key: str, what: str) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"{what}: '{key}' must be a whole number, got {v!r}")
    return v


def _id(d: dict, what: str) -> int:
    v = _int(d, "id", what)
    if not (0 <= v <= MAX_ID):
        raise ValueError(f"{what}: id must be in [0, {MAX_ID}]")
    return v


def _entity(d: dict) -> Entity:
    name = d.get("name", "?")
    eid = _id(d, f"entity {name}")
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
    unknown = set(d) - {"id", "side", "name", "function", "represents", "x", "y", "facing_deg", "frontage",
                        "depth", "strength", "task", "succession", "equipment", "parents", "plan", "profile"}
    if unknown:
        raise ValueError(f"entity {name}: unknown keys {sorted(unknown)}")
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
        profile=_profile_of(d, f"entity {name}"),
    )


def _profile_of(d: dict, what: str) -> str:
    from .decisions import PROFILES
    p = d.get("profile", "by_the_book")
    if p not in PROFILES:
        raise ValueError(f"{what}: unknown profile {p!r} (known: {sorted(PROFILES)})")
    return p


def _commander(d: dict) -> Commander:
    name = d.get("name", "?")
    cid = _id(d, f"commander {name}")
    if d["side"] not in SIDES:
        raise ValueError(f"commander {name}: unknown side {d['side']}")
    if d["rank"] not in RANKS:
        raise ValueError(f"commander {name}: unknown rank {d['rank']}")
    return Commander(id=cid, side=d["side"], name=name, rank=d["rank"], x=float(d["x"]), y=float(d["y"]),
                     mobility=d.get("mobility", "horse"), commands=[int(i) for i in d.get("commands", [])],
                     profile=_profile_of(d, f"commander {name}"))


def _order_spec(d: dict, what: str, terrain=None) -> dict:
    """Validate an order specification (plan instruction or input). A place must be on
    passable ground (Codex review 005, finding 6)."""
    kind = d.get("kind")
    if kind not in om.ORDER_KINDS:
        raise ValueError(f"{what}: unknown order kind {kind!r}")
    if d.get("latitude", "normal") not in om.LATITUDES:
        raise ValueError(f"{what}: unknown latitude {d.get('latitude')!r}")
    allowed = {"kind", "latitude"}
    if kind in om.PLACE_KINDS:
        allowed.add("place")
        pl = d.get("place")
        if not (isinstance(pl, list) and len(pl) == 2):
            raise ValueError(f"{what}: {kind} needs a place [x, y]")
        if terrain is not None and not terrain.passable(float(pl[0]), float(pl[1])):
            raise ValueError(f"{what}: the place {pl} is off the field or in the stream")
    if kind == "face":
        allowed.add("toward")
        tw = d.get("toward")
        if not (isinstance(tw, list) and len(tw) == 2):
            raise ValueError(f"{what}: face needs a point 'toward': [x, y]")
    if kind in om.TARGET_KINDS:
        allowed.add("target")
        tg = d.get("target")
        if not (isinstance(tg, dict) and set(tg) == {"near", "side"} and tg["side"] in SIDES):
            raise ValueError(f"{what}: {kind} needs a target {{'near': [x, y], 'side': 'A' or 'B'}}")
    extra = set(d) - allowed
    if extra:
        raise ValueError(f"{what}: unexpected keys {sorted(extra)}")
    return dict(d)


def _plan(d: dict, e: Entity, terrain, commanders: set) -> om.Plan:
    """Every entity has a plan: its home (by default where it deploys, finding 9) and any
    conditional instructions. An instruction may name the emitters whose signals it obeys
    ("from"); by default only the entity's own commanders bind it."""
    unknown = set(d) - {"home", "on"}
    if unknown:
        raise ValueError(f"entity {e.name}: plan has unknown keys {sorted(unknown)}")
    home = d.get("home", [e.x, e.y])
    if not terrain.passable(float(home[0]), float(home[1])):
        raise ValueError(f"entity {e.name}: plan home is not on passable ground")
    entries = []
    for k, entry in enumerate(d.get("on", [])):
        if set(entry) - {"when", "do", "from"}:
            raise ValueError(f"entity {e.name}: plan entry {k} has unknown keys")
        when, do = entry.get("when"), entry.get("do")
        frm = entry.get("from")
        if frm is not None and not (isinstance(frm, list) and set(frm) <= commanders):
            raise ValueError(f"entity {e.name}: plan entry {k}: 'from' must list commanders")
        if not isinstance(when, dict) or len(when) != 1:
            raise ValueError(f"entity {e.name}: plan entry {k} needs one 'when' condition")
        (cond, val), = when.items()
        if cond == "signal":
            if not om.valid_signal(val):
                raise ValueError(f"entity {e.name}: plan entry {k}: unknown signal {val!r}")
        elif cond == "enemy_within":
            if not (isinstance(val, list) and len(val) == 3):
                raise ValueError(f"entity {e.name}: plan entry {k}: enemy_within needs [x, y, radius]")
        elif cond == "after_s":
            float(val)
        else:
            raise ValueError(f"entity {e.name}: plan entry {k}: unknown condition {cond!r}")
        if "from" in entry and cond != "signal":
            raise ValueError(f"entity {e.name}: plan entry {k}: 'from' applies only to signals")
        entries.append({"when": dict(when), "do": _order_spec(do or {}, f"entity {e.name} plan entry {k}", terrain),
                        "from": None if frm is None else sorted(int(i) for i in frm), "fired": False})
    return om.Plan(home=(float(home[0]), float(home[1])), on=entries)


def subordinates(commanders: dict, cid: int) -> set:
    """Everyone under a commander, at any depth (the graph is checked acyclic first)."""
    out, todo = set(), list(commanders[cid].commands)
    while todo:
        i = todo.pop()
        if i in out:
            continue
        out.add(i)
        if i in commanders:
            todo.extend(commanders[i].commands)
    return out


def _check_command_graph(commanders: list, everyone: set, sides: dict) -> None:
    """Finding 11: each id is commanded by at most one commander, once; an army commander
    commands wings and entities, a wing commander only entities; no cycles."""
    by_id = {c.id: c for c in commanders}
    seen = {}
    for c in commanders:
        if len(set(c.commands)) != len(c.commands):
            raise ValueError(f"commander {c.name}: commands the same id twice")
        for i in c.commands:
            if i not in everyone or i == c.id:
                raise ValueError(f"commander {c.name}: commands unknown id {i}")
            if sides[i] != c.side:
                raise ValueError(f"commander {c.name}: commands id {i} on the other side")
            if i in seen:
                raise ValueError(f"id {i} is commanded by both {seen[i]} and {c.id}")
            seen[i] = c.id
            if i in by_id and (c.rank != "army" or by_id[i].rank != "wing"):
                raise ValueError(f"commander {c.name} ({c.rank}) cannot command commander {i} ({by_id[i].rank})")
    for c in commanders:                       # with the rank rule, a cycle is impossible; check anyway
        stack, path = [c.id], set()
        while stack:
            i = stack.pop()
            if i == c.id and path:
                raise ValueError(f"commander {c.name}: command cycle")
            if i in path:
                continue
            path.add(i)
            if i in by_id:
                stack.extend(by_id[i].commands)


def _inputs(spec: list, everyone: set, commanders: dict, sides: dict, terrain, tick_s: float) -> list:
    """Inputs with authority checked (finding 1): an order goes from a commander to someone in
    his command, or from an entity to itself; a report goes to a commander on the same side;
    a signal comes from a living commander and is addressed within his command."""
    out = []
    for k, d in enumerate(spec):
        what = f"input {k}"
        t = int(round(float(d["at_s"]) / tick_s))
        kinds = [x for x in ("order", "report", "signal") if x in d]
        if len(kinds) != 1 or set(d) != {"at_s", kinds[0]}:
            raise ValueError(f"{what}: needs 'at_s' and exactly one of order, report, signal")
        kind = kinds[0]
        body = dict(d[kind])
        if kind == "order":
            i, r = body.get("issuer"), body.get("recipient")
            if i not in everyone or r not in everyone:
                raise ValueError(f"{what}: unknown issuer or recipient")
            if not (i == r and i not in commanders) and not (i in commanders and r in subordinates(commanders, i)):
                raise ValueError(f"{what}: {i} has no authority to order {r}")
            _order_spec({k2: v for k2, v in body.items() if k2 not in ("issuer", "recipient")}, what, terrain)
        elif kind == "report":
            sd, r = body.get("sender"), body.get("recipient")
            if sd not in everyone or r not in commanders or set(body) != {"sender", "recipient"} or sd == r:
                raise ValueError(f"{what}: a report needs a known sender and a commander to receive it")
            if sides[sd] != sides[r]:
                raise ValueError(f"{what}: a report goes to a commander on the sender's own side")
        else:
            if body.get("issuer") not in commanders:
                raise ValueError(f"{what}: signals are given by commanders")
            if not om.valid_signal(body.get("meaning", "")):
                raise ValueError(f"{what}: unknown signal {body.get('meaning')!r}")
            to = body.get("to", "all")
            if to != "all" and not (isinstance(to, list) and set(to) <= subordinates(commanders, body["issuer"])):
                raise ValueError(f"{what}: 'to' must be 'all' or a list of ids in the issuer's command")
            if set(body) - {"issuer", "meaning", "to"}:
                raise ValueError(f"{what}: unexpected keys in the signal")
        out.append([t, k, kind, body])
    out.sort(key=lambda r: (r[0], r[1]))
    return [[t, kind, body, k] for t, k, kind, body in out]


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
    _check_command_graph(commanders, everyone, sides)
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
    by_id = {d.get("id"): d for d in spec["entities"]}
    cmd_ids = {c.id for c in commanders}
    for e in entities:
        w.plans[e.id] = _plan(by_id[e.id].get("plan", {}), e, terrain, cmd_ids)
    w.inputs = _inputs(spec.get("inputs", []), everyone, {c.id: c for c in commanders}, sides, terrain,
                       w.params["tick_seconds"])
    for c in commanders:
        if c.side not in ("A", "B"):
            raise ValueError("commander side")
    try:
        observe.check_all(w, "at load")
    except observe.ConsistencyError as err:       # an inconsistent file is a bad input, not a simulation fault
        raise ValueError(f"scenario {path}: {err}") from err
    return w
