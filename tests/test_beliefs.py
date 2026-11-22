"""Step 3 tests: belief pictures, perception and information integrity (specification 5.4, 7.1 check 3)."""
from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from imperatores import belief, engine, params, record, scenario, sight, terrain
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


def beliefs_json(w, owners):
    return json.dumps({o: belief.to_json(w.beliefs[o]) for o in owners}, sort_keys=True)


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


class InformationIntegrity(unittest.TestCase):
    def test_hidden_entity_never_in_enemy_beliefs(self):
        w = scenario.load(FIELD, 1)
        record.snapshot(w)
        for _ in range(900):                                   # 30 minutes
            engine.step(w)
            for o in A_OWNERS:
                self.assertNotIn(HIDDEN, w.beliefs[o].contacts, f"owner {o} knows of the hidden reserve")
        self.assertIn(HORSE, w.beliefs[900].contacts)          # the horse in the open is seen

    def test_moving_an_unseen_entity_changes_no_enemy_belief(self):
        """Stale-truth test: the true state of an unseen entity changes; no belief may change."""
        a, b = scenario.load(FIELD, 3), scenario.load(FIELD, 3)
        record.snapshot(a)
        record.snapshot(b)
        engine.step(a, 100)
        engine.step(b, 100)
        b.entity(HIDDEN).x, b.entity(HIDDEN).y = 3200.0, 1200.0   # still hidden behind the hill
        b.entity(HIDDEN).fit -= 100
        b.entity(HIDDEN).dead += 100
        engine.step(a, 300)
        engine.step(b, 300)
        self.assertEqual(beliefs_json(a, A_OWNERS), beliefs_json(b, A_OWNERS))

    def test_unseen_contact_keeps_last_known_state(self):
        s = spec()
        s["entities"][3]["task"] = {"kind": "move_to", "x": 3000, "y": 1300}   # the horse rides behind the hill
        w = scenario.load(write(s), 1)
        record.snapshot(w)
        engine.step(w, 1200)
        c = w.beliefs[900].contacts[HORSE]
        true = w.entity(HORSE)
        self.assertLess(c["seen_t"], w.tick - 100)              # not seen for a while
        self.assertGreater(abs(c["x"] - true.x) + abs(c["y"] - true.y), 300)  # belief is out of date
        v = belief.view(w, 900)
        self.assertGreater(v.age(v.contact(HORSE)), 100)

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
            elif isinstance(o, (tuple,)):
                for x in o:
                    walk(x)
            elif hasattr(o, "items"):
                for k, x in o.items():
                    walk(x)
        walk(v)

    def test_view_is_read_only(self):
        w = scenario.load(FIELD, 1)
        engine.run(w, 60)
        v = belief.view(w, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            v.contacts[0].x = 0.0
        with self.assertRaises(TypeError):
            v.own["fit"] = 0
        before = beliefs_json(w, (1,))
        _ = belief.view(w, 1)
        self.assertEqual(before, beliefs_json(w, (1,)))

    def test_officer_knows_own_entity_exactly_commander_has_no_own(self):
        w = scenario.load(FIELD, 1)
        engine.run(w, 20)
        own = w.beliefs[1].own
        self.assertEqual(own["fit"], w.entity(1).fit)
        self.assertIsNone(w.beliefs[900].own)


class Perception(unittest.TestCase):
    def test_errors_grow_with_distance(self):
        es = [ent(1, "A", 200, 1000)] + [ent(10 + k, "B", 200 + 300, 600 + 40 * k) for k in range(10)] \
             + [ent(30 + k, "B", 200 + 2500, 600 + 40 * k) for k in range(10)]
        w = flat_world(es, commanders=[{"id": 99, "side": "A", "name": "c", "rank": "army", "x": 200, "y": 1000}])
        near, far = [], []
        for _ in range(60):
            perception.step(w)
            for tid, c in w.beliefs[99].contacts.items():
                e = w.entity(tid)
                err = abs(c["x"] - e.x) + abs(c["y"] - e.y)
                (near if tid < 30 else far).append(err)
            w.tick += perception._interval_ticks(P)
        self.assertGreater(np.mean(far), 3 * np.mean(near))

    def test_recognition_bands(self):
        es = [ent(1, "A", 100, 1000),
              ent(2, "B", 100 + 500, 1000, function="light_cavalry", mobility="horse"),
              ent(3, "B", 100 + 1500, 1000, function="light_cavalry", mobility="horse"),
              ent(4, "B", 100 + 2800, 1000, function="light_cavalry", mobility="horse")]
        w = flat_world(es, commanders=[{"id": 99, "side": "A", "name": "c", "rank": "army", "x": 100, "y": 1000}])
        perception.step(w)
        kinds = {t: c["kind"] for t, c in w.beliefs[99].contacts.items()}
        self.assertEqual(kinds, {1: "heavy_infantry", 2: "light_cavalry", 3: "horse", 4: "troops"})
        self.assertIsNone(w.beliefs[99].contacts[4]["facing"])
        self.assertIsNone(w.beliefs[99].contacts[3]["order"])

    def test_officer_attention_range_but_commander_sees_further(self):
        es = [ent(1, "A", 100, 1000), ent(2, "B", 100 + P["officer_attention_range"] + 300, 1000)]
        w = flat_world(es, commanders=[{"id": 99, "side": "A", "name": "c", "rank": "army", "x": 100, "y": 1050}])
        perception.step(w)
        self.assertNotIn(2, w.beliefs[1].contacts)
        self.assertIn(2, w.beliefs[99].contacts)

    def test_a_pair_is_unaffected_by_other_entities(self):
        base = [ent(1, "A", 100, 1000), ent(2, "B", 1200, 1100)]
        more = base + [ent(3, "B", 1150, 1050), ent(4, "A", 3000, 300)]
        a, b = flat_world(base), flat_world(more)
        for w in (a, b):
            perception.step(w)
        self.assertEqual(a.beliefs[1].contacts[2], b.beliefs[1].contacts[2])

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

    def test_distribution(self):
        z = keyed_normals(5, "perception", [np.arange(20000), np.zeros(20000, dtype=np.int64)], 2).ravel()
        self.assertAlmostEqual(float(z.mean()), 0.0, delta=0.03)
        self.assertAlmostEqual(float(z.std()), 1.0, delta=0.03)

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
        b = belief.Belief(owner=1)
        belief.observe(b, {"id": 5, "side": "B", "kind": "foot", "x": 1.0, "y": 1.0, "pos_err": 1.0,
                           "strength": 100, "order": None, "facing": None, "seen_t": 50})
        old = {"id": 5, "side": "B", "kind": "foot", "x": 9.0, "y": 9.0, "pos_err": 1.0,
               "strength": 90, "order": None, "facing": None, "seen_t": 40}
        self.assertEqual(belief.merge_report(b, [old], sender=7, received_t=60), [])
        self.assertEqual(b.contacts[5]["x"], 1.0)
        new = dict(old, seen_t=55, x=5.0)
        self.assertEqual(belief.merge_report(b, [new], sender=7, received_t=60), [5])
        c = b.contacts[5]
        self.assertEqual((c["x"], c["source"], c["received_t"], c["first_seen_t"]), (5.0, {"report_from": 7}, 60, 50))

    def test_report_about_an_unknown_body_adds_it(self):
        b = belief.Belief(owner=1)
        rc = {"id": 8, "side": "B", "kind": "horse", "x": 3.0, "y": 4.0, "pos_err": 10.0,
              "strength": 30, "order": None, "facing": None, "seen_t": 10}
        belief.merge_report(b, [rc], sender=2, received_t=30)
        self.assertEqual(b.contacts[8]["first_seen_t"], 30)       # first known when the report arrived


class ReplayAndLoading(unittest.TestCase):
    def test_replay_exact_and_beliefs_in_digest(self):
        a, b = scenario.load(FIELD, 2), scenario.load(FIELD, 2)
        engine.run(a, 600)
        engine.run(b, 600)
        self.assertEqual(record.digest(a), record.digest(b))
        c = scenario.load(FIELD, 2, {"pos_error_per_km": 60.0})   # only perception differs
        engine.run(c, 600)
        self.assertEqual([(e.x, e.y) for e in a.entities], [(e.x, e.y) for e in c.entities])
        self.assertNotEqual(record.digest(a), record.digest(c))
        json.dumps(record.to_json(a), allow_nan=False)

    def test_bad_commanders_refused(self):
        for mutate in (lambda s: s["commanders"][0].update(id=1),                 # clashes with an entity id
                       lambda s: s["commanders"][1].update(commands=[51]),        # other side
                       lambda s: s["commanders"][1].update(commands=[12345]),     # unknown
                       lambda s: s["commanders"][0].update(rank="king")):
            s = spec()
            mutate(s)
            with self.assertRaises(ValueError):
                scenario.load(write(s), 1)


class Performance(unittest.TestCase):
    def test_perception_cycle_at_full_army_size(self):
        es = []
        for side, x0 in (("A", 1000), ("B", 3000)):
            for k in range(100):
                es.append(ent(len(es) + 1, side, x0 + (k // 10) * 50, 500 + (k % 10) * 100))
        cmds = [{"id": 1000 + k, "side": "A" if k < 3 else "B", "name": f"c{k}", "rank": "army" if k in (0, 3) else "wing",
                 "x": 600 if k < 3 else 3400, "y": 500 + 400 * (k % 3)} for k in range(6)]
        w = flat_world(es, commanders=cmds, extra_terrain={"hills": [[2000, 1000, 30, 900]]})
        t0 = time.perf_counter()
        for _ in range(5):
            perception.step(w)
            w.tick += perception._interval_ticks(P)
        per = (time.perf_counter() - t0) / 5
        battle = per * (3 * 3600 / P["perception_interval_s"])
        print(f"\n  perception cycle, 200 entities + 6 commanders: {per * 1000:.0f} ms "
              f"(about {battle:.0f} s over a 3-hour battle)")
        self.assertLess(per, 5.0)


if __name__ == "__main__":
    unittest.main()
