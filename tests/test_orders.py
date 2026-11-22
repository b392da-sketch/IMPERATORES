"""Step 4 tests: orders, messengers, signals, plans and reports (specification 5.5, 7.1 check 4)."""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from imperatores import belief, engine, params, record, scenario
from imperatores.systems import command, perception

P = params.resolve()
TICK = P["tick_seconds"]


def write(s) -> Path:
    f = Path(tempfile.mkdtemp()) / "scenario.json"
    f.write_text(json.dumps(s))
    return f


def ent(i, side, x, y, function="heavy_infantry", mobility="foot", plan=None, task=None, strength=120):
    d = {"id": i, "side": side, "name": f"e{i}", "function": function, "x": x, "y": y, "frontage": 40,
         "depth": 15, "strength": strength, "equipment": {"reach": "sword", "mobility": mobility}}
    if plan:
        d["plan"] = plan
    if task:
        d["task"] = task
    return d


def world(entities, commanders, inputs=(), terrain=None, overrides=None, seed=1):
    s = {"name": "t", "terrain": terrain or {"width": 4000, "height": 3000, "cell": 20},
         "commanders": commanders, "entities": entities, "inputs": list(inputs)}
    w = scenario.load(write(s), seed, overrides)
    record.snapshot(w)
    return w


def army(cid=900, side="A", x=300, y=1500, commands=(1,)):
    return {"id": cid, "side": side, "name": f"c{cid}", "rank": "army", "x": x, "y": y, "commands": list(commands)}


def stages(w, oid):
    return [s[0] for s in w.orders[oid].stages]


def run_until(w, pred, max_s=3600):
    for _ in range(int(max_s / TICK)):
        if pred():
            return True
        engine.step(w)
    return pred()


class OrderLife(unittest.TestCase):
    def test_stages_in_order_and_the_entity_moves(self):
        w = world([ent(1, "A", 1500, 1500)], [army()],
                  [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "advance_to", "place": [2500, 1500]}}])
        self.assertTrue(run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status == "executed"))
        self.assertEqual(stages(w, "900.1"), ["decided", "sent", "delivered", "understood", "executed"])
        t = {s[0]: s[1] for s in w.orders["900.1"].stages}
        self.assertGreater(t["delivered"], t["sent"])
        ride = (t["delivered"] - t["sent"]) * TICK
        self.assertAlmostEqual(ride, (1200 - P["deliver_radius_m"]) / P["messenger_speed_horse"], delta=10)
        engine.step(w, 30)
        self.assertGreater(w.entity(1).x, 1500)
        self.assertEqual(w.entity(1).task.get("order"), "900.1")

    def test_further_away_arrives_later(self):
        def delay(x):
            w = world([ent(1, "A", x, 1500)], [army()],
                      [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}}])
            run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status == "executed")
            return w.orders["900.1"].stages[-1][1]
        self.assertGreater(delay(3000), delay(1000))

    def test_a_stream_makes_the_messenger_ride_round_by_the_ford(self):
        terr = {"width": 4000, "height": 3000, "cell": 20, "stream": {"width": 10, "points": [[1000, 0], [1000, 3000]]},
                "fords": [[1000, 2800, 40]]}
        def delay(terrain):
            w = world([ent(1, "A", 1500, 1500)], [army()],
                      [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}}], terrain=terrain)
            run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status == "executed")
            return w.orders["900.1"].stages[-1][1]
        self.assertGreater(delay(terr), delay(None) + 100)

    def test_no_messenger_free_means_waiting(self):
        inputs = [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}} for _ in range(3)]
        w = world([ent(1, "A", 2000, 1500)], [army()], inputs, overrides={"messengers_army": 2})
        engine.step(w)
        self.assertIn("waiting for a messenger", stages(w, "900.3"))
        self.assertNotIn("sent", stages(w, "900.3"))
        self.assertTrue(run_until(w, lambda: "sent" in stages(w, "900.3")))
        t_sent3 = [s[1] for s in w.orders["900.3"].stages if s[0] == "sent"][0]
        returned = [e["t"] for e in w.events if e["kind"] == "messenger_returned"]
        self.assertTrue(returned and t_sent3 >= min(returned))


class Failures(unittest.TestCase):
    def test_messenger_caught_by_enemy_horse(self):
        es = [ent(1, "A", 2500, 1500), ent(60, "B", 1400, 1520, function="light_cavalry", mobility="horse")]
        w = world(es, [army()], [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}}],
                  overrides={"intercept_per_min": 3.0, "intercept_mounted_factor": 4.0, "intercept_radius_m": 400.0})
        run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status in ("failed", "executed"))
        o = w.orders["900.1"]
        self.assertEqual(o.status, "failed")
        self.assertEqual(o.stages[-1][2]["why"], "messenger captured")
        self.assertEqual(w.entity(1).task, {"kind": "hold"})          # never received

    def test_recipient_not_where_expected_is_found_when_seen(self):
        es = [ent(1, "A", 1500, 1500, task={"kind": "move_to", "x": 1500, "y": 1800})]
        w = world(es, [army()], [{"at_s": 120, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}}])
        run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status in ("failed", "executed"))
        self.assertEqual(w.orders["900.1"].status, "executed")

    def test_recipient_out_of_sight_cannot_be_found(self):
        terr = {"width": 4000, "height": 3000, "cell": 20, "woods": [[2400, 1100, 3600, 2900]]}
        es = [ent(1, "A", 2000, 1500, task={"kind": "move_to", "x": 3000, "y": 2500})]
        w = world(es, [army()], [{"at_s": 600, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}}],
                  terrain=terr, overrides={"search_time_s": 60.0})
        run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status in ("failed", "executed"), 4000)
        o = w.orders["900.1"]
        self.assertEqual(o.status, "failed")
        self.assertEqual(o.stages[-1][2]["why"], "the messenger could not find the recipient")
        self.assertIn("messenger_searching", [e["kind"] for e in w.events])

    def test_target_not_identified(self):
        es = [ent(1, "A", 1000, 1500), ent(50, "B", 2600, 1500)]
        cmds = [army(x=1900, y=1500)]           # the commander can see the enemy body; the entity cannot (beyond 1.5 km)
        w = world(es, cmds, [{"at_s": 20, "order": {"issuer": 900, "recipient": 1, "kind": "attack",
                                                    "target": {"near": [2600, 1500], "side": "B"}}}])
        run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status in ("failed", "executed"))
        o = w.orders["900.1"]
        self.assertEqual(o.status, "failed")
        self.assertTrue(o.stages[-1][2]["why"].startswith("target not identified"))

    def test_misread_target(self):
        # the commander describes body 50; the recipient cannot see 50 but knows body 51 nearby, and takes it to mean 51
        terr = {"width": 4000, "height": 3000, "cell": 20, "woods": [[1500, 1300, 1700, 1460]]}
        es = [ent(1, "A", 1300, 1150), ent(50, "B", 1900, 1500), ent(51, "B", 1800, 1250)]
        w = world(es, [army(x=1600, y=1700)],
                  [{"at_s": 20, "order": {"issuer": 900, "recipient": 1, "kind": "attack",
                                          "target": {"near": [1900, 1500], "side": "B"}}}],
                  terrain=terr, overrides={"order_target_radius_m": 400.0})
        run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status in ("failed", "executed"))
        o = w.orders["900.1"]
        self.assertEqual(o.intended, 50)
        und = [s for s in o.stages if s[0] == "understood"]
        self.assertTrue(und, o.stages)
        self.assertEqual(und[0][2].get("misread"), {"meant": 50, "took": 51})

    def test_disordered_entity_waits_then_the_order_lapses(self):
        w = world([ent(1, "A", 1000, 1500)], [army()],
                  [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "advance_to", "place": [2000, 1500]}}],
                  overrides={"order_wait_timeout_s": 120.0, "order_recovery_per_min_halted": 0.0})
        w.entity(1).order = 0.1
        run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status in ("failed", "executed"))
        o = w.orders["900.1"]
        self.assertIn("waiting to execute", stages(w, "900.1"))
        self.assertEqual(o.status, "failed")
        self.assertIn("disordered", o.stages[-1][2]["why"])

    def test_disordered_entity_executes_once_reformed(self):
        w = world([ent(1, "A", 1000, 1500)], [army()],
                  [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "advance_to", "place": [2000, 1500]}}],
                  overrides={"order_recovery_per_min_halted": 0.02})
        w.entity(1).order = 0.25
        run_until(w, lambda: w.orders.get("900.1") and w.orders["900.1"].status in ("failed", "executed"))
        self.assertEqual(w.orders["900.1"].status, "executed")
        self.assertIn("waiting to execute", stages(w, "900.1"))


class Relay(unittest.TestCase):
    def test_wing_commander_relays_to_his_entities(self):
        cmds = [army(commands=(910,)), {"id": 910, "side": "A", "name": "wing", "rank": "wing", "x": 800, "y": 1000,
                                         "commands": [1, 2]}]
        es = [ent(1, "A", 1500, 900), ent(2, "A", 1500, 1100)]
        w = world(es, cmds, [{"at_s": 0, "order": {"issuer": 900, "recipient": 910, "kind": "withdraw_to", "place": [600, 1000]}}])
        run_until(w, lambda: all(o.status in ("executed", "failed") for o in w.orders.values()) and len(w.orders) == 3)
        relayed = [o for o in w.orders.values() if o.origin == "relay"]
        self.assertEqual(sorted(o.recipient for o in relayed), [1, 2])
        self.assertTrue(all(o.parent == "900.1" and o.status == "executed" for o in relayed))


class Signals(unittest.TestCase):
    def test_recall_heard_within_range_only(self):
        es = [ent(1, "A", 500, 1500, plan={"home": [400, 1500]}), ent(2, "A", 300 + P["signal_range_m"] + 300, 1500)]
        w = world(es, [army(commands=(1, 2))], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "recall"}}])
        engine.step(w)
        kinds = {(e["kind"], e["entity"]) for e in w.events}
        self.assertIn(("signal_heard", 1), kinds)
        self.assertIn(("signal_not_heard", 2), kinds)
        self.assertEqual(w.entity(1).task["kind"], "move_to")
        self.assertEqual((w.entity(1).task["x"], w.entity(1).task["y"]), (400.0, 1500.0))

    def test_a_hill_shortens_hearing_range(self):
        es = [ent(1, "A", 300 + 0.7 * P["signal_range_m"], 1500)]
        flat = world(es, [army()], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "recall"}}])
        hilly = world(es, [army()], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "recall"}}],
                      terrain={"width": 4000, "height": 3000, "cell": 20, "hills": [[580, 1500, 40, 200]]})
        for w in (flat, hilly):
            engine.step(w)
        self.assertIn("signal_heard", [e["kind"] for e in flat.events])
        self.assertIn("signal_not_heard", [e["kind"] for e in hilly.events])

    def test_unaddressed_units_ignore_unless_misattributed(self):
        es = [ent(1, "A", 500, 1500), ent(2, "A", 500, 1600)]
        for prob, expect in ((0.0, False), (0.5, True)):
            w = world(es, [army(commands=(1, 2))], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "recall", "to": [1]}}],
                      overrides={"signal_misattribution_prob": prob}, seed=4)
            engine.step(w)
            acted = ("signal_heard", 2) in {(e["kind"], e["entity"]) for e in w.events}
            if prob == 0.0:
                self.assertFalse(acted)
        # with probability 0.5, across seeds some unaddressed units act and some do not
        acted = []
        for seed in range(12):
            w = world(es, [army(commands=(1, 2))], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "recall", "to": [1]}}],
                      overrides={"signal_misattribution_prob": 0.5}, seed=seed)
            engine.step(w)
            acted.append(("signal_misattributed", 2) in {(e["kind"], e["entity"]) for e in w.events})
        self.assertTrue(any(acted) and not all(acted))

    def test_prearranged_cue_and_a_signal_without_meaning(self):
        plan = {"on": [{"when": {"signal": "action:reserve"}, "do": {"kind": "advance_to", "place": [1500, 1500]}}]}
        es = [ent(1, "A", 500, 1500, plan=plan), ent(2, "A", 500, 1700)]
        w = world(es, [army(commands=(1, 2))], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "action:reserve"}}])
        engine.step(w)
        self.assertEqual(w.entity(1).task["kind"], "move_to")
        self.assertIn(("signal_without_meaning", 2), {(e["kind"], e["entity"]) for e in w.events})

    def test_advance_is_flagged_as_an_extension(self):
        w = world([ent(1, "A", 500, 1500)], [army()], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "advance"}}])
        engine.step(w)
        ev = [e for e in w.events if e["kind"] == "signal_emitted"][0]
        self.assertTrue(ev["data"]["extension"])


class Plans(unittest.TestCase):
    def test_condition_fires_only_on_what_the_officer_has_seen(self):
        plan = {"on": [{"when": {"enemy_within": [2000, 1500, 400]}, "do": {"kind": "withdraw_to", "place": [600, 1500]}}]}
        hidden = {"width": 4000, "height": 3000, "cell": 20, "hills": [[1500, 1500, 40, 500]]}
        es = [ent(1, "A", 1000, 1500, plan=plan), ent(50, "B", 2000, 1500)]
        w = world(es, [], terrain=hidden)
        engine.step(w, 30)
        self.assertNotIn("plan_triggered", [e["kind"] for e in w.events])   # enemy there, but unseen
        w2 = world(es, [])                                                   # flat: seen
        engine.step(w2, 30)
        self.assertIn("plan_triggered", [e["kind"] for e in w2.events])
        self.assertEqual(w2.entity(1).task["kind"], "move_to")

    def test_time_condition(self):
        plan = {"on": [{"when": {"after_s": 60}, "do": {"kind": "advance_to", "place": [1500, 1500]}}]}
        w = world([ent(1, "A", 1000, 1500, plan=plan)], [])
        engine.step(w, 29)
        self.assertEqual(w.entity(1).task["kind"], "hold")
        engine.step(w, 2)
        self.assertEqual(w.entity(1).task["kind"], "move_to")


class Reports(unittest.TestCase):
    def test_report_carries_the_senders_picture_as_it_was(self):
        es = [ent(1, "A", 2000, 1500), ent(50, "B", 2800, 1500)]
        terr = {"width": 4000, "height": 3000, "cell": 20, "hills": [[1300, 1500, 40, 300]]}
        w = world(es, [army(x=300, y=1500)], [{"at_s": 10, "report": {"sender": 1, "recipient": 900}}], terrain=terr)
        engine.step(w, 6)
        self.assertIsNone(belief.handle_of(w.beliefs[900], 50))              # the commander cannot see it
        run_until(w, lambda: "report_delivered" in [e["kind"] for e in w.events], 2000)
        reported = [c for c in w.beliefs[900].tracks.values() if c.side == "B"]
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0].source, "report")
        self.assertEqual(reported[0].report_from, 1)


class Integrity(unittest.TestCase):
    def test_attack_moves_on_belief_not_truth(self):
        es = [ent(1, "A", 1000, 1500), ent(50, "B", 1800, 1500)]
        terr = {"width": 4000, "height": 3000, "cell": 20}
        w = world(es, [army(x=1000, y=1600)], [{"at_s": 20, "order": {"issuer": 900, "recipient": 1, "kind": "attack",
                                                                        "target": {"near": [1800, 1500], "side": "B"}}}],
                  terrain=terr)
        run_until(w, lambda: w.entity(1).task.get("kind") == "approach")
        h = w.entity(1).task["handle"]
        believed = w.beliefs[1].tracks[h]
        w.entity(50).x = 3900.0                  # the enemy leaves; the officer last saw it at 1800 until he looks again
        perception_every = perception._interval_ticks(P)
        while w.tick % perception_every:         # move only between looks
            engine.step(w)
        self.assertLessEqual(abs(w.entity(1).task["x"] - believed.x), 100)

    def test_replay_exact_with_orders_and_messengers(self):
        def run():
            es = [ent(1, "A", 2500, 1500), ent(2, "A", 2500, 1800), ent(60, "B", 1400, 1600, function="light_cavalry", mobility="horse")]
            w = world(es, [army(commands=(1, 2))],
                      [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}},
                       {"at_s": 0, "order": {"issuer": 900, "recipient": 2, "kind": "advance_to", "place": [3000, 1800]}},
                       {"at_s": 30, "signal": {"issuer": 900, "meaning": "recall"}}], seed=7)
            engine.run(w, 900)
            return w
        a, b = run(), run()
        self.assertEqual(record.digest(a), record.digest(b))
        json.dumps(record.to_json(a), allow_nan=False)

    def test_one_orders_fate_does_not_shift_anothers(self):
        """Paired intervention: adding a second order (its own messenger and draws) leaves the
        first messenger's ride and the first order's stages unchanged."""
        es = [ent(1, "A", 2500, 1500), ent(2, "A", 2500, 2500), ent(60, "B", 1400, 1600, function="light_cavalry", mobility="horse")]
        one = [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}}]
        two = one + [{"at_s": 0, "order": {"issuer": 910, "recipient": 2, "kind": "hold"}}]
        cmds = [army(commands=(1,)), {"id": 910, "side": "A", "name": "w", "rank": "wing", "x": 300, "y": 2500, "commands": [2]}]
        a, b = world(es, cmds, one, seed=3), world(es, cmds, two, seed=3)
        for w in (a, b):
            engine.run(w, 900)
        self.assertEqual(a.orders["900.1"].stages, b.orders["900.1"].stages)


class Loading(unittest.TestCase):
    def test_bad_inputs_and_plans_refused(self):
        bad = [
            ([ent(1, "A", 500, 1500)], [army()], [{"at_s": 0, "order": {"issuer": 900, "recipient": 99, "kind": "hold"}}]),
            ([ent(1, "A", 500, 1500)], [army()], [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "dance"}}]),
            ([ent(1, "A", 500, 1500)], [army()], [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "attack"}}]),
            ([ent(1, "A", 500, 1500)], [army()], [{"at_s": 0, "signal": {"issuer": 1, "meaning": "recall"}}]),
            ([ent(1, "A", 500, 1500)], [army()], [{"at_s": 0, "signal": {"issuer": 900, "meaning": "charge!"}}]),
            ([ent(1, "A", 500, 1500, plan={"on": [{"when": {"moon": 1}, "do": {"kind": "hold"}}]})], [army()], []),
            ([ent(1, "A", 500, 1500, plan={"home": [-5, 0]})], [army()], []),
        ]
        for es, cmds, inputs in bad:
            with self.assertRaises((ValueError, KeyError)):
                world(es, cmds, inputs)


if __name__ == "__main__":
    unittest.main()
