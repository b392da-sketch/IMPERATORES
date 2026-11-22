"""Regression tests for Codex review 006 (step 5: decisions). Each test names its finding."""
from __future__ import annotations

import json
import unittest
from types import MappingProxyType
from unittest import mock

import numpy as np

from imperatores import belief, decisions as dm, engine, params, record, scenario
from imperatores.systems import command, decide, perception
from tests.test_beliefs import FIELD, HIDDEN, spec, write
from tests.test_decisions import PK, contact, officer_ctx
from tests.test_orders import army, ent, world

P = params.resolve()
FLAT = {"width": 2000, "height": 2000, "cell": 20}
WALL = {"width": 2000, "height": 2000, "cell": 20, "stream": {"width": 1, "points": [[1000, 0], [1000, 2000]]}}


def force(name_prefix):
    """Make the next decision choose the first option whose name starts with `name_prefix`."""
    real = dm.choose

    def pick(opts, temperature, u):
        i, probs = real(opts, temperature, u)
        for k, o in enumerate(opts):
            if o.name.startswith(name_prefix):
                return k, probs
        raise AssertionError(f"no option {name_prefix}: {[o.name for o in opts]}")
    return mock.patch.object(dm, "choose", pick)


def army_ctx(done=()):
    subs = (dm.SubView(1, 1000, 1000, 120, 0, (1000, 1000)), dm.SubView(2, 2000, 1000, 120, 0, (2000, 1000)))
    return dm.Context(owner=900, rank="army", side="A", tick=100, tick_s=2.0, tendencies=dm.PROFILES["by_the_book"],
                      profile="by_the_book", own=MappingProxyType({"x": 500, "y": 1000, "side": "A"}),
                      contacts=(contact(1, 1100, 1000, strength=250), contact(2, 2100, 1000, strength=120)),
                      home=(500, 1000), trigger="scan", subs=subs, done=done, params=PK)


class SelfTargets(unittest.TestCase):
    def test_codex_006_1_the_chosen_track_is_the_one_attacked(self):
        w = world([ent(1, "A", 1000, 1000)], [], terrain=FLAT)
        command.belief_mod_ensure(w)
        for t in (50, 51):                               # two bodies the officer cannot tell apart
            belief.apply_sighting(w, 1, t, "B", "foot", 1100.0, 1000.0, 5.0, 100, None, None, False)
        with force("attack:2"):
            rec = decide.make(w, 1, "routine")
        o = w.orders[rec["links"][0]["order"]]
        self.assertEqual(rec["chosen"], "attack:2")
        self.assertEqual(o.understood_handle, 2)
        self.assertEqual(w.entity(1).task["handle"], 2)

    def test_codex_006_1_a_vanished_choice_fails_visibly(self):
        w = world([ent(1, "A", 1000, 1000)], [], terrain=FLAT)
        command.belief_mod_ensure(w)
        h = belief.apply_sighting(w, 1, 50, "B", "foot", 1100.0, 1000.0, 5.0, 100, None, None, False)
        spec_ = {"kind": "attack", "target": belief.view(w, 1).contact(h)}
        spec_["target"] = command.om.TargetDescription("B", "foot", 1100.0, 1000.0, 0)
        del w.beliefs[1].tracks[h]
        o = command.issue(w, 1, 1, spec_, "decision", key=(1, 1, 99, 0), oid="t", parent="d1.0", own_handle=h)
        self.assertEqual(o.status, "failed")
        self.assertEqual(o.stages[-1][2]["why"], "the body he chose is no longer in his picture")


class Commitments(unittest.TestCase):
    def _field(self):
        es = [ent(1, "A", 500, 1500), ent(2, "A", 1500, 1500), ent(50, "B", 600, 1500, strength=300)]
        w = world(es, [army(x=300, y=1500, commands=(1, 2))], terrain=WALL,
                  overrides={"search_time_s": 60.0, "messenger_loss_per_km": 0.0})
        command.belief_mod_ensure(w)
        perception.step(w)                               # the commander sees the enemy; no one has decided yet
        return w

    def test_codex_006_2_news_of_failure_frees_the_reserve(self):
        w = self._field()
        with force("reinforce:2>1"):
            rec = decide.make(w, 900, "test")
        oid = rec["links"][0]["order"]
        self.assertIn(2, decide._context(w, 900, "x").committed)
        engine.step(w, 60)
        self.assertEqual(w.orders[oid].status, "failed")
        news = [e for e in w.events if e["kind"] == "news_of_failure"]
        self.assertEqual(news[0]["data"]["order"], oid)
        # freed by the news, the reserve can be sent again, and here it is
        later = [d for d in w.decisions.values() if d["owner"] == 900 and d["t"] >= news[0]["t"]]
        self.assertIn("reinforce:2>1", [d["chosen"] for d in later])
        self.assertTrue(all(e[2] != oid for e in w.deciders[900]["committed"]))

    def test_codex_006_2_without_news_the_commitment_lapses(self):
        w = self._field()
        with force("reinforce:2>1"):
            decide.make(w, 900, "test")
        w.deciders[900]["committed"][0][2] = "never-heard-of"     # as if the rider never came back
        w.deciders[900]["done"][0][2] = "never-heard-of"
        w.tick += int(P["commitment_review_s"] / P["tick_seconds"])
        ctx = decide._context(w, 900, "x")
        self.assertEqual((ctx.committed, ctx.done), ((), ()))


class Latitude(unittest.TestCase):
    def test_codex_006_3_another_target_is_beyond_a_strict_attack_order(self):
        o = dm.OrderView("o", "attack", "strict", 900, target_handle=1)
        opts = {x.name: x for x in dm.officer_options(officer_ctx("bold", [contact(1, 1200, 1000), contact(2, 1300, 1000)],
                                                                   standing=o))[0]}
        self.assertFalse(opts["attack:1"].beyond_orders)
        self.assertTrue(opts["attack:2"].beyond_orders)
        self.assertLess(opts["attack:2"].components["deviation"], 0)

    def test_codex_006_3_beyond_orders_is_recorded_even_at_zero_cost(self):
        pk = MappingProxyType({**PK, "latitude_cost_free": 0.0})
        o = dm.OrderView("o", "hold", "free", 900)
        ctx = officer_ctx("bold", [contact(1, 1200, 1000, strength=60)], standing=o)
        ctx = dm.Context(**{**ctx.__dict__, "params": pk})
        opts = {x.name: x for x in dm.officer_options(ctx)[0]}
        self.assertTrue(opts["attack:1"].beyond_orders)
        self.assertEqual(opts["attack:1"].components["deviation"], 0.0)


class Receipt(unittest.TestCase):
    def test_codex_006_4_receipt_scores_the_track_he_understood(self):
        far_described = dm.OrderView("o", "attack", "normal", 900, target_at=(1250, 1000), target_handle=2)
        at_track = dm.OrderView("o", "attack", "normal", 900, target_at=(1800, 1000), target_handle=2)
        c = [contact(2, 1800, 1000, strength=300)]
        a = dm.receipt_options(officer_ctx(contacts=c, received=far_described))[0][0].components["risk"]
        b = dm.receipt_options(officer_ctx(contacts=c, received=at_track))[0][0].components["risk"]
        self.assertLess(a, 0)
        self.assertEqual(a, b)


class Facing(unittest.TestCase):
    def test_codex_006_5_face_turns_to_the_flank_threat_and_is_rescored(self):
        ctx = officer_ctx(contacts=[contact(1, 1150, 1000, strength=400), contact(2, 1000, 1200, strength=120)])
        opts = {o.name: o for o in dm.officer_options(ctx)[0]}
        face = opts["face"]
        self.assertEqual(face.actions[0]["spec"]["toward"], [1000, 1200])
        heading = np.arctan2(200, 0)
        self.assertAlmostEqual(face.components["exposure"], -dm.exposure_at(ctx, heading) * (1 - ctx.tendencies.risk))
        # turning north puts the big frontal body on his flank: worse than staying as he is
        self.assertLess(face.components["exposure"], opts["continue"].components["exposure"])


class Interrupts(unittest.TestCase):
    def test_codex_006_6_threatened_units_come_from_the_unfiltered_picture(self):
        self.assertEqual(decide._hot(army_ctx()), [1, 2])
        self.assertEqual(decide._hot(army_ctx(done=("withdraw:1", "recall"))), [1, 2])


class Records(unittest.TestCase):
    def test_codex_006_7_a_decision_can_be_rebuilt_from_its_record(self):
        """Round trip: the record alone reproduces the menu, scores, probabilities, actions and choice."""
        cmds = [dict(army(x=600, y=1500, commands=(1, 2)), profile="bold")]
        es = [ent(1, "A", 1200, 1500), ent(2, "A", 700, 1800), ent(50, "B", 1550, 1500, strength=300)]
        w = world(es, cmds, seed=1)
        engine.run(w, 600)
        checked = {"officer": 0, "army": 0, "receipt": 0}
        for rec in w.decisions.values():
            ctx = decide.context_from_record(rec)
            opts, i, probs, _, side = dm.decide(ctx, rec["draw"])
            self.assertEqual([o.name for o in opts], [o["name"] for o in rec["options"]], rec["id"])
            self.assertEqual([o.total for o in opts], [o["total"] for o in rec["options"]], rec["id"])
            self.assertEqual(probs, [o["p"] for o in rec["options"]], rec["id"])
            self.assertEqual(json.loads(json.dumps([o.actions for o in opts])), [o["actions"] for o in rec["options"]])
            self.assertEqual(json.loads(json.dumps(side)), rec["side_actions"])
            self.assertEqual(opts[i].name, rec["chosen"])
            checked["receipt" if rec["inputs"]["received"] else rec["rank"]] += 1
        self.assertTrue(all(checked.values()), checked)

    def test_codex_006_8_a_pending_report_interrupt_is_in_the_trace(self):
        w = world([ent(1, "A", 500, 1500)], [army()])
        w.tick = 1
        command.belief_mod_ensure(w)
        a = record.state_bytes(w)
        w.reported_to.add(900)
        self.assertNotEqual(record.state_bytes(w), a)

    def test_codex_006_notes_queued_report_contents_are_in_the_trace(self):
        def queued(x):
            w = world([ent(1, "A", 2500, 1500), ent(50, "B", x, 1500)], [army()],
                      [{"at_s": 0, "report": {"sender": 1, "recipient": 900}}],
                      overrides={"runners_entity": 1})
            command.belief_mod_ensure(w)
            belief.apply_sighting(w, 1, 50, "B", "foot", float(x), 1500.0, 5.0, 100, None, None, False)
            w.staff[1] = 0                                   # no runner free: the report waits in the queue
            w.messengers.append(command.om.Messenger(key=(1, 9), sender=1, mobility="foot", x=2500.0, y=1500.0,
                                                     message=command.om.Message("x", (1, 9), "report", 1, 900, 0)))
            command.run_inputs(w)
            return record.state_bytes(w)
        self.assertNotEqual(queued(2900), queued(2950))


class InputKeys(unittest.TestCase):
    def _key(self, inputs):
        w = world([ent(1, "A", 300, 1500)], [army()], inputs, seed=1)
        engine.step(w)
        m = next(m for m in w.messengers if m.id == "900.1")
        return m.key, w.orders["900.1"].stages

    def test_codex_006_9_other_inputs_never_shift_an_inputs_key(self):
        hold = {"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}}
        sig = {"at_s": 0, "signal": {"issuer": 900, "meaning": "advance", "to": []}}
        rep = {"at_s": 20, "report": {"sender": 1, "recipient": 900}}
        base = self._key([hold])
        self.assertEqual(self._key([sig, hold]), base)        # prepended
        self.assertEqual(self._key([hold, rep]), base)        # appended
        self.assertEqual(self._key([rep, sig, hold]), base)   # reordered around it


class Timing(unittest.TestCase):
    def test_codex_006_11_routine_and_receipt_in_one_tick_are_ordered_and_reset_the_timer(self):
        w = world([ent(1, "A", 500, 1500)], [army(x=500)],
                  [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "hold"}}])
        command.belief_mod_ensure(w)
        decide._state(w, 1)["next"] = 0
        engine.step(w)
        mine = sorted((d for d in w.decisions.values() if d["owner"] == 1 and d["t"] == 0), key=lambda d: d["seq_in_tick"])
        self.assertEqual([(d["trigger"], d["seq_in_tick"]) for d in mine], [("routine", 1), ("order arrived", 2)])
        self.assertGreater(w.deciders[1]["next"], 0)

    def test_codex_006_notes_inverted_ranges_refused(self):
        with self.assertRaises(ValueError):
            params.resolve({"decide_officer_min_s": 60.0, "decide_officer_max_s": 20.0})


class StaleTruthUnderAThreat(unittest.TestCase):
    def test_codex_006_notes_hidden_body_moved_while_a_visible_threat_drives_decisions(self):
        """Side A is busy with a visible enemy; moving a hidden one changes nothing it decides or does."""
        s = spec()
        s["entities"].append({"id": 53, "side": "B", "name": "visible foot", "function": "heavy_infantry", "x": 1000,
                              "y": 1500, "frontage": 40, "depth": 15, "strength": 400,
                              "equipment": {"reach": "sword", "mobility": "foot"}})
        s["commanders"][2]["commands"].append(53)
        f = write(s)
        a, b = scenario.load(f, 3), scenario.load(f, 3)
        for w in (a, b):
            engine.step(w, 100)
        b.entity(HIDDEN).x, b.entity(HIDDEN).y = 3200.0, 1200.0
        for w in (a, b):
            engine.step(w, 300)
        owners = (900, 910, 1, 2)
        da = [d for d in a.decisions.values() if d["owner"] in owners]
        self.assertTrue(any(d["chosen"] not in ("continue", "wait") for d in da), "side A never acted")
        db = [d for d in b.decisions.values() if d["owner"] in owners]
        self.assertEqual(json.dumps(da, sort_keys=True), json.dumps(db, sort_keys=True))
        self.assertEqual([(e.x, e.y, e.task) for e in a.entities if e.side == "A"],
                         [(e.x, e.y, e.task) for e in b.entities if e.side == "A"])


if __name__ == "__main__":
    unittest.main()
