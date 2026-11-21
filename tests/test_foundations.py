"""Step 1 tests: determinism, consistency, keyed randomness, parameters and scenario loading.

Tests marked "Codex 002/N" reproduce a finding of review 002 and check its fix.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from imperatores import engine, params, record, scenario
from imperatores.rng import Random
from imperatores.systems import observe
from imperatores.systems.observe import ConsistencyError

ROOT = Path(__file__).resolve().parent.parent
MARCH = ROOT / "scenarios" / "test_march.json"
TURMA, BLOCK, HASTATI_I = 20, 50, 10


def spec():
    return json.loads(MARCH.read_text())


def write(s) -> Path:
    f = Path(tempfile.mkdtemp()) / "scenario.json"
    f.write_text(json.dumps(s))
    return f


def run(seed=1, seconds=1200, overrides=None, path=MARCH):
    w = scenario.load(path, seed, overrides)
    engine.run(w, seconds)
    return w


def trajectory(seed, seconds, path):
    """Full-precision state of every entity after every tick, by stable id."""
    w = scenario.load(path, seed)
    record.snapshot(w)
    out = []
    for _ in range(int(seconds / w.params["tick_seconds"])):
        engine.step(w)
        out.append({e.id: (e.x, e.y, e.facing, e.fatigue, e.order) for e in w.entities})
    return out


class Replay(unittest.TestCase):
    def test_same_seed_same_record(self):
        self.assertEqual(record.digest(run(7)), record.digest(run(7)))
        self.assertEqual(json.dumps(record.to_json(run(7))), json.dumps(record.to_json(run(7))))

    def test_different_seed_different_states(self):
        a, b = run(7), run(8)
        self.assertNotEqual([(e.x, e.y) for e in a.entities], [(e.x, e.y) for e in b.entities])

    def test_run_length_is_part_of_identity(self):            # Codex 002/5
        a, b = run(1, seconds=2), run(1, seconds=4)
        self.assertNotEqual(a.entities[0].x, b.entities[0].x)
        self.assertNotEqual(record.digest(a), record.digest(b))
        self.assertEqual(a.snapshots[-1]["t"], a.tick)          # final state always recorded
        self.assertEqual(b.snapshots[-1]["t"], b.tick)

    def test_trace_covers_unsnapshotted_ticks(self):           # Codex 002/5
        w = scenario.load(MARCH, 1)
        record.snapshot(w)
        engine.step(w)                                          # tick 1: no scheduled snapshot
        t1 = w.trace
        w2 = scenario.load(MARCH, 1)
        record.snapshot(w2)
        engine.step(w2)
        w2.entities[0].x += 1e-9                                # tiny difference, invisible to rounding
        record.advance_trace(w2)
        self.assertNotEqual(t1, w2.trace)

    def test_record_is_strict_json(self):
        json.dumps(record.to_json(run(3, seconds=200)), allow_nan=False)


class Consistency(unittest.TestCase):
    def test_full_run_passes_checks(self):
        run(1, seconds=2400)

    def test_extra_man_is_caught(self):
        w = scenario.load(MARCH, 1)
        w.entities[0].dead += 1
        with self.assertRaises(ConsistencyError):
            engine.step(w)

    def test_fractional_and_out_of_range_states_caught_before_masking(self):   # Codex 002/4
        w = scenario.load(MARCH, 1)
        e = w.entities[0]
        e.fit -= 0.5
        e.dead += 0.5
        with self.assertRaises(ConsistencyError):
            engine.step(w)
        w = scenario.load(MARCH, 1)
        w.entities[0].task = {"kind": "hold"}
        w.entities[0].order = 2.0                               # movement would clamp this to 1.0
        with self.assertRaises(ConsistencyError):
            engine.step(w)
        w = scenario.load(MARCH, 1)
        w.entities[0].fatigue = float("nan")
        with self.assertRaises(ConsistencyError):
            engine.step(w)

    def test_violation_hidden_by_a_later_phase_is_caught(self):  # Codex 002/4
        w = scenario.load(MARCH, 1)
        e = w.entities[0]

        def bad(w):
            e.dead += 1

        def undo(w):
            e.dead -= 1

        with mock.patch.object(engine, "PHASES", [("bad", bad), ("undo", undo)]):
            with self.assertRaises(ConsistencyError):
                engine.step(w)

    def test_unannounced_roster_change_is_caught(self):        # Codex 002/4
        w = scenario.load(MARCH, 1)
        observe.begin_tick(w)
        w.entities.append(dataclasses.replace(w.entities[0], id=99, x=-1.0))
        with self.assertRaises(ConsistencyError):
            observe.end_tick(w)

    def test_teleport_is_caught(self):
        w = scenario.load(MARCH, 1)
        observe.begin_tick(w)
        w.entities[0].x += 500
        with self.assertRaises(ConsistencyError):
            observe.end_tick(w)

    def test_upper_range_settings_do_not_trip_the_speed_guard(self):  # Codex 002/3
        w = scenario.load(MARCH, 2, {"pace_cavalry": 5, "pace_jitter": 0.2, "max_speed_any": 5})
        engine.run(w, 600)

    def test_arrival(self):
        w = run(1, seconds=3600)
        ev = [e for e in w.events if e["kind"] == "arrived" and e["entity"] == TURMA]
        self.assertEqual(len(ev), 1)
        t = w.entity(TURMA)
        self.assertEqual(t.task, {"kind": "hold"})
        tx, ty = ev[0]["data"]["target"]
        self.assertLessEqual(((t.x - tx) ** 2 + (t.y - ty) ** 2) ** 0.5, w.params["arrival_tolerance"])
        self.assertTrue(ev[0]["causes"])

    def test_rough_ground_slows_and_disorders(self):
        s = spec()
        s["terrain"]["rough"] = []
        open_w = run(1, seconds=1200, path=write(s))
        rough_w = run(1, seconds=1200)
        self.assertLess(rough_w.entity(HASTATI_I).x, open_w.entity(HASTATI_I).x)
        self.assertLess(rough_w.entity(HASTATI_I).order, 1.0)
        self.assertEqual(open_w.entity(HASTATI_I).order, 1.0)

    def test_blocked_move_costs_nothing(self):                  # Codex 002/8
        w = scenario.load(MARCH, 1)
        e = w.entities[0]
        e.x = 4000.0
        e.task = {"kind": "move_to", "x": 4100, "y": e.y}       # target off the field, set directly
        engine.step(w)
        self.assertEqual(e.x, 4000.0)
        self.assertEqual(e.fatigue, 0.0)


class Events(unittest.TestCase):
    def test_logged_event_cannot_be_rewritten_by_its_inputs(self):  # Codex 002/6
        w = scenario.load(MARCH, 1)
        belief = {"x": 10}
        causes = [{"note": "n"}]
        record.log(w, "probe", 0, {"belief": belief}, causes)
        d = record.digest(w)
        belief["x"] = 20
        causes.append({"note": "m"})
        self.assertEqual(w.events[0]["data"]["belief"]["x"], 10)
        self.assertEqual(len(w.events[0]["causes"]), 1)
        self.assertEqual(d, record.digest(w))

    def test_non_json_event_data_refused(self):
        w = scenario.load(MARCH, 1)
        with self.assertRaises(ValueError):
            record.log(w, "probe", 0, {"x": float("nan")})


class KeyedRandom(unittest.TestCase):
    def test_streams_are_independent_by_key(self):
        a, b = Random(5), Random(5)
        a.gen("movement", 1).random(1000)
        self.assertEqual(a.gen("movement", 2).random(), b.gen("movement", 2).random())

    def test_distinct_keys_never_share_a_stream(self):          # Codex 002/2
        r = Random(5)
        self.assertNotEqual(list(r.gen("movement", 1).integers(0, 2 ** 32, 4)),
                            list(Random(5).gen("movement", 1, 1).integers(0, 2 ** 32, 4)))
        with self.assertRaises(ValueError):
            r.gen("movement", 2 ** 32 + 1)
        with self.assertRaises(TypeError):
            r.gen("movement", 1.9)
        with self.assertRaises(TypeError):
            r.gen("movement", True)

    def test_unknown_stream_refused(self):
        with self.assertRaises(ValueError):
            Random(1).gen("no_such_stream", 1)

    def test_holding_one_entity_leaves_others_untouched(self):
        s = spec()
        s["entities"][3]["task"] = {"kind": "hold"}             # the turma stays put
        base, alt = trajectory(11, 600, MARCH), trajectory(11, 600, write(s))
        for tick_a, tick_b in zip(base, alt):
            for eid in (10, 11, 12, 50):
                self.assertEqual(tick_a[eid], tick_b[eid])
        self.assertNotEqual(base[-1][TURMA], alt[-1][TURMA])

    def test_removing_an_entity_leaves_others_untouched(self):  # Codex 002/1
        s = spec()
        s["entities"][4]["task"] = {"kind": "move_to", "x": 3000, "y": 1500}
        removed = copy.deepcopy(s)
        del removed["entities"][3]                              # remove the turma (id 20)
        base, alt = trajectory(1, 600, write(s)), trajectory(1, 600, write(removed))
        for tick_a, tick_b in zip(base, alt):
            self.assertNotIn(TURMA, tick_b)
            for eid in (10, 11, 12, 50):
                self.assertEqual(tick_a[eid], tick_b[eid])
        w = scenario.load(write(removed), 1)
        self.assertEqual(w.entity(12).parents, [10, 11])        # links survive by id


class Params(unittest.TestCase):
    def test_every_param_has_range_label_basis_and_grade_if_evidenced(self):   # Codex 002/7
        for k, p in params.PARAMS.items():
            self.assertLessEqual(p.lo, p.value, k)
            self.assertLessEqual(p.value, p.hi, k)
            self.assertIn(p.label, (params.EVIDENCED, params.ASSUMPTION), k)
            self.assertTrue(p.basis, k)
            if p.label == params.EVIDENCED:
                self.assertTrue(p.grade, k)

    def test_bad_overrides_refused(self):                       # Codex 002/7
        for bad in ({"pace_infantry_formed": 10.0}, {"snapshot_every_ticks": 1.9},
                    {"snapshot_every_ticks": True}, {"pace_jitter": float("nan")}):
            with self.assertRaises((ValueError, TypeError)):
                params.resolve(bad)
        with self.assertRaises(KeyError):
            params.resolve({"no_such_value": 1.0})
        self.assertEqual(params.resolve({"snapshot_every_ticks": 3.0})["snapshot_every_ticks"], 3)

    def test_override_changes_run(self):
        slow = run(1, seconds=600, overrides={"pace_infantry_formed": 0.6})
        fast = run(1, seconds=600, overrides={"pace_infantry_formed": 1.4})
        self.assertLess(slow.entity(HASTATI_I).x, fast.entity(HASTATI_I).x)


class ScenarioLoading(unittest.TestCase):
    def _refused(self, mutate):
        s = spec()
        mutate(s)
        with self.assertRaises(ValueError):
            scenario.load(write(s), 1)

    def test_bad_inputs_refused(self):
        self._refused(lambda s: s["entities"][0].update(side="C"))
        self._refused(lambda s: s["entities"][1].update(id=10))                  # duplicate id
        self._refused(lambda s: s["entities"][0].pop("id"))
        self._refused(lambda s: s["entities"][2].update(parents=[999]))
        self._refused(lambda s: s["entities"][0].update(task={"kind": "move_to", "x": 9999, "y": 0}))
        self._refused(lambda s: s["entities"][0].update(strength=1.5))
        self._refused(lambda s: s["terrain"].pop("cell"))
        self._refused(lambda s: s["entities"][0].update(x=-5))

    def test_ids_are_not_positions(self):
        w = scenario.load(MARCH, 1)
        self.assertEqual([e.id for e in w.entities], [10, 11, 12, 20, 50])
        self.assertEqual(w.entity(12).parents, [10, 11])
        self.assertEqual(len(w.entity(10).succession), 4)


if __name__ == "__main__":
    unittest.main()
