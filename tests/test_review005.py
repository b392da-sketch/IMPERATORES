"""Regression tests for Codex review 005 (step 4: orders, messengers, signals and plans).

Each test is marked with the finding it covers. Fixtures follow the review's reproductions.
"""
from __future__ import annotations

import unittest

from imperatores import belief, engine, orders as om, params, record
from imperatores.systems import command, messengers, movement
from tests.test_orders import army, ent, run_until, stages, world

P = params.resolve()
TICK = P["tick_seconds"]
STREAM = {"width": 1000, "height": 1000, "cell": 20, "stream": {"width": 1, "points": [[450, 0], [450, 1000]]}}


def order(i, r, kind="hold", at=0, **k):
    return {"at_s": at, "order": {"issuer": i, "recipient": r, "kind": kind, **k}}


def terminal_stages(o):
    return [s for s in o.stages if s[0] in om.TERMINAL]


class Authority(unittest.TestCase):
    def test_codex_005_1_orders_need_authority(self):
        """Codex 005/1: an enemy, or a unit outside the issuer's command, cannot be ordered."""
        with self.assertRaises(ValueError):
            world([ent(1, "B", 310, 1500)], [army(commands=())], [order(900, 1, "advance_to", place=[900, 1500])])
        with self.assertRaises(ValueError):          # same side, but not his to command
            world([ent(1, "A", 310, 1500), ent(2, "A", 310, 1700)], [army(commands=(1,))], [order(900, 2)])
        with self.assertRaises(ValueError):          # a report to an enemy commander
            world([ent(1, "A", 310, 1500)], [army(), army(cid=950, side="B", commands=())],
                  [{"at_s": 0, "report": {"sender": 1, "recipient": 950}}])
        w = world([ent(1, "A", 500, 1500), ent(2, "B", 600, 1500)], [army()])
        with self.assertRaises(ValueError):          # the runtime API checks too
            command.issue(w, 900, 2, {"kind": "hold"}, "input", key=(900, 9, 0), oid="x")

    def test_codex_005_1_riders_go_to_where_the_sender_believes(self):
        """Codex 005/1: an unseen friendly unit's live position is never read; the rider goes to
        its home in the plan until the sender has a more recent track of it."""
        w = world([ent(1, "A", 500, 1500)], [army()])
        command.belief_mod_ensure(w)
        self.assertEqual(command.believed_position(w, 900, 1), (500.0, 1500.0))
        w.entity(1).x = 800.0                        # moved, unseen
        self.assertEqual(command.believed_position(w, 900, 1), (500.0, 1500.0))


class Supersession(unittest.TestCase):
    def _disordered(self, inputs, **ov):
        w = world([ent(1, "A", 500, 1500)], [army()], inputs,
                  overrides={"order_recovery_per_min_halted": 0.0, **ov})
        w.entity(1).order = 0.1
        return w

    def test_codex_005_2_a_later_order_supersedes_a_waiting_one(self):
        """Codex 005/2: the displaced order ends, once, with a link to its replacement."""
        w = self._disordered([order(1, 1, "advance_to", place=[900, 1500]), order(1, 1)])
        engine.step(w, 400)
        a, b = w.orders["1.1"], w.orders["1.2"]
        self.assertEqual(a.status, "failed")
        self.assertEqual(a.stages[-1][2]["why"], "superseded by a later order")
        self.assertEqual(a.stages[-1][2]["superseded_by"], "1.2")
        self.assertEqual(b.status, "executed")
        self.assertEqual(w.pending, {})
        for o in (a, b):
            self.assertEqual(len(terminal_stages(o)), 1)

    def test_codex_005_2_two_messengers_in_one_tick(self):
        w = self._disordered([order(900, 1, "advance_to", place=[900, 1500]),
                              order(900, 1, "advance_to", place=[900, 1600])])
        run_until(w, lambda: len(w.orders) == 2 and all(o.status in om.TERMINAL for o in w.orders.values()), 2000)
        self.assertEqual(w.orders["900.1"].stages[-1][2].get("superseded_by"), "900.2")
        self.assertEqual(w.orders["900.2"].status, "failed")              # it then lapses: still disordered
        self.assertIn("disordered", w.orders["900.2"].stages[-1][2]["why"])

    def test_codex_005_2_a_signal_supersedes_a_waiting_order(self):
        w = self._disordered([order(900, 1, "advance_to", place=[900, 1500]),
                              {"at_s": 120, "signal": {"issuer": 900, "meaning": "recall"}}])
        engine.step(w, 61)
        self.assertEqual(w.orders["900.1"].status if "900.1" in w.orders else None, "failed")
        self.assertEqual(w.orders["900.1"].stages[-1][2].get("superseded_by"), "900.s1>1")

    def test_codex_005_2_destruction_ends_a_waiting_order(self):
        w = self._disordered([order(1, 1, "advance_to", place=[900, 1500])])
        engine.step(w)
        self.assertIn(1, w.pending)
        e = w.entity(1)
        e.dead, e.fit = e.fit, 0
        engine.step(w)
        self.assertEqual(w.orders["1.1"].status, "failed")
        self.assertEqual(w.orders["1.1"].stages[-1][2]["why"], "the entity has no men left fit")


class Stranding(unittest.TestCase):
    def test_codex_005_3_an_unreachable_recipient_ends_the_ride(self):
        """Codex 005/3: riders who cannot reach a visible recipient give up and come home; the
        queue drains; nothing waits for ever."""
        w = world([ent(1, "A", 510, 500)], [army(x=390, y=500)], [order(900, 1)] * 3, terrain=STREAM,
                  overrides={"messengers_army": 2, "search_time_s": 60.0})
        engine.step(w, 350)
        self.assertEqual([o.status for o in w.orders.values()], ["failed"] * 3)
        self.assertTrue(all(o.stages[-1][2]["why"] == "the messenger could not reach the recipient"
                            for o in w.orders.values()))
        self.assertEqual(w.staff[900], 2)
        self.assertTrue(all(ms.status == "home" for ms in w.messengers))

    def test_codex_005_3_a_used_up_route_is_replanned(self):
        w = world([ent(1, "A", 500, 1500)], [army()], [order(900, 1)],
                  overrides={"deliver_radius_m": 10.0, "messenger_loss_per_km": 0.0})
        engine.step(w)
        w.entity(1).x = 515.0
        engine.step(w, 100)
        self.assertEqual(w.orders["900.1"].status, "executed")

    def test_codex_005_3_no_messengers_left(self):
        """Every rider caught: the rest of the queue fails at once, and staff is conserved."""
        es = [ent(1, "A", 2500, 1500)] + [ent(60 + k, "B", 400, 1480 + 10 * k, function="light_cavalry",
                                              mobility="horse") for k in range(4)]
        w = world(es, [army()], [order(900, 1)] * 3,
                  overrides={"messengers_army": 2, "intercept_per_min": 3.0, "intercept_mounted_factor": 4.0})
        run_until(w, lambda: len(w.orders) == 3 and all(o.status in om.TERMINAL for o in w.orders.values()), 600)
        whys = [o.stages[-1][2]["why"] for o in w.orders.values()]
        self.assertEqual(whys.count("messenger captured"), 2)
        self.assertIn("no messengers left to carry it", whys)
        self.assertEqual(command.staff_problems(w), [])

    def test_codex_005_3_a_rider_with_no_way_back_is_stranded(self):
        w = world([ent(1, "A", 510, 500)], [army(x=390, y=500)], [order(900, 1)], terrain=STREAM,
                  overrides={"search_time_s": 60.0})
        engine.step(w)
        ms = w.messengers[0]
        ms.status, ms.x, ms.y, ms.route = "returning", 520.0, 500.0, None
        engine.step(w, 40)
        self.assertEqual(ms.status, "stranded")
        self.assertEqual(w.staff[900] + 1, w.staff_initial[900])
        self.assertEqual(command.staff_problems(w), [])


class Handoff(unittest.TestCase):
    def test_codex_005_4_no_delivery_across_a_barrier(self):
        w = world([ent(1, "A", 461, 500)], [army(x=439, y=500)], [order(900, 1)], terrain=STREAM,
                  overrides={"search_time_s": 60.0})
        engine.step(w)
        self.assertNotEqual(w.orders["900.1"].status, "executed")
        engine.step(w, 60)
        self.assertEqual(w.orders["900.1"].status, "failed")

    def test_codex_005_4_interception_comes_before_handoff(self):
        """A rider caught in the tick he would hand over never delivers."""
        caught = 0
        for seed in range(12):
            es = [ent(1, "A", 310, 1500)] + [ent(60 + k, "B", 300, 1490 + 5 * k, function="light_cavalry",
                                                 mobility="horse") for k in range(3)]
            w = world(es, [army()], [order(900, 1)], seed=seed,
                      overrides={"intercept_per_min": 3.0, "intercept_mounted_factor": 4.0})
            engine.step(w)
            if w.messengers[0].status == "captured":
                caught += 1
                self.assertEqual(w.orders["900.1"].status, "failed")
                self.assertNotIn("delivered", stages(w, "900.1"))
            else:
                self.assertEqual(w.orders["900.1"].status, "executed")
        self.assertGreater(caught, 0)

    def test_codex_005_4_a_dead_commander_receives_nothing(self):
        cmds = [army(x=500, commands=(910,)), {"id": 910, "side": "A", "name": "w", "rank": "wing", "x": 500, "y": 1500,
                                               "commands": [1]}]
        w = world([ent(1, "A", 500, 1500)], cmds, [order(900, 910)])
        w.commander(910).alive = False
        engine.step(w, 3)
        self.assertEqual(w.orders["900.1"].status, "failed")
        self.assertEqual(w.orders["900.1"].stages[-1][2]["why"], "the recipient is dead")
        self.assertEqual(len(w.orders), 1)                               # nothing relayed

    def test_codex_005_4_a_dead_issuer_sends_nothing(self):
        w = world([ent(1, "A", 2000, 1500)], [army()], [order(900, 1, at=10)])
        w.commander(900).alive = False
        engine.step(w, 10)
        self.assertEqual(w.orders["900.1"].status, "failed")
        self.assertEqual(w.messengers, [])


class ApproachRoute(unittest.TestCase):
    def test_codex_005_5_a_small_belief_update_near_arrival(self):
        w = world([ent(1, "A", 500, 1500)], [], overrides={"pace_jitter": 0.0})
        command.belief_mod_ensure(w)
        h = belief.apply_sighting(w, 1, 99, "B", "foot", 550.0, 1500.0, 1.0, 100, None, None, False)
        w.entity(1).task = {"kind": "approach", "handle": h, "standoff": 30.0}
        movement.step(w)
        belief.apply_sighting(w, 1, 99, "B", "foot", 570.0, 1500.0, 1.0, 100, None, None, False)
        for _ in range(40):
            movement.step(w)
        self.assertAlmostEqual(w.entity(1).x, 540.0, delta=P["arrival_tolerance"] + 1e-6)
        self.assertIn("closed_on_target", [e["kind"] for e in w.events])


class Lifecycle(unittest.TestCase):
    def test_codex_005_6_delivery_is_idempotent(self):
        w = world([ent(1, "A", 500, 1500)], [army(x=500)], [order(900, 1)])
        engine.step(w)
        self.assertFalse(command.deliver(w, w.messengers[0].message))
        self.assertEqual(stages(w, "900.1"), ["decided", "sent", "delivered", "understood", "executed"])

    def test_codex_005_6_illegal_transitions_raise(self):
        w = world([ent(1, "A", 500, 1500)], [army(x=500)], [order(900, 1)])
        engine.step(w)
        with self.assertRaises(RuntimeError):
            om.transition(w, w.orders["900.1"], "delivered")

    def test_codex_005_6_no_executed_without_a_route(self):
        with self.assertRaises(ValueError):                              # off the field: refused at load
            world([ent(1, "A", 500, 1500)], [], [order(1, 1, "advance_to", place=[-1, 1500])])
        w = world([ent(1, "A", 300, 500)], [], [order(1, 1, "advance_to", place=[700, 500])], terrain=STREAM)
        engine.step(w)
        o = w.orders["1.1"]
        self.assertEqual(o.status, "failed")
        self.assertEqual(o.stages[-1][2]["why"], "no route to the place")
        self.assertEqual(w.entity(1).task, {"kind": "hold"})


class Identity(unittest.TestCase):
    def _after_gap(self, tid):
        w = world([ent(1, "A", 500, 1500)], [])
        command.belief_mod_ensure(w)
        belief.apply_sighting(w, 1, 50, "B", "foot", 900.0, 1500.0, 10.0, 100, None, None, False)
        w.tick += int(P["track_gap_s"] / TICK) + 5
        return w, belief.apply_sighting(w, 1, tid, "B", "foot", 901.0, 1500.0, 10.0, 100, None, None, False)

    def test_codex_005_7_identical_sightings_give_identical_handles(self):
        """Codex 005/7: the paired identity swap. Same observations, different hidden ids."""
        (wa, ha), (wb, hb) = self._after_gap(50), self._after_gap(51)
        self.assertEqual(ha, hb)
        self.assertEqual([c for c in belief.view(wa, 1).contacts], [c for c in belief.view(wb, 1).contacts])

    def test_codex_005_7_a_merged_track_is_followed(self):
        w = world([ent(1, "A", 500, 1500)], [])
        command.belief_mod_ensure(w)
        h1 = belief.apply_sighting(w, 1, 50, "B", "foot", 900.0, 1500.0, 10.0, 100, None, None, False)
        w.entity(1).task = {"kind": "approach", "handle": h1, "standoff": 30.0}
        w.tick += int(P["track_gap_s"] / TICK) + 5
        h2 = belief.apply_sighting(w, 1, 50, "B", "foot", 2000.0, 1500.0, 10.0, 100, None, None, False)
        self.assertNotEqual(h1, h2)
        belief.apply_sighting(w, 1, 50, "B", "heavy_infantry", 2000.0, 1500.0, 10.0, 100, None, None, True)
        self.assertNotIn(h1, w.beliefs[1].tracks)
        self.assertEqual(belief.resolve(w.beliefs[1], h1), h2)
        movement.step(w)
        self.assertEqual(w.entity(1).task["handle"], h2)
        self.assertIn("target_track_merged", [e["kind"] for e in w.events])


class Replay(unittest.TestCase):
    def test_codex_005_8_audit_details_and_counters_are_covered(self):
        w = world([ent(1, "A", 500, 1500)], [army(x=500)], [order(900, 1, "advance_to", place=[900, 1500])])
        engine.step(w)
        d0 = record.digest(w)
        w.orders["900.1"].stages[0][2]["origin"] = "changed"
        self.assertNotEqual(record.digest(w), d0)
        s0 = record.state_bytes(w)
        w.seq[(900, "order")] += 1
        self.assertNotEqual(record.state_bytes(w), s0)

    def test_codex_005_8_queued_content_is_covered(self):
        def queued(kind):
            w = world([ent(1, "A", 2500, 1500)], [army()], [order(900, 1)] * 2 + [order(900, 1, kind, place=[2600, 1500])]
                      if kind != "hold" else [order(900, 1)] * 3, overrides={"messengers_army": 2})
            engine.step(w)
            return record.state_bytes(w)
        self.assertNotEqual(queued("hold"), queued("advance_to"))


class SignalBinding(unittest.TestCase):
    def test_codex_005_9_cavalry_engage_binds_only_mounted_troops(self):
        plan = {"on": [{"when": {"signal": "cavalry_engage"}, "do": {"kind": "advance_to", "place": [700, 1500]}}]}
        es = [ent(1, "A", 500, 1500, plan=plan),
              ent(2, "A", 500, 1600, function="light_cavalry", mobility="horse", plan=plan)]
        w = world(es, [army(commands=(1, 2))], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "cavalry_engage"}}])
        engine.step(w)
        self.assertEqual(w.entity(1).task["kind"], "hold")
        self.assertIn(("signal_not_applicable", 1), {(e["kind"], e["entity"]) for e in w.events})
        self.assertEqual(w.entity(2).task["kind"], "move_to")

    def test_codex_005_9_only_own_commanders_bind_unless_the_plan_names_the_emitter(self):
        cue = {"when": {"signal": "action:go"}, "do": {"kind": "advance_to", "place": [700, 1500]}}
        for named, expect in ((None, "hold"), ([950], "move_to")):
            entry = dict(cue, **({"from": named} if named else {}))
            es = [ent(1, "A", 500, 1500, plan={"on": [entry]}), ent(2, "A", 500, 1700)]
            cmds = [army(commands=(1,)), army(cid=950, x=400, y=1600, commands=(2,))]
            w = world(es, cmds, [{"at_s": 0, "signal": {"issuer": 950, "meaning": "action:go", "to": [2]}}],
                      overrides={"signal_misattribution_prob": 0.5}, seed=0)
            # force the misattribution path for entity 1 by checking every seed until it hears it
            for seed in range(30):
                w = world(es, cmds, [{"at_s": 0, "signal": {"issuer": 950, "meaning": "action:go", "to": [2]}}],
                          overrides={"signal_misattribution_prob": 0.5}, seed=seed)
                engine.step(w)
                if ("signal_heard", 1) in {(e["kind"], e["entity"]) for e in w.events}:
                    break
            else:
                self.fail("entity 1 never heard the signal")
            self.assertEqual(w.entity(1).task["kind"], expect, named)
            if named is None:
                self.assertIn(("signal_ignored", 1), {(e["kind"], e["entity"]) for e in w.events})

    def test_codex_005_9_recall_home_is_the_deployment_position(self):
        es = [ent(1, "A", 500, 1500, task={"kind": "move_to", "x": 700, "y": 1500})]
        w = world(es, [army()], [{"at_s": 60, "signal": {"issuer": 900, "meaning": "recall"}}])
        engine.step(w, 31)
        self.assertEqual((w.entity(1).task["kind"], w.entity(1).task["x"], w.entity(1).task["y"]),
                         ("move_to", 500.0, 1500.0))

    def test_codex_005_9_a_destroyed_addressee_is_recorded(self):
        w = world([ent(1, "A", 500, 1500)], [army()], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "recall"}}])
        e = w.entity(1)
        e.dead, e.fit = e.fit, 0
        engine.step(w)
        self.assertIn(("signal_not_received", 1), {(ev["kind"], ev["entity"]) for ev in w.events})


class Keys(unittest.TestCase):
    def test_codex_005_10_an_unrelated_signal_leaves_a_riders_draws_alone(self):
        def run(extra):
            es = [ent(1, "A", 2500, 1500), ent(60, "B", 1400, 1600, function="light_cavalry", mobility="horse")]
            w = world(es, [army()], [order(900, 1)] + extra, seed=1)
            engine.run(w, 600)
            return w
        a = run([])
        b = run([{"at_s": 0, "signal": {"issuer": 900, "meaning": "advance", "to": []}}])
        self.assertEqual(a.messengers[0].key, b.messengers[0].key)
        self.assertEqual(a.orders["900.1"].stages, b.orders["900.1"].stages)


class CommandGraph(unittest.TestCase):
    def test_codex_005_11_cycles_and_duplicates_refused(self):
        wing = {"id": 910, "side": "A", "name": "w", "rank": "wing", "x": 300, "y": 1000, "commands": [900]}
        bad = [
            [army(commands=(910,)), wing],                                            # cycle (and a wing commanding an army)
            [army(commands=(1, 1))],                                                   # the same id twice
            [army(commands=(1,)), army(cid=950, commands=(1,))],                       # two commanders for one unit
            [army(commands=(910,)), dict(wing, rank="army", commands=[1])],            # army commanding an army
        ]
        for cmds in bad:
            with self.assertRaises(ValueError):
                world([ent(1, "A", 500, 1500)], cmds)


if __name__ == "__main__":
    unittest.main()
