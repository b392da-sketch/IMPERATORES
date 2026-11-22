"""Tests for the fixes to Codex review 003 (step 2: terrain, sight and routes).

Each test reproduces a finding and checks its fix; several compare against an independent oracle.
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from imperatores import engine, params, pathing, scenario, sight, terrain
from imperatores.terrain import FORD, STREAM, WOODS

P = params.resolve()


def build(**k):
    base = {"cell": 20}
    base.update(k)
    return terrain.build(base)


def write(s) -> Path:
    f = Path(tempfile.mkdtemp()) / "scenario.json"
    f.write_text(json.dumps(s))
    return f


def one_unit(terrain_spec, x, y, tx, ty, function="heavy_infantry", mobility="foot", overrides=None):
    s = {"name": "t", "terrain": terrain_spec,
         "entities": [{"id": 1, "side": "A", "name": "u", "function": function, "x": x, "y": y,
                       "frontage": 40, "depth": 18, "strength": 120,
                       "equipment": {"reach": "sword", "mobility": mobility},
                       "task": {"kind": "move_to", "x": tx, "y": ty}}]}
    return scenario.load(write(s), 1, overrides)


def touches_oracle(t, ax, ay, bx, by, i, j):
    """Independent check: does the closed segment meet the closed square of cell (i, j)? (Liang-Barsky)"""
    c = t.cell
    x0, x1, y0, y1 = j * c, (j + 1) * c, i * c, (i + 1) * c
    dx, dy = bx - ax, by - ay
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
        if abs(p) < 1e-12:
            if q < -1e-9:
                return False
            continue
        r = q / p
        if p < 0:
            lo = max(lo, r)
        else:
            hi = min(hi, r)
        if lo > hi + 1e-9:
            return False
    return True


class F1StreamAtTheFieldEdge(unittest.TestCase):
    def test_oblique_entry_blocks_crossing(self):
        t = build(width=100, height=100, stream={"width": 1, "points": [[50, -100], [90, 100]]})
        self.assertFalse(t.segment_passable(65, 1, 76, 1))
        self.assertIsNone(pathing.plan(t, P, "horse", 65, 1, 76, 1))

    def test_segment_off_the_field_marks_nothing(self):
        t = build(width=100, height=100, stream={"width": 1, "points": [[0, -20], [100, -20]]})
        self.assertEqual(int((t.ground == STREAM).sum()), 0)

    def test_join_near_the_edge_has_no_gap(self):
        t = build(width=200, height=200, stream={"width": 1, "points": [[-50, 30], [7, 3], [190, 210]]})
        rng = np.random.default_rng(3)
        crossings = 0
        for _ in range(4000):
            ax, ay = rng.uniform(0, 200, 2)
            ang, L = rng.uniform(0, 2 * math.pi), rng.uniform(1, 30)
            bx, by = ax + L * math.cos(ang), ay + L * math.sin(ang)
            if not t.inside(bx, by):
                continue
            # does the step properly cross the drawn polyline (clipped to the field)?
            crosses = False
            for (px, py), (qx, qy) in (((-50, 30), (7, 3)), ((7, 3), (190, 210))):
                d1 = (qx - px) * (ay - py) - (qy - py) * (ax - px)
                d2 = (qx - px) * (by - py) - (qy - py) * (bx - px)
                d3 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                d4 = (bx - ax) * (qy - ay) - (by - ay) * (qx - ax)
                if d1 * d2 < 0 and d3 * d4 < 0:
                    crosses = True
            if crosses:
                crossings += 1
                self.assertFalse(t.segment_passable(ax, ay, bx, by), (ax, ay, bx, by))
        self.assertGreater(crossings, 50)


class F2NoStallOnAFordRoute(unittest.TestCase):
    def test_codex_cases_arrive(self):
        ts = {"width": 100, "height": 100, "cell": 20,
              "stream": {"width": 1, "points": [[50, 0], [50, 100]]}, "fords": [[50, 50, 1]]}
        for start, extra in (((21, 22), {}), ((21, 2), {"arrival_tolerance": 20})):
            w = one_unit(ts, *start, 75, 2, overrides={"pace_jitter": 0.0, **extra})
            engine.run(w, 900)
            kinds = [e["kind"] for e in w.events]
            self.assertEqual(kinds.count("arrived"), 1, (start, kinds))

    def test_arrival_tolerance_only_at_the_final_target(self):
        ts = {"width": 100, "height": 100, "cell": 20,
              "stream": {"width": 1, "points": [[50, 0], [50, 100]]}, "fords": [[50, 50, 1]]}
        w = one_unit(ts, 21, 2, 75, 2, overrides={"pace_jitter": 0.0, "arrival_tolerance": 20})
        crossed_at_ford = False
        for _ in range(450):
            engine.step(w)
            e = w.entity(1)
            if abs(e.x - 50) < 10:
                crossed_at_ford |= w.terrain.ground_at(e.x, e.y) == FORD
        self.assertTrue(crossed_at_ford)


class F3F8ExactSight(unittest.TestCase):
    def test_codex_cases(self):
        t = build(width=240, height=80, woods=[[100, 40, 120, 60]])
        self.assertFalse(sight.line_of_sight(t, P, 11, 48.95, 2, 211, 28.95, 2))     # canopy corner clip
        t = build(width=60, height=20)
        t.elev[0, 1] = 2.1
        self.assertFalse(sight.line_of_sight(t, P, 10, 10, 2, 55, 10, 2))            # low crest between samples
        t = build(width=400, height=400, woods=[[100, 0, 120, 400]])
        self.assertFalse(sight.line_of_sight(t, P, 90, 10, 2, 350, 10, 2))           # screen beside an open observer
        self.assertFalse(sight.line_of_sight(t, P, 350, 10, 2, 90, 10, 2))

    def test_inside_a_wood_one_sees_out_nearby(self):
        t = build(width=400, height=400, woods=[[100, 0, 140, 400]])
        self.assertTrue(sight.line_of_sight(t, P, 135, 10, 1.7, 180, 10, 2))         # from inside, out through own wood
        self.assertTrue(sight.line_of_sight(t, P, 180, 10, 1.7, 135, 10, 2))         # into its edge, close up

    def test_exact_agrees_with_a_dense_oracle(self):
        """Exact visible must never be contradicted by a dense sample; exact blocked is
        confirmed by the dense sample except for near-grazing lines."""
        t = build(width=800, height=400, hills=[[400, 200, 25, 300], [650, 100, 12, 120]],
                  woods=[[200, 50, 260, 150], [500, 250, 540, 330]])
        rng = np.random.default_rng(11)
        n = 300
        ox, oy, tx, ty = rng.uniform(0, 800, n), rng.uniform(0, 400, n), rng.uniform(0, 800, n), rng.uniform(0, 400, n)
        exact = sight.visible_pairs(t, P, ox, oy, np.full(n, 1.7), tx, ty, np.full(n, 2.0))

        def dense(k):
            d = math.hypot(tx[k] - ox[k], ty[k] - oy[k])
            if d > P["sight_range_max"]:
                return False
            wo = t.ground_at(ox[k], oy[k]) == WOODS
            wt = t.ground_at(tx[k], ty[k]) == WOODS
            if (wo or wt) and d > P["sight_range_in_woods"]:
                return False
            z0 = t.height_at(ox[k], oy[k]) + 1.7
            z1 = t.height_at(tx[k], ty[k]) + 2.0
            m = max(2, int(d / 0.25))
            s = np.linspace(0, 1, m + 1)
            xs, ys = ox[k] + (tx[k] - ox[k]) * s, oy[k] + (ty[k] - oy[k]) * s
            g = t.height_at_many(xs, ys)
            wood = t.ground_at_many(xs, ys) == WOODS
            start = np.cumprod(wood).astype(bool) & wo
            end = np.cumprod(wood[::-1])[::-1].astype(bool) & wt
            g = g + np.where(wood & ~start & ~end, P["wood_canopy_height"], 0.0)
            return not (g[1:-1] > (z0 + (z1 - z0) * s)[1:-1] + 1e-9).any()

        disagree = [k for k in range(n) if exact[k] and not dense(k)]
        self.assertEqual(disagree, [], "exact says visible but a dense sample finds a block")
        self.assertTrue(exact.any() and not exact.all())


class F4ExactSegmentCells(unittest.TestCase):
    def test_symmetric_and_matches_oracle(self):
        t = build(width=200, height=200)
        rng = np.random.default_rng(5)
        cases = [(10, 30, 20, 20), (20, 1, 20, 19), (20, 20, 20, 20), (0, 0, 200, 200), (40, 40, 60, 20)]
        for _ in range(300):
            a = rng.uniform(0, 200, 2)
            b = a + rng.uniform(-60, 60, 2)
            if rng.random() < 0.3:
                a = np.round(a / 20) * 20                    # land on grid lines and corners often
            cases.append((*np.clip(a, 0, 200), *np.clip(b, 0, 200)))
        ny, nx = t.shape
        for ax, ay, bx, by in cases:
            fwd = set(terrain.cells_on_segment(t, ax, ay, bx, by))
            rev = set(terrain.cells_on_segment(t, bx, by, ax, ay))
            self.assertEqual(fwd, rev, (ax, ay, bx, by))
            oracle = {(i, j) for i in range(ny) for j in range(nx) if touches_oracle(t, ax, ay, bx, by, i, j)}
            self.assertEqual(fwd, oracle, (ax, ay, bx, by))


class F5Fords(unittest.TestCase):
    def test_ford_must_join_two_banks(self):
        with self.assertRaises(ValueError):          # stream does not cut the field, so the ford joins nothing
            build(width=200, height=200, stream={"width": 1, "points": [[50, 50], [150, 50]]}, fords=[[100, 50, 5]])

    def test_effective_opening_reported(self):
        t = build(width=100, height=100, stream={"width": 1, "points": [[50, 0], [50, 100]]}, fords=[[50, 50, 1]])
        openings = terrain.ford_openings(t)
        self.assertEqual(len(openings), 1)
        self.assertGreaterEqual(openings[0]["approx_width_m"], 20)


class F6F7Routes(unittest.TestCase):
    def test_shortening_never_costs_more(self):
        t = build(width=120, height=40, woods=[[0, 0, 60, 20], [0, 20, 20, 40]])
        st = {}
        pathing.plan(t, P, "formed", 10, 10, 110, 10, st)
        self.assertLessEqual(st["cost"], st["raw_cost"] + 1e-9)
        rng = np.random.default_rng(2)
        t = build(width=600, height=400, rough=[[100, 0, 200, 300]], woods=[[300, 100, 400, 400], [450, 0, 520, 200]])
        for _ in range(30):
            sx, sy, gx, gy = rng.uniform(1, 599), rng.uniform(1, 399), rng.uniform(1, 599), rng.uniform(1, 399)
            st = {}
            r = pathing.plan(t, P, "formed", sx, sy, gx, gy, st)
            self.assertIsNotNone(r)
            self.assertLessEqual(st["cost"], st["raw_cost"] + 1e-9)

    def test_every_leg_passable_and_on_the_field(self):
        t = build(width=41, height=100, stream={"width": 1, "points": [[0, 50], [39, 50]]})
        r = pathing.plan(t, P, "formed", 30, 30, 30, 70)
        self.assertIsNotNone(r)
        pts = [(30, 30)] + r
        for a, b in zip(pts, pts[1:]):
            self.assertTrue(t.inside(*b))
            self.assertTrue(t.segment_passable(*a, *b), (a, b))

    def test_off_field_start_or_goal_refused(self):
        t = build(width=100, height=100)
        with self.assertRaises(ValueError):
            pathing.plan(t, P, "formed", -1, 10, 50, 50)


class F9EngineOwnedRoutes(unittest.TestCase):
    def test_scenario_cannot_supply_a_route(self):
        s = json.loads((Path(__file__).resolve().parent.parent / "scenarios" / "test_field.json").read_text())
        s["entities"][0]["task"]["route"] = []
        with self.assertRaises(ValueError):
            scenario.load(write(s), 1)

    def test_new_target_replaces_the_route(self):
        w = one_unit({"width": 1000, "height": 1000, "cell": 20, "woods": [[400, 300, 600, 700]]}, 100, 500, 900, 500)
        engine.step(w, 5)
        e = w.entity(1)
        self.assertEqual(e.route_for, [900.0, 500.0])
        e.task = {"kind": "move_to", "x": 100.0, "y": 900.0}
        engine.step(w)
        self.assertEqual(e.route_for, [100.0, 900.0])
        engine.run(w, 1800)
        arrived = [ev for ev in w.events if ev["kind"] == "arrived"]
        self.assertEqual(arrived[-1]["data"]["target"], [100.0, 900.0])


class F10PlanningCost(unittest.TestCase):
    def test_shortening_checks_grow_linearly_on_winding_routes(self):
        checks = {}
        for n in (9, 15, 21):
            spec = {"width": 20 * n, "height": 20 * n, "cell": 20}
            t = build(**spec)
            for r in range(1, n, 2):                         # every odd row is stream with one gap
                t.ground[r, :] = STREAM
                t.ground[r, (n - 1) if (r // 2) % 2 == 0 else 0] = 0
            st = {}
            route = pathing.plan(t, P, "formed", 10, 10, 20 * n - 10, 20 * n - 10, st)
            self.assertIsNotNone(route)
            checks[n] = st["shorten_checks"] / st["raw_points"]
        self.assertLess(max(checks.values()), 3.0, checks)   # bounded checks per raw point


class F11Values(unittest.TestCase):
    def test_slope_lookahead_is_a_parameter(self):
        self.assertIn("slope_lookahead_m", params.PARAMS)


if __name__ == "__main__":
    unittest.main()
