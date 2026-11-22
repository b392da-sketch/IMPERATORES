"""Step 2 tests: terrain building, line of sight, route planning and movement over ground."""
from __future__ import annotations

import json
import math
import tempfile
import time
import unittest
from pathlib import Path

from imperatores import engine, params, pathing, record, scenario, sight, terrain
from imperatores.terrain import FORD, OPEN, ROUGH, STREAM, WOODS

ROOT = Path(__file__).resolve().parent.parent
FIELD = ROOT / "scenarios" / "test_field.json"
P = params.resolve()


def spec():
    return json.loads(FIELD.read_text())


def write(s) -> Path:
    f = Path(tempfile.mkdtemp()) / "scenario.json"
    f.write_text(json.dumps(s))
    return f


def flat(**extra):
    base = {"width": 2000, "height": 1000, "cell": 20}
    base.update(extra)
    return terrain.build(base)


class Building(unittest.TestCase):
    def test_ground_types_placed(self):
        t = terrain.build(spec()["terrain"])
        self.assertEqual(t.ground_at(1400, 800), WOODS)
        self.assertEqual(t.ground_at(1800, 1200), ROUGH)
        self.assertEqual(t.ground_at(2850, 1500), FORD)
        self.assertEqual(t.ground_at(2810, 300), STREAM)
        self.assertEqual(t.ground_at(500, 500), OPEN)
        self.assertGreater(t.height_at(2000, 2400), 35.0)
        self.assertLess(t.height_at(500, 500), 1.0)

    def test_bad_terrain_refused(self):
        for bad in ({"fords": [[100, 100, 10]]},                                   # ford without stream
                    {"stream": {"width": 10, "points": [[0, 500], [2000, 500]]},
                     "fords": [[1000, 900, 10]]},                                    # ford off the stream
                    {"woods": [[100, 100, 100, 200]]},                               # no area
                    {"hills": [[500, 500, 10, 0]]}):
            with self.assertRaises(ValueError):
                flat(**bad)

    def test_segment_traversal_is_exact(self):
        t = flat()
        cells = terrain.cells_on_segment(t, 10, 10, 50, 10)
        self.assertEqual(cells, [(0, 0), (0, 1), (0, 2)])
        diag = terrain.cells_on_segment(t, 10, 10, 50, 50)     # passes through two cell corners
        self.assertIn((0, 1), diag)
        self.assertIn((1, 0), diag)
        self.assertEqual(diag[-1], (2, 2))

    def test_no_step_crosses_a_thin_diagonal_stream(self):
        import numpy as np
        t = flat(stream={"width": 1, "points": [[0, 0], [2000, 1000]]})
        rng = np.random.default_rng(0)
        crossings = 0
        for _ in range(3000):
            x = rng.uniform(40, 1960)
            y = x / 2 + rng.uniform(-12, 12)                              # start close to the stream line
            ang, L = rng.uniform(0, 2 * math.pi), rng.uniform(1, 16)    # up to one tick at a gallop
            bx, by = x + L * math.cos(ang), y + L * math.sin(ang)
            side_a, side_b = y - x / 2, by - bx / 2
            if t.inside(bx, by) and side_a * side_b < 0:                  # the step crosses the stream line
                crossings += 1
                self.assertFalse(t.segment_passable(x, y, bx, by), (x, y, bx, by))
        self.assertGreater(crossings, 20)

    def test_stream_is_continuous(self):
        # a thin stream must still be at least one cell wide so nothing slips through diagonally
        t = flat(stream={"width": 1, "points": [[0, 0], [2000, 1000]]})
        r = pathing.plan(t, P, "formed", 100, 900, 1900, 100)
        self.assertIsNone(r)


class Sight(unittest.TestCase):
    def los(self, t, a, b, eye=1.7, tgt=2.0):
        return sight.line_of_sight(t, P, a[0], a[1], eye, b[0], b[1], tgt)

    def test_open_ground_visible_within_range(self):
        t = flat()
        self.assertTrue(self.los(t, (100, 500), (1900, 500)))

    def test_range_limit(self):
        t = terrain.build({"width": 6000, "height": 1000, "cell": 20})
        self.assertFalse(self.los(t, (100, 500), (100 + P["sight_range_max"] + 50, 500)))

    def test_hill_blocks_view_from_low_ground_but_not_from_the_top(self):
        t = flat(hills=[[1000, 500, 30, 400]])
        self.assertFalse(self.los(t, (200, 500), (1800, 500)))           # over the hill: blocked
        self.assertTrue(self.los(t, (1000, 500), (1800, 500)))           # from the top: seen
        self.assertTrue(self.los(t, (1000, 500), (200, 500)))

    def test_higher_ground_sees_over_a_wood(self):
        t = flat(woods=[[900, 0, 1100, 1000]], hills=[[200, 500, 80, 300]])
        self.assertFalse(self.los(t, (700, 500), (1500, 500)))           # low ground: wood in the way
        self.assertTrue(self.los(t, (200, 500), (1500, 500)))            # from the hilltop: over the canopy

    def test_inside_a_wood_sight_is_short(self):
        t = flat(woods=[[500, 0, 1500, 1000]])
        self.assertTrue(self.los(t, (1000, 500), (1040, 500)))
        self.assertFalse(self.los(t, (1000, 500), (1300, 500)))
        self.assertFalse(self.los(t, (100, 500), (1000, 500)))           # cannot see deep into it

    def test_symmetric_on_flat_ground(self):
        t = flat(woods=[[900, 0, 1100, 1000]])
        self.assertEqual(self.los(t, (100, 500), (1900, 500)), self.los(t, (1900, 500), (100, 500)))


class Routes(unittest.TestCase):
    def test_straight_on_open_ground(self):
        self.assertEqual(pathing.plan(flat(), P, "formed", 100, 500, 1900, 500), [(1900, 500)])

    def test_route_crosses_stream_only_at_the_ford(self):
        t = terrain.build(spec()["terrain"])
        r = pathing.plan(t, P, "horse", 1000, 300, 3300, 300)
        self.assertIsNotNone(r)
        pts = [(1000, 300)] + r
        crossed = []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            n = int(math.hypot(bx - ax, by - ay) / 5) + 1
            for k in range(n + 1):
                x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
                g = t.ground_at(x, y)
                self.assertNotEqual(g, STREAM, f"route enters the stream at ({x:.0f}, {y:.0f})")
                if g == FORD:
                    crossed.append((x, y))
        self.assertTrue(crossed, "route must use the ford")

    def test_formed_troops_avoid_most_of_a_wood_when_it_is_quicker(self):
        t = flat(woods=[[900, 300, 1100, 700]])
        f = pathing.factor_grid(t, P, "formed")
        st = {}
        r = pathing.plan(t, P, "formed", 100, 500, 1900, 500, st)
        through = pathing.segment_cost(t, f, 100, 500, 1900, 500)
        self.assertLess(st["cost"], through)                 # quicker than marching straight through
        self.assertLessEqual(st["cost"], st["raw_cost"] + 1e-9)
        pts = [(100, 500)] + r
        in_wood = 0.0
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            for k in range(400):
                x, y = ax + (bx - ax) * (k + 0.5) / 400, ay + (by - ay) * (k + 0.5) / 400
                if t.ground_at(x, y) == WOODS:
                    in_wood += math.hypot(bx - ax, by - ay) / 400
        self.assertLess(in_wood, 40.0)                       # at most a corner, not the 200 m depth

    def test_no_route(self):
        t = flat(stream={"width": 10, "points": [[1000, 0], [1000, 1000]]})
        self.assertIsNone(pathing.plan(t, P, "formed", 100, 500, 1900, 500))

    def test_deterministic(self):
        t = terrain.build(spec()["terrain"])
        self.assertEqual(pathing.plan(t, P, "formed", 1000, 1500, 3300, 1500),
                         pathing.plan(t, P, "formed", 1000, 1500, 3300, 1500))

    def test_planning_time_reported(self):
        t = terrain.build(spec()["terrain"])
        t0 = time.perf_counter()
        pathing.plan(t, P, "horse", 1000, 300, 3300, 300)
        elapsed = time.perf_counter() - t0
        print(f"\n  route across the test field planned in {elapsed * 1000:.0f} ms")
        self.assertLess(elapsed, 5.0)


class Movement(unittest.TestCase):
    def test_units_reach_targets_across_the_ford(self):
        w = scenario.load(FIELD, 1)
        engine.run(w, 3 * 3600)
        arrived = {e["entity"] for e in w.events if e["kind"] == "arrived"}
        self.assertEqual(arrived, {1, 2})

    def test_crossing_the_ford_costs_formed_troops_order(self):
        def lowest_order(path):
            w = scenario.load(path, 1)
            low = 1.0
            for _ in range(int(3 * 3600 / P["tick_seconds"])):   # order recovers once halted: watch the march
                engine.step(w)
                low = min(low, w.entity(1).order)
            return low
        s = spec()
        del s["terrain"]["stream"], s["terrain"]["fords"]
        self.assertEqual(lowest_order(write(s)), 1.0)          # same march, no stream: order kept
        self.assertLess(lowest_order(FIELD), 0.99)

    def test_woods_disorder_formed_troops_more_than_open_order(self):
        def low(function, mobility):
            s = {"name": "t", "terrain": {"width": 2000, "height": 1000, "cell": 20, "woods": [[800, 0, 1200, 1000]]},
                 "entities": [{"id": 1, "side": "A", "name": "m", "function": function,
                               "equipment": {"reach": "sword", "mobility": mobility},
                               "x": 100, "y": 500, "frontage": 40, "depth": 18, "strength": 120,
                               "task": {"kind": "move_to", "x": 1900, "y": 500}}]}
            w = scenario.load(write(s), 1)
            m = 1.0
            for _ in range(1200):
                engine.step(w)
                m = min(m, w.entity(1).order)
            return m
        self.assertLess(low("heavy_infantry", "foot"), 1.0)
        self.assertEqual(low("skirmishers", "foot"), 1.0)

    def test_uphill_slower_than_flat(self):
        def time_to(target_x, hills):
            s = {"name": "t", "terrain": {"width": 2000, "height": 1000, "cell": 20, "hills": hills},
                 "entities": [{"id": 1, "side": "A", "name": "m", "function": "heavy_infantry",
                               "x": 100, "y": 500, "frontage": 40, "depth": 18, "strength": 120,
                               "task": {"kind": "move_to", "x": target_x, "y": 500}}]}
            w = scenario.load(write(s), 1, {"pace_jitter": 0.0})
            engine.run(w, 3600)
            ev = [e for e in w.events if e["kind"] == "arrived"]
            return ev[0]["t"]
        self.assertGreater(time_to(1000, [[1000, 500, 60, 1200]]), time_to(1000, []))

    def test_no_route_logged_and_unit_holds(self):
        s = spec()
        s["terrain"]["fords"] = []
        s["terrain"]["stream"]["points"] = [[2800, 0], [2900, 3000]]
        w = scenario.load(write(s), 1)
        engine.run(w, 60)
        kinds = [(e["kind"], e["entity"]) for e in w.events]
        self.assertIn(("no_route", 1), kinds)
        self.assertEqual(w.entity(1).task, {"kind": "hold"})

    def test_cannot_start_or_aim_into_the_stream(self):
        s = spec()
        s["entities"][0]["task"] = {"kind": "move_to", "x": 2810, "y": 300}
        with self.assertRaises(ValueError):
            scenario.load(write(s), 1)
        s = spec()
        s["entities"][0]["x"], s["entities"][0]["y"] = 2810, 300
        with self.assertRaises(ValueError):
            scenario.load(write(s), 1)

    def test_replay_exact_with_terrain(self):
        a, b = scenario.load(FIELD, 4), scenario.load(FIELD, 4)
        engine.run(a, 1800)
        engine.run(b, 1800)
        self.assertEqual(record.digest(a), record.digest(b))
        json.dumps(record.to_json(a), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
