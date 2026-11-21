"""Step 1 tests: determinism, consistency, keyed randomness, parameters and scenario loading."""
from __future__ import annotations

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from imperatores import engine, params, record, scenario
from imperatores.rng import Random
from imperatores.systems.observe import ConsistencyError

ROOT = Path(__file__).resolve().parent.parent
MARCH = ROOT / "scenarios" / "test_march.json"


def run(seed=1, seconds=1200, overrides=None, path=MARCH):
    w = scenario.load(path, seed, overrides)
    engine.run(w, seconds)
    return w


class Replay(unittest.TestCase):
    def test_same_seed_same_record(self):
        self.assertEqual(record.digest(run(7)), record.digest(run(7)))

    def test_different_seed_different_record(self):
        self.assertNotEqual(record.digest(run(7)), record.digest(run(8)))

    def test_record_is_json_serialisable(self):
        json.dumps(record.to_json(run(3, seconds=200)))


class Consistency(unittest.TestCase):
    def test_full_run_passes_checks(self):
        w = run(1, seconds=2400)
        for e in w.entities:
            self.assertTrue(e.headcount_ok(), e.name)

    def test_headcount_violation_is_caught(self):
        w = scenario.load(MARCH, 1)
        engine.record.snapshot(w)
        w.entities[0].dead += 1                     # a man appears from nowhere in the dead column
        with self.assertRaises(ConsistencyError):
            engine.step(w)

    def test_teleport_is_caught(self):
        w = scenario.load(MARCH, 1)
        from imperatores.systems import observe
        observe.begin_tick(w)
        w.entities[0].x += 500
        with self.assertRaises(ConsistencyError):
            observe.end_tick(w)

    def test_movement_reaches_target_and_logs_arrival(self):
        w = run(1, seconds=3600)
        arrived = {e["entity"] for e in w.events if e["kind"] == "arrived"}
        self.assertIn(3, arrived)                   # the turma reaches its target within the hour
        self.assertTrue(all(e["causes"] for e in w.events), "every event carries a cause")

    def test_rough_ground_slows_and_disorders(self):
        open_w = run(1, seconds=1200, path=self._no_rough())
        rough_w = run(1, seconds=1200)
        self.assertLess(rough_w.entities[0].x, open_w.entities[0].x)
        self.assertLess(rough_w.entities[0].order, 1.0)

    def _no_rough(self):
        spec = json.loads(MARCH.read_text())
        spec["terrain"]["rough"] = []
        f = Path(tempfile.mkdtemp()) / "open.json"
        f.write_text(json.dumps(spec))
        return f


class KeyedRandom(unittest.TestCase):
    def test_streams_are_independent_by_key(self):
        a, b = Random(5), Random(5)
        a.gen("movement", 1).random(1000)          # heavy use of entity 1's stream in run a only
        self.assertEqual(a.gen("movement", 2).random(), b.gen("movement", 2).random())

    def test_intervention_on_one_entity_leaves_others_untouched(self):
        """Changing one entity's orders must not change another entity's random draws or path."""
        base = scenario.load(MARCH, 11)
        alt = scenario.load(MARCH, 11)
        alt.entities[3].task = {"kind": "hold"}     # the turma no longer moves (and stops drawing)
        engine.run(base, 1200)
        engine.run(alt, 1200)
        for i in (0, 1, 2):
            self.assertEqual((base.entities[i].x, base.entities[i].y),
                             (alt.entities[i].x, alt.entities[i].y))
        self.assertNotEqual(base.entities[3].x, alt.entities[3].x)

    def test_unknown_stream_refused(self):
        with self.assertRaises(ValueError):
            Random(1).gen("no_such_stream", 1)


class Params(unittest.TestCase):
    def test_every_param_has_range_label_and_basis(self):
        for k, p in params.PARAMS.items():
            self.assertLessEqual(p.lo, p.value, k)
            self.assertLessEqual(p.value, p.hi, k)
            self.assertIn(p.label, (params.EVIDENCED, params.ASSUMPTION), k)
            self.assertTrue(p.basis, k)

    def test_override_outside_range_refused(self):
        with self.assertRaises(ValueError):
            params.resolve({"pace_infantry_formed": 10.0})
        with self.assertRaises(KeyError):
            params.resolve({"no_such_value": 1.0})

    def test_override_changes_run(self):
        slow = run(1, seconds=600, overrides={"pace_infantry_formed": 0.6})
        fast = run(1, seconds=600, overrides={"pace_infantry_formed": 1.4})
        self.assertLess(slow.entities[0].x, fast.entities[0].x)


class ScenarioLoading(unittest.TestCase):
    def test_bad_side_refused(self):
        spec = json.loads(MARCH.read_text())
        spec["entities"][0]["side"] = "C"
        f = Path(tempfile.mkdtemp()) / "bad.json"
        f.write_text(json.dumps(spec))
        with self.assertRaises(ValueError):
            scenario.load(f, 1)

    def test_velites_linked_to_parent_maniples(self):
        w = scenario.load(MARCH, 1)
        self.assertEqual(w.entities[2].parents, [0, 1])
        self.assertEqual(len(w.entities[0].succession), 4)


if __name__ == "__main__":
    unittest.main()
