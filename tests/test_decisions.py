"""Step 5 tests: decisions (specification 5.6, 6; acceptance checks 3, 5 and 7 in part)."""
from __future__ import annotations

import json
import math
import re
import time
import unittest
from pathlib import Path
from types import MappingProxyType

from imperatores import belief, decisions as dm, engine, params, record, scenario
from imperatores.belief import Contact
from imperatores.systems import decide
from tests.test_beliefs import A_OWNERS, FIELD, HIDDEN, spec, write
from tests.test_orders import army, ent, world

ROOT = Path(__file__).resolve().parent.parent
P = params.resolve()
PK = MappingProxyType({k: P[k] for k in decide._PARAM_KEYS})


def contact(h, x, y, strength=120, side="B", kind="heavy_infantry", seen_t=100, source="seen"):
    return Contact(handle=h, side=side, kind=kind, x=x, y=y, pos_err=5.0, strength=strength, order=None, facing=None,
                   seen_t=seen_t, first_seen_t=seen_t, source=source, report_from=None, received_t=seen_t)


def officer_ctx(profile="by_the_book", contacts=(), standing=None, received=None, facing=0.0, task="hold",
                fit=120, fatigue=0.0, order=1.0):
    own = MappingProxyType({"x": 1000.0, "y": 1000.0, "facing": facing, "fit": fit, "start_strength": 120,
                            "fatigue": fatigue, "order": order, "task": task, "side": "A", "reported_t": -10 ** 9})
    return dm.Context(owner=1, rank="officer", side="A", tick=100, tick_s=2.0, tendencies=dm.PROFILES[profile],
                      profile=profile, own=own, contacts=tuple(contacts), home=(800.0, 1000.0), trigger="routine",
                      standing=standing, received=received, has_commander=True, params=PK)


def probs(ctx):
    opts, _, p, _, _ = dm.decide(ctx, 0.5)
    return {o.name: pi for o, pi in zip(opts, p)}


def total(pr, prefix):
    return sum(v for k, v in pr.items() if k.startswith(prefix))


class Structure(unittest.TestCase):
    def test_decision_code_sees_only_what_it_is_given(self):
        """Check 3, structural (review 006/10): the decision module imports nothing that could
        reach the world, and names none of its hidden parts. A tripwire for trusted code, not a sandbox."""
        import ast
        src = (ROOT / "imperatores" / "decisions.py").read_text()
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "no relative imports")
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported, {"__future__", "dataclasses", "math", "types"})
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for word in ("world", "w", "by_id", "entities", "commanders_by_id", "beliefs", "_truth", "_former",
                     "audit", "intended", "misread", "handle_of", "orders", "messengers"):
            self.assertNotIn(word, names, word)

    def test_the_context_holds_only_values(self):
        """What decide.py hands the scorer: immutable value objects and plain data, nothing that
        refers back into the world (review 006/10)."""
        w = scenario.load(FIELD, 2)
        engine.step(w, 6)
        allowed = (int, float, str, bool, type(None), dm.Tendencies, dm.OrderView, dm.SubView, Contact)

        def check(v, path):
            if isinstance(v, (tuple, list)):
                for k, x in enumerate(v):
                    check(x, f"{path}[{k}]")
            elif isinstance(v, MappingProxyType):
                for k, x in v.items():
                    check(x, f"{path}.{k}")
            else:
                self.assertIsInstance(v, allowed, path)
        for owner in (1, 2, 51, 900, 910, 950):
            ctx = decide._context(w, owner, "test")
            for f in ctx.__dataclass_fields__:
                check(getattr(ctx, f), f)

    def test_every_decision_is_recorded_with_inputs_options_and_choice(self):
        w = scenario.load(FIELD, 2)
        engine.run(w, 600)
        self.assertTrue(w.decisions)
        for d in w.decisions.values():
            self.assertEqual(set(d) >= {"id", "owner", "t", "trigger", "inputs", "options", "chosen", "links"}, True)
            self.assertIn(d["chosen"], [o["name"] for o in d["options"]])
            self.assertAlmostEqual(sum(o["p"] for o in d["options"]), 1.0, places=9)
            for o in d["options"]:
                self.assertAlmostEqual(o["total"], sum(o["components"].values()), places=9)
        for o in w.orders.values():                               # check 7, in part: every decision order links back
            if o.origin == "decision":
                self.assertIn(o.parent, w.decisions)
                self.assertIn({"order": o.id}, w.decisions[o.parent]["links"])
        json.dumps(record.to_json(w), allow_nan=False)


class InformationIntegrity(unittest.TestCase):
    def test_stale_truth_leaves_every_decision_unchanged(self):
        """Check 3: moving an unseen entity changes no decision of the side that cannot see it."""
        a, b = scenario.load(FIELD, 3), scenario.load(FIELD, 3)
        for w in (a, b):
            record.snapshot(w)
            engine.step(w, 100)
        b.entity(HIDDEN).x, b.entity(HIDDEN).y = 3200.0, 1200.0
        for w in (a, b):
            engine.step(w, 400)

        def side_a(w):
            return json.dumps([d for d in sorted(w.decisions.values(), key=lambda d: d["id"]) if d["owner"] in A_OWNERS],
                              sort_keys=True)
        self.assertEqual(side_a(a), side_a(b))

    def test_hidden_entity_appears_in_no_decision_of_the_other_side(self):
        """Check 3: with or without the hidden reserve, side A decides exactly the same."""
        s = spec()
        s2 = dict(s, entities=[e for e in s["entities"] if e["id"] != HIDDEN],
                  commanders=[dict(c, commands=[i for i in c["commands"] if i != HIDDEN]) for c in s["commanders"]])
        a, b = scenario.load(FIELD, 4), scenario.load(write(s2), 4)
        for w in (a, b):
            engine.run(w, 900)
        da = [d for d in a.decisions.values() if d["owner"] in A_OWNERS]
        db = [d for d in b.decisions.values() if d["owner"] in A_OWNERS]
        self.assertTrue(da)
        self.assertEqual(json.dumps(da, sort_keys=True), json.dumps(db, sort_keys=True))


class Tendencies(unittest.TestCase):
    def test_profiles_change_choices(self):
        threats = [contact(1, 1250, 1000, strength=60)]
        bold, cautious = probs(officer_ctx("bold", threats)), probs(officer_ctx("cautious", threats))
        self.assertGreater(total(bold, "attack"), total(cautious, "attack") + 0.1)
        strong = [contact(1, 1150, 1000, strength=400)]
        bold, cautious = probs(officer_ctx("bold", strong)), probs(officer_ctx("cautious", strong))
        self.assertGreater(total(cautious, "withdraw"), total(bold, "withdraw") + 0.1)

    def test_latitude_changes_how_often_he_acts_beyond_orders(self):
        threats = [contact(1, 1250, 1000, strength=60)]

        def beyond(lat):
            o = dm.OrderView(id="900.1", kind="hold", latitude=lat, issuer=900)
            opts, _, p, _, _ = dm.decide(officer_ctx("bold", threats, standing=o), 0.5)
            return sum(pi for op, pi in zip(opts, p) if op.beyond_orders)
        self.assertGreater(beyond("free"), beyond("normal") + 0.05)
        self.assertGreater(beyond("normal"), beyond("strict") + 0.05)

    def test_reports_count_for_less_than_his_own_eyes(self):
        seen = probs(officer_ctx("cautious", [contact(1, 1150, 1000, strength=400)]))
        told = probs(officer_ctx("cautious", [contact(1, 1150, 1000, strength=400, source="report")]))
        self.assertGreater(total(seen, "withdraw"), total(told, "withdraw"))

    def test_a_threat_on_the_flank_makes_facing_it_likely(self):
        pr = probs(officer_ctx("by_the_book", [contact(1, 1000, 1200, strength=300)], facing=0.0))
        self.assertIn("face", pr)
        self.assertEqual(max(pr, key=pr.get), "face")
        weak = probs(officer_ctx("by_the_book", [contact(1, 1000, 1400, strength=40)], facing=0.0))
        self.assertGreater(weak["continue"], weak["face"])            # a small, distant body: not worth turning
        front = probs(officer_ctx("by_the_book", [contact(1, 1250, 1000, strength=200)], facing=0.0))
        self.assertNotIn("face", front)


class Behaviour(unittest.TestCase):
    def _reserve_field(self, seed, profile="by_the_book"):
        cmds = [dict(army(x=600, y=1500, commands=(1, 2)), profile=profile)]
        es = [ent(1, "A", 1200, 1500), ent(2, "A", 700, 1800), ent(50, "B", 1550, 1500, strength=300)]
        return world(es, cmds, seed=seed)

    def test_commander_sometimes_commits_his_reserve_and_responses_vary(self):
        chosen = []
        for seed in range(10):
            w = self._reserve_field(seed)
            engine.run(w, 400)
            chosen.append(tuple(d["chosen"] for d in sorted(w.decisions.values(), key=lambda d: (d["t"], d["id"]))
                                if d["owner"] == 900))
        flat = [c for run in chosen for c in run]
        self.assertTrue(any(c.startswith("reinforce:2>1") for c in flat), flat)
        self.assertGreater(len(set(chosen)), 1)                   # not the same every seed

    def test_a_committed_reserve_advances_under_an_order_linked_to_the_decision(self):
        for seed in range(20):
            w = self._reserve_field(seed, profile="bold")
            engine.run(w, 600)
            sent = [o for o in w.orders.values() if o.origin == "decision" and o.recipient == 2 and o.issuer == 900]
            if sent and sent[0].status == "executed":
                break
        else:
            self.fail("no seed in which the reserve was committed and the order executed")
        d = w.decisions[sent[0].parent]
        self.assertTrue(d["chosen"].startswith("reinforce:2>1"))
        self.assertEqual(d["inputs"]["contacts"][0]["side"], "B")
        self.assertGreater(w.entity(2).x, 700)

    def test_a_new_contact_interrupts(self):
        w = world([ent(1, "A", 1000, 1500), ent(50, "B", 1400, 1500, task={"kind": "move_to", "x": 1300, "y": 1500})],
                  [], overrides={"decide_officer_min_s": 60.0, "decide_officer_max_s": 120.0})
        engine.step(w, 6)
        first = sorted((d for d in w.decisions.values() if d["owner"] == 1), key=lambda d: d["t"])
        self.assertTrue(first)
        self.assertEqual(first[0]["trigger"], "contact")
        self.assertEqual(first[0]["t"], 0)

    def test_an_order_can_be_declined_and_it_is_recorded(self):
        found = None
        for seed in range(40):
            es = [ent(1, "A", 1000, 1500, strength=60), ent(50, "B", 1400, 1500, strength=400)]
            w = world(es, [dict(army(x=900, y=1500), profile="by_the_book")],
                      [{"at_s": 0, "order": {"issuer": 900, "recipient": 1, "kind": "advance_to", "place": [1380, 1500],
                                             "latitude": "free"}}],
                      overrides={"decision_temperature": 2.0}, seed=seed)
            for ent_ in w.entities:
                if ent_.id == 1:
                    ent_.profile = "bold"
            engine.run(w, 120)
            o = w.orders.get("900.1")
            if o and o.status == "failed" and o.stages[-1][2]["why"] == "the recipient chose otherwise":
                found = (w, o)
                break
        self.assertIsNotNone(found, "no seed declined")
        w, o = found
        d = w.decisions[o.stages[-1][2]["decision"]]
        self.assertEqual(d["chosen"], "decline")
        self.assertEqual(d["trigger"], "order arrived")
        self.assertEqual(d["inputs"]["received"]["id"], "900.1")
        self.assertIn("order_declined", [e["kind"] for e in w.events])

    def test_facing_turns_the_entity(self):
        w = world([ent(1, "A", 1000, 1500), ent(50, "B", 1000, 1800, strength=300)], [], seed=1)
        engine.run(w, 300)
        faced = [d for d in w.decisions.values() if d["owner"] == 1 and d["chosen"] == "face"]
        self.assertTrue(faced)
        self.assertIn("faced", [e["kind"] for e in w.events if e["entity"] == 1])
        self.assertAlmostEqual(w.entity(1).facing, math.pi / 2, delta=math.radians(P["face_tolerance_deg"]) + 0.05)


class Replay(unittest.TestCase):
    def test_replay_exact_with_decisions(self):
        def run():
            w = scenario.load(FIELD, 7)
            engine.run(w, 900)
            return record.digest(w)
        self.assertEqual(run(), run())

    def test_one_officers_tendencies_leave_a_distant_officers_decisions_alone(self):
        """Paired intervention: decisions are keyed per decision-maker, so changing one officer's
        profile changes nothing for an officer who never interacts with him."""
        def run(profile):
            es = [dict(ent(1, "A", 500, 500), profile=profile), ent(50, "B", 800, 500),
                  ent(2, "A", 500, 2500), ent(60, "B", 800, 2500)]
            w = world(es, [], terrain={"width": 4000, "height": 3000, "cell": 20}, seed=5)
            engine.run(w, 600)
            return w
        a, b = run("bold"), run("cautious")
        da = [d for d in a.decisions.values() if d["owner"] in (2, 60)]
        db = [d for d in b.decisions.values() if d["owner"] in (2, 60)]
        self.assertEqual(json.dumps(da, sort_keys=True), json.dumps(db, sort_keys=True))
        self.assertNotEqual(json.dumps([d for d in a.decisions.values() if d["owner"] == 1], sort_keys=True),
                            json.dumps([d for d in b.decisions.values() if d["owner"] == 1], sort_keys=True))


class Loading(unittest.TestCase):
    def test_unknown_profile_refused(self):
        with self.assertRaises(ValueError):
            world([dict(ent(1, "A", 500, 1500), profile="reckless")], [])


class Performance(unittest.TestCase):
    def test_decision_cost_is_measured(self):
        es = [ent(k, "A", 1000, 300 + 30 * k) for k in range(1, 101)] + \
             [ent(200 + k, "B", 1400, 300 + 30 * k) for k in range(1, 101)]
        cmds = [army(cid=900, x=600, y=1800, commands=tuple(range(1, 101))),
                army(cid=950, side="B", x=1900, y=1800, commands=tuple(200 + k for k in range(1, 101)))]
        w = world(es, cmds, terrain={"width": 3000, "height": 3600, "cell": 20})
        engine.step(w, 5)                                       # past the first perception cycle
        t0 = time.perf_counter()
        n0 = len(w.decisions)
        for _ in range(15):                                     # 30 s: three perception cycles
            decide.step(w)
            w.tick += 1
        dt = time.perf_counter() - t0
        print(f"\n  decide phase, 200 entities + 2 commanders in contact: {dt / 15 * 1000:.0f} ms per tick, "
              f"{len(w.decisions) - n0} decisions in 30 s (about {dt / 15 * 5400:.0f} s over a 3-hour battle)")
        self.assertLess(dt, 120)


if __name__ == "__main__":
    unittest.main()
