"""Step 3 tests: belief pictures, perception and information integrity (specification 5.4, 7.1 check 3).

Tests marked "Codex 004/N" reproduce a finding of review 004 and check its fix.
"""
from __future__ import annotations

import dataclasses
import json
import math
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from imperatores import belief, engine, params, record, scenario, sight, terrain
from imperatores.belief import Contact
from imperatores.rng import keyed_normals
from imperatores.state import Entity, World
from imperatores.systems import perception

ROOT = Path(__file__).resolve().parent.parent
FIELD = ROOT / "scenarios" / "test_beliefs.json"
P = params.resolve()
A_OWNERS = (900, 910, 1, 2)
HIDDEN, HORSE = 51, 52


def spec():
    return json.loads(FIELD.read_text())


def write(s) -> Path:
    f = Path(tempfile.mkdtemp()) / "scenario.json"
    f.write_text(json.dumps(s))
    return f


def tracks_json(w, owners):
    return json.dumps({o: belief.to_record(w.beliefs[o]) for o in owners}, sort_keys=True)


def contact_of(w, owner, true_id):
    """Test helper: the owner's current contact for a true body, or None."""
    h = belief.handle_of(w.beliefs[owner], true_id)
    return None if h is None else w.beliefs[owner].tracks[h]


def flat_world(entities, commanders=(), extra_terrain=None, overrides=None):
    s = {"name": "t", "terrain": {"width": 4000, "height": 2000, "cell": 20, **(extra_terrain or {})},
         "commanders": list(commanders), "entities": list(entities)}
    return scenario.load(write(s), 1, overrides)


def ent(i, side, x, y, function="heavy_infantry", mobility="foot", strength=120, task=None):
    d = {"id": i, "side": side, "name": f"e{i}", "function": function, "x": x, "y": y,
         "frontage": 40, "depth": 15, "strength": strength, "equipment": {"reach": "sword", "mobility": mobility}}
    if task:
        d["task"] = task
    return d


def cmd(i, side, x, y, rank="army"):
    return {"id": i, "side": side, "name": f"c{i}", "rank": rank, "x": x, "y": y}


def report_contact(side="B", kind="foot", x=2900.0, y=1500.0, seen_t=0, strength=300):
    return Contact(handle=1, side=side, kind=kind, x=x, y=y, pos_err=30.0, strength=strength, order=None,
                   facing=None, seen_t=seen_t, first_seen_t=seen_t, source="seen", report_from=None,
                   received_t=seen_t)


def step_perception(w, cycles=1):
    for _ in range(cycles):
        perception.step(w)
        w.tick += perception._interval_ticks(P)


class InformationIntegrity(unittest.TestCase):
    def test_hidden_entity_never_in_enemy_beliefs(self):
        w = scenario.load(FIELD, 1)
        record.snapshot(w)
        for _ in range(900):                                   # 30 minutes
            engine.step(w)
            for o in A_OWNERS:
                self.assertIsNone(contact_of(w, o, HIDDEN), f"owner {o} has a sighting of the hidden reserve")
                for c in w.beliefs[o].tracks.values():
                    self.assertFalse(abs(c.x - 2900) < 300 and abs(c.y - 1500) < 300, "a track near the hidden reserve")
        self.assertIsNotNone(contact_of(w, 900, HORSE))        # the horse in the open is seen

    def test_moving_an_unseen_entity_changes_no_enemy_belief(self):
        """Stale-truth test: the true state of an unseen entity changes; no belief may change."""
        a, b = scenario.load(FIELD, 3), scenario.load(FIELD, 3)
        for w in (a, b):
            record.snapshot(w)
            engine.step(w, 100)
        b.entity(HIDDEN).x, b.entity(HIDDEN).y = 3200.0, 1200.0   # still hidden behind the hill
        b.entity(HIDDEN).fit -= 100
        b.entity(HIDDEN).dead += 100
        engine.step(a, 300)
        engine.step(b, 300)
        self.assertEqual(tracks_json(a, A_OWNERS), tracks_json(b, A_OWNERS))

    def test_unseen_contact_keeps_last_known_state(self):
        s = spec()
        s["entities"][3]["task"] = {"kind": "move_to", "x": 3000, "y": 1300}   # the horse rides behind the hill
        w = scenario.load(write(s), 1)
        record.snapshot(w)
        engine.step(w, 1200)
        v = belief.view(w, 900)
        c = v.contact(belief.handle_of(w.beliefs[900], HORSE))
        true = w.entity(HORSE)
        self.assertGreater(v.age(c), 100)
        self.assertGreater(abs(c.x - true.x) + abs(c.y - true.y), 300)

    def test_view_holds_no_reference_to_the_world(self):
        w = scenario.load(FIELD, 1)
        engine.run(w, 60)
        v = belief.view(w, 900)
        seen = set()

        def walk(o):
            if id(o) in seen:
                return
            seen.add(id(o))
            self.assertNotIsInstance(o, (World, Entity, belief.Belief, dict, list))
            if dataclasses.is_dataclass(o):
                for f in dataclasses.fields(o):
                    walk(getattr(o, f.name))
            elif isinstance(o, tuple):
                for x in o:
                    walk(x)
            elif hasattr(o, "items"):
                for _, x in o.items():
                    walk(x)
            else:
                self.assertIsInstance(o, (int, float, str, type(None)), type(o))
        walk(v)

    def test_view_is_read_only(self):
        w = scenario.load(FIELD, 1)
        engine.run(w, 60)
        v = belief.view(w, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            v.contacts[0].x = 0.0
        with self.assertRaises(TypeError):
            v.own["fit"] = 0

    def test_export_is_detached(self):                          # Codex 004/1
        w = scenario.load(FIELD, 1)
        engine.step(w)
        before = belief.view(w, 900)
        d = belief.to_record(w.beliefs[900])
        d["tracks"][0]["x"] = w.entity(HIDDEN).x
        self.assertEqual(belief.view(w, 900).contacts, before.contacts)

    def test_bad_values_refused_at_the_boundary(self):          # Codex 004/1
        w = scenario.load(FIELD, 1)
        engine.step(w)
        for bad in (dict(x=(w.entity(HIDDEN),)), dict(x=float("nan")), dict(strength=1.5),
                    dict(side="C"), dict(kind="elephants"), dict(order=2.0)):
            with self.assertRaises((ValueError, TypeError)):
                belief.apply_report(w, 1, [dataclasses.replace(report_contact(), **bad)], sender=900, received_t=1)
        with self.assertRaises(TypeError):
            belief.apply_report(w, 1, [{"side": "B"}], sender=900, received_t=1)

    def test_own_knowledge_is_current_every_tick(self):        # Codex 004/5
        s = spec()
        s["entities"][0]["task"] = {"kind": "move_to", "x": 800, "y": 1500}
        w = scenario.load(write(s), 1, {"pace_jitter": 0.0})
        record.snapshot(w)
        engine.step(w, 3)
        own = belief.view(w, 1).own
        self.assertEqual((own["x"], own["known_t"]), (w.entity(1).x, w.tick))
        cown = belief.view(w, 900).own
        self.assertEqual((cown["kind"], cown["rank"], cown["x"]), ("commander", "army", 400.0))


def gap_ticks():
    every = perception._interval_ticks(P)
    need = int(P["track_gap_s"] / P["tick_seconds"]) + 1
    return every * (-(-need // every) + 1)                     # whole perception cycles, longer than the gap


class Tracking(unittest.TestCase):                              # Codex 004/3
    def world(self):
        return flat_world([ent(1, "A", 100, 1000), ent(2, "B", 1500, 1000, function="light_cavalry", mobility="horse")],
                          commanders=[cmd(99, "A", 100, 1050)])

    def test_handles_are_local_not_true_ids(self):
        w = self.world()
        perception.step(w)
        self.assertEqual(sorted(w.beliefs[99].tracks), [1, 2])     # the owner's own labels
        self.assertNotIn(2, [c.handle for c in belief.view(w, 1).contacts if c.side == "B"] + [99])

    def test_reacquired_unrecognised_body_is_a_new_track(self):
        w = self.world()
        perception.step(w)
        h0 = belief.handle_of(w.beliefs[99], 2)
        w.entity(2).y = 1999.0
        w.entity(2).x = 3900.0                                   # beyond sight
        w.tick += gap_ticks()
        perception.step(w)
        w.entity(2).x, w.entity(2).y = 1500.0, 1500.0            # back elsewhere, 1.5 km off: "horse", not recognised
        w.tick += perception._interval_ticks(P)
        perception.step(w)
        h1 = belief.handle_of(w.beliefs[99], 2)
        self.assertNotEqual(h0, h1)
        self.assertIn(h0, w.beliefs[99].tracks)                  # the old track remains, a duplicate

    def test_recognition_merges_the_duplicate(self):
        w = self.world()
        perception.step(w)
        h0 = belief.handle_of(w.beliefs[99], 2)
        w.entity(2).x = 3900.0
        w.tick += gap_ticks()
        perception.step(w)
        w.entity(2).x, w.entity(2).y = 1500.0, 1500.0
        w.tick += perception._interval_ticks(P)
        perception.step(w)                                       # new track (unrecognised, elsewhere)
        self.assertEqual(len([c for c in w.beliefs[99].tracks.values() if c.side == "B"]), 2)
        w.entity(2).x, w.entity(2).y = 600.0, 1300.0             # close: recognised
        w.tick += perception._interval_ticks(P)
        perception.step(w)
        horse_tracks = [c for c in w.beliefs[99].tracks.values() if c.side == "B"]
        self.assertEqual(len(horse_tracks), 1)
        self.assertEqual(horse_tracks[0].kind, "light_cavalry")
        self.assertLessEqual(horse_tracks[0].first_seen_t, w.beliefs[99].tracks.get(h0, horse_tracks[0]).first_seen_t)

    def test_report_matched_by_attributes_not_identity(self):
        w = self.world()
        perception.step(w)
        n = len(w.beliefs[1].tracks)
        far = report_contact(kind="horse", x=3000.0, y=300.0, seen_t=w.tick)   # nowhere near anything known
        belief.apply_report(w, 1, [far], sender=99, received_t=w.tick)
        self.assertEqual(len(w.beliefs[1].tracks), n + 1)
        near = report_contact(kind="horse", x=3010.0, y=310.0, seen_t=w.tick + 1)
        belief.apply_report(w, 1, [near], sender=99, received_t=w.tick + 1)
        self.assertEqual(len(w.beliefs[1].tracks), n + 1)        # same body by position and kind


class Perception(unittest.TestCase):
    def test_errors_grow_with_distance(self):
        es = [ent(1, "A", 200, 1000)] + [ent(10 + k, "B", 500, 600 + 40 * k) for k in range(10)] \
             + [ent(30 + k, "B", 2700, 600 + 40 * k) for k in range(10)]
        w = flat_world(es, commanders=[cmd(99, "A", 200, 1000)])
        near, far = [], []
        for _ in range(60):
            perception.step(w)
            for tid in list(range(10, 20)) + list(range(30, 40)):
                c = contact_of(w, 99, tid)
                if c is None or c.seen_t != w.tick:
                    continue
                e = w.entity(tid)
                (near if tid < 30 else far).append(abs(c.x - e.x) + abs(c.y - e.y))
            w.tick += perception._interval_ticks(P)
        self.assertGreater(np.mean(far), 3 * np.mean(near))

    def test_recognition_bands(self):
        es = [ent(1, "A", 100, 1000),
              ent(2, "B", 600, 1000, function="light_cavalry", mobility="horse"),
              ent(3, "B", 1600, 1000, function="light_cavalry", mobility="horse"),
              ent(4, "B", 2900, 1000, function="light_cavalry", mobility="horse")]
        w = flat_world(es, commanders=[cmd(99, "A", 100, 1000)])
        perception.step(w)
        kinds = {t: contact_of(w, 99, t).kind for t in (1, 2, 3, 4)}
        self.assertEqual(kinds, {1: "heavy_infantry", 2: "light_cavalry", 3: "horse", 4: "troops"})
        self.assertIsNone(contact_of(w, 99, 4).facing)
        self.assertIsNone(contact_of(w, 99, 3).order)

    def test_uncertainty_does_not_reveal_the_true_range(self):  # Codex 004/6
        w = scenario.load(FIELD, 1)
        perception.step(w)
        c = contact_of(w, 900, HORSE)
        true_d = math.hypot(w.entity(HORSE).x - 400, w.entity(HORSE).y - 1500)
        self.assertEqual(c.pos_err, round(c.pos_err))            # whole metres
        self.assertNotAlmostEqual(c.pos_err * 1000 / P["pos_error_per_km"], true_d, places=3)

    def test_facing_to_visual_resolution(self):
        es = [ent(1, "A", 100, 1000), ent(2, "B", 500, 1000)]
        w = flat_world(es)
        w.entity(2).facing = 0.3
        perception.step(w)
        res = math.radians(P["facing_resolution_deg"])
        f = contact_of(w, 1, 2).facing
        self.assertAlmostEqual(f / res, round(f / res), places=9)

    def test_officer_attention_range_but_commander_sees_further(self):
        es = [ent(1, "A", 100, 1000), ent(2, "B", 100 + P["officer_attention_range"] + 300, 1000)]
        w = flat_world(es, commanders=[cmd(99, "A", 100, 1050)])
        perception.step(w)
        self.assertIsNone(contact_of(w, 1, 2))
        self.assertIsNotNone(contact_of(w, 99, 2))

    def test_a_pair_is_unaffected_by_other_entities(self):
        base = [ent(1, "A", 100, 1000), ent(2, "B", 1200, 1100)]
        more = base + [ent(3, "B", 1150, 1600), ent(4, "A", 3000, 300)]
        a, b = flat_world(base), flat_world(more)
        for w in (a, b):
            perception.step(w)
        ca, cb = contact_of(a, 1, 2), contact_of(b, 1, 2)
        self.assertEqual(dataclasses.replace(ca, handle=0), dataclasses.replace(cb, handle=0))

    def test_visibility_of_a_pair_does_not_depend_on_the_batch(self):
        t = terrain.build({"width": 4000, "height": 2000, "cell": 20, "hills": [[2000, 1000, 40, 800]],
                           "woods": [[800, 200, 1200, 600]]})
        rng = np.random.default_rng(1)
        tx, ty = rng.uniform(0, 4000, 200), rng.uniform(0, 2000, 200)
        batch = sight.visible_many(t, P, 300, 1000, 1.7, tx, ty, np.full(200, 2.0))
        single = [sight.line_of_sight(t, P, 300, 1000, 1.7, x, y, 2.0) for x, y in zip(tx, ty)]
        self.assertEqual(list(batch), single)
        self.assertTrue(batch.any() and not batch.all())


class KeyedDraws(unittest.TestCase):
    def test_pure_function_of_keys(self):
        a = keyed_normals(5, "perception", [np.array([1, 2, 3]), np.array([7, 7, 7])], 4)
        b = keyed_normals(5, "perception", [np.array([2]), np.array([7])], 4)
        np.testing.assert_array_equal(a[1], b[0])
        self.assertFalse(np.array_equal(a[0], a[1]))

    def test_distribution_and_open_interval(self):
        from imperatores.rng import keyed_uniforms
        z = keyed_normals(5, "perception", [np.arange(100000), np.zeros(100000, dtype=np.int64)], 2).ravel()
        self.assertAlmostEqual(float(z.mean()), 0.0, delta=0.015)
        self.assertAlmostEqual(float(z.std()), 1.0, delta=0.015)
        self.assertLess(float(np.abs(z).max()), 7.0)
        u = keyed_uniforms(5, "perception", [np.arange(100000)], 2)
        self.assertTrue((u > 0).all() and (u < 1).all())

    def test_seed_and_stream_matter_and_bad_keys_refused(self):
        k = [np.array([1]), np.array([2])]
        self.assertFalse(np.array_equal(keyed_normals(5, "perception", k, 2), keyed_normals(6, "perception", k, 2)))
        self.assertFalse(np.array_equal(keyed_normals(5, "perception", k, 2), keyed_normals(5, "movement", k, 2)))
        with self.assertRaises(ValueError):
            keyed_normals(5, "perception", [np.array([-1])], 1)
        with self.assertRaises(ValueError):
            keyed_normals(5, "perception", [np.array([1.5])], 1)


class Reports(unittest.TestCase):
    def test_newer_replaces_older_is_ignored(self):
        w = flat_world([ent(1, "A", 100, 1000)])
        perception.ensure_beliefs(w)
        belief.apply_report(w, 1, [report_contact(x=1000.0, y=1000.0, seen_t=50)], sender=7, received_t=60)
        h = sorted(w.beliefs[1].tracks)[0]
        self.assertEqual(belief.apply_report(w, 1, [report_contact(x=1010.0, y=1000.0, seen_t=40)], sender=7, received_t=61), [])
        self.assertEqual(w.beliefs[1].tracks[h].x, 1000.0)
        self.assertEqual(belief.apply_report(w, 1, [report_contact(x=1020.0, y=1000.0, seen_t=55)], sender=8, received_t=62), [h])
        c = w.beliefs[1].tracks[h]
        self.assertEqual((c.x, c.source, c.report_from, c.received_t, c.first_seen_t), (1020.0, "report", 8, 62, 60))


class ReplayAndLoading(unittest.TestCase):
    def test_replay_exact(self):
        a, b = scenario.load(FIELD, 2), scenario.load(FIELD, 2)
        engine.run(a, 600)
        engine.run(b, 600)
        self.assertEqual(record.digest(a), record.digest(b))
        json.dumps(record.to_json(a), allow_nan=False)

    def test_a_report_alone_changes_the_digest(self):           # Codex 004/2
        a, b = scenario.load(FIELD, 1), scenario.load(FIELD, 1)
        for w in (a, b):
            record.snapshot(w)
            engine.step(w)
        belief.apply_report(b, 1, [report_contact()], sender=900, received_t=1)
        engine.step(a, 10)
        engine.step(b, 10)
        self.assertEqual([(e.x, e.y) for e in a.entities], [(e.x, e.y) for e in b.entities])
        self.assertNotEqual(record.digest(a), record.digest(b))

    def test_an_unsnapshotted_belief_field_changes_the_digest(self):   # Codex 004/2
        a = scenario.load(FIELD, 1, {"order_error": 0.1})
        b = scenario.load(FIELD, 1, {"order_error": 0.2})          # changes only judged order in beliefs
        for w in (a, b):
            engine.run(w, 60)
        self.assertEqual([(e.x, e.y) for e in a.entities], [(e.x, e.y) for e in b.entities])
        self.assertNotEqual(a.belief_trace, b.belief_trace)

    def test_bad_commanders_refused(self):
        for mutate in (lambda s: s["commanders"][0].update(id=1),
                       lambda s: s["commanders"][1].update(commands=[51]),
                       lambda s: s["commanders"][1].update(commands=[12345]),
                       lambda s: s["commanders"][0].update(rank="king"),
                       lambda s: s["commanders"][0].update(id=2 ** 32)):      # Codex 004/9
            s = spec()
            mutate(s)
            with self.assertRaises(ValueError):
                scenario.load(write(s), 1)


class TerrainAndRoutes(unittest.TestCase):
    def test_terrain_is_read_only(self):                         # Codex 004/4
        t = terrain.build({"width": 240, "height": 80, "cell": 20})
        sight.line_of_sight(t, P, 10, 10, 2, 230, 10, 2)
        with self.assertRaises(ValueError):
            t.ground[0, 5] = terrain.WOODS
        with self.assertRaises(ValueError):
            t.elev[0, 0] = 3.0

    def test_one_rule_for_points_and_moves_at_a_stream(self):   # Codex 004/8
        t = terrain.build({"width": 100, "height": 100, "cell": 20, "stream": {"width": 1, "points": [[50, 0], [50, 100]]}})
        self.assertFalse(t.passable(60, 10))                     # on the edge of a stream cell
        self.assertTrue(t.passable(61, 10))
        self.assertTrue(t.segment_passable(61, 10, 70, 10))

    def test_grazing_tolerance(self):                             # Codex 004/10
        t = terrain.build({"width": 240, "height": 80, "cell": 20, "woods": [[100, 40, 120, 60]]})
        self.assertTrue(sight.line_of_sight(t, P, 11, 48.9 + 1e-12, 2, 211, 28.9 + 1e-12, 2))   # nm: grazing
        self.assertFalse(sight.line_of_sight(t, P, 11, 49.0, 2, 211, 29.0, 2))                  # cm: blocked

    def test_astar_edges_cost_exactly_at_clipped_cells(self):     # Codex 004/7
        from imperatores import pathing
        t = terrain.build({"width": 41, "height": 60, "cell": 20, "rough": [[20, 40, 40, 60]]})
        st = {}
        r = pathing.plan(t, P, "formed", 30, 30, 40.5, 59, st)
        self.assertIsNotNone(r)
        self.assertLessEqual(st["cost"], st["raw_cost"] + 1e-9)


class Performance(unittest.TestCase):
    def test_perception_cycle_at_full_army_size(self):
        es = []
        for side, x0 in (("A", 1000), ("B", 3000)):
            for k in range(100):
                es.append(ent(len(es) + 1, side, x0 + (k // 10) * 50, 500 + (k % 10) * 100))
        cmds = [cmd(1000 + k, "A" if k < 3 else "B", 600 if k < 3 else 3400, 500 + 400 * (k % 3),
                    "army" if k in (0, 3) else "wing") for k in range(6)]
        w = flat_world(es, commanders=cmds, extra_terrain={"hills": [[2000, 1000, 30, 900]]})
        t0 = time.perf_counter()
        step_perception(w, 5)
        per = (time.perf_counter() - t0) / 5
        battle = per * (3 * 3600 / P["perception_interval_s"])
        print(f"\n  perception cycle, 200 entities + 6 commanders: {per * 1000:.0f} ms "
              f"(about {battle:.0f} s over a 3-hour battle)")
        self.assertLess(per, 5.0)


if __name__ == "__main__":
    unittest.main()
